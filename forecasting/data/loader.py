"""Canonical OHLCV loading (CSV offline + optional Alpaca live)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from forecasting.core.schema import CANONICAL_OHLCV_COLUMNS, assert_canonical_ohlcv

logger = logging.getLogger("forecasting.data")

COLUMN_ALIASES = {
    "date": "timestamp",
    "datetime": "timestamp",
    "time": "timestamp",
    "timestamps": "timestamp",
    "vol": "volume",
    "amt": "amount",
    "ticker": "symbol",
    "code": "symbol",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
}


class BarsClient(Protocol):
    """Minimal protocol so forecasting/ does not import FastAPI app objects."""

    def bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]: ...


def normalize_ohlcv(frame: pd.DataFrame, *, default_symbol: str | None = None) -> pd.DataFrame:
    """Normalize a frame into DatetimeIndex + open/high/low/close/volume."""
    data = frame.copy()
    data.columns = [str(c).strip() for c in data.columns]
    rename = {
        src: dst
        for src, dst in COLUMN_ALIASES.items()
        if src in data.columns and dst not in data.columns
    }
    if rename:
        data = data.rename(columns=rename)
    # Lowercase remaining
    data = data.rename(columns={c: c.lower() for c in data.columns if c != c.lower()})

    if not isinstance(data.index, pd.DatetimeIndex):
        if "timestamp" in data.columns:
            data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
            data = data.set_index("timestamp")
        else:
            data.index = pd.to_datetime(data.index, utc=True)
    else:
        if data.index.tz is None:
            data.index = data.index.tz_localize("UTC")
        else:
            data.index = data.index.tz_convert("UTC")

    data = data.sort_index()
    if "volume" not in data.columns:
        data["volume"] = 0.0
    for col in CANONICAL_OHLCV_COLUMNS:
        if col not in data.columns and col != "volume":
            raise ValueError(f"OHLCV frame missing required column: {col}")
    out = data[list(CANONICAL_OHLCV_COLUMNS)].astype(float)
    out = out.dropna(how="any")
    if default_symbol is not None:
        out.attrs["symbol"] = default_symbol
    assert_canonical_ohlcv(out)
    return out


def load_ohlcv_csv(path: str | Path, *, ticker: str | None = None) -> pd.DataFrame:
    """Load OHLCV from CSV (compatible with kronos_backtest column norms)."""
    frame = pd.read_csv(path)
    return normalize_ohlcv(frame, default_symbol=ticker)


def bars_to_ohlcv(bars: list[dict[str, Any]], *, ticker: str | None = None) -> pd.DataFrame:
    if not bars:
        raise ValueError("no bars provided")
    frame = pd.DataFrame(bars)
    return normalize_ohlcv(frame, default_symbol=ticker)


def load_ohlcv(
    ticker: str,
    *,
    timeframe: str = "1Day",
    limit: int = 256,
    start: datetime | None = None,
    end: datetime | None = None,
    csv_path: str | Path | None = None,
    client: BarsClient | None = None,
) -> pd.DataFrame:
    """Fetch + normalize OHLCV.

    Prefer ``csv_path`` for offline/reproducible runs. Otherwise use ``client``
    (Alpaca-compatible BarsClient) or build one from env credentials.
    """
    if csv_path is not None:
        return load_ohlcv_csv(csv_path, ticker=ticker)

    bars_client = client or _default_alpaca_client()
    if bars_client is None:
        raise RuntimeError(
            "No data source: pass csv_path, client, or set ALPACA_API_KEY / ALPACA_API_SECRET"
        )
    bars = bars_client.bars(ticker.upper(), timeframe, start, end, limit)
    if len(bars) > limit:
        bars = bars[-limit:]
    return bars_to_ohlcv(bars, ticker=ticker.upper())


class _EnvAlpacaClient:
    """Thin Alpaca stock-bars client; does not import backend.app."""

    def __init__(self, key: str, secret: str, *, feed: str = "iex") -> None:
        self.key = key
        self.secret = secret
        self.feed = feed
        self._client: Any = None

    def _stock_data(self) -> Any:
        if self._client is None:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.enums import DataFeed

            self._client = StockHistoricalDataClient(self.key, self.secret)
            self._feed = getattr(DataFeed, self.feed.upper(), DataFeed.IEX)
        return self._client

    def bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None,
        end: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        from alpaca.common.enums import Sort
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        mapping = {
            "1Min": TimeFrame.Minute,
            "5Min": TimeFrame(5, TimeFrameUnit.Minute),
            "15Min": TimeFrame(15, TimeFrameUnit.Minute),
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day,
        }
        if timeframe not in mapping:
            raise ValueError(f"unsupported timeframe: {timeframe}")
        end = end or datetime.now(timezone.utc)
        if start is None:
            if timeframe == "1Day":
                history_days = max(30, limit * 2)
            elif timeframe == "1Hour":
                history_days = max(7, limit // 5)
            else:
                history_days = max(7, limit // 48)
            start = end - timedelta(days=history_days)
        self._stock_data()
        result = self._client.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=symbol.upper(),
                timeframe=mapping[timeframe],
                start=start,
                end=end,
                limit=limit,
                feed=self._feed,
                sort=Sort.DESC,
            )
        )
        data = getattr(result, "data", result)
        items = data.get(symbol.upper(), []) if isinstance(data, dict) else []
        bars: list[dict[str, Any]] = []
        for bar in items:
            ts = getattr(bar, "timestamp", None) or getattr(bar, "t", None)
            if ts is None:
                continue
            bars.append(
                {
                    "timestamp": pd.Timestamp(ts).tz_convert("UTC")
                    if getattr(pd.Timestamp(ts), "tzinfo", None)
                    else pd.Timestamp(ts, tz="UTC"),
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": float(getattr(bar, "volume", 0) or 0),
                }
            )
        return sorted(bars, key=lambda b: b["timestamp"])


def _default_alpaca_client() -> _EnvAlpacaClient | None:
    key = os.environ.get("ALPACA_API_KEY") or os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("ALPACA_API_SECRET") or os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        return None
    feed = os.environ.get("ALPACA_DATA_FEED", "iex")
    return _EnvAlpacaClient(key, secret, feed=feed)
