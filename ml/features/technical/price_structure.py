"""Price structure features (distances, breakouts, drawdown, returns, patterns)."""

from __future__ import annotations

import pandas as pd

from ml.features.technical._common import last_valid, require_ohlcv
from ml.features.technical.moving_averages import sma


def price_structure_series(ohlcv: pd.DataFrame) -> pd.DataFrame:
    frame = require_ohlcv(ohlcv)
    open_ = frame["open"]
    high = frame["high"]
    low = frame["low"]
    close = frame["close"]
    sma10 = sma(close, 10)
    sma20 = sma(close, 20)
    sma50 = sma(close, 50)
    sma200 = sma(close, 200)
    rolling_high_20 = high.rolling(20, min_periods=20).max()
    rolling_low_20 = low.rolling(20, min_periods=20).min()
    prior_high_5 = high.shift(1).rolling(5, min_periods=5).max()
    prior_low_5 = low.shift(1).rolling(5, min_periods=5).max()
    peak = close.cummax()
    drawdown = close / peak.replace(0.0, pd.NA) - 1.0
    range_20 = (rolling_high_20 - rolling_low_20).replace(0.0, pd.NA)
    bar_range = (high - low).replace(0.0, pd.NA)
    prev_open = open_.shift(1)
    prev_close = close.shift(1)
    bullish = close > open_
    bearish = close < open_
    prev_bearish = prev_close < prev_open
    prev_bullish = prev_close > prev_open
    # Candle patterns use only current + prior bar (no future leakage).
    bullish_engulfing = (
        prev_bearish
        & bullish
        & (open_ <= prev_close)
        & (close >= prev_open)
    ).astype(float)
    bearish_engulfing = (
        prev_bullish
        & bearish
        & (open_ >= prev_close)
        & (close <= prev_open)
    ).astype(float)
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
            # Pattern / regime features for directional stance (feature_version 1.2.0+)
            "sma_cross_10_20": (sma10 > sma20).astype(float),
            "sma_trend_align": ((sma10 > sma20) & (sma20 > sma50)).astype(float),
            "sma20_slope_5": sma20 / sma20.shift(5).replace(0.0, pd.NA) - 1.0,
            "higher_high_5": (high > prior_high_5).astype(float),
            "higher_low_5": (low > prior_low_5).astype(float),
            "close_location_20": (close - rolling_low_20) / range_20,
            "body_ratio": (close - open_).abs() / bar_range,
            "bullish_engulfing": bullish_engulfing,
            "bearish_engulfing": bearish_engulfing,
            "gap_return": open_ / prev_close.replace(0.0, pd.NA) - 1.0,
        },
        index=frame.index,
    )


def price_structure_features(ohlcv: pd.DataFrame) -> dict[str, float | None]:
    frame = price_structure_series(ohlcv)
    return {column: last_valid(frame[column]) for column in frame.columns}
