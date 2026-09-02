"""Rolling volatility features."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml.features.technical._common import last_valid, require_ohlcv


def volatility_series(ohlcv: pd.DataFrame, window: int = 20) -> pd.Series:
    frame = require_ohlcv(ohlcv)
    returns = frame["close"].pct_change()
    return returns.rolling(window=window, min_periods=window).std(ddof=0).rename("rolling_volatility")


def volatility_features(ohlcv: pd.DataFrame, window: int = 20) -> dict[str, float | None]:
    series = volatility_series(ohlcv, window=window)
    value = last_valid(series)
    return {"rolling_volatility": value, "rolling_volatility_annualized": None if value is None else float(value * np.sqrt(252))}
