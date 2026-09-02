"""Institutional flow feature scaffold (MVP-3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def institutional_flow_features(
    events: list[dict[str, Any]],
    *,
    as_of: datetime,
) -> dict[str, float]:
    """Only events with published_at <= as_of will be used when implemented."""
    _ = events, as_of
    return {}
