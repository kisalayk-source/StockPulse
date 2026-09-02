"""Moving averages (SMA / EMA)."""

from __future__ import annotations

import pandas as pd

from ml.features.technical._common import last_valid, require_ohlcv


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def moving_average_features(ohlcv: pd.DataFrame) -> dict[str, float | None]:
    frame = require_ohlcv(ohlcv)
    close = frame["close"]
    features: dict[str, float | None] = {}
    for window in (10, 20, 50, 100, 200):
        features[f"sma_{window}"] = last_valid(sma(close, window))
    for window in (10, 20, 50, 200):
        features[f"ema_{window}"] = last_valid(ema(close, window))
    return features


def moving_average_series(ohlcv: pd.DataFrame) -> pd.DataFrame:
    frame = require_ohlcv(ohlcv)
    close = frame["close"]
    data: dict[str, pd.Series] = {}
    for window in (10, 20, 50, 100, 200):
        data[f"sma_{window}"] = sma(close, window)
    for window in (10, 20, 50, 200):
        data[f"ema_{window}"] = ema(close, window)
    return pd.DataFrame(data, index=frame.index)
