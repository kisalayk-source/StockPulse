from __future__ import annotations

from typing import Any

from app.sec.models import NormalizedEvent


def score_major_holder(events: list[NormalizedEvent], config: dict[str, Any]) -> tuple[float, list[str]]:
    holder_events = [event for event in events if event.component == "major_holder"]
    if not holder_events:
        return 50.0, []
    score = 50.0
    evidence: list[str] = []
    thresholds = config.get("major_holder_thresholds", [0.05, 0.10, 0.20])
    for event in holder_events:
        meta = event.metadata or {}
        passive = bool(meta.get("passive_flag"))
        style = "passive beneficial ownership" if passive else "activist-style filing"
        if event.event_type in {"NEW_MAJOR_HOLDER", "OWNERSHIP_INCREASE"}:
            score += 12.0 if not passive else 6.0
            evidence.append(f"+ Beneficial ownership increased ({style})")
        elif event.event_type in {"OWNERSHIP_DECREASE", "OWNERSHIP_EXIT"}:
            score -= 12.0 if not passive else 6.0
            evidence.append(f"- Beneficial ownership decreased ({style})")
        pct = meta.get("ownership_pct")
        if pct is not None:
            for threshold in thresholds:
                if abs(float(pct) - threshold) < 0.005:
                    evidence.append(f"  Ownership near {threshold * 100:.0f}% threshold")
    return max(0.0, min(100.0, score)), evidence
