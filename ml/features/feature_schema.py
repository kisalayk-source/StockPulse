"""Feature schema and versioning."""

from __future__ import annotations

from ml import FEATURE_VERSION

FEATURE_SCHEMA_VERSION = FEATURE_VERSION

TECHNICAL_FEATURE_KEYS = (
    "sma_10",
    "sma_20",
    "sma_50",
    "sma_100",
    "sma_200",
    "ema_10",
    "ema_20",
    "ema_50",
    "ema_200",
    "rsi",
    "macd",
    "macd_signal",
    "macd_histogram",
    "roc",
    "momentum",
    "atr",
    "bollinger_upper",
    "bollinger_middle",
    "bollinger_lower",
    "bollinger_width",
    "bollinger_percent_b",
    "rolling_volatility",
    "rolling_volatility_annualized",
    "volume_sma",
    "volume_ratio",
    "volume_acceleration",
    "obv",
    "price_volume_corr",
    "distance_from_sma20",
    "distance_from_sma50",
    "distance_from_sma200",
    "high_breakout_20",
    "low_breakout_20",
    "drawdown",
    "return_1d",
    "return_5d",
    "return_20d",
)


def normalize_feature_dict(values: dict[str, float | None]) -> dict[str, float]:
    """Drop nulls and coerce to float for model input / snapshot storage."""
    out: dict[str, float] = {}
    for key, value in values.items():
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number != number:  # NaN
            continue
        out[key] = number
    return out
