"""Shared forecast input/output schemas.

Every adapter must squeeze its native I/O into these types so ensemble,
eval, and API layers never special-case a model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

CANONICAL_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
# Adapters may omit open/high/low/volume for univariate models; close is required.
PREDICTED_REQUIRED_COLUMNS = ("close",)


@dataclass
class ForecastInput:
    ticker: str
    ohlcv: pd.DataFrame  # DatetimeIndex; columns open/high/low/close/volume
    horizon: int  # number of future bars to predict
    context_len: int | None = None  # adapter default if None
    timeframe: str = "1Day"  # used for future timestamp synthesis


@dataclass
class ForecastResult:
    model_name: str
    ticker: str
    predicted: pd.DataFrame  # at least ``close``; length == horizon
    quantiles: dict[float, pd.DataFrame] | None = None
    latency_ms: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


def assert_forecast_result(result: ForecastResult, *, horizon: int | None = None) -> None:
    """Raise AssertionError if ``result`` does not conform to the contract."""
    if not isinstance(result, ForecastResult):
        raise AssertionError(f"expected ForecastResult, got {type(result)!r}")
    if not result.model_name:
        raise AssertionError("model_name must be non-empty")
    if not result.ticker:
        raise AssertionError("ticker must be non-empty")
    if not isinstance(result.predicted, pd.DataFrame):
        raise AssertionError("predicted must be a DataFrame")
    if result.predicted.empty:
        raise AssertionError("predicted must not be empty")
    missing = [col for col in PREDICTED_REQUIRED_COLUMNS if col not in result.predicted.columns]
    if missing:
        raise AssertionError(f"predicted missing required columns: {missing}")
    expected = horizon if horizon is not None else len(result.predicted)
    if len(result.predicted) != expected:
        raise AssertionError(
            f"predicted length {len(result.predicted)} != expected horizon {expected}"
        )
    if result.latency_ms < 0:
        raise AssertionError("latency_ms must be >= 0")
    if result.quantiles is not None:
        if not isinstance(result.quantiles, dict):
            raise AssertionError("quantiles must be a dict or None")
        for q, frame in result.quantiles.items():
            if not isinstance(frame, pd.DataFrame):
                raise AssertionError(f"quantile {q} value must be a DataFrame")
            if "close" not in frame.columns:
                raise AssertionError(f"quantile {q} frame missing close")
            if len(frame) != len(result.predicted):
                raise AssertionError(f"quantile {q} length mismatch")
    if not isinstance(result.meta, dict):
        raise AssertionError("meta must be a dict")


def assert_canonical_ohlcv(ohlcv: pd.DataFrame) -> None:
    """Validate OHLCV frame used as ForecastInput.ohlcv."""
    if not isinstance(ohlcv, pd.DataFrame):
        raise AssertionError("ohlcv must be a DataFrame")
    if ohlcv.empty:
        raise AssertionError("ohlcv must not be empty")
    if not isinstance(ohlcv.index, pd.DatetimeIndex):
        raise AssertionError("ohlcv must have a DatetimeIndex")
    missing = [col for col in CANONICAL_OHLCV_COLUMNS if col not in ohlcv.columns]
    if missing:
        raise AssertionError(f"ohlcv missing columns: {missing}")
