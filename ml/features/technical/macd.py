"""MACD features."""

from __future__ import annotations

import pandas as pd

from ml.features.technical._common import last_valid, require_ohlcv
from ml.features.technical.moving_averages import ema


def macd_series(
    ohlcv: pd.DataFrame,
    *,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    frame = require_ohlcv(ohlcv)
    close = frame["close"]
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    histogram = macd_line - signal_line
    return pd.DataFrame(
        {"macd": macd_line, "macd_signal": signal_line, "macd_histogram": histogram},
        index=frame.index,
    )


def macd_features(ohlcv: pd.DataFrame) -> dict[str, float | None]:
    frame = macd_series(ohlcv)
    return {
        "macd": last_valid(frame["macd"]),
        "macd_signal": last_valid(frame["macd_signal"]),
        "macd_histogram": last_valid(frame["macd_histogram"]),
    }
