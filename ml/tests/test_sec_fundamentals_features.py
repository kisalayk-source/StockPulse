"""Unit tests for SEC flow + Finnhub fundamental features (MVP-3/4)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.features.feature_pipeline import build_feature_snapshot
from ml.features.fundamentals import compute_fundamental_features, valuation_features
from ml.features.sec import compute_sec_features, institutional_flow_features


def _synthetic_ohlcv(n: int = 80, seed: int = 11) -> pd.DataFrame:
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


def _sec_events() -> list[dict]:
    return [
        {
            "component": "institutional",
            "event_type": "INCREASED",
            "filing_date": "2024-03-01",
            "polarity": 0.7,
            "metadata": {"manager": "Alpha"},
        },
        {
            "component": "institutional",
            "event_type": "NEW_POSITION",
            "filing_date": "2024-03-15",
            "polarity": 1.0,
            "metadata": {"manager": "Beta"},
        },
        {
            "component": "institutional",
            "event_type": "DECREASED",
            "filing_date": "2024-06-01",
            "polarity": -0.7,
            "metadata": {"manager": "Gamma"},
        },
        {
            "component": "insider",
            "event_type": "DISCRETIONARY_BUY",
            "filing_date": "2024-03-10",
            "metadata": {"insider_name": "CEO Person", "insider_title": "CEO", "value": 250_000},
        },
        {
            "component": "major_holder",
            "event_type": "OWNERSHIP_INCREASE",
            "filing_date": "2024-03-20",
            "metadata": {"ownership_pct": 0.08, "passive_flag": False},
        },
    ]


def test_institutional_flow_is_deterministic() -> None:
    events = _sec_events()
    as_of = datetime(2024, 4, 1, tzinfo=timezone.utc)
    first = institutional_flow_features(events, as_of=as_of)
    second = institutional_flow_features(events, as_of=as_of)
    assert first == second
    assert first["inst_event_count"] == 2.0
    assert first["inst_increase_count"] == 1.0
    assert first["inst_new_count"] == 1.0
    assert "inst_flow_score" in first


def test_sec_features_ignore_future_filings() -> None:
    events = _sec_events()
    as_of = datetime(2024, 4, 1, tzinfo=timezone.utc)
    features = compute_sec_features(events, as_of=as_of)
    # June decrease must not affect April as_of
    assert features["inst_event_count"] == 2.0
    assert features.get("inst_decrease_count", 0.0) == 0.0
    assert "insider_flow_score" in features
    assert "ownership_flow_score" in features

    later = compute_sec_features(events, as_of=datetime(2024, 7, 1, tzinfo=timezone.utc))
    assert later["inst_event_count"] == 3.0
    assert later["inst_decrease_count"] == 1.0


def test_empty_sec_and_fundamentals() -> None:
    as_of = datetime(2024, 4, 1, tzinfo=timezone.utc)
    assert compute_sec_features([], as_of=as_of) == {}
    assert compute_fundamental_features({}) == {}
    assert valuation_features({"pe_ratio": None, "noise": 1}) == {}


def test_fundamental_features_passthrough() -> None:
    metrics = {
        "pe_ratio": 18.5,
        "market_cap": 2e11,
        "dividend_yield": 0.012,
        "eps": 4.2,
        "revenue_growth": 0.09,
        "eps_growth": 0.11,
        "roic": 0.14,
        "fcf_margin": 0.18,
        "debt_to_equity": 0.8,
        "ignored": 99,
    }
    features = compute_fundamental_features(metrics)
    assert features["pe_ratio"] == 18.5
    assert features["revenue_growth"] == 0.09
    assert features["debt_to_equity"] == 0.8
    assert "ignored" not in features


def test_snapshot_builds_sec_and_fundamentals_from_raw_inputs() -> None:
    ohlcv = _synthetic_ohlcv(120)
    # Use a late cutoff so March SEC filings are in the past relative to as_of
    cutoff = ohlcv.index[-1]
    assert cutoff.to_pydatetime().date().isoformat() >= "2024-04-01"
    snap = build_feature_snapshot(
        "TEST",
        ohlcv,
        as_of=cutoff,
        sec_events=_sec_events(),
        fundamentals_metrics={"pe_ratio": 20.0, "revenue_growth": 0.05, "roic": 0.12},
    )
    assert snap.technical
    assert snap.sec.get("inst_event_count", 0) > 0
    assert snap.fundamentals.get("pe_ratio") == 20.0
    # Explicit ready-made dicts win over raw inputs
    snap2 = build_feature_snapshot(
        "TEST",
        ohlcv,
        as_of=cutoff,
        sec={"inst_flow_score": 70.0},
        fundamentals={"pe_ratio": 1.0},
        sec_events=_sec_events(),
        fundamentals_metrics={"pe_ratio": 99.0},
    )
    assert snap2.sec == {"inst_flow_score": 70.0}
    assert snap2.fundamentals == {"pe_ratio": 1.0}
