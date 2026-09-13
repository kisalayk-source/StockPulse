"""Walk-forward fold generation for hybrid prediction (MVP-6).

Financial series are never shuffled. Embargo bars purge label leakage between
train and test when the label horizon spans multiple bars.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Literal

import pandas as pd


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_index: pd.DatetimeIndex
    test_index: pd.DatetimeIndex
    mode: str

    @property
    def train_start(self) -> pd.Timestamp:
        return pd.Timestamp(self.train_index.min())

    @property
    def train_end(self) -> pd.Timestamp:
        return pd.Timestamp(self.train_index.max())

    @property
    def test_start(self) -> pd.Timestamp:
        return pd.Timestamp(self.test_index.min())

    @property
    def test_end(self) -> pd.Timestamp:
        return pd.Timestamp(self.test_index.max())

    def validate(self) -> None:
        if len(self.train_index) == 0 or len(self.test_index) == 0:
            raise ValueError(f"fold {self.fold_id} has empty train or test index")
        if self.train_index.max() >= self.test_index.min():
            raise ValueError(
                f"fold {self.fold_id} overlaps: train max {self.train_index.max()} "
                f">= test min {self.test_index.min()}"
            )


def walk_forward_splits(
    index: pd.DatetimeIndex | pd.Index,
    *,
    train_bars: int,
    test_bars: int,
    step_bars: int | None = None,
    embargo_bars: int = 0,
    mode: Literal["expanding", "rolling"] = "expanding",
    max_folds: int | None = None,
) -> Iterator[WalkForwardFold]:
    """Yield chronological train/test folds.

    Parameters
    ----------
    train_bars:
        Minimum training window length (bars).
    test_bars:
        Out-of-sample evaluation window length.
    step_bars:
        How far to advance the test window each fold (defaults to ``test_bars``).
    embargo_bars:
        Bars dropped from the end of train (typically ``horizon_bars``) so labels
        cannot peek into the test window.
    mode:
        ``expanding`` grows train from the series start; ``rolling`` keeps a
        fixed-length train window ending just before the embargo/test.
    """
    if train_bars < 10:
        raise ValueError("train_bars must be >= 10")
    if test_bars < 1:
        raise ValueError("test_bars must be >= 1")
    if embargo_bars < 0:
        raise ValueError("embargo_bars must be >= 0")
    if mode not in {"expanding", "rolling"}:
        raise ValueError("mode must be 'expanding' or 'rolling'")

    idx = pd.DatetimeIndex(index)
    if not idx.is_monotonic_increasing:
        raise ValueError("walk-forward requires a chronological index")
    if idx.has_duplicates:
        raise ValueError("walk-forward index must not contain duplicates")

    step = int(step_bars if step_bars is not None else test_bars)
    if step < 1:
        raise ValueError("step_bars must be >= 1")

    n = len(idx)
    fold_id = 0
    test_start = train_bars + embargo_bars

    while test_start + test_bars <= n:
        test_end = test_start + test_bars
        train_end = test_start - embargo_bars
        if mode == "expanding":
            train_start = 0
        else:
            train_start = max(0, train_end - train_bars)
        if train_end - train_start < max(10, train_bars // 2):
            break

        train_index = idx[train_start:train_end]
        test_index = idx[test_start:test_end]
        fold = WalkForwardFold(
            fold_id=fold_id,
            train_index=train_index,
            test_index=test_index,
            mode=mode,
        )
        fold.validate()
        yield fold
        fold_id += 1
        if max_folds is not None and fold_id >= max_folds:
            break
        test_start += step
