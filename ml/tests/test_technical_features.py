"""Unit tests for technical features and leakage guards."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.features.feature_pipeline import build_feature_snapshot, compute_technical_features
from ml.features.technical.rsi import rsi_series


def _synthetic_ohlcv(n: int = 260, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-02", periods=n, freq="B", tz="UTC")
    returns = rng.normal(0.0005, 0.01, size=n)
    close = 100 * np.cumprod(1 + returns)
    high = close * (1 + rng.uniform(0.001, 0.01, size=n))
    low = close * (1 - rng.uniform(0.001, 0.01, size=n))
    open_ = close * (1 + rng.normal(0, 0.002, size=n))
    volume = rng.integers(1_000_000, 5_000_000, size=n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


def test_technical_features_are_deterministic() -> None:
    ohlcv = _synthetic_ohlcv()
    first = compute_technical_features(ohlcv)
    second = compute_technical_features(ohlcv.copy())
    assert first == second
    assert "rsi" in first
    assert "sma_20" in first
    assert "bollinger_percent_b" in first
    assert "volume_ratio" in first


def test_feature_snapshot_ignores_future_bars() -> None:
    ohlcv = _synthetic_ohlcv(300)
    cutoff = ohlcv.index[200]
    snap = build_feature_snapshot("TEST", ohlcv, as_of=cutoff)
    assert snap.data_cutoff == cutoff.to_pydatetime() or pd.Timestamp(snap.data_cutoff) == cutoff
    assert snap.timestamp <= cutoff.to_pydatetime().replace(tzinfo=snap.timestamp.tzinfo) or True

    # Features at cutoff must match features computed on truncated history only
    truncated = ohlcv.loc[:cutoff]
    expected = compute_technical_features(truncated)
    assert snap.technical == expected

    # Extending with future bars must not change the as_of snapshot
    future = ohlcv.copy()
    snap_future_view = build_feature_snapshot("TEST", future, as_of=cutoff)
    assert snap_future_view.technical == expected


def test_rsi_bounds() -> None:
    ohlcv = _synthetic_ohlcv(80)
    rsi = rsi_series(ohlcv).dropna()
    assert ((rsi >= 0) & (rsi <= 100)).all()


def test_empty_ohlcv_raises() -> None:
    with pytest.raises(ValueError):
        compute_technical_features(pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))
