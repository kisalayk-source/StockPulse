"""Major-holder (13D/13G) ownership features — PIT-safe (MVP-3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ml.features.feature_schema import normalize_feature_dict
from ml.features.sec._common import filter_events_as_of, to_float

_INCREASE = {"NEW_MAJOR_HOLDER", "OWNERSHIP_INCREASE"}
_DECREASE = {"OWNERSHIP_DECREASE", "OWNERSHIP_EXIT"}


def ownership_features(
    events: list[dict[str, Any]],
    *,
    as_of: datetime,
) -> dict[str, float]:
    """Only events with filing_date / published_at <= as_of are used."""
    pit = filter_events_as_of(events, as_of, component="major_holder")
    if not pit:
        return {}

    score = 50.0
    increases = 0
    decreases = 0
    max_ownership_pct = 0.0
    activist_increase = 0.0

    for event in pit:
        et = str(event.get("event_type") or "")
        meta = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
        passive = bool(meta.get("passive_flag"))
        pct = to_float(meta.get("ownership_pct"))
        if pct is not None:
            max_ownership_pct = max(max_ownership_pct, pct)
        if et in _INCREASE:
            increases += 1
            score += 12.0 if not passive else 6.0
            if not passive:
                activist_increase = 1.0
        elif et in _DECREASE:
            decreases += 1
            score -= 12.0 if not passive else 6.0

    return normalize_feature_dict(
        {
            "ownership_event_count": float(len(pit)),
            "ownership_increase_count": float(increases),
            "ownership_decrease_count": float(decreases),
            "ownership_max_pct": max_ownership_pct,
            "ownership_activist_increase": activist_increase,
            "ownership_flow_score": max(0.0, min(100.0, score)),
        }
    )
