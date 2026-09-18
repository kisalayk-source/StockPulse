"""Government data orchestration: ingest, map, query, alerts."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.government.clients import SamGovClient, UsaSpendingClient
from app.government.config import government_config_for_settings
from app.government.db_models import GovernmentContract, GovernmentEvent
from app.government.mapping import GovernmentCompanyMapper
from app.government.market_reaction import compute_market_reaction
from app.government.scoring import compute_government_score, materiality_value, revenue_ratio
from app.government.types import (
    AWARD_TYPES,
    OBLIGATION_TYPES,
    OPPORTUNITY_TYPES,
    NormalizedGovernmentEvent,
)
from app.sec.db_models import SecCompanyMapping
from app.services.providers import ProviderUnavailable

logger = logging.getLogger("app.government")


class GovernmentService:
    def __init__(
        self,
        settings: Settings,
        *,
        sam: SamGovClient | None = None,
        usa: UsaSpendingClient | None = None,
    ) -> None:
        self.settings = settings
        self.config = government_config_for_settings(settings)
        self.sam = sam or SamGovClient(settings)
        self.usa = usa or UsaSpendingClient(settings)
        self.mapper = GovernmentCompanyMapper(self.config)

    async def aclose(self) -> None:
        for client in (self.sam, self.usa):
            if hasattr(client, "aclose"):
                await client.aclose()

    def _company_name_for_ticker(self, session: Session, ticker: str) -> str | None:
        row = (
            session.query(SecCompanyMapping)
            .filter(SecCompanyMapping.ticker == ticker.upper())
            .one_or_none()
        )
        return row.company_name if row else None

    def _known_agencies(self, session: Session, ticker: str, *, before: datetime | None = None) -> set[str]:
        query = session.query(GovernmentEvent.agency).filter(
            GovernmentEvent.ticker == ticker.upper(),
            GovernmentEvent.agency.isnot(None),
            GovernmentEvent.event_type.in_(tuple(AWARD_TYPES | OBLIGATION_TYPES)),
        )
        if before is not None:
            query = query.filter(GovernmentEvent.event_at < before)
        return {str(a[0]) for a in query.distinct().all() if a and a[0]}

    def upsert_event(
        self,
        session: Session,
        event: NormalizedGovernmentEvent,
        *,
        force_ticker: str | None = None,
    ) -> tuple[GovernmentEvent | None, bool]:
        """Insert or skip duplicate. Returns (row, inserted)."""
        existing = (
            session.query(GovernmentEvent)
            .filter(
                GovernmentEvent.source == event.source,
                GovernmentEvent.event_id == event.event_id,
            )
            .one_or_none()
        )
        if existing is not None:
            logger.info(
                "government_duplicate_events",
                extra={
                    "provider": event.source,
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                },
            )
            return existing, False

        mapping = self.mapper.resolve(
            session,
            uei=event.uei,
            cage=event.cage,
            cik=event.cik,
            company_name=event.company_name,
            ticker_hint=force_ticker or event.ticker,
        )
        ticker = mapping.ticker if self.mapper.is_confident(mapping.confidence) else None
        # When syncing a specific ticker by name search, allow attaching if hint matches
        if force_ticker and mapping.ticker and mapping.ticker.upper() == force_ticker.upper():
            if mapping.confidence >= float((self.config.get("mapping") or {}).get("fuzzy_min_confidence", 0.55)):
                ticker = force_ticker.upper()
        elif force_ticker and not mapping.ticker and event.company_name:
            # Name search already scoped to company — attach with moderate confidence
            ticker = force_ticker.upper()
            mapping = type(mapping)(
                ticker=ticker,
                confidence=max(mapping.confidence, 0.8),
                method=mapping.method if mapping.method != "unmapped" else "sync_hint",
                cik=mapping.cik,
            )

        if ticker and mapping.confidence > 0:
            self.mapper.persist(
                session,
                mapping,
                uei=event.uei,
                cage=event.cage,
                company_name=event.company_name,
            )

        row = GovernmentEvent(
            source=event.source,
            event_id=event.event_id,
            event_type=event.event_type,
            contract_number=event.contract_number,
            solicitation_number=event.solicitation_number,
            company_name=event.company_name,
            parent_company=event.parent_company,
            uei=event.uei.upper() if event.uei else None,
            cage=event.cage.upper() if event.cage else None,
            ticker=ticker,
            cik=mapping.cik or event.cik,
            mapping_confidence=mapping.confidence if ticker else mapping.confidence,
            agency=event.agency,
            sub_agency=event.sub_agency,
            title=event.title,
            description=event.description,
            naics=event.naics,
            psc=event.psc,
            contract_type=event.contract_type,
            estimated_value=event.estimated_value,
            ceiling_amount=event.ceiling_amount,
            awarded_amount=event.awarded_amount,
            obligated_amount=event.obligated_amount,
            transaction_amount=event.transaction_amount,
            posted_date=event.posted_date,
            award_date=event.award_date,
            period_start=event.period_start,
            period_end=event.period_end,
            published_at=event.published_at or event.event_at,
            event_at=event.event_at or event.published_at,
            sole_source=bool(event.sole_source),
            idiq=bool(event.idiq),
            option_only=bool(event.option_only),
            source_url=event.source_url,
            raw_json=json.dumps(event.raw, default=str)[:50_000] if event.raw else None,
        )
        session.add(row)
        session.flush()
        self._upsert_contract_rollup(session, row)
        return row, True

    def _upsert_contract_rollup(self, session: Session, event: GovernmentEvent) -> None:
        if not event.contract_number:
            return
        row = (
            session.query(GovernmentContract)
            .filter(
                GovernmentContract.contract_number == event.contract_number,
                GovernmentContract.ticker == event.ticker,
            )
            .one_or_none()
        )
        if row is None:
            row = GovernmentContract(
                contract_number=event.contract_number,
                ticker=event.ticker,
            )
            session.add(row)
        row.solicitation_number = event.solicitation_number or row.solicitation_number
        row.company_name = event.company_name or row.company_name
        row.agency = event.agency or row.agency
        if event.ceiling_amount is not None:
            row.ceiling_amount = max(float(row.ceiling_amount or 0), float(event.ceiling_amount))
        if event.awarded_amount is not None:
            row.awarded_amount = max(float(row.awarded_amount or 0), float(event.awarded_amount))
        if event.obligated_amount is not None:
            row.obligated_amount = max(float(row.obligated_amount or 0), float(event.obligated_amount))
        row.period_start = event.period_start or row.period_start
        row.period_end = event.period_end or row.period_end
        row.sole_source = row.sole_source or bool(event.sole_source)
        row.idiq = row.idiq or bool(event.idiq)
        if event.period_start and event.period_end:
            row.multi_year = (event.period_end - event.period_start).days >= int(
                (self.config.get("thresholds") or {}).get("multi_year_days", 365)
            )
        if event.event_type in AWARD_TYPES:
            row.incumbent = True

    async def sync_ticker(
        self,
        session: Session,
        ticker: str,
        *,
        lookback_days: int | None = None,
        posted_from: datetime | None = None,
        posted_to: datetime | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        symbol = ticker.upper().strip()
        provider_errors: list[dict[str, str]] = []
        ingest_cfg = self.config.get("ingest") or {}
        days = int(lookback_days or ingest_cfg.get("lookback_days", 90))
        end = posted_to or datetime.now(timezone.utc)
        start = posted_from or (end - timedelta(days=days))
        limit = int(ingest_cfg.get("page_limit", 100))
        max_pages = int(ingest_cfg.get("max_pages", 5))
        company_name = self._company_name_for_ticker(session, symbol)

        collected: list[NormalizedGovernmentEvent] = []

        try:
            sam_events = await self.sam.search_opportunities(
                posted_from=start,
                posted_to=end,
                keyword=company_name or symbol,
                limit=limit,
                max_pages=max_pages,
            )
            collected.extend(sam_events)
        except ProviderUnavailable as exc:
            provider_errors.append({"provider": exc.provider, "message": str(exc)})
            logger.warning(
                "government_provider_errors",
                extra={"provider": exc.provider, "ticker": symbol, "error": str(exc)},
            )
        except Exception as exc:
            provider_errors.append({"provider": "sam_gov", "message": type(exc).__name__})
            logger.exception("government_provider_errors", extra={"provider": "sam_gov", "ticker": symbol})

        try:
            usa_events = await self.usa.search_awards(
                recipient_name=company_name or symbol,
                keyword=company_name,
                posted_from=start,
                posted_to=end,
                limit=limit,
                max_pages=max_pages,
            )
            collected.extend(usa_events)
        except ProviderUnavailable as exc:
            provider_errors.append({"provider": exc.provider, "message": str(exc)})
        except Exception as exc:
            provider_errors.append({"provider": "usaspending", "message": type(exc).__name__})
            logger.exception("government_provider_errors", extra={"provider": "usaspending", "ticker": symbol})

        inserted = 0
        awards = 0
        opportunities = 0
        for event in collected:
            row, was_new = self.upsert_event(session, event, force_ticker=symbol)
            if not was_new:
                continue
            inserted += 1
            if event.event_type in AWARD_TYPES:
                awards += 1
            if event.event_type in OPPORTUNITY_TYPES:
                opportunities += 1
            logger.info(
                "government_events_ingested",
                extra={
                    "provider": event.source,
                    "event_id": event.event_id,
                    "ticker": symbol,
                    "event_type": event.event_type,
                    "processing_time": round((perf_counter() - started) * 1000, 2),
                },
            )

        session.commit()
        elapsed = round((perf_counter() - started) * 1000, 2)
        logger.info(
            "government_awards_ingested",
            extra={"ticker": symbol, "count": awards, "processing_time": elapsed},
        )
        logger.info(
            "government_opportunities_ingested",
            extra={"ticker": symbol, "count": opportunities, "processing_time": elapsed},
        )
        return {
            "ticker": symbol,
            "fetched": len(collected),
            "inserted": inserted,
            "awards": awards,
            "opportunities": opportunities,
            "provider_errors": provider_errors,
            "processing_time_ms": elapsed,
        }

    async def backfill(
        self,
        session: Session,
        ticker: str,
        *,
        start: datetime,
        end: datetime | None = None,
    ) -> dict[str, Any]:
        return await self.sync_ticker(
            session,
            ticker,
            posted_from=start,
            posted_to=end or datetime.now(timezone.utc),
        )

    def events_for_ticker(
        self,
        session: Session,
        ticker: str,
        *,
        as_of: datetime | None = None,
        confident_only: bool = True,
    ) -> list[GovernmentEvent]:
        query = session.query(GovernmentEvent).filter(GovernmentEvent.ticker == ticker.upper())
        if confident_only:
            min_conf = float((self.config.get("mapping") or {}).get("min_confidence", 0.75))
            query = query.filter(
                (GovernmentEvent.mapping_confidence.is_(None))
                | (GovernmentEvent.mapping_confidence >= min_conf)
            )
        rows = query.order_by(GovernmentEvent.event_at.desc()).all()
        if as_of is None:
            return rows
        cutoff = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
        out: list[GovernmentEvent] = []
        for row in rows:
            event_at = row.event_at
            published = row.published_at
            if event_at is not None and event_at.tzinfo is None:
                event_at = event_at.replace(tzinfo=timezone.utc)
            if published is not None and published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if event_at is not None and event_at > cutoff:
                continue
            if published is not None and published > cutoff:
                continue
            if event_at is None and published is None:
                continue
            out.append(row)
        return out

    def events_as_dicts(
        self,
        session: Session,
        ticker: str,
        *,
        as_of: datetime | None = None,
    ) -> list[dict[str, Any]]:
        return [self._event_to_dict(row) for row in self.events_for_ticker(session, ticker, as_of=as_of)]

    def _event_to_dict(self, row: GovernmentEvent) -> dict[str, Any]:
        def iso(value: datetime | None) -> str | None:
            if value is None:
                return None
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.isoformat()

        return {
            "event_type": row.event_type,
            "event_id": row.event_id,
            "source": row.source,
            "contract_number": row.contract_number,
            "solicitation_number": row.solicitation_number,
            "company_name": row.company_name,
            "parent_company": row.parent_company,
            "uei": row.uei,
            "cage": row.cage,
            "ticker": row.ticker,
            "cik": row.cik,
            "agency": row.agency,
            "sub_agency": row.sub_agency,
            "title": row.title,
            "description": row.description,
            "naics": row.naics,
            "psc": row.psc,
            "contract_type": row.contract_type,
            "estimated_value": row.estimated_value,
            "ceiling_amount": row.ceiling_amount,
            "awarded_amount": row.awarded_amount,
            "obligated_amount": row.obligated_amount,
            "transaction_amount": row.transaction_amount,
            "posted_date": iso(row.posted_date),
            "award_date": iso(row.award_date),
            "period_start": iso(row.period_start),
            "period_end": iso(row.period_end),
            "published_at": iso(row.published_at),
            "event_at": iso(row.event_at),
            "source_url": row.source_url,
            "sole_source": row.sole_source,
            "idiq": row.idiq,
            "option_only": row.option_only,
            "mapping_confidence": row.mapping_confidence,
        }

    def _window_sum(
        self,
        events: list[dict[str, Any]],
        *,
        types: set[str],
        days: int,
        as_of: datetime,
        amount_key: str,
    ) -> tuple[int, float]:
        cutoff = as_of - timedelta(days=days)
        count = 0
        total = 0.0
        for event in events:
            if event.get("event_type") not in types:
                continue
            raw_ts = event.get("event_at") or event.get("published_at")
            if not raw_ts:
                continue
            ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < cutoff or ts > as_of:
                continue
            count += 1
            value = event.get(amount_key)
            if value is not None:
                total += float(value)
        return count, total

    def build_alerts(
        self,
        *,
        score: float,
        flags: dict[str, Any],
        award_value_30d: float,
        obligation_value_30d: float,
        opportunity_value_30d: float,
        ticker: str,
    ) -> list[dict[str, Any]]:
        alerts_cfg = self.config.get("alerts") or {}
        alerts: list[dict[str, Any]] = []
        if score >= float(alerts_cfg.get("government_score_min", 80)):
            alerts.append(
                {
                    "type": "government_score",
                    "severity": "info",
                    "message": f"{ticker} Government Score {score:.0f}/100",
                }
            )
        if award_value_30d >= float(alerts_cfg.get("large_award_amount", 25_000_000)):
            alerts.append(
                {
                    "type": "large_award",
                    "severity": "warning",
                    "message": f"{ticker} large government award ${award_value_30d:,.0f} (30d)",
                }
            )
        if obligation_value_30d >= float(alerts_cfg.get("large_obligation_amount", 10_000_000)):
            alerts.append(
                {
                    "type": "large_obligation",
                    "severity": "warning",
                    "message": f"{ticker} large obligation ${obligation_value_30d:,.0f} (30d)",
                }
            )
        if opportunity_value_30d >= float(alerts_cfg.get("large_opportunity_amount", 50_000_000)):
            alerts.append(
                {
                    "type": "large_opportunity",
                    "severity": "info",
                    "message": f"{ticker} high-value procurement opportunity ${opportunity_value_30d:,.0f} (30d)",
                }
            )
        if alerts_cfg.get("new_customer", True) and flags.get("new_customer"):
            alerts.append(
                {
                    "type": "new_customer",
                    "severity": "info",
                    "message": f"{ticker} new government customer detected",
                }
            )
        if alerts_cfg.get("sole_source", True) and flags.get("sole_source"):
            alerts.append(
                {
                    "type": "sole_source",
                    "severity": "info",
                    "message": f"{ticker} sole-source government award activity",
                }
            )
        for alert in alerts:
            logger.info(
                "government_alert",
                extra={
                    "ticker": ticker,
                    "alert_type": alert["type"],
                    "alert_message": alert["message"],
                },
            )
        return alerts

    def analysis_payload(
        self,
        session: Session,
        ticker: str,
        *,
        annual_revenue: float | None = None,
        bars: list[dict[str, Any]] | None = None,
        as_of: datetime | None = None,
        sync_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        symbol = ticker.upper()
        now = as_of or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        events = self.events_as_dicts(session, symbol, as_of=now)
        known = self._known_agencies(session, symbol, before=now - timedelta(days=90))
        incumbent_count = (
            session.query(GovernmentContract)
            .filter(
                GovernmentContract.ticker == symbol,
                GovernmentContract.incumbent.is_(True),
            )
            .count()
        )
        scored = compute_government_score(
            events,
            config=self.config,
            annual_revenue=annual_revenue,
            known_agencies=known,
            incumbent_contracts=incumbent_count,
        )
        flags = scored["flags"]

        award_count_30d, award_value_30d = self._window_sum(
            events, types=set(AWARD_TYPES), days=30, as_of=now, amount_key="awarded_amount"
        )
        _, obligation_value_30d = self._window_sum(
            events, types=set(OBLIGATION_TYPES), days=30, as_of=now, amount_key="obligated_amount"
        )
        opportunity_count_30d, opportunity_value_30d = self._window_sum(
            events, types=set(OPPORTUNITY_TYPES), days=30, as_of=now, amount_key="estimated_value"
        )
        obligations_30d = sum(
            1
            for e in events
            if e.get("event_type") in OBLIGATION_TYPES
            and self._in_window(e, days=30, as_of=now)
        )

        recent = []
        for event in events[:25]:
            value = materiality_value(event)
            if value is None:
                value = event.get("ceiling_amount") or event.get("estimated_value")
            item = {
                "date": (event.get("event_at") or event.get("published_at") or "")[:10],
                "agency": event.get("agency"),
                "event": event.get("event_type"),
                "title": event.get("title"),
                "value": value,
                "status": event.get("event_type"),
                "source": event.get("source"),
                "source_url": event.get("source_url"),
                "sole_source": event.get("sole_source"),
            }
            if (
                bars
                and event.get("event_type") in AWARD_TYPES
                and (event.get("event_at") or event.get("published_at"))
            ):
                item["market_reaction"] = compute_market_reaction(
                    bars,
                    event.get("event_at") or event.get("published_at"),
                )
            recent.append(item)

        open_opportunities = [
            e for e in events if e.get("event_type") in OPPORTUNITY_TYPES
        ][:20]
        recent_awards = [e for e in events if e.get("event_type") in AWARD_TYPES][:20]
        recent_obligations = [e for e in events if e.get("event_type") in OBLIGATION_TYPES][:20]

        agency_totals: dict[str, float] = {}
        for event in events:
            if event.get("event_type") not in (AWARD_TYPES | OBLIGATION_TYPES):
                continue
            agency = event.get("agency") or "Unknown"
            value = materiality_value(event) or 0.0
            agency_totals[agency] = agency_totals.get(agency, 0.0) + float(value)
        top_agencies = [
            {"agency": name, "value": round(value, 2)}
            for name, value in sorted(agency_totals.items(), key=lambda kv: kv[1], reverse=True)[:8]
        ]

        exposure_value = sum(float(materiality_value(e) or 0.0) for e in events if e.get("event_type") in AWARD_TYPES)
        exposure_ratio = None
        if annual_revenue and annual_revenue > 0:
            exposure_ratio = round(exposure_value / annual_revenue, 6)

        alerts = self.build_alerts(
            score=float(scored["government_score"]),
            flags=flags,
            award_value_30d=award_value_30d,
            obligation_value_30d=obligation_value_30d,
            opportunity_value_30d=opportunity_value_30d,
            ticker=symbol,
        )

        provider_errors = list((sync_meta or {}).get("provider_errors") or [])
        return {
            "ticker": symbol,
            "as_of": now.isoformat(),
            "government": {
                "score": scored["government_score"],
                "early_signal_score": scored["government_early_signal_score"],
                "awards_30d": award_count_30d,
                "award_value_30d": round(award_value_30d, 2),
                "obligations_30d": obligations_30d,
                "obligation_value_30d": round(obligation_value_30d, 2),
                "opportunity_count_30d": opportunity_count_30d,
                "opportunity_value_30d": round(opportunity_value_30d, 2),
                "new_customer": bool(flags.get("new_customer")),
                "sole_source": bool(flags.get("sole_source")),
                "incumbent": bool(flags.get("incumbent")),
                "multi_year": bool(flags.get("multi_year")),
                "revenue_exposure": exposure_ratio,
                "contract_value": round(exposure_value, 2),
            },
            "recent_activity": recent,
            "open_opportunities": open_opportunities,
            "recent_awards": recent_awards,
            "recent_obligations": recent_obligations,
            "top_agencies": top_agencies,
            "alerts": alerts,
            "provider_errors": provider_errors,
            "sync": sync_meta,
        }

    def _in_window(self, event: dict[str, Any], *, days: int, as_of: datetime) -> bool:
        raw_ts = event.get("event_at") or event.get("published_at")
        if not raw_ts:
            return False
        ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (as_of - timedelta(days=days)) <= ts <= as_of
