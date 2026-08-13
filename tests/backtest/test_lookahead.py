from __future__ import annotations

import pandas as pd
import pytest

from kronos_backtest.data.loader import MarketData
from kronos_backtest.exceptions import LookAheadBiasError
from kronos_backtest.predictor import ConstantPredictor, KronosBacktestPredictor, ScriptedPredictor
from kronos_backtest.data.validator import (
    assert_corporate_actions_not_in_future,
    assert_indicators_not_in_future,
    assert_ohlc_not_in_future,
    assert_returns_not_in_future,
    assert_training_does_not_contain_test,
    assert_volume_not_in_future,
    validate_context,
)
from tests.backtest.helpers import ohlcv_frame


CURRENT = pd.Timestamp("2020-01-03")


def _history_with_future(**future_cols) -> pd.DataFrame:
    frame = ohlcv_frame(
        [
            ("2020-01-01", 100, 100),
            ("2020-01-02", 101, 101),
            ("2020-01-03", 102, 102),
            ("2020-01-04", 103, 103),
        ]
    )
    for key, value in future_cols.items():
        frame.loc[frame["timestamp"] == pd.Timestamp("2020-01-04"), key] = value
    return frame


def test_future_ohlc_is_rejected() -> None:
    frame = _history_with_future()
    with pytest.raises(LookAheadBiasError, match="OHLC"):
        assert_ohlc_not_in_future(frame, CURRENT)


def test_future_volume_is_rejected() -> None:
    frame = _history_with_future(volume=9_999_999)
    with pytest.raises(LookAheadBiasError, match="volume"):
        assert_volume_not_in_future(frame, CURRENT)


def test_future_returns_and_labels_are_rejected() -> None:
    frame = _history_with_future(returns=0.42, label=1.0, target=1.0)
    with pytest.raises(LookAheadBiasError, match="returns/labels"):
        assert_returns_not_in_future(frame, CURRENT)


def test_future_indicators_are_rejected() -> None:
    frame = _history_with_future(sma_20=110.0, rsi=80.0)
    with pytest.raises(LookAheadBiasError, match="indicators"):
        assert_indicators_not_in_future(frame, CURRENT)


def test_future_corporate_actions_are_rejected() -> None:
    frame = _history_with_future(dividend=2.5, split_factor=2.0)
    with pytest.raises(LookAheadBiasError, match="corporate actions"):
        assert_corporate_actions_not_in_future(frame, CURRENT)


def test_validate_context_rejects_injected_future_row() -> None:
    frame = _history_with_future(sma_20=1.0, returns=0.5, dividend=1.0)
    with pytest.raises(LookAheadBiasError):
        validate_context(frame, CURRENT)


def test_training_data_cannot_contain_test_period() -> None:
    train = ohlcv_frame(
        [
            ("2020-01-01", 100, 100),
            ("2020-01-02", 101, 101),
            ("2020-01-05", 105, 105),
        ]
    )
    test = ohlcv_frame(
        [
            ("2020-01-03", 102, 102),
            ("2020-01-04", 103, 103),
        ]
    )
    with pytest.raises(LookAheadBiasError, match="leaks into the test period"):
        assert_training_does_not_contain_test(train, test)


def test_market_data_get_history_never_returns_future_rows() -> None:
    data = MarketData(_history_with_future())
    history = data.get_history(CURRENT)
    assert history["timestamp"].max() <= CURRENT
    assert pd.Timestamp("2020-01-04") not in set(history["timestamp"])


def test_predictor_rejects_future_context() -> None:
    predictor = ConstantPredictor(0.01, symbol="TEST")
    with pytest.raises(LookAheadBiasError):
        predictor.predict(_history_with_future(), CURRENT)


def test_kronos_wrapper_refuses_future_data_before_model_call() -> None:
    class Forbidden:
        def predict(self, *args, **kwargs):
            raise AssertionError("Kronos must not be called with future context")

    wrapper = KronosBacktestPredictor(Forbidden(), lookback=4, symbol="TEST")
    with pytest.raises(LookAheadBiasError):
        wrapper.predict(_history_with_future(), CURRENT)


def test_kronos_wrapper_passes_only_as_of_history_and_synthesized_horizon() -> None:
    captured: dict = {}

    class Inner:
        def predict(self, df, x_timestamp, y_timestamp, **kwargs):
            captured["df"] = df
            captured["x"] = pd.to_datetime(x_timestamp)
            captured["y"] = pd.to_datetime(y_timestamp)
            return pd.DataFrame(
                {
                    "open": [102],
                    "high": [103],
                    "low": [101],
                    "close": [104],
                    "volume": [0],
                    "amount": [0],
                },
                index=pd.DatetimeIndex(y_timestamp),
            )

    history = ohlcv_frame(
        [
            ("2020-01-01", 100, 100),
            ("2020-01-02", 101, 101),
            ("2020-01-03", 102, 102),
        ]
    )
    wrapper = KronosBacktestPredictor(Inner(), lookback=8, pred_len=2, symbol="TEST")
    prediction = wrapper.predict(history, CURRENT)
    assert captured["x"].max() <= CURRENT
    assert captured["y"].min() > CURRENT
    assert pd.Timestamp("2020-01-04") not in set(pd.to_datetime(history["timestamp"]))
    assert prediction.expected_return == pytest.approx(104 / 102 - 1)


def test_scripted_predictor_validates_as_of() -> None:
    history = ohlcv_frame([("2020-01-01", 100, 100), ("2020-01-03", 102, 102)])
    predictor = ScriptedPredictor({CURRENT: 0.02}, symbol="TEST")
    out = predictor.predict(history, CURRENT)
    assert out.expected_return == 0.02
    with pytest.raises(LookAheadBiasError):
        predictor.predict(_history_with_future(), CURRENT)
