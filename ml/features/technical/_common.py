"""Shared helpers for technical indicators."""

from __future__ import annotations

import pandas as pd


def require_ohlcv(ohlcv: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(ohlcv.columns)
    if missing:
        raise ValueError(f"ohlcv missing columns: {sorted(missing)}")
    if ohlcv.empty:
        raise ValueError("ohlcv is empty")
    return ohlcv.sort_index()


def last_valid(series: pd.Series) -> float | None:
    if series.empty:
        return None
    value = series.iloc[-1]
    if pd.isna(value):
        return None
    return float(value)
