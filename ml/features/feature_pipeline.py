"""Deterministic feature pipeline and immutable snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pandas as pd

from ml import FEATURE_VERSION
from ml.data import FeatureSnapshot
from ml.data.loaders import filter_bars_as_of
from ml.features.feature_schema import normalize_feature_dict
from ml.features.technical import (
    atr_features,
    atr_series,
    bollinger_features,
    bollinger_series,
    macd_features,
    macd_series,
    momentum_features,
    momentum_series,
    moving_average_features,
    moving_average_series,
    price_structure_features,
    price_structure_series,
    rsi_features,
    rsi_series,
    volatility_features,
    volatility_series,
    volume_features,
    volume_series,
)


def compute_technical_frame(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Row-wise technical feature matrix aligned to ``ohlcv`` index."""
    parts = [
        moving_average_series(ohlcv),
        rsi_series(ohlcv).to_frame(),
        macd_series(ohlcv),
        momentum_series(ohlcv),
        atr_series(ohlcv).to_frame(),
        bollinger_series(ohlcv),
        volatility_series(ohlcv).to_frame(),
        volume_series(ohlcv),
        price_structure_series(ohlcv),
    ]
    # annualized vol derived from rolling vol column
    frame = pd.concat(parts, axis=1)
    if "rolling_volatility" in frame.columns:
        frame["rolling_volatility_annualized"] = frame["rolling_volatility"] * (252**0.5)
    return frame


def compute_technical_features(ohlcv: pd.DataFrame) -> dict[str, float]:
    """Latest technical feature vector (deterministic for identical OHLCV)."""
    values: dict[str, float | None] = {}
    values.update(moving_average_features(ohlcv))
    values.update(rsi_features(ohlcv))
    values.update(macd_features(ohlcv))
    values.update(momentum_features(ohlcv))
    values.update(atr_features(ohlcv))
    values.update(bollinger_features(ohlcv))
    values.update(volatility_features(ohlcv))
    values.update(volume_features(ohlcv))
    values.update(price_structure_features(ohlcv))
    return normalize_feature_dict(values)


def build_feature_snapshot(
    ticker: str,
    ohlcv: pd.DataFrame,
    *,
    as_of: datetime | pd.Timestamp | str | None = None,
    sec: dict[str, float] | None = None,
    fundamentals: dict[str, float] | None = None,
    market_regime: dict[str, Any] | None = None,
    feature_version: str = FEATURE_VERSION,
) -> FeatureSnapshot:
    """Build an immutable feature snapshot using only data available at ``as_of``."""
    if ohlcv.empty:
        raise ValueError("cannot build feature snapshot from empty ohlcv")

    if as_of is None:
        cutoff = ohlcv.index.max()
    else:
        cutoff = pd.Timestamp(as_of)
        if cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize("UTC")
        else:
            cutoff = cutoff.tz_convert("UTC")

    point_in_time = filter_bars_as_of(ohlcv, cutoff)
    if point_in_time.empty:
        raise ValueError(f"no bars available at or before {cutoff.isoformat()}")

    technical = compute_technical_features(point_in_time)
    ts = point_in_time.index.max().to_pydatetime()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    return FeatureSnapshot(
        ticker=ticker.upper(),
        timestamp=ts,
        feature_version=feature_version,
        data_cutoff=ts,
        technical=technical,
        sec=dict(sec or {}),
        fundamentals=dict(fundamentals or {}),
        market_regime=dict(market_regime or {}),
        snapshot_id=uuid4().hex,
    )
