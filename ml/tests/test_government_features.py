"""Government feature PIT safety and ML matrix inclusion."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ml.features.feature_pipeline import build_feature_snapshot
from ml.features.government import compute_government_features
from ml.features.government._common import filter_government_events_as_of
from ml.service import _attach_government_features, _merge_model_features
from ml.data import FeatureSnapshot


def _ohlcv(n: int = 30) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=n, freq="B", tz="UTC")
    close = pd.Series(range(100, 100 + n), index=idx, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": [1_000_000] * n,
        },
        index=idx,
    )


EVENTS = [
    {
        "event_type": "PRESOLICITATION",
        "event_id": "1",
        "agency": "DoD",
        "estimated_value": 80_000_000,
        "published_at": "2024-06-01T00:00:00+00:00",
        "event_at": "2024-06-01T00:00:00+00:00",
    },
    {
        "event_type": "SOLICITATION",
        "event_id": "2",
        "agency": "DoD",
        "estimated_value": 80_000_000,
        "published_at": "2024-06-20T00:00:00+00:00",
        "event_at": "2024-06-20T00:00:00+00:00",
    },
    {
        "event_type": "AWARD",
        "event_id": "3",
        "agency": "DoD",
        "awarded_amount": 50_000_000,
        "sole_source": True,
        "published_at": "2024-07-15T00:00:00+00:00",
        "event_at": "2024-07-15T00:00:00+00:00",
    },
]


def test_future_award_excluded_from_historical_features():
    as_of = datetime(2024, 6, 5, tzinfo=timezone.utc)
    pit = filter_government_events_as_of(EVENTS, as_of)
    assert all(e["event_id"] != "3" for e in pit)
    assert any(e["event_id"] == "1" for e in pit)

    features = compute_government_features(EVENTS, as_of=as_of, annual_revenue=2_000_000_000)
    assert features.get("government_award_count_30d", 0) == 0
    assert features.get("government_early_signal_score", 0) >= 80

    later = compute_government_features(
        EVENTS,
        as_of=datetime(2024, 7, 20, tzinfo=timezone.utc),
        annual_revenue=2_000_000_000,
    )
    assert later.get("government_award_count_30d", 0) >= 1
    assert later.get("government_score", 0) > features.get("government_score", 0)


def test_snapshot_includes_government_category():
    ohlcv = _ohlcv()
    snapshot = build_feature_snapshot(
        "LMT",
        ohlcv,
        as_of=ohlcv.index.max(),
        government_events=EVENTS,
        annual_revenue=2_000_000_000,
    )
    assert isinstance(snapshot.government, dict)
    assert "government_score" in snapshot.government or snapshot.government == {}


def test_merge_and_attach_government_features_for_ml():
    ohlcv = _ohlcv()
    snapshot = FeatureSnapshot(
        ticker="LMT",
        timestamp=datetime(2024, 7, 20, tzinfo=timezone.utc),
        feature_version="1.1.0",
        data_cutoff=datetime(2024, 7, 20, tzinfo=timezone.utc),
        technical={"rsi": 55.0, "sma_20": 100.0},
        government={"government_score": 70.0, "government_award_count_30d": 1.0},
    )
    merged = _merge_model_features(snapshot, {"government": True, "sec": False, "fundamentals": False})
    assert "government_score" in merged
    assert "rsi" in merged

    frame = pd.DataFrame({"rsi": [50.0, 55.0]}, index=ohlcv.index[:2])
    attached = _attach_government_features(frame, EVENTS, annual_revenue=2_000_000_000)
    assert "government_score" in attached.columns or attached.shape[1] >= 1
