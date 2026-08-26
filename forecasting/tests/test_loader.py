"""Data loader tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from forecasting.core.schema import assert_canonical_ohlcv
from forecasting.data.loader import bars_to_ohlcv, load_ohlcv_csv, normalize_ohlcv

FIXTURE = Path(__file__).parent / "fixtures" / "sample_ohlcv.csv"


def test_load_ohlcv_csv_canonical():
    frame = load_ohlcv_csv(FIXTURE, ticker="TEST")
    assert_canonical_ohlcv(frame)
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert frame.index.tz is not None
    assert len(frame) > 50
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]


def test_normalize_adds_volume():
    raw = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=5, freq="D"),
            "open": [1, 2, 3, 4, 5],
            "high": [2, 3, 4, 5, 6],
            "low": [0.5, 1.5, 2.5, 3.5, 4.5],
            "close": [1.5, 2.5, 3.5, 4.5, 5.5],
        }
    )
    frame = normalize_ohlcv(raw)
    assert (frame["volume"] == 0.0).all()


def test_bars_to_ohlcv():
    bars = [
        {
            "timestamp": "2024-01-02T00:00:00Z",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 100,
        },
        {
            "timestamp": "2024-01-03T00:00:00Z",
            "open": 1.5,
            "high": 2.5,
            "low": 1.0,
            "close": 2.0,
            "volume": 110,
        },
    ]
    frame = bars_to_ohlcv(bars, ticker="AAA")
    assert_canonical_ohlcv(frame)
    assert len(frame) == 2


def test_normalize_rejects_missing_close():
    raw = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=3, freq="D"),
            "open": [1, 2, 3],
            "high": [2, 3, 4],
            "low": [0.5, 1, 2],
            "volume": [1, 1, 1],
        }
    )
    with pytest.raises(ValueError, match="close"):
        normalize_ohlcv(raw)
