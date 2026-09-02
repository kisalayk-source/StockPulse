"""Insider flow feature scaffold (MVP-3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def insider_flow_features(
    events: list[dict[str, Any]],
    *,
    as_of: datetime,
) -> dict[str, float]:
    _ = events, as_of
    return {}
