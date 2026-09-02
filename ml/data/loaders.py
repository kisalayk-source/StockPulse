"""Convert provider bar dicts to a canonical OHLCV DataFrame."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def bars_to_ohlcv(bars: list[dict[str, Any]], *, ascending: bool = True) -> pd.DataFrame:
    """Build a DatetimeIndex OHLCV frame from Alpaca-style bar dicts.

    Bars with timestamps after a caller's cutoff should be filtered *before*
    invoking this helper when enforcing point-in-time constraints.
    """
    if not bars:
        return pd.DataFrame(columns=list(OHLCV_COLUMNS))

    rows: list[dict[str, Any]] = []
    for bar in bars:
        ts = bar.get("timestamp")
        if ts is None:
            continue
        if isinstance(ts, str):
            ts = pd.Timestamp(ts)
        elif isinstance(ts, datetime):
            ts = pd.Timestamp(ts)
        else:
            ts = pd.Timestamp(ts)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        try:
            rows.append(
                {
                    "timestamp": ts,
                    "open": float(bar["open"]),
                    "high": float(bar["high"]),
                    "low": float(bar["low"]),
                    "close": float(bar["close"]),
                    "volume": float(bar.get("volume") or 0.0),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue

    if not rows:
        return pd.DataFrame(columns=list(OHLCV_COLUMNS))

    frame = pd.DataFrame(rows).drop_duplicates(subset=["timestamp"]).set_index("timestamp")
    frame = frame.sort_index(ascending=ascending)
    return frame[list(OHLCV_COLUMNS)]


def filter_bars_as_of(ohlcv: pd.DataFrame, as_of: pd.Timestamp | datetime | str) -> pd.DataFrame:
    """Return only rows with index <= as_of (UTC-normalized)."""
    if ohlcv.empty:
        return ohlcv
    cutoff = pd.Timestamp(as_of)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    else:
        cutoff = cutoff.tz_convert("UTC")
    return ohlcv.loc[ohlcv.index <= cutoff].copy()
