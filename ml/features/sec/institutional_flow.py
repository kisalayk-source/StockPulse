"""Institutional (13F) flow features — PIT-safe (MVP-3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ml.features.feature_schema import normalize_feature_dict
from ml.features.sec._common import filter_events_as_of, to_float

# Mirrors backend/app/sec/normalization.INSTITUTIONAL_CLASSIFICATIONS
_INST_POLARITY: dict[str, float] = {
    "NEW_POSITION": 1.0,
    "INCREASED": 0.7,
    "UNCHANGED": 0.0,
    "DECREASED": -0.7,
    "EXITED": -1.0,
}


def institutional_flow_features(
    events: list[dict[str, Any]],
    *,
    as_of: datetime,
) -> dict[str, float]:
    """Only events with filing_date / published_at <= as_of are used."""
    pit = filter_events_as_of(events, as_of, component="institutional")
    if not pit:
        return {}

    counts = {"increased": 0, "new": 0, "decreased": 0, "exited": 0, "unchanged": 0}
    weighted = 0.0
    weight_sum = 0.0
    for event in pit:
        et = str(event.get("event_type") or "")
        polarity = to_float(event.get("polarity"))
        if polarity is None:
            polarity = _INST_POLARITY.get(et, 0.0)
        weight = abs(polarity) or 0.1
        weighted += polarity
        weight_sum += weight
        if et == "INCREASED":
            counts["increased"] += 1
        elif et == "NEW_POSITION":
            counts["new"] += 1
        elif et == "DECREASED":
            counts["decreased"] += 1
        elif et == "EXITED":
            counts["exited"] += 1
        else:
            counts["unchanged"] += 1

    net_polarity = weighted / weight_sum if weight_sum > 0 else 0.0
    flow_score = max(0.0, min(100.0, 50.0 + net_polarity * 50.0))
    return normalize_feature_dict(
        {
            "inst_event_count": float(len(pit)),
            "inst_net_polarity": net_polarity,
            "inst_increase_count": float(counts["increased"]),
            "inst_decrease_count": float(counts["decreased"]),
            "inst_new_count": float(counts["new"]),
            "inst_exit_count": float(counts["exited"]),
            "inst_flow_score": flow_score,
        }
    )
