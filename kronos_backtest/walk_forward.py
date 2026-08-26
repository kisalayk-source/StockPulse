"""Walk-forward fold generation. Financial series are never shuffled."""

from __future__ import annotations

from dataclasses import dataclass
import re

import pandas as pd

from kronos_backtest.config import WalkForwardConfig
from kronos_backtest.data.validator import assert_training_does_not_contain_test
from kronos_backtest.exceptions import ConfigurationError, LookAheadBiasError


_PERIOD = re.compile(r"^\s*(\d+)\s*([ymwd]|bars?|b)?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    train_index: pd.DatetimeIndex
    test_index: pd.DatetimeIndex
    mode: str

    def validate(self, train_frame: pd.DataFrame, test_frame: pd.DataFrame, embargo_bars: int = 0) -> None:
        if not self.train_index.is_monotonic_increasing or not self.test_index.is_monotonic_increasing:
            raise LookAheadBiasError("Walk-forward indices must stay chronological")
        if len(self.train_index) and len(self.test_index) and self.train_index.max() >= self.test_index.min():
            raise LookAheadBiasError(
                f"Fold {self.fold_id} overlaps: train max {self.train_index.max()} "
                f">= test min {self.test_index.min()}"
            )
        assert_training_does_not_contain_test(train_frame, test_frame, embargo_bars=embargo_bars)


def parse_period(value: str | int, index: pd.DatetimeIndex) -> tuple[str, int] | pd.DateOffset:
    """Return either ('bars', n) or a DateOffset."""
    if isinstance(value, int):
        return ("bars", value)
    text = str(value).strip()
    match = _PERIOD.match(text)
    if not match:
        raise ConfigurationError(f"Unrecognized period: {value!r}")
    count = int(match.group(1))
    unit = (match.group(2) or "b").lower()
    if unit in {"b", "bar", "bars"}:
        return ("bars", count)
    mapping = {"y": "years", "m": "months", "w": "weeks", "d": "days"}
    return pd.DateOffset(**{mapping[unit]: count})


def _end_exclusive(index: pd.DatetimeIndex, start: pd.Timestamp, period: tuple[str, int] | pd.DateOffset) -> pd.Timestamp:
    """First timestamp not included in [start, start+period)."""
    if isinstance(period, tuple):
        _, bars = period
        positions = index.get_indexer([start], method="bfill")
        loc = int(positions[0])
        if loc < 0:
            loc = 0
        end_loc = loc + bars
        if end_loc >= len(index):
            return index[-1] + pd.Timedelta(nanoseconds=1)
        return pd.Timestamp(index[end_loc])
    target = pd.Timestamp(start) + period
    return pd.Timestamp(target)


class WalkForwardEngine:
    def __init__(self, config: WalkForwardConfig) -> None:
        self.config = config

    def folds(self, index: pd.DatetimeIndex) -> list[WalkForwardFold]:
        if not index.is_monotonic_increasing:
            raise LookAheadBiasError("Walk-forward requires chronological timestamps")
        if index.has_duplicates:
            raise LookAheadBiasError("Walk-forward index contains duplicates")
        if len(index) < 3:
            raise ConfigurationError("Need at least 3 bars for walk-forward")

        train_period = parse_period(self.config.training_period, index)
        test_period = parse_period(self.config.test_period, index)
        folds: list[WalkForwardFold] = []
        origin = pd.Timestamp(index[0])

        first_test_start = _end_exclusive(index, origin, train_period)
        test_start = first_test_start
        fold_id = 0
        while test_start <= index[-1]:
            test_end = _end_exclusive(index, test_start, test_period)
            if test_end <= test_start:
                break
            if self.config.type == "expanding":
                train_start = origin
            else:
                train_start = _roll_start(index, test_start, train_period)
            train_index = index[(index >= train_start) & (index < test_start)]
            test_index = index[(index >= test_start) & (index < test_end)]
            if self.config.embargo_bars:
                if len(train_index) <= self.config.embargo_bars:
                    test_start = test_end
                    continue
                train_index = train_index[: -self.config.embargo_bars]
            if len(train_index) == 0 or len(test_index) == 0:
                if test_end > index[-1] and not len(test_index):
                    break
                test_start = test_end
                continue
            if train_index.max() >= test_index.min():
                raise LookAheadBiasError("Generated overlapping walk-forward fold")
            folds.append(
                WalkForwardFold(
                    fold_id=fold_id,
                    train_start=pd.Timestamp(train_index.min()),
                    train_end=pd.Timestamp(train_index.max()),
                    test_start=pd.Timestamp(test_index.min()),
                    test_end=pd.Timestamp(test_index.max()),
                    train_index=train_index,
                    test_index=test_index,
                    mode=self.config.type,
                )
            )
            fold_id += 1
            test_start = test_end
        if not folds:
            raise ConfigurationError("Walk-forward produced no folds; check periods versus data length")
        return folds


def _roll_start(
    index: pd.DatetimeIndex,
    test_start: pd.Timestamp,
    train_period: tuple[str, int] | pd.DateOffset,
) -> pd.Timestamp:
    if isinstance(train_period, tuple):
        _, bars = train_period
        loc = int(index.get_indexer([test_start], method="bfill")[0])
        start_loc = max(0, loc - bars)
        return pd.Timestamp(index[start_loc])
    candidate = pd.Timestamp(test_start) - train_period
    return max(pd.Timestamp(index[0]), pd.Timestamp(candidate))
