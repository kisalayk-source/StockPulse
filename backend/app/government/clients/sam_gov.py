"""SAM.gov Opportunities API client."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import Settings
from app.government.normalize import clean_str, first_present, parse_datetime, to_float
from app.government.types import SAM_PTYPE_MAP, NormalizedGovernmentEvent
from app.services.providers import ProviderUnavailable

logger = logging.getLogger("app.government.sam")

SAM_SEARCH_URL = "https://api.sam.gov/opportunities/v2/search"


class SamGovClient:
    """Async SAM.gov Get Opportunities client with pagination and retry."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.api_key = settings.sam_gov_api_key
        self.enabled = settings.government_enabled
        self.client = client or httpx.AsyncClient(timeout=45.0, follow_redirects=True)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    def _require_key(self) -> None:
        if not self.enabled:
            raise ProviderUnavailable("sam_gov", "Government data is disabled")
        if not self.api_key:
            raise ProviderUnavailable("sam_gov", "SAM_GOV_API_KEY is not configured")

    async def _get(self, params: dict[str, Any], *, retries: int = 3) -> dict[str, Any]:
        self._require_key()
        # Never log api_key
        safe_params = {k: v for k, v in params.items() if k != "api_key"}
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                response = await self.client.get(
                    SAM_SEARCH_URL,
                    params={**params, "api_key": self.api_key},
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                if response.status_code in {401, 403}:
                    raise ProviderUnavailable("sam_gov", "SAM.gov API key rejected")
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, dict) else {}
            except ProviderUnavailable:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "government_provider_errors",
                    extra={
                        "provider": "sam_gov",
                        "attempt": attempt + 1,
                        "error_type": type(exc).__name__,
                        "params": str(safe_params)[:200],
                    },
                )
                await asyncio.sleep(0.5 * (2**attempt))
        raise ProviderUnavailable(
            "sam_gov",
            f"SAM.gov request failed after retries: {type(last_error).__name__ if last_error else 'unknown'}",
        )

    async def search_opportunities(
        self,
        *,
        posted_from: date | datetime | None = None,
        posted_to: date | datetime | None = None,
        keyword: str | None = None,
        uei: str | None = None,
        limit: int = 100,
        max_pages: int = 5,
        ptypes: str | None = "o,p,r,k,a,s",
    ) -> list[NormalizedGovernmentEvent]:
        today = datetime.now(timezone.utc).date()
        end = posted_to.date() if isinstance(posted_to, datetime) else (posted_to or today)
        start = (
            posted_from.date()
            if isinstance(posted_from, datetime)
            else (posted_from or (end - timedelta(days=90)))
        )
        # SAM requires MM/dd/yyyy and max ~1 year span
        if (end - start).days > 365:
            start = end - timedelta(days=365)

        events: list[NormalizedGovernmentEvent] = []
        offset = 0
        page_limit = max(1, min(limit, 1000))
        for _ in range(max(1, max_pages)):
            params: dict[str, Any] = {
                "postedFrom": start.strftime("%m/%d/%Y"),
                "postedTo": end.strftime("%m/%d/%Y"),
                "limit": page_limit,
                "offset": offset,
            }
            if ptypes:
                params["ptype"] = ptypes
            if keyword:
                params["title"] = keyword
            if uei:
                params["ueiSAM"] = uei

            payload = await self._get(params)
            rows = payload.get("opportunitiesData") or payload.get("opportunities") or []
            if not isinstance(rows, list):
                rows = []
            for row in rows:
                if isinstance(row, dict):
                    events.append(normalize_sam_opportunity(row))
            total = int(payload.get("totalRecords") or 0)
            offset += page_limit
            if not rows or offset >= total:
                break
        return events


def normalize_sam_opportunity(row: dict[str, Any]) -> NormalizedGovernmentEvent:
    notice_id = clean_str(
        first_present(row.get("noticeId"), row.get("solicitationNumber"), row.get("opportunityId")),
        max_len=128,
    ) or "unknown"
    ptype = str(row.get("type") or row.get("ptype") or "").strip().lower()
    # Some responses use full names
    name_map = {
        "sources sought": "SOURCES_SOUGHT",
        "presolicitation": "PRESOLICITATION",
        "solicitation": "SOLICITATION",
        "combined synopsis/solicitation": "SOLICITATION",
        "award notice": "AWARD",
        "award": "AWARD",
        "special notice": "PROCUREMENT_FORECAST",
    }
    if len(ptype) == 1:
        event_type = SAM_PTYPE_MAP.get(ptype, "SOLICITATION")
    else:
        event_type = name_map.get(ptype, SAM_PTYPE_MAP.get(ptype[:1], "SOLICITATION"))

    posted = parse_datetime(first_present(row.get("postedDate"), row.get("publishDate")))
    award_date = parse_datetime(row.get("awardDate") or row.get("award", {}).get("date") if isinstance(row.get("award"), dict) else row.get("awardDate"))
    award_obj = row.get("award") if isinstance(row.get("award"), dict) else {}
    awarded_amount = to_float(first_present(award_obj.get("amount"), row.get("awardAmount"), row.get("award")))
    ceiling = to_float(first_present(row.get("awardCeiling"), row.get("archiveDate"), row.get("baseAndAllOptionsValue")))
    estimated = to_float(first_present(row.get("awardFloor"), row.get("estimatedValue"), awarded_amount))

    awardee = row.get("awardee") if isinstance(row.get("awardee"), dict) else {}
    company_name = clean_str(
        first_present(
            awardee.get("name"),
            row.get("organizationName"),
            row.get("awardeeName"),
        ),
        max_len=512,
    )
    uei = clean_str(first_present(awardee.get("ueiSAM"), row.get("ueiSAM"), row.get("uei")), max_len=32)
    cage = clean_str(first_present(awardee.get("cageCode"), row.get("cageCode")), max_len=16)

    office = row.get("officeAddress") if isinstance(row.get("officeAddress"), dict) else {}
    agency = clean_str(
        first_present(row.get("fullParentPathName"), row.get("department"), row.get("organizationName")),
        max_len=256,
    )
    sub_agency = clean_str(first_present(row.get("subtier"), office.get("city")), max_len=256)

    point_of_contact = row.get("pointOfContact")
    description = None
    if isinstance(point_of_contact, list) and point_of_contact:
        description = clean_str(point_of_contact[0].get("title") if isinstance(point_of_contact[0], dict) else None)

    title = clean_str(row.get("title"), max_len=1024)
    naics = clean_str(first_present(row.get("naicsCode"), row.get("naics")), max_len=16)
    psc = clean_str(first_present(row.get("classificationCode"), row.get("psc")), max_len=16)
    sol_num = clean_str(row.get("solicitationNumber"), max_len=128)
    set_aside = clean_str(row.get("typeOfSetAsideDescription") or row.get("typeOfSetAside"), max_len=64)
    sole_source = bool(
        set_aside
        and any(token in set_aside.lower() for token in ("sole source", "sole-source", "other than full"))
    )
    contract_type = clean_str(first_present(row.get("typeOfContractPricing"), set_aside), max_len=64)
    idiq = bool(contract_type and "idiq" in contract_type.lower()) or bool(
        title and "idiq" in title.lower()
    )

    ui_link = clean_str(row.get("uiLink") or row.get("additionalInfoLink"), max_len=1024)
    event_at = award_date or posted
    published_at = posted or award_date

    return NormalizedGovernmentEvent(
        event_type=event_type,
        event_id=f"sam:{notice_id}",
        source="sam_gov",
        contract_number=clean_str(award_obj.get("number") or row.get("contractNumber"), max_len=128),
        solicitation_number=sol_num,
        company_name=company_name,
        uei=uei,
        cage=cage,
        agency=agency,
        sub_agency=sub_agency,
        title=title,
        description=description or clean_str(row.get("description"), max_len=4000),
        naics=naics,
        psc=psc,
        contract_type=contract_type,
        estimated_value=estimated,
        ceiling_amount=ceiling,
        awarded_amount=awarded_amount,
        posted_date=posted,
        award_date=award_date,
        published_at=published_at,
        event_at=event_at,
        source_url=ui_link,
        sole_source=sole_source,
        idiq=idiq,
        raw=row,
    )
