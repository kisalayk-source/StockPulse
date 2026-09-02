"""Average True Range."""

from __future__ import annotations

import pandas as pd

from ml.features.technical._common import last_valid, require_ohlcv


def true_range(ohlcv: pd.DataFrame) -> pd.Series:
    frame = require_ohlcv(ohlcv)
    prev_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr_series(ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = true_range(ohlcv)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean().rename("atr")


def atr_features(ohlcv: pd.DataFrame, period: int = 14) -> dict[str, float | None]:
    return {"atr": last_valid(atr_series(ohlcv, period=period))}
