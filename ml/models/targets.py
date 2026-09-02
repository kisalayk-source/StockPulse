"""Label construction for directional classification."""

from __future__ import annotations

import pandas as pd


def add_forward_return_target(
    ohlcv: pd.DataFrame,
    features: pd.DataFrame,
    *,
    horizon_bars: int,
    threshold: float = 0.0,
) -> pd.DataFrame:
    """Attach binary target: 1 if forward return >= threshold else 0.

    Drops the final ``horizon_bars`` rows (no future return available) and rows
    with incomplete features.
    """
    if horizon_bars < 1:
        raise ValueError("horizon_bars must be >= 1")
    close = ohlcv["close"].reindex(features.index)
    future = close.shift(-horizon_bars)
    forward_return = future / close - 1.0
    frame = features.copy()
    frame["forward_return"] = forward_return
    frame["target"] = (forward_return >= threshold).astype(int)
    usable = frame.dropna()
    # Ensure we never keep rows whose forward window extends past available data
    if len(ohlcv) > horizon_bars:
        last_valid_index = ohlcv.index[-(horizon_bars + 1)]
        usable = usable.loc[usable.index <= last_valid_index]
    return usable
