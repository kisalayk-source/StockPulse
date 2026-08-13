"""Look-ahead bias detection for market data, labels, and corporate actions."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from kronos_backtest.exceptions import LookAheadBiasError
from kronos_backtest.types import (
    CORPORATE_ACTION_COLUMNS,
    FUTURE_SENSITIVE_COLUMNS,
    PRICE_COLUMNS,
    RETURN_COLUMNS,
    VOLUME_COLUMNS,
)


def to_timestamp(value: pd.Timestamp | str) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("UTC").tz_localize(None)
    return stamp


def timestamps_of(frame: pd.DataFrame) -> pd.DatetimeIndex:
    if "timestamp" in frame.columns:
        stamps = pd.DatetimeIndex(pd.to_datetime(frame["timestamp"]))
    else:
        stamps = pd.DatetimeIndex(pd.to_datetime(frame.index))
    if stamps.tz is not None:
        stamps = stamps.tz_convert("UTC").tz_localize(None)
    return stamps


def _future_mask(stamps: pd.DatetimeIndex, current: pd.Timestamp) -> pd.Series:
    current = to_timestamp(current)
    return pd.Series(stamps > current, index=stamps)


def _describe_columns(frame: pd.DataFrame, names: Iterable[str]) -> str:
    present = [name for name in names if name in frame.columns]
    return ", ".join(present) if present else "indexed rows"


def assert_no_lookahead(
    frame: pd.DataFrame,
    current_timestamp: pd.Timestamp | str,
    *,
    columns: Iterable[str] | None = None,
    kind: str = "market data",
) -> None:
    """Reject any row whose timestamp is strictly after ``current_timestamp``.

    All columns on a future row are treated as leaked information, including
    OHLC, volume, returns, indicators, labels, and corporate actions.
    """
    if frame.empty:
        return
    current = to_timestamp(current_timestamp)
    stamps = timestamps_of(frame)
    if stamps.max() <= current:
        return
    future = frame.loc[stamps > current]
    inspected = list(columns) if columns is not None else list(frame.columns)
    leaked = [name for name in inspected if name in future.columns]
    sample = stamps[stamps > current].min()
    raise LookAheadBiasError(
        f"Look-ahead bias detected in {kind}: timestamp {sample} is after "
        f"{current}. Leaked fields: {_describe_columns(future, leaked) or 'timestamp'}."
    )


def assert_ohlc_not_in_future(frame: pd.DataFrame, current_timestamp: pd.Timestamp | str) -> None:
    assert_no_lookahead(frame, current_timestamp, columns=PRICE_COLUMNS, kind="OHLC")


def assert_volume_not_in_future(frame: pd.DataFrame, current_timestamp: pd.Timestamp | str) -> None:
    assert_no_lookahead(frame, current_timestamp, columns=VOLUME_COLUMNS, kind="volume")


def assert_returns_not_in_future(frame: pd.DataFrame, current_timestamp: pd.Timestamp | str) -> None:
    assert_no_lookahead(frame, current_timestamp, columns=RETURN_COLUMNS, kind="returns/labels")


def assert_indicators_not_in_future(frame: pd.DataFrame, current_timestamp: pd.Timestamp | str) -> None:
    reserved = set(FUTURE_SENSITIVE_COLUMNS) | {"timestamp", "symbol"}
    indicator_cols = [name for name in frame.columns if name not in reserved]
    assert_no_lookahead(frame, current_timestamp, columns=indicator_cols, kind="indicators")


def assert_corporate_actions_not_in_future(
    frame: pd.DataFrame, current_timestamp: pd.Timestamp | str
) -> None:
    assert_no_lookahead(
        frame,
        current_timestamp,
        columns=CORPORATE_ACTION_COLUMNS,
        kind="corporate actions",
    )


def assert_training_does_not_contain_test(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    embargo_bars: int = 0,
) -> None:
    """Training data must end before the test period begins."""
    if train.empty or test.empty:
        return
    train_stamps = timestamps_of(train)
    test_stamps = timestamps_of(test)
    test_start = test_stamps.min()
    cutoff = test_start
    if embargo_bars:
        ordered = train_stamps.sort_values()
        cutoff_candidates = ordered[ordered < test_start]
        if len(cutoff_candidates) >= embargo_bars:
            cutoff = cutoff_candidates[-(embargo_bars)]
        else:
            cutoff = test_start
    if train_stamps.max() >= cutoff:
        raise LookAheadBiasError(
            f"Training data leaks into the test period: train max {train_stamps.max()} "
            f">= test start {test_start} (cutoff {cutoff})."
        )


def validate_context(
    frame: pd.DataFrame,
    current_timestamp: pd.Timestamp | str,
    *,
    corporate_actions: pd.DataFrame | None = None,
) -> None:
    """Full context gate used before Kronos prediction and fine-tuning."""
    assert_ohlc_not_in_future(frame, current_timestamp)
    assert_volume_not_in_future(frame, current_timestamp)
    assert_returns_not_in_future(frame, current_timestamp)
    assert_indicators_not_in_future(frame, current_timestamp)
    assert_corporate_actions_not_in_future(frame, current_timestamp)
    if corporate_actions is not None and not corporate_actions.empty:
        assert_corporate_actions_not_in_future(corporate_actions, current_timestamp)


def validate_sorted_ohlcv(frame: pd.DataFrame) -> None:
    if frame.empty:
        raise LookAheadBiasError("Market data is empty")
    required = {"open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise LookAheadBiasError(f"Market data missing columns: {sorted(missing)}")
    stamps = timestamps_of(frame)
    if stamps.has_duplicates:
        raise LookAheadBiasError("Market data contains duplicate timestamps")
    if not stamps.is_monotonic_increasing:
        raise LookAheadBiasError("Market data must be sorted chronologically")
