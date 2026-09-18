"""Map government contractors to StockPulse tickers."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy.orm import Session

from app.government.db_models import GovernmentCompanyMapping
from app.sec.db_models import SecCompanyMapping

logger = logging.getLogger("app.government.mapping")

_SUFFIXES = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|llc|l\.l\.c|ltd|limited|plc|lp|llp|holdings|group)\b\.?",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9\s]+")


def normalize_company_name(name: str | None) -> str | None:
    if not name:
        return None
    text = name.lower().strip()
    text = _SUFFIXES.sub(" ", text)
    text = _NON_ALNUM.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


@dataclass
class MappingResult:
    ticker: str | None
    confidence: float
    method: str
    cik: str | None = None


class GovernmentCompanyMapper:
    """Resolve UEI / CAGE / CIK / legal name → ticker with confidence."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        mapping = (config or {}).get("mapping") or {}
        self.min_confidence = float(mapping.get("min_confidence", 0.75))
        self.fuzzy_min = float(mapping.get("fuzzy_min_confidence", 0.55))
        self.fuzzy_accept = float(mapping.get("fuzzy_accept_confidence", 0.85))

    def resolve(
        self,
        session: Session,
        *,
        uei: str | None = None,
        cage: str | None = None,
        cik: str | None = None,
        company_name: str | None = None,
        ticker_hint: str | None = None,
    ) -> MappingResult:
        if ticker_hint:
            hint = ticker_hint.strip().upper()
            if hint:
                return MappingResult(ticker=hint, confidence=1.0, method="existing", cik=cik)

        if uei:
            row = (
                session.query(GovernmentCompanyMapping)
                .filter(GovernmentCompanyMapping.uei == uei.strip().upper())
                .one_or_none()
            )
            if row:
                return MappingResult(
                    ticker=row.ticker.upper(),
                    confidence=float(row.confidence),
                    method="uei",
                    cik=row.cik,
                )

        if cage:
            row = (
                session.query(GovernmentCompanyMapping)
                .filter(GovernmentCompanyMapping.cage == cage.strip().upper())
                .one_or_none()
            )
            if row:
                return MappingResult(
                    ticker=row.ticker.upper(),
                    confidence=float(row.confidence),
                    method="cage",
                    cik=row.cik,
                )

        if cik:
            padded = cik.strip().zfill(10)
            sec = (
                session.query(SecCompanyMapping)
                .filter(SecCompanyMapping.cik == padded)
                .one_or_none()
            )
            if sec:
                return MappingResult(
                    ticker=sec.ticker.upper(),
                    confidence=0.95,
                    method="cik",
                    cik=padded,
                )
            gov = (
                session.query(GovernmentCompanyMapping)
                .filter(GovernmentCompanyMapping.cik == padded)
                .one_or_none()
            )
            if gov:
                return MappingResult(
                    ticker=gov.ticker.upper(),
                    confidence=float(gov.confidence),
                    method="cik",
                    cik=padded,
                )

        normalized = normalize_company_name(company_name)
        if normalized:
            exact = (
                session.query(GovernmentCompanyMapping)
                .filter(GovernmentCompanyMapping.normalized_name == normalized)
                .one_or_none()
            )
            if exact:
                return MappingResult(
                    ticker=exact.ticker.upper(),
                    confidence=float(exact.confidence),
                    method="name",
                    cik=exact.cik,
                )

            sec_rows = session.query(SecCompanyMapping).filter(SecCompanyMapping.company_name.isnot(None)).all()
            best: MappingResult | None = None
            for sec in sec_rows:
                sec_norm = normalize_company_name(sec.company_name)
                if not sec_norm:
                    continue
                if sec_norm == normalized:
                    return MappingResult(
                        ticker=sec.ticker.upper(),
                        confidence=0.9,
                        method="name",
                        cik=sec.cik,
                    )
                ratio = SequenceMatcher(None, normalized, sec_norm).ratio()
                if ratio < self.fuzzy_min:
                    continue
                # Cap fuzzy confidence so uncertain matches do not drive signals
                conf = min(0.74, round(ratio * self.fuzzy_accept, 4))
                if best is None or conf > best.confidence:
                    best = MappingResult(
                        ticker=sec.ticker.upper(),
                        confidence=conf,
                        method="fuzzy",
                        cik=sec.cik,
                    )
            if best is not None:
                logger.info(
                    "government_mapping_success" if best.confidence >= self.min_confidence else "government_mapping_failure",
                    extra={
                        "method": best.method,
                        "ticker": best.ticker,
                        "confidence": best.confidence,
                        "company_name": company_name,
                    },
                )
                return best

        logger.info(
            "government_mapping_failure",
            extra={"uei": uei, "cage": cage, "cik": cik, "company_name": company_name},
        )
        return MappingResult(ticker=None, confidence=0.0, method="unmapped")

    def persist(
        self,
        session: Session,
        result: MappingResult,
        *,
        uei: str | None = None,
        cage: str | None = None,
        company_name: str | None = None,
    ) -> None:
        if not result.ticker or result.confidence <= 0:
            return
        normalized = normalize_company_name(company_name)
        existing = None
        if uei:
            existing = (
                session.query(GovernmentCompanyMapping)
                .filter(GovernmentCompanyMapping.uei == uei.strip().upper())
                .one_or_none()
            )
        if existing is None and cage:
            existing = (
                session.query(GovernmentCompanyMapping)
                .filter(GovernmentCompanyMapping.cage == cage.strip().upper())
                .one_or_none()
            )
        if existing is None and normalized:
            existing = (
                session.query(GovernmentCompanyMapping)
                .filter(GovernmentCompanyMapping.normalized_name == normalized)
                .one_or_none()
            )
        if existing is None:
            existing = GovernmentCompanyMapping(
                ticker=result.ticker.upper(),
                confidence=result.confidence,
                method=result.method,
            )
            session.add(existing)
        existing.ticker = result.ticker.upper()
        existing.confidence = max(float(existing.confidence or 0), result.confidence)
        existing.method = result.method
        if uei:
            existing.uei = uei.strip().upper()
        if cage:
            existing.cage = cage.strip().upper()
        if result.cik:
            existing.cik = result.cik.zfill(10)
        if company_name:
            existing.company_name = company_name[:512]
        if normalized:
            existing.normalized_name = normalized
        logger.info(
            "government_mapping_success",
            extra={
                "ticker": existing.ticker,
                "method": existing.method,
                "confidence": existing.confidence,
                "uei": existing.uei,
                "cage": existing.cage,
            },
        )

    def is_confident(self, confidence: float | None) -> bool:
        return float(confidence or 0.0) >= self.min_confidence
