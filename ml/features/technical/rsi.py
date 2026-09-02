"""Relative Strength Index."""

from __future__ import annotations

import pandas as pd

from ml.features.technical._common import last_valid, require_ohlcv


def rsi_series(ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
    frame = require_ohlcv(ohlcv)
    delta = frame["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, pd.NA)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(avg_loss != 0.0, 100.0)
    rsi = rsi.where(avg_gain != 0.0, 0.0)
    return rsi.rename("rsi")


def rsi_features(ohlcv: pd.DataFrame, period: int = 14) -> dict[str, float | None]:
    return {"rsi": last_valid(rsi_series(ohlcv, period=period))}
