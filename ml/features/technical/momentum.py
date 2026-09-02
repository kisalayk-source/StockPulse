"""Momentum / ROC features."""

from __future__ import annotations

import pandas as pd

from ml.features.technical._common import last_valid, require_ohlcv


def momentum_series(ohlcv: pd.DataFrame, period: int = 10) -> pd.DataFrame:
    frame = require_ohlcv(ohlcv)
    close = frame["close"]
    momentum = close - close.shift(period)
    roc = close.pct_change(periods=period)
    return pd.DataFrame({"momentum": momentum, "roc": roc}, index=frame.index)


def momentum_features(ohlcv: pd.DataFrame, period: int = 10) -> dict[str, float | None]:
    frame = momentum_series(ohlcv, period=period)
    return {
        "momentum": last_valid(frame["momentum"]),
        "roc": last_valid(frame["roc"]),
    }
