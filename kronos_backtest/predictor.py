"""Predictor protocol, look-ahead gated Kronos wrapper, and deterministic stubs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from kronos_backtest.data.validator import timestamps_of, to_timestamp, validate_context
from kronos_backtest.exceptions import InsufficientHistoryError, LookAheadBiasError
from kronos_backtest.types import Prediction


class Predictor(Protocol):
    def predict(self, historical_data: pd.DataFrame, current_timestamp: pd.Timestamp) -> Prediction:
        ...


class FineTuner(Protocol):
    def fit(
        self,
        train_data: pd.DataFrame,
        train_end: pd.Timestamp,
        test_start: pd.Timestamp,
    ) -> Predictor:
        ...


def _require_as_of(historical_data: pd.DataFrame, current_timestamp: pd.Timestamp) -> None:
    validate_context(historical_data, current_timestamp)
    if historical_data.empty:
        raise InsufficientHistoryError("Predictor received empty history")
    if timestamps_of(historical_data).max() > to_timestamp(current_timestamp):
        raise LookAheadBiasError("Predictor context extends beyond current_timestamp")


@dataclass
class ScriptedPredictor:
    """Deterministic forecasts keyed by as-of timestamp. Used by tests."""

    expected_returns: dict[pd.Timestamp, float]
    symbol: str = "TEST"
    confidence: float = 1.0
    default_return: float = 0.0

    def predict(self, historical_data: pd.DataFrame, current_timestamp: pd.Timestamp) -> Prediction:
        current = to_timestamp(current_timestamp)
        _require_as_of(historical_data, current)
        expected = self.expected_returns.get(current, self.default_return)
        last_close = float(historical_data.iloc[-1]["close"])
        return Prediction(
            timestamp=current,
            symbol=str(historical_data.iloc[-1].get("symbol", self.symbol)),
            expected_return=float(expected),
            predicted_close=last_close * (1.0 + float(expected)),
            confidence=self.confidence,
        )


@dataclass
class ConstantPredictor:
    expected_return: float
    symbol: str = "TEST"
    confidence: float = 1.0

    def predict(self, historical_data: pd.DataFrame, current_timestamp: pd.Timestamp) -> Prediction:
        current = to_timestamp(current_timestamp)
        _require_as_of(historical_data, current)
        last_close = float(historical_data.iloc[-1]["close"])
        return Prediction(
            timestamp=current,
            symbol=str(historical_data.iloc[-1].get("symbol", self.symbol)),
            expected_return=self.expected_return,
            predicted_close=last_close * (1.0 + self.expected_return),
            confidence=self.confidence,
        )


class PretrainedFineTuner:
    """Pretrained mode: freeze the supplied predictor after validating the train window."""

    def __init__(self, predictor: Predictor) -> None:
        self._predictor = predictor

    def fit(
        self,
        train_data: pd.DataFrame,
        train_end: pd.Timestamp,
        test_start: pd.Timestamp,
    ) -> Predictor:
        validate_context(train_data, train_end)
        if timestamps_of(train_data).max() >= to_timestamp(test_start):
            raise LookAheadBiasError("Fine-tune training window includes test-period timestamps")
        return self._predictor


class CallbackFineTuner:
    """User-supplied fine-tune callback. Test data is never passed in."""

    def __init__(self, factory) -> None:
        self._factory = factory

    def fit(
        self,
        train_data: pd.DataFrame,
        train_end: pd.Timestamp,
        test_start: pd.Timestamp,
    ) -> Predictor:
        validate_context(train_data, train_end)
        if timestamps_of(train_data).max() >= to_timestamp(test_start):
            raise LookAheadBiasError("Fine-tune training window includes test-period timestamps")
        return self._factory(train_data, train_end)


class KronosBacktestPredictor:
    """Wraps ``model.KronosPredictor`` and refuses any future context.

    Future *calendar* timestamps for the forecast horizon are synthesized from
    the inferred bar frequency. Actual future OHLCV is never passed to Kronos.
    """

    def __init__(
        self,
        kronos_predictor,
        *,
        lookback: int = 64,
        pred_len: int = 1,
        sample_count: int = 1,
        temperature: float = 1.0,
        top_k: int = 0,
        top_p: float = 0.9,
        symbol: str = "ASSET",
    ) -> None:
        self._predictor = kronos_predictor
        self.lookback = lookback
        self.pred_len = pred_len
        self.sample_count = sample_count
        self.temperature = temperature
        self.top_k = top_k
        self.top_p = top_p
        self.symbol = symbol

    @classmethod
    def from_pretrained(
        cls,
        *,
        tokenizer_id: str,
        model_id: str,
        device: str = "cpu",
        max_context: int = 512,
        **kwargs,
    ) -> "KronosBacktestPredictor":
        from model import Kronos, KronosPredictor, KronosTokenizer

        tokenizer = KronosTokenizer.from_pretrained(tokenizer_id)
        model = Kronos.from_pretrained(model_id)
        tokenizer.eval()
        model.eval()
        inner = KronosPredictor(model, tokenizer, device=device, max_context=max_context)
        return cls(inner, **kwargs)

    def predict(self, historical_data: pd.DataFrame, current_timestamp: pd.Timestamp) -> Prediction:
        current = to_timestamp(current_timestamp)
        _require_as_of(historical_data, current)
        history = historical_data.tail(self.lookback).copy()
        if len(history) < 2:
            raise InsufficientHistoryError("Kronos needs at least two historical bars")
        x_timestamp = pd.Series(timestamps_of(history), name="timestamps")
        inferred = pd.Series(x_timestamp).diff().median()
        step = inferred if pd.notna(inferred) and inferred > pd.Timedelta(0) else pd.Timedelta(days=1)
        y_timestamp = pd.Series(
            [current + step * (i + 1) for i in range(self.pred_len)],
            name="timestamps",
        )
        feature_cols = [col for col in ("open", "high", "low", "close", "volume", "amount") if col in history.columns]
        pred_df = self._predictor.predict(
            df=history[feature_cols],
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=self.pred_len,
            T=self.temperature,
            top_k=self.top_k,
            top_p=self.top_p,
            sample_count=self.sample_count,
            verbose=False,
        )
        last_close = float(history.iloc[-1]["close"])
        predicted_close = float(pred_df.iloc[-1]["close"])
        expected = (predicted_close / last_close - 1.0) if last_close else 0.0
        return Prediction(
            timestamp=current,
            symbol=str(history.iloc[-1].get("symbol", self.symbol)),
            expected_return=expected,
            predicted_close=predicted_close,
            confidence=1.0,
            horizon_bars=self.pred_len,
        )
