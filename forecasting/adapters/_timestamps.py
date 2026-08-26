"""Future timestamp synthesis for path forecasts (session-aware)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd


def future_timestamps(
    last: datetime | pd.Timestamp,
    timeframe: str,
    count: int,
) -> pd.DatetimeIndex:
    """Synthesize ``count`` future bar timestamps after ``last``.

    For US equity sessions: skip weekends; for intraday, roll to next RTH open
    after the 16:00 ET close.
    """
    if isinstance(last, pd.Timestamp):
        last_dt = last.to_pydatetime()
    else:
        last_dt = last
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    eastern = last_dt.astimezone(ZoneInfo("America/New_York"))
    result: list[datetime] = []
    if timeframe == "1Day":
        cursor = eastern
        while len(result) < count:
            cursor += timedelta(days=1)
            if cursor.weekday() < 5:
                result.append(cursor)
    else:
        minutes = {"1Min": 1, "5Min": 5, "15Min": 15, "1Hour": 60}.get(timeframe)
        if minutes is None:
            # Fall back to median-step style using daily calendar
            cursor = eastern
            while len(result) < count:
                cursor += timedelta(days=1)
                if cursor.weekday() < 5:
                    result.append(cursor)
        else:
            cursor = eastern
            close_t = datetime.strptime("16:00", "%H:%M").time()
            open_t = datetime.strptime("09:30", "%H:%M").time()
            while len(result) < count:
                cursor += timedelta(minutes=minutes)
                if cursor.weekday() >= 5 or cursor.time() >= close_t:
                    cursor = (cursor + timedelta(days=1)).replace(
                        hour=9, minute=30, second=0, microsecond=0
                    )
                    while cursor.weekday() >= 5:
                        cursor += timedelta(days=1)
                if cursor.time() >= open_t:
                    result.append(cursor)
    return pd.DatetimeIndex(result)


def infer_step_timestamps(
    history_index: pd.DatetimeIndex,
    count: int,
) -> pd.DatetimeIndex:
    """Fallback when timeframe is unknown: median bar spacing from history."""
    if len(history_index) < 2:
        step = pd.Timedelta(days=1)
        last = history_index[-1] if len(history_index) else pd.Timestamp.utcnow()
    else:
        inferred = pd.Series(history_index).diff().median()
        step = inferred if pd.notna(inferred) and inferred > pd.Timedelta(0) else pd.Timedelta(days=1)
        last = history_index[-1]
    return pd.DatetimeIndex([last + step * (i + 1) for i in range(count)])
