"""Price structure features (distances, breakouts, drawdown, returns)."""

from __future__ import annotations

import pandas as pd

from ml.features.technical._common import last_valid, require_ohlcv
from ml.features.technical.moving_averages import sma


def price_structure_series(ohlcv: pd.DataFrame) -> pd.DataFrame:
    frame = require_ohlcv(ohlcv)
    close = frame["close"]
    sma20 = sma(close, 20)
    sma50 = sma(close, 50)
    sma200 = sma(close, 200)
    rolling_high_20 = frame["high"].rolling(20, min_periods=20).max()
    rolling_low_20 = frame["low"].rolling(20, min_periods=20).min()
    peak = close.cummax()
    drawdown = close / peak.replace(0.0, pd.NA) - 1.0
    return pd.DataFrame(
        {
            "distance_from_sma20": close / sma20.replace(0.0, pd.NA) - 1.0,
            "distance_from_sma50": close / sma50.replace(0.0, pd.NA) - 1.0,
            "distance_from_sma200": close / sma200.replace(0.0, pd.NA) - 1.0,
            "high_breakout_20": (close >= rolling_high_20).astype(float),
            "low_breakout_20": (close <= rolling_low_20).astype(float),
            "drawdown": drawdown,
            "return_1d": close.pct_change(1),
            "return_5d": close.pct_change(5),
            "return_20d": close.pct_change(20),
        },
        index=frame.index,
    )


def price_structure_features(ohlcv: pd.DataFrame) -> dict[str, float | None]:
    frame = price_structure_series(ohlcv)
    return {column: last_valid(frame[column]) for column in frame.columns}
