from __future__ import annotations

from typing import Any

from app.sec.models import NormalizedEvent
from app.sec.normalization import polarity_for_institutional


def score_institutional(events: list[NormalizedEvent], config: dict[str, Any]) -> tuple[float, list[str]]:
    inst_events = [event for event in events if event.component == "institutional"]
    if not inst_events:
        return 50.0, []
    weighted = 0.0
    weight_sum = 0.0
    evidence: list[str] = []
    counts = {"increased": 0, "new": 0, "decreased": 0, "exited": 0}
    for event in inst_events:
        polarity = polarity_for_institutional(event.event_type, config)
        weight = abs(polarity) or 0.1
        weighted += polarity
        weight_sum += weight
        et = event.event_type
        if et == "INCREASED":
            counts["increased"] += 1
        elif et == "NEW_POSITION":
            counts["new"] += 1
        elif et == "DECREASED":
            counts["decreased"] += 1
        elif et == "EXITED":
            counts["exited"] += 1
    if counts["increased"]:
        evidence.append(f"+ {counts['increased']} institutions reported increased positions")
    if counts["new"]:
        evidence.append(f"+ {counts['new']} new institutional positions reported")
    if counts["decreased"]:
        evidence.append(f"- {counts['decreased']} institutions reduced positions")
    if counts["exited"]:
        evidence.append(f"- {counts['exited']} institutions exited positions")
    if weight_sum <= 0:
        return 50.0, evidence
    normalized = weighted / weight_sum
    score = 50.0 + normalized * 50.0
    return max(0.0, min(100.0, score)), evidence
