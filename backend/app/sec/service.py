from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import Settings
from app.sec.client import SecClient
from app.sec.config_loader import get_sec_config
from app.sec.db_models import (
    AccumulationEvent,
    AccumulationScore,
    BeneficialOwnership,
    InsiderTransaction,
    InstitutionalHolding,
    InstitutionalPositionChange,
    SecCompanyMapping,
    SecFiling,
)
from app.sec.edgar import edgar_filing_url, form_family, iter_recent_filings, normalize_cik
from app.sec.engines.accumulation import compute_accumulation_score, persist_score_snapshot
from app.sec.evidence import build_evidence_list
from app.sec.forms.form_13d import parse_13d
from app.sec.forms.form_13f import match_ticker_from_issuer, parse_13f_infotable, parse_13f_primary
from app.sec.forms.form_13g import parse_13g
from app.sec.forms.form_4 import parse_form4
from app.sec.models import NormalizedEvent
from app.sec.normalization import (
    classify_beneficial_ownership_event,
    classify_institutional_change,
    classify_insider_transaction,
    institutional_change_pct,
    polarity_for_institutional,
    polarity_for_insider,
    polarity_for_major_holder,
    utc_now,
)
from app.sec.scan import AccumulationScanManager
from app.sec.sectors import DEFAULT_SECTOR_BUCKETS, normalize_sector, sector_matches
from app.sec.submissions import TickerCikMapper
from app.services.providers import ProviderUnavailable

logger = logging.getLogger("app.sec.service")

SEC_FORM_FAMILIES = {"13F", "13D", "13G", "4"}

CAVEATS = [
    "13F: Quarterly reported holdings — not real-time trade activity.",
    "13D/13G: Beneficial ownership disclosures — interpret context carefully.",
    "Form 4: Insider transaction filings — filing date may differ from transaction date.",
]


class SecService:
    def __init__(
        self,
        settings: Settings,
        client: SecClient | None = None,
        mapper: TickerCikMapper | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or SecClient(settings)
        self.mapper = mapper or TickerCikMapper(settings, self.client)
        self._config = get_sec_config(settings)
        self._scan_manager = AccumulationScanManager(self, settings)

    def scan_status(self) -> dict[str, Any]:
        return self._scan_manager.scan_status()

    def start_accumulation_scan(self, services: Any, *, refresh: bool = False) -> dict[str, Any]:
        return self._scan_manager.start_scan(services, refresh=refresh)

    def maybe_auto_scan(self, session: Session, services: Any) -> None:
        self._scan_manager.maybe_auto_start(session, services)

    async def mini_scan(self, services: Any, tickers: list[str], *, cap: int = 25) -> None:
        await self._scan_manager.mini_scan(services, tickers, cap=cap)

    def list_sectors(self, session: Session) -> list[dict[str, Any]]:
        rows = session.query(SecCompanyMapping).filter(SecCompanyMapping.sector.isnot(None)).all()
        counts: dict[str, int] = {}
        for row in rows:
            bucket = normalize_sector(row.sector)
            if not bucket:
                continue
            counts[bucket] = counts.get(bucket, 0) + 1
        sectors = [{"sector": name, "ticker_count": counts[name]} for name in sorted(counts)]
        if sectors:
            return sectors
        return [{"sector": name, "ticker_count": 0} for name in DEFAULT_SECTOR_BUCKETS[:5]]

    def _latest_scores(self, session: Session) -> list[AccumulationScore]:
        subq = (
            session.query(
                AccumulationScore.ticker.label("ticker"),
                func.max(AccumulationScore.score_date).label("max_date"),
            )
            .group_by(AccumulationScore.ticker)
            .subquery()
        )
        return (
            session.query(AccumulationScore)
            .join(
                subq,
                (AccumulationScore.ticker == subq.c.ticker)
                & (AccumulationScore.score_date == subq.c.max_date),
            )
            .order_by(AccumulationScore.score.desc())
            .all()
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def sync_ticker(self, session: Session, ticker: str, finnhub: Any = None) -> None:
        mapping = await self.mapper.resolve_cik(ticker, session)
        if not mapping:
            raise ProviderUnavailable("sec", f"Unable to resolve CIK for {ticker}")
        if finnhub is not None:
            try:
                profile = await finnhub.company_profile(ticker)
                await self.mapper.enrich_sector(
                    session,
                    ticker,
                    profile.get("sector"),
                    profile.get("industry"),
                    profile.get("exchange"),
                )
            except Exception:
                logger.debug("finnhub_profile_enrich_failed", extra={"ticker": ticker.upper()})
        cik = mapping["cik"]
        submissions = await self.client.submissions(cik)
        filings = iter_recent_filings(submissions, SEC_FORM_FAMILIES)
        for filing in filings[:40]:
            accession = filing["accession_number"]
            existing = session.query(SecFiling).filter(SecFiling.accession_number == accession).one_or_none()
            if existing is not None:
                continue
            await self.ingest_filing(session, cik, ticker.upper(), filing)

    async def ingest_filing(
        self,
        session: Session,
        cik: str,
        ticker: str,
        filing_meta: dict[str, Any],
    ) -> None:
        accession = filing_meta["accession_number"]
        form_type = filing_meta["form_type"]
        family = filing_meta.get("form_family") or form_family(form_type)
        row = SecFiling(
            accession_number=accession,
            cik=normalize_cik(cik),
            ticker=ticker,
            form_type=form_type,
            form_family=family,
            filing_date=filing_meta.get("filing_date"),
            report_period=filing_meta.get("report_period"),
            is_amendment=bool(filing_meta.get("is_amendment")),
            raw_metadata=json.dumps(filing_meta, default=str),
        )
        session.add(row)
        session.flush()
        if filing_meta.get("is_amendment"):
            self._supersede_prior(session, ticker, family, accession)
        try:
            xml_text = await self.client.fetch_filing_document(cik, accession, form_type)
        except ProviderUnavailable:
            return
        if family == "13F":
            await self._ingest_13f(session, row, xml_text, cik)
        elif family == "13D":
            await self._ingest_13d(session, row, xml_text, ticker, form_type)
        elif family == "13G":
            await self._ingest_13g(session, row, xml_text, ticker, form_type)
        elif family == "4":
            await self._ingest_form4(session, row, xml_text, ticker)

    def _supersede_prior(self, session: Session, ticker: str, family: str, accession: str) -> None:
        prior = (
            session.query(SecFiling)
            .filter(
                SecFiling.ticker == ticker,
                SecFiling.form_family == family,
                SecFiling.superseded.is_(False),
                SecFiling.accession_number != accession,
            )
            .order_by(SecFiling.filing_date.desc())
            .first()
        )
        if prior is not None:
            prior.superseded = True
            prior.replaces_accession = accession

    async def _ingest_13f(self, session: Session, filing: SecFiling, xml_text: str, cik: str) -> None:
        manager_name, report_period = parse_13f_primary(xml_text)
        holdings = parse_13f_infotable(xml_text, manager_name or "Unknown", cik)
        if report_period and not filing.report_period:
            filing.report_period = report_period
        target = filing.ticker
        for holding in holdings:
            issuer_ticker = match_ticker_from_issuer(holding.issuer_name, target)
            if target and issuer_ticker and issuer_ticker != target:
                continue
            holding.issuer_ticker = issuer_ticker or target
            holding.report_period = filing.report_period
            session.add(
                InstitutionalHolding(
                    accession_number=filing.accession_number,
                    manager_name=holding.manager_name,
                    manager_cik=holding.manager_cik,
                    issuer_name=holding.issuer_name,
                    issuer_ticker=holding.issuer_ticker,
                    issuer_cusip=holding.issuer_cusip,
                    report_period=holding.report_period,
                    shares=holding.shares,
                    market_value=holding.market_value,
                    security_type=holding.security_type,
                    put_call=holding.put_call,
                )
            )
        session.flush()
        if target:
            self._compute_institutional_changes(session, target)

    def _compute_institutional_changes(self, session: Session, ticker: str) -> None:
        holdings = (
            session.query(InstitutionalHolding)
            .filter(InstitutionalHolding.issuer_ticker == ticker)
            .order_by(InstitutionalHolding.report_period.desc())
            .all()
        )
        by_manager: dict[str, list[InstitutionalHolding]] = {}
        for holding in holdings:
            key = holding.manager_cik or holding.manager_name
            by_manager.setdefault(key, []).append(holding)
        for manager_key, rows in by_manager.items():
            rows.sort(key=lambda item: item.report_period or date.min, reverse=True)
            if len(rows) < 2:
                if len(rows) == 1 and rows[0].shares > 0:
                    classification = "NEW_POSITION"
                    self._upsert_position_change(session, rows[0], 0.0, rows[0].shares, classification)
                continue
            current = rows[0]
            previous = rows[1]
            classification = classify_institutional_change(previous.shares, current.shares)
            if classification == "UNCHANGED":
                continue
            self._upsert_position_change(
                session,
                current,
                previous.shares,
                current.shares,
                classification,
            )

    def _upsert_position_change(
        self,
        session: Session,
        holding: InstitutionalHolding,
        previous_shares: float,
        current_shares: float,
        classification: str,
    ) -> None:
        filing = session.query(SecFiling).filter(SecFiling.accession_number == holding.accession_number).one_or_none()
        existing = (
            session.query(InstitutionalPositionChange)
            .filter(
                InstitutionalPositionChange.manager_name == holding.manager_name,
                InstitutionalPositionChange.issuer_ticker == holding.issuer_ticker,
                InstitutionalPositionChange.report_period == holding.report_period,
            )
            .one_or_none()
        )
        payload = {
            "manager_name": holding.manager_name,
            "manager_cik": holding.manager_cik,
            "issuer_ticker": holding.issuer_ticker or "",
            "report_period": holding.report_period,
            "previous_shares": previous_shares,
            "current_shares": current_shares,
            "change_shares": current_shares - previous_shares,
            "change_pct": institutional_change_pct(previous_shares, current_shares),
            "classification": classification,
            "accession_number": holding.accession_number,
            "filing_date": filing.filing_date if filing else None,
        }
        if existing is None:
            session.add(InstitutionalPositionChange(**payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
        session.flush()

    async def _ingest_13d(self, session: Session, filing: SecFiling, xml_text: str, ticker: str, form_type: str) -> None:
        parsed = parse_13d(xml_text, form_type=form_type, is_amendment=filing.is_amendment)
        if parsed is None:
            return
        parsed.issuer_ticker = ticker
        parsed.filing_date = filing.filing_date
        await self._store_beneficial(session, filing, parsed)

    async def _ingest_13g(self, session: Session, filing: SecFiling, xml_text: str, ticker: str, form_type: str) -> None:
        parsed = parse_13g(xml_text, form_type=form_type, is_amendment=filing.is_amendment)
        if parsed is None:
            return
        parsed.issuer_ticker = ticker
        parsed.filing_date = filing.filing_date
        await self._store_beneficial(session, filing, parsed)

    async def _store_beneficial(self, session: Session, filing: SecFiling, parsed: Any) -> None:
        prior = (
            session.query(BeneficialOwnership)
            .filter(
                BeneficialOwnership.issuer_ticker == parsed.issuer_ticker,
                BeneficialOwnership.reporter_name == parsed.reporter_name,
            )
            .order_by(BeneficialOwnership.filing_date.desc())
            .first()
        )
        prev_pct = prior.ownership_pct if prior else None
        event_type = classify_beneficial_ownership_event(prev_pct, parsed.ownership_pct)
        session.add(
            BeneficialOwnership(
                accession_number=filing.accession_number,
                reporter_name=parsed.reporter_name,
                reporter_cik=parsed.reporter_cik,
                issuer_ticker=parsed.issuer_ticker,
                issuer_name=parsed.issuer_name,
                shares=parsed.shares,
                ownership_pct=parsed.ownership_pct,
                form_type=parsed.form_type,
                filing_date=parsed.filing_date,
                purpose=parsed.purpose,
                passive_flag=parsed.passive_flag,
                is_amendment=parsed.is_amendment,
                event_type=event_type,
            )
        )
        session.flush()

    async def _ingest_form4(self, session: Session, filing: SecFiling, xml_text: str, ticker: str) -> None:
        transactions = parse_form4(xml_text)
        for txn in transactions:
            txn.issuer_ticker = ticker
            txn.filing_date = filing.filing_date
            normalized = classify_insider_transaction(txn.transaction_code)
            existing = (
                session.query(InsiderTransaction)
                .filter(
                    InsiderTransaction.accession_number == filing.accession_number,
                    InsiderTransaction.transaction_code == txn.transaction_code,
                    InsiderTransaction.transaction_date == txn.transaction_date,
                    InsiderTransaction.insider_name == txn.insider_name,
                    InsiderTransaction.shares == txn.shares,
                )
                .one_or_none()
            )
            if existing is not None:
                continue
            session.add(
                InsiderTransaction(
                    accession_number=filing.accession_number,
                    insider_name=txn.insider_name,
                    insider_title=txn.insider_title,
                    issuer_ticker=txn.issuer_ticker,
                    transaction_date=txn.transaction_date,
                    filing_date=txn.filing_date,
                    transaction_code=txn.transaction_code,
                    normalized_type=normalized,
                    shares=txn.shares,
                    price=txn.price,
                    value=txn.value,
                    shares_owned_after=txn.shares_owned_after,
                    ownership_type=txn.ownership_type,
                    is_derivative=txn.is_derivative,
                )
            )
        session.flush()

    def load_normalized_events(self, session: Session, ticker: str) -> list[NormalizedEvent]:
        symbol = ticker.upper()
        events: list[NormalizedEvent] = []
        labels = self._config.get("signal_labels", {})
        for change in (
            session.query(InstitutionalPositionChange)
            .filter(InstitutionalPositionChange.issuer_ticker == symbol)
            .order_by(InstitutionalPositionChange.report_period.desc())
            .limit(100)
        ):
            event_id = f"inst:{change.accession_number}:{change.manager_name}:{change.report_period}"
            if session.query(AccumulationEvent).filter(AccumulationEvent.event_id == event_id).one_or_none():
                pass
            polarity = polarity_for_institutional(change.classification, self._config)
            events.append(
                NormalizedEvent(
                    event_id=event_id,
                    source="13F",
                    accession_number=change.accession_number,
                    filing_date=change.filing_date,
                    reporting_period=change.report_period,
                    event_type=change.classification,
                    component="institutional",
                    signal_label=labels.get("institutional", "Reported institutional position change"),
                    data_timestamp=utc_now(),
                    ticker=symbol,
                    polarity=polarity,
                    metadata={
                        "manager": change.manager_name,
                        "change_pct": change.change_pct,
                        "detail": (
                            f"{change.manager_name} reported {change.classification.lower().replace('_', ' ')} "
                            f"({change.previous_shares:.0f} → {change.current_shares:.0f} shares)"
                        ),
                    },
                )
            )
        for txn in (
            session.query(InsiderTransaction)
            .filter(InsiderTransaction.issuer_ticker == symbol)
            .order_by(InsiderTransaction.transaction_date.desc())
            .limit(100)
        ):
            event_id = f"insider:{txn.accession_number}:{txn.insider_name}:{txn.transaction_date}:{txn.transaction_code}:{txn.shares}"
            events.append(
                NormalizedEvent(
                    event_id=event_id,
                    source="Form4",
                    accession_number=txn.accession_number,
                    filing_date=txn.filing_date,
                    reporting_period=txn.transaction_date,
                    event_type=txn.normalized_type,
                    component="insider",
                    signal_label=labels.get("insider", "Insider transaction filing"),
                    data_timestamp=utc_now(),
                    ticker=symbol,
                    polarity=polarity_for_insider(txn.normalized_type),
                    metadata={
                        "insider_name": txn.insider_name,
                        "insider_title": txn.insider_title,
                        "value": txn.value,
                        "transaction_code": txn.transaction_code,
                    },
                )
            )
        for holder in (
            session.query(BeneficialOwnership)
            .filter(BeneficialOwnership.issuer_ticker == symbol)
            .order_by(BeneficialOwnership.filing_date.desc())
            .limit(50)
        ):
            event_id = f"major:{holder.accession_number}:{holder.reporter_name}"
            events.append(
                NormalizedEvent(
                    event_id=event_id,
                    source=holder.form_type,
                    accession_number=holder.accession_number,
                    filing_date=holder.filing_date,
                    reporting_period=None,
                    event_type=holder.event_type or "OWNERSHIP_UNCHANGED",
                    component="major_holder",
                    signal_label=labels.get("major_holder", "Beneficial ownership disclosure"),
                    data_timestamp=utc_now(),
                    ticker=symbol,
                    polarity=polarity_for_major_holder(holder.event_type or ""),
                    metadata={
                        "reporter": holder.reporter_name,
                        "ownership_pct": holder.ownership_pct,
                        "passive_flag": holder.passive_flag,
                        "purpose": holder.purpose,
                    },
                )
            )
        return events

    async def accumulation_for_ticker(
        self,
        session: Session,
        ticker: str,
        alpaca: Any,
        finnhub: Any,
        sync: bool = True,
    ) -> dict[str, Any]:
        provider_errors: list[dict[str, str]] = []
        symbol = ticker.upper()
        if sync:
            try:
                await self.sync_ticker(session, symbol, finnhub)
            except ProviderUnavailable as exc:
                provider_errors.append({"provider": exc.provider, "message": str(exc)})
            except Exception as exc:
                logger.error("sec_sync_failed", extra={"ticker": symbol, "error_type": type(exc).__name__})
                provider_errors.append({"provider": "sec", "message": "SEC sync failed"})

        events = self.load_normalized_events(session, symbol)
        bars: list[dict[str, Any]] = []
        spy_bars: list[dict[str, Any]] = []
        fundamentals: dict[str, float | None] = {}
        try:
            bars = alpaca.bars(symbol, "1Day", None, None, 120)
        except Exception:
            provider_errors.append({"provider": "alpaca", "message": "Price/volume data unavailable"})
        try:
            spy_bars = alpaca.bars("SPY", "1Day", None, None, 120)
        except Exception:
            spy_bars = []
        try:
            fundamentals = await finnhub.extended_fundamentals(symbol)
        except Exception:
            provider_errors.append({"provider": "finnhub", "message": "Fundamentals unavailable"})

        score_payload = compute_accumulation_score(events, bars, fundamentals, self._config, spy_bars)
        persist_score_snapshot(session, symbol, score_payload)
        history = self._score_history(session, symbol)
        evidence = build_evidence_list(events, score_payload)
        return {
            "ticker": symbol,
            "score": score_payload["score"],
            "signal": score_payload["signal"],
            "classification": score_payload["classification"],
            "components": score_payload["components"],
            "events": evidence,
            "history": history,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "provider_errors": provider_errors,
        }

    def _score_history(self, session: Session, ticker: str, limit: int = 12) -> list[dict[str, Any]]:
        rows = (
            session.query(AccumulationScore)
            .filter(AccumulationScore.ticker == ticker.upper())
            .order_by(AccumulationScore.score_date.desc())
            .limit(limit)
            .all()
        )
        return [
            {"date": row.score_date.isoformat(), "score": row.score, "classification": row.classification}
            for row in reversed(rows)
        ]

    def institutional_payload(self, session: Session, ticker: str) -> dict[str, Any]:
        symbol = ticker.upper()
        changes = (
            session.query(InstitutionalPositionChange)
            .filter(InstitutionalPositionChange.issuer_ticker == symbol)
            .order_by(InstitutionalPositionChange.report_period.desc())
            .limit(50)
            .all()
        )
        return {
            "ticker": symbol,
            "changes": [
                {
                    "manager": row.manager_name,
                    "reporting_period": row.report_period.isoformat() if row.report_period else None,
                    "filing_date": row.filing_date.isoformat() if row.filing_date else None,
                    "classification": row.classification,
                    "previous_shares": row.previous_shares,
                    "current_shares": row.current_shares,
                    "change_pct": row.change_pct,
                    "signal_label": "Reported institutional position change",
                }
                for row in changes
            ],
        }

    def insiders_payload(self, session: Session, ticker: str) -> dict[str, Any]:
        symbol = ticker.upper()
        rows = (
            session.query(InsiderTransaction)
            .filter(InsiderTransaction.issuer_ticker == symbol)
            .order_by(InsiderTransaction.transaction_date.desc())
            .limit(50)
            .all()
        )
        return {
            "ticker": symbol,
            "transactions": [
                {
                    "insider": row.insider_name,
                    "title": row.insider_title,
                    "transaction_date": row.transaction_date.isoformat() if row.transaction_date else None,
                    "filing_date": row.filing_date.isoformat() if row.filing_date else None,
                    "code": row.transaction_code,
                    "normalized_type": row.normalized_type,
                    "shares": row.shares,
                    "price": row.price,
                    "value": row.value,
                }
                for row in rows
            ],
        }

    def sec_intelligence(self, session: Session, ticker: str, accumulation: dict[str, Any]) -> dict[str, Any]:
        symbol = ticker.upper()
        major = (
            session.query(BeneficialOwnership)
            .filter(BeneficialOwnership.issuer_ticker == symbol)
            .order_by(BeneficialOwnership.filing_date.desc())
            .limit(20)
            .all()
        )
        return {
            "ticker": symbol,
            "accumulation": accumulation,
            "institutional_changes": self.institutional_payload(session, symbol)["changes"][:20],
            "insider_transactions": self.insiders_payload(session, symbol)["transactions"][:20],
            "major_holder_changes": [
                {
                    "reporter": row.reporter_name,
                    "form_type": row.form_type,
                    "filing_date": row.filing_date.isoformat() if row.filing_date else None,
                    "ownership_pct": row.ownership_pct,
                    "event_type": row.event_type,
                    "passive": row.passive_flag,
                    "purpose": row.purpose,
                }
                for row in major
            ],
            "caveats": CAVEATS,
        }

    def top_accumulation(
        self,
        session: Session,
        sector: str | None = None,
        min_score: float = 0.0,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        rows = self._latest_scores(session)
        results: list[dict[str, Any]] = []
        for row in rows:
            if row.score < min_score:
                continue
            mapping = session.query(SecCompanyMapping).filter(SecCompanyMapping.ticker == row.ticker).one_or_none()
            if sector:
                if mapping is None or not sector_matches(mapping.sector, sector):
                    continue
            components = json.loads(row.components_json)
            results.append(
                {
                    "ticker": row.ticker,
                    "score": row.score,
                    "classification": row.classification,
                    "sector": normalize_sector(mapping.sector) if mapping and mapping.sector else None,
                    "components": components,
                }
            )
        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:limit]

    def sector_accumulation(self, session: Session, sector: str) -> dict[str, Any]:
        mappings = session.query(SecCompanyMapping).filter(SecCompanyMapping.sector.isnot(None)).all()
        tickers = [row.ticker for row in mappings if sector_matches(row.sector, sector)]
        scores: list[float] = []
        increasing = 0
        decreasing = 0
        stocks: list[dict[str, Any]] = []
        for ticker in tickers:
            history = self._score_history(session, ticker, limit=2)
            if not history:
                continue
            current = history[-1]["score"]
            scores.append(current)
            if len(history) >= 2:
                if history[-1]["score"] > history[-2]["score"]:
                    increasing += 1
                elif history[-1]["score"] < history[-2]["score"]:
                    decreasing += 1
            row = (
                session.query(AccumulationScore)
                .filter(AccumulationScore.ticker == ticker)
                .order_by(AccumulationScore.score_date.desc())
                .first()
            )
            components = json.loads(row.components_json) if row else {}
            stocks.append({"ticker": ticker, "score": current, "components": components})
        count = len(scores)
        return {
            "sector": sector,
            "ticker_count": count,
            "avg_score": round(sum(scores) / count, 1) if count else 0.0,
            "pct_increasing": round(increasing / count * 100, 1) if count else 0.0,
            "pct_decreasing": round(decreasing / count * 100, 1) if count else 0.0,
            "stocks": sorted(stocks, key=lambda item: item["score"], reverse=True),
        }

    async def recent_filings_payload(
        self,
        session: Session,
        ticker: str,
        finnhub: Any,
        *,
        months: int = 6,
        limit: int = 100,
    ) -> dict[str, Any]:
        symbol = ticker.upper()
        provider_errors: list[dict[str, str]] = []
        try:
            await self.sync_ticker(session, symbol, finnhub)
        except ProviderUnavailable as exc:
            provider_errors.append({"provider": exc.provider, "message": str(exc)})
        except Exception:
            provider_errors.append({"provider": "sec", "message": "SEC sync failed"})

        cutoff = date.today() - timedelta(days=max(1, months) * 30)
        filings = (
            session.query(SecFiling)
            .filter(SecFiling.ticker == symbol, SecFiling.filing_date >= cutoff)
            .order_by(SecFiling.filing_date.desc())
            .limit(limit)
            .all()
        )
        mapping = session.query(SecCompanyMapping).filter(SecCompanyMapping.ticker == symbol).one_or_none()
        cik = mapping.cik if mapping else None
        records: list[dict[str, Any]] = []
        summary: dict[str, int] = {"13F": 0, "13D": 0, "13G": 0, "4": 0}
        for filing in filings:
            family = filing.form_family
            if family in summary:
                summary[family] += 1
            description = filing.form_type
            if filing.is_amendment:
                description = f"{description} (amendment)"
            url = edgar_filing_url(cik, filing.accession_number) if cik else None
            records.append(
                {
                    "accession_number": filing.accession_number,
                    "form_type": filing.form_type,
                    "form_family": family,
                    "filing_date": filing.filing_date.isoformat() if filing.filing_date else None,
                    "report_period": filing.report_period.isoformat() if filing.report_period else None,
                    "description": description,
                    "is_amendment": filing.is_amendment,
                    "edgar_url": url,
                }
            )

        insider_rows = (
            session.query(InsiderTransaction)
            .filter(InsiderTransaction.issuer_ticker == symbol)
            .filter(InsiderTransaction.filing_date >= cutoff)
            .order_by(InsiderTransaction.filing_date.desc())
            .limit(50)
            .all()
        )
        insider_transactions = [
            {
                "insider": row.insider_name,
                "title": row.insider_title,
                "transaction_date": row.transaction_date.isoformat() if row.transaction_date else None,
                "filing_date": row.filing_date.isoformat() if row.filing_date else None,
                "code": row.transaction_code,
                "normalized_type": row.normalized_type,
                "shares": row.shares,
                "price": row.price,
                "value": row.value,
                "accession_number": row.accession_number,
            }
            for row in insider_rows
        ]
        ownership_rows = (
            session.query(BeneficialOwnership)
            .filter(BeneficialOwnership.issuer_ticker == symbol)
            .filter(BeneficialOwnership.filing_date >= cutoff)
            .order_by(BeneficialOwnership.filing_date.desc())
            .limit(50)
            .all()
        )
        beneficial_ownership = [
            {
                "reporter": row.reporter_name,
                "form_type": row.form_type,
                "filing_date": row.filing_date.isoformat() if row.filing_date else None,
                "ownership_pct": row.ownership_pct,
                "event_type": row.event_type,
                "passive": row.passive_flag,
                "accession_number": row.accession_number,
            }
            for row in ownership_rows
        ]
        return {
            "ticker": symbol,
            "months": months,
            "cutoff_date": cutoff.isoformat(),
            "summary": summary,
            "filings": records,
            "insider_transactions": insider_transactions,
            "beneficial_ownership": beneficial_ownership,
            "provider_errors": provider_errors,
        }

    def ingest_fixture_filing(self, session: Session, ticker: str, filing_meta: dict[str, Any], xml_text: str) -> None:
        """Test/dev helper to ingest fixture XML without network."""
        symbol = ticker.upper()
        mapping = {"ticker": symbol, "cik": filing_meta.get("cik", "0000320193")}
        self.mapper.seed_mapping({symbol: mapping})
        company_row = session.query(SecCompanyMapping).filter(SecCompanyMapping.ticker == symbol).one_or_none()
        if company_row is None:
            session.add(
                SecCompanyMapping(
                    ticker=symbol,
                    cik=mapping["cik"],
                    company_name=filing_meta.get("company_name", ticker),
                    sector=normalize_sector(filing_meta.get("sector")) or filing_meta.get("sector"),
                )
            )
        elif filing_meta.get("sector"):
            company_row.sector = normalize_sector(filing_meta.get("sector")) or filing_meta.get("sector")
        filing_meta.setdefault("form_family", form_family(filing_meta["form_type"]))
        filing_meta.setdefault("is_amendment", False)
        existing_filing = (
            session.query(SecFiling)
            .filter(SecFiling.accession_number == filing_meta["accession_number"])
            .one_or_none()
        )
        if existing_filing is not None:
            return
        row = SecFiling(
            accession_number=filing_meta["accession_number"],
            cik=mapping["cik"],
            ticker=ticker.upper(),
            form_type=filing_meta["form_type"],
            form_family=filing_meta["form_family"],
            filing_date=filing_meta.get("filing_date"),
            report_period=filing_meta.get("report_period"),
            is_amendment=filing_meta.get("is_amendment", False),
        )
        session.add(row)
        session.flush()
        if filing_meta.get("is_amendment"):
            self._supersede_prior(session, ticker.upper(), filing_meta["form_family"], filing_meta["accession_number"])
        family = filing_meta["form_family"]
        if family == "13F":
            manager_name, report_period = parse_13f_primary(xml_text)
            if report_period:
                row.report_period = report_period
            holdings = parse_13f_infotable(xml_text, manager_name or "Fund A", mapping["cik"])
            for holding in holdings:
                holding.issuer_ticker = ticker.upper()
                holding.report_period = row.report_period
                session.add(
                    InstitutionalHolding(
                        accession_number=row.accession_number,
                        manager_name=holding.manager_name,
                        manager_cik=holding.manager_cik,
                        issuer_name=holding.issuer_name,
                        issuer_ticker=holding.issuer_ticker,
                        issuer_cusip=holding.issuer_cusip,
                        report_period=holding.report_period,
                        shares=holding.shares,
                        market_value=holding.market_value,
                    )
                )
            self._compute_institutional_changes(session, ticker.upper())
        elif family == "13D":
            parsed = parse_13d(xml_text, filing_meta["form_type"])
            if parsed:
                parsed.issuer_ticker = ticker.upper()
                parsed.filing_date = filing_meta.get("filing_date")
                session.add(
                    BeneficialOwnership(
                        accession_number=row.accession_number,
                        reporter_name=parsed.reporter_name,
                        issuer_ticker=ticker.upper(),
                        issuer_name=parsed.issuer_name,
                        shares=parsed.shares,
                        ownership_pct=parsed.ownership_pct,
                        form_type=parsed.form_type,
                        filing_date=parsed.filing_date,
                        purpose=parsed.purpose,
                        passive_flag=parsed.passive_flag,
                        event_type="NEW_MAJOR_HOLDER",
                    )
                )
        elif family == "4":
            for txn in parse_form4(xml_text):
                session.add(
                    InsiderTransaction(
                        accession_number=row.accession_number,
                        insider_name=txn.insider_name,
                        insider_title=txn.insider_title,
                        issuer_ticker=ticker.upper(),
                        transaction_date=txn.transaction_date or filing_meta.get("filing_date"),
                        filing_date=filing_meta.get("filing_date"),
                        transaction_code=txn.transaction_code,
                        normalized_type=classify_insider_transaction(txn.transaction_code),
                        shares=txn.shares,
                        price=txn.price,
                        value=txn.value,
                    )
                )
        session.flush()
