from __future__ import annotations

import pandas as pd
import pytest

from kronos_backtest.config import WalkForwardConfig
from kronos_backtest.data.loader import MarketData
from kronos_backtest.exceptions import LookAheadBiasError
from kronos_backtest.predictor import CallbackFineTuner, ConstantPredictor
from kronos_backtest.walk_forward import WalkForwardEngine
from tests.backtest.helpers import daily_closes


def _index(n: int = 40) -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-01", periods=n)


def test_expanding_window_no_overlap_and_chronological() -> None:
    engine = WalkForwardEngine(
        WalkForwardConfig(type="expanding", training_period="10b", test_period="5b")
    )
    folds = engine.folds(_index())
    assert folds
    previous_test_start = None
    for fold in folds:
        assert fold.mode == "expanding"
        assert fold.train_index.max() < fold.test_index.min()
        assert fold.train_start == folds[0].train_start
        if previous_test_start is not None:
            assert fold.test_start > previous_test_start
        previous_test_start = fold.test_start
        train_len = len(fold.train_index)
        if fold.fold_id > 0:
            assert train_len > len(folds[0].train_index)


def test_rolling_window_keeps_train_length() -> None:
    engine = WalkForwardEngine(
        WalkForwardConfig(type="rolling", training_period="10b", test_period="5b")
    )
    folds = engine.folds(_index())
    lengths = {len(fold.train_index) for fold in folds}
    assert lengths == {10}
    for fold in folds:
        assert fold.train_index.max() < fold.test_index.min()


def test_never_shuffles_financial_data() -> None:
    folds = WalkForwardEngine(
        WalkForwardConfig(type="expanding", training_period="8b", test_period="4b")
    ).folds(_index(24))
    for fold in folds:
        assert list(fold.train_index) == sorted(fold.train_index)
        assert list(fold.test_index) == sorted(fold.test_index)
    test_starts = [fold.test_start for fold in folds]
    assert test_starts == sorted(test_starts)


def test_fine_tune_rejects_test_period_rows() -> None:
    data = MarketData(daily_closes([100 + i for i in range(20)]))
    folds = WalkForwardEngine(
        WalkForwardConfig(type="expanding", training_period="8b", test_period="4b")
    ).folds(data.index())
    fold = folds[0]
    dirty = data.slice_by_timestamps(fold.train_index.union(fold.test_index))
    tuner = CallbackFineTuner(lambda train, end: ConstantPredictor(0.01))
    with pytest.raises(LookAheadBiasError):
        tuner.fit(dirty, fold.train_end, fold.test_start)
    with pytest.raises(LookAheadBiasError, match="test-period"):
        tuner.fit(dirty, dirty["timestamp"].max(), fold.test_start)


def test_fine_tune_callback_sees_only_training_window() -> None:
    data = MarketData(daily_closes([100 + i for i in range(20)]))
    fold = WalkForwardEngine(
        WalkForwardConfig(type="expanding", training_period="8b", test_period="4b")
    ).folds(data.index())[0]
    seen: list[pd.Timestamp] = []

    def factory(train, end):
        seen.append(train["timestamp"].max())
        assert train["timestamp"].max() < fold.test_start
        return ConstantPredictor(0.01)

    predictor = CallbackFineTuner(factory).fit(
        data.slice_by_timestamps(fold.train_index),
        fold.train_end,
        fold.test_start,
    )
    assert seen[0] == fold.train_end
    assert predictor is not None


def test_engine_walk_forward_freezes_model_per_fold() -> None:
    data = MarketData(daily_closes([100 + i for i in range(24)]))
    seen_ends: list[pd.Timestamp] = []

    def factory(train, end):
        seen_ends.append(end)
        assert train["timestamp"].max() <= end
        return ConstantPredictor(0.03, symbol="TEST")

    from kronos_backtest.config import BacktestConfig, WalkForwardConfig
    from kronos_backtest.engine import BacktestEngine

    config = BacktestConfig(
        symbol="TEST",
        initial_capital=10_000,
        walk_forward=WalkForwardConfig(
            enabled=True, type="expanding", training_period="8b", test_period="4b"
        ),
    )
    result = BacktestEngine(
        data,
        ConstantPredictor(0.03, symbol="TEST"),
        config,
        fine_tuner=CallbackFineTuner(factory),
    ).run()
    assert seen_ends
    assert result.metadata.get("folds")
    assert result.equity_curve["timestamp"].is_monotonic_increasing
