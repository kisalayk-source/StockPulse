"""Volume features."""

from __future__ import annotations

import pandas as pd

from ml.features.technical._common import last_valid, require_ohlcv
from ml.features.technical.moving_averages import sma


def volume_series(ohlcv: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    frame = require_ohlcv(ohlcv)
    volume = frame["volume"]
    volume_sma = sma(volume, window)
    volume_ratio = volume / volume_sma.replace(0.0, pd.NA)
    volume_accel = volume.pct_change()
    direction = frame["close"].diff().fillna(0.0).apply(lambda x: 1.0 if x >= 0 else -1.0)
    obv = (direction * volume).cumsum()
    pv_corr = frame["close"].pct_change().rolling(window=window, min_periods=window).corr(
        volume.pct_change()
    )
    return pd.DataFrame(
        {
            "volume_sma": volume_sma,
            "volume_ratio": volume_ratio,
            "volume_acceleration": volume_accel,
            "obv": obv,
            "price_volume_corr": pv_corr,
        },
        index=frame.index,
    )


def volume_features(ohlcv: pd.DataFrame, window: int = 20) -> dict[str, float | None]:
    frame = volume_series(ohlcv, window=window)
    return {column: last_valid(frame[column]) for column in frame.columns}
