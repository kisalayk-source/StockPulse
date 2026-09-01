from __future__ import annotations

import json
from typing import Any

from app.sec.models import NormalizedEvent


def build_evidence_list(events: list[NormalizedEvent], score_payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for event in events:
        items.append(
            {
                "source": event.source,
                "accession_number": event.accession_number,
                "filing_date": event.filing_date.isoformat() if event.filing_date else None,
                "reporting_period": event.reporting_period.isoformat() if event.reporting_period else None,
                "event_type": event.event_type,
                "component": event.component,
                "signal_label": event.signal_label,
                "data_timestamp": event.data_timestamp.isoformat(),
                "polarity": event.polarity,
                "detail": event.metadata.get("detail") if event.metadata else None,
            }
        )
    evidence = score_payload.get("evidence", {})
    for text in evidence.get("positive", []):
        items.append(
            {
                "source": "accumulation_score",
                "event_type": "POSITIVE",
                "signal_label": text,
                "component": "summary",
            }
        )
    for text in evidence.get("negative", []):
        items.append(
            {
                "source": "accumulation_score",
                "event_type": "NEGATIVE",
                "signal_label": text,
                "component": "summary",
            }
        )
    return items


def events_to_json(events: list[NormalizedEvent]) -> str:
    return json.dumps(
        [
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "component": event.component,
                "polarity": event.polarity,
            }
            for event in events
        ]
    )
