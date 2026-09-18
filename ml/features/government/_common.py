"""Point-in-time helpers for government event features."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def as_of_datetime(as_of: datetime | date) -> datetime:
    if isinstance(as_of, datetime):
        ts = as_of
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    return datetime(as_of.year, as_of.month, as_of.day, tzinfo=timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        try:
            d = date.fromisoformat(text[:10])
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        except ValueError:
            return None


def filter_government_events_as_of(
    events: list[dict[str, Any]],
    as_of: datetime | date,
) -> list[dict[str, Any]]:
    """Keep events with event_at <= as_of AND published_at <= as_of (when present).

    Requires at least one of event_at / published_at. Future awards must not leak.
    """
    cutoff = as_of_datetime(as_of)
    out: list[dict[str, Any]] = []
    for event in events:
        event_at = _parse_dt(event.get("event_at"))
        published_at = _parse_dt(event.get("published_at"))
        if event_at is None and published_at is None:
            continue
        if event_at is not None and event_at > cutoff:
            continue
        if published_at is not None and published_at > cutoff:
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
    if number != number:
        return default
    return number
