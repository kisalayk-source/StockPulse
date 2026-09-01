from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.sec.client import SecClient
from app.sec.db_models import SecCompanyMapping
from app.sec.edgar import normalize_cik
from app.sec.sectors import normalize_sector

logger = logging.getLogger("app.sec.submissions")


class TickerCikMapper:
    """Ticker to CIK resolution with memory and DB cache."""

    def __init__(self, settings: Settings, client: SecClient) -> None:
        self.settings = settings
        self.client = client
        self._ticker_index: dict[str, dict[str, Any]] | None = None
        self._loaded_at: datetime | None = None

    async def _load_index(self) -> dict[str, dict[str, Any]]:
        if self._ticker_index and self._loaded_at and datetime.now(timezone.utc) - self._loaded_at < timedelta(days=7):
            return self._ticker_index
        payload = await self.client.company_tickers()
        index: dict[str, dict[str, Any]] = {}
        for entry in payload.values() if isinstance(payload, dict) else []:
            ticker = str(entry.get("ticker", "")).upper()
            if not ticker:
                continue
            index[ticker] = {
                "ticker": ticker,
                "cik": normalize_cik(entry.get("cik_str") or entry.get("cik")),
                "company_name": entry.get("title"),
            }
        self._ticker_index = index
        self._loaded_at = datetime.now(timezone.utc)
        return index

    async def resolve_cik(self, ticker: str, session: Session | None = None) -> dict[str, Any] | None:
        symbol = ticker.upper()
        if session is not None:
            row = session.query(SecCompanyMapping).filter(SecCompanyMapping.ticker == symbol).one_or_none()
            if row is not None:
                return {
                    "ticker": row.ticker,
                    "cik": row.cik,
                    "company_name": row.company_name,
                    "exchange": row.exchange,
                    "sector": row.sector,
                    "industry": row.industry,
                }
        index = await self._load_index()
        match = index.get(symbol)
        if match and session is not None:
            self._persist_mapping(session, match)
        return match

    def _persist_mapping(self, session: Session, mapping: dict[str, Any]) -> None:
        ticker = mapping["ticker"]
        row = session.query(SecCompanyMapping).filter(SecCompanyMapping.ticker == ticker).one_or_none()
        if row is None:
            row = SecCompanyMapping(
                ticker=ticker,
                cik=mapping["cik"],
                company_name=mapping.get("company_name"),
            )
            session.add(row)
        else:
            row.cik = mapping["cik"]
            row.company_name = mapping.get("company_name") or row.company_name
        session.flush()

    async def enrich_sector(
        self,
        session: Session,
        ticker: str,
        sector: str | None,
        industry: str | None,
        exchange: str | None = None,
    ) -> None:
        row = session.query(SecCompanyMapping).filter(SecCompanyMapping.ticker == ticker.upper()).one_or_none()
        if row is None:
            return
        if sector:
            row.sector = normalize_sector(sector) or sector
        if industry:
            row.industry = industry
        if exchange:
            row.exchange = exchange
        session.flush()

    def seed_mapping(self, mappings: dict[str, dict[str, Any]]) -> None:
        """Test helper to inject ticker index without network."""
        self._ticker_index = mappings
        self._loaded_at = datetime.now(timezone.utc)
