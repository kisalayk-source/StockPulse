"""USAspending.gov awards / obligations client."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import Settings
from app.government.normalize import clean_str, first_present, parse_datetime, to_float
from app.government.types import NormalizedGovernmentEvent
from app.services.providers import ProviderUnavailable

logger = logging.getLogger("app.government.usaspending")

USA_BASE = "https://api.usaspending.gov/api/v2"
SPENDING_BY_AWARD = f"{USA_BASE}/search/spending_by_award/"
AWARD_DETAIL = f"{USA_BASE}/awards/"


class UsaSpendingClient:
    """Async USAspending client (no API key required)."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.enabled = settings.government_enabled
        self.client = client or httpx.AsyncClient(timeout=45.0, follow_redirects=True)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def _post(self, url: str, body: dict[str, Any], *, retries: int = 3) -> dict[str, Any]:
        if not self.enabled:
            raise ProviderUnavailable("usaspending", "Government data is disabled")
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                response = await self.client.post(url, json=body)
                if response.status_code in {429, 500, 502, 503, 504}:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, dict) else {}
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "government_provider_errors",
                    extra={
                        "provider": "usaspending",
                        "attempt": attempt + 1,
                        "error_type": type(exc).__name__,
                    },
                )
                await asyncio.sleep(0.5 * (2**attempt))
        raise ProviderUnavailable(
            "usaspending",
            f"USAspending request failed after retries: {type(last_error).__name__ if last_error else 'unknown'}",
        )

    async def search_awards(
        self,
        *,
        keyword: str | None = None,
        recipient_name: str | None = None,
        uei: str | None = None,
        posted_from: date | datetime | None = None,
        posted_to: date | datetime | None = None,
        limit: int = 100,
        max_pages: int = 5,
    ) -> list[NormalizedGovernmentEvent]:
        today = datetime.now(timezone.utc).date()
        end = posted_to.date() if isinstance(posted_to, datetime) else (posted_to or today)
        start = (
            posted_from.date()
            if isinstance(posted_from, datetime)
            else (posted_from or (end - timedelta(days=90)))
        )

        filters: dict[str, Any] = {
            "time_period": [
                {
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                }
            ],
            "award_type_codes": ["A", "B", "C", "D"],
        }
        if keyword or recipient_name:
            filters["keywords"] = [keyword or recipient_name]
        if uei:
            filters["recipient_search_text"] = [uei]
        elif recipient_name:
            filters["recipient_search_text"] = [recipient_name]

        events: list[NormalizedGovernmentEvent] = []
        page = 1
        page_limit = max(1, min(limit, 100))
        for _ in range(max(1, max_pages)):
            body = {
                "filters": filters,
                "fields": [
                    "Award ID",
                    "Recipient Name",
                    "Recipient UEI",
                    "Award Amount",
                    "Total Outlays",
                    "Description",
                    "Awarding Agency",
                    "Awarding Sub Agency",
                    "Start Date",
                    "End Date",
                    "Award Type",
                    "NAICS Code",
                    "PSC Code",
                    "generated_internal_id",
                ],
                "page": page,
                "limit": page_limit,
                "sort": "Award Amount",
                "order": "desc",
            }
            payload = await self._post(SPENDING_BY_AWARD, body)
            rows = payload.get("results") or []
            if not isinstance(rows, list):
                rows = []
            for row in rows:
                if isinstance(row, dict):
                    events.append(normalize_usa_award(row))
                    # Companion obligation event when outlays / amounts present
                    obligation = normalize_usa_obligation(row)
                    if obligation is not None:
                        events.append(obligation)
            page_meta = payload.get("page_metadata") or {}
            has_next = bool(page_meta.get("hasNext") or page_meta.get("has_next"))
            if not rows or not has_next:
                break
            page += 1
        return events


def normalize_usa_award(row: dict[str, Any]) -> NormalizedGovernmentEvent:
    award_id = clean_str(
        first_present(row.get("Award ID"), row.get("generated_internal_id"), row.get("award_id")),
        max_len=128,
    ) or "unknown"
    internal = clean_str(row.get("generated_internal_id"), max_len=128) or award_id
    start = parse_datetime(row.get("Start Date"))
    end = parse_datetime(row.get("End Date"))
    awarded = to_float(first_present(row.get("Award Amount"), row.get("award_amount")))
    obligated = to_float(first_present(row.get("Total Outlays"), row.get("obligated_amount")))
    award_type = clean_str(row.get("Award Type"), max_len=64)
    is_mod = bool(award_type and "modif" in award_type.lower())
    is_option = bool(award_type and "option" in award_type.lower())
    event_type = "OPTION_EXERCISED" if is_option else ("AWARD_MODIFICATION" if is_mod else "AWARD")
    idiq = bool(award_type and "idiq" in award_type.lower())
    event_at = start or end or datetime.now(timezone.utc)

    return NormalizedGovernmentEvent(
        event_type=event_type,
        event_id=f"usa:award:{internal}",
        source="usaspending",
        contract_number=award_id,
        company_name=clean_str(row.get("Recipient Name"), max_len=512),
        uei=clean_str(row.get("Recipient UEI"), max_len=32),
        agency=clean_str(row.get("Awarding Agency"), max_len=256),
        sub_agency=clean_str(row.get("Awarding Sub Agency"), max_len=256),
        title=clean_str(row.get("Description"), max_len=1024),
        description=clean_str(row.get("Description"), max_len=4000),
        naics=clean_str(row.get("NAICS Code"), max_len=16),
        psc=clean_str(row.get("PSC Code"), max_len=16),
        contract_type=award_type,
        awarded_amount=awarded,
        obligated_amount=obligated,
        award_date=start,
        period_start=start,
        period_end=end,
        published_at=start or end,
        event_at=event_at,
        source_url=f"https://www.usaspending.gov/award/{internal}" if internal else None,
        idiq=idiq,
        option_only=is_option,
        raw=row,
    )


def normalize_usa_obligation(row: dict[str, Any]) -> NormalizedGovernmentEvent | None:
    obligated = to_float(first_present(row.get("Total Outlays"), row.get("obligated_amount")))
    transaction = to_float(row.get("transaction_amount"))
    amount = obligated if obligated is not None else transaction
    if amount is None or amount <= 0:
        return None
    award_id = clean_str(
        first_present(row.get("Award ID"), row.get("generated_internal_id")),
        max_len=128,
    ) or "unknown"
    internal = clean_str(row.get("generated_internal_id"), max_len=128) or award_id
    start = parse_datetime(row.get("Start Date"))
    return NormalizedGovernmentEvent(
        event_type="OBLIGATION",
        event_id=f"usa:obligation:{internal}",
        source="usaspending",
        contract_number=award_id,
        company_name=clean_str(row.get("Recipient Name"), max_len=512),
        uei=clean_str(row.get("Recipient UEI"), max_len=32),
        agency=clean_str(row.get("Awarding Agency"), max_len=256),
        sub_agency=clean_str(row.get("Awarding Sub Agency"), max_len=256),
        title=clean_str(row.get("Description"), max_len=1024),
        obligated_amount=obligated,
        transaction_amount=amount,
        award_date=start,
        published_at=start,
        event_at=start or datetime.now(timezone.utc),
        source_url=f"https://www.usaspending.gov/award/{internal}" if internal else None,
        raw=row,
    )
