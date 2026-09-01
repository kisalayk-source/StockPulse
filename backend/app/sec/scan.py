from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_session
from app.services.kronos import BLUE_CHIP_UNIVERSE

logger = logging.getLogger("app.sec.scan")

ETF_TICKERS = frozenset(
    {
        "SPY",
        "QQQ",
        "IWM",
        "DIA",
        "VOO",
        "VTI",
        "IVV",
        "XLF",
        "XLK",
        "XLE",
        "XLV",
        "XLI",
        "XLY",
        "XLP",
        "XLU",
        "XLB",
        "XLRE",
        "XLC",
        "ARKK",
        "GLD",
        "SLV",
        "TLT",
        "HYG",
        "EEM",
        "EFA",
    }
)

SCAN_MIN_TICKERS = 10


def build_scan_universe(kronos: Any, *, cap: int = 100) -> list[str]:
    symbols: list[str] = []
    for symbol in BLUE_CHIP_UNIVERSE:
        upper = str(symbol).upper()
        if upper and upper not in ETF_TICKERS:
            symbols.append(upper)
    try:
        movers_payload = kronos.scan_movers(limit=25, refresh=False)
        for item in movers_payload.get("movers") or []:
            ticker = str(item.get("symbol") or item.get("ticker") or "").upper()
            if ticker and ticker not in ETF_TICKERS:
                symbols.append(ticker)
        for bucket in ("gainers", "losers"):
            for item in movers_payload.get(bucket) or []:
                ticker = str(item.get("symbol") or item.get("ticker") or "").upper()
                if ticker and ticker not in ETF_TICKERS:
                    symbols.append(ticker)
    except Exception:
        logger.debug("movers_universe_unavailable")
    unique = list(dict.fromkeys(symbols))
    return unique[: max(1, cap)]


class AccumulationScanManager:
    def __init__(self, sec_service: Any, settings: Settings) -> None:
        self._sec = sec_service
        self._settings = settings
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._progress: dict[str, Any] = {"status": "idle", "scanned": 0, "total": 0, "errors": []}

    def scan_status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._progress)

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def scored_ticker_count(self, session: Session) -> int:
        from app.sec.db_models import AccumulationScore

        return session.query(AccumulationScore.ticker).distinct().count()

    def maybe_auto_start(self, session: Session, services: Any) -> None:
        if not self._settings.sec_enabled:
            return
        if self.is_running():
            return
        if self.scored_ticker_count(session) >= SCAN_MIN_TICKERS:
            return
        self.start_scan(services, refresh=False)

    def start_scan(self, services: Any, *, refresh: bool = False) -> dict[str, Any]:
        if not self._settings.sec_enabled:
            return {"status": "disabled", "scanned": 0, "total": 0, "errors": []}
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return dict(self._progress)
            self._progress = {
                "status": "pending",
                "scanned": 0,
                "total": 0,
                "errors": [],
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "refresh": refresh,
            }
            self._thread = threading.Thread(
                target=self._run_scan,
                args=(services, refresh),
                name="sec-accumulation-scan",
                daemon=True,
            )
            self._thread.start()
            return dict(self._progress)

    def _run_scan(self, services: Any, refresh: bool) -> None:
        try:
            cap = self._settings.sec_scan_universe_cap
            tickers = build_scan_universe(services.kronos, cap=cap)
            with self._lock:
                self._progress = {
                    **self._progress,
                    "total": len(tickers),
                    "status": "running",
                }
            asyncio.run(self._scan_tickers(services, tickers))
            with self._lock:
                self._progress = {
                    **self._progress,
                    "status": "ready",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
        except Exception:
            logger.exception("accumulation_scan_failed")
            with self._lock:
                self._progress = {
                    **self._progress,
                    "status": "error",
                    "error": "Accumulation scan failed; check server logs",
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }

    async def _scan_tickers(self, services: Any, tickers: list[str]) -> None:
        for idx, ticker in enumerate(tickers, start=1):
            gen = get_session()
            session = next(gen)
            try:
                try:
                    await services.sec.accumulation_for_ticker(
                        session,
                        ticker,
                        services.alpaca,
                        services.finnhub,
                        sync=True,
                    )
                except Exception as exc:
                    logger.warning(
                        "accumulation_scan_ticker_failed",
                        extra={"ticker": ticker, "error_type": type(exc).__name__},
                    )
                    with self._lock:
                        errors = list(self._progress.get("errors") or [])
                        if len(errors) < 20:
                            errors.append({"ticker": ticker, "message": type(exc).__name__})
                        self._progress["errors"] = errors
            finally:
                try:
                    next(gen)
                except StopIteration:
                    pass
            with self._lock:
                self._progress["scanned"] = idx
                self._progress["status"] = "running"

    async def mini_scan(self, services: Any, tickers: list[str], *, cap: int = 25) -> None:
        limited = list(dict.fromkeys(t.upper() for t in tickers if t))[:cap]
        if not limited:
            return
        await self._scan_tickers(services, limited)
