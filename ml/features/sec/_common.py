"""Shared helpers for PIT-safe SEC event feature builders."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def as_of_date(as_of: datetime | date) -> date:
    if isinstance(as_of, datetime):
        ts = as_of
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc).date()
    return as_of


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return as_of_date(value)
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def event_available_date(event: dict[str, Any]) -> date | None:
    """Publication date used for point-in-time filtering (filing first)."""
    for key in ("filing_date", "published_at", "reporting_period"):
        parsed = _parse_date(event.get(key))
        if parsed is not None:
            return parsed
    return None


def filter_events_as_of(
    events: list[dict[str, Any]],
    as_of: datetime | date,
    *,
    component: str | None = None,
) -> list[dict[str, Any]]:
    """Keep events with publication date <= as_of (and optional component)."""
    cutoff = as_of_date(as_of)
    out: list[dict[str, Any]] = []
    for event in events:
        if component is not None and str(event.get("component") or "") != component:
            continue
        available = event_available_date(event)
        if available is None or available > cutoff:
            continue
        out.append(event)
    return out


def to_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return number
