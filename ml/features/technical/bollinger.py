"""Bollinger Bands."""

from __future__ import annotations

import pandas as pd

from ml.features.technical._common import last_valid, require_ohlcv
from ml.features.technical.moving_averages import sma


def bollinger_series(
    ohlcv: pd.DataFrame,
    *,
    window: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    frame = require_ohlcv(ohlcv)
    close = frame["close"]
    middle = sma(close, window)
    std = close.rolling(window=window, min_periods=window).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    width = (upper - lower) / middle.replace(0.0, pd.NA)
    percent_b = (close - lower) / (upper - lower).replace(0.0, pd.NA)
    return pd.DataFrame(
        {
            "bollinger_middle": middle,
            "bollinger_upper": upper,
            "bollinger_lower": lower,
            "bollinger_width": width,
            "bollinger_percent_b": percent_b,
        },
        index=frame.index,
    )


def bollinger_features(ohlcv: pd.DataFrame) -> dict[str, float | None]:
    frame = bollinger_series(ohlcv)
    return {column: last_valid(frame[column]) for column in frame.columns}
