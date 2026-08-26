"""Benchmark strategies that share the same execution and cost engine."""

from __future__ import annotations

from kronos_backtest.data.loader import MarketData
from kronos_backtest.portfolio import Portfolio
from kronos_backtest.strategy.strategy import Strategy
from kronos_backtest.types import Bar, Prediction, Signal, SignalAction


def _signal(prediction: Prediction, action: SignalAction, reason: str) -> Signal:
    expected = 0.01 if action is SignalAction.BUY else (-0.01 if action is SignalAction.SELL else 0.0)
    return Signal(
        timestamp=prediction.timestamp,
        symbol=prediction.symbol,
        action=action,
        expected_return=expected,
        edge=expected,
        confidence=1.0,
        estimated_cost=0.0,
        reason=reason,
    )


class BuyAndHoldStrategy(Strategy):
    def __init__(self) -> None:
        self._opened = False

    def generate_signal(self, prediction: Prediction, market: Bar, portfolio: Portfolio) -> Signal:
        if not self._opened and portfolio.position(market.symbol).is_flat:
            self._opened = True
            return _signal(prediction, SignalAction.BUY, "buy and hold entry")
        return _signal(prediction, SignalAction.HOLD, "buy and hold")


class MomentumStrategy(Strategy):
    def __init__(self, data: MarketData, lookback: int = 5) -> None:
        self.data = data
        self.lookback = lookback

    def generate_signal(self, prediction: Prediction, market: Bar, portfolio: Portfolio) -> Signal:
        history = self.data.get_history(market.timestamp, symbol=market.symbol, lookback=self.lookback + 1)
        if len(history) < self.lookback + 1:
            return _signal(prediction, SignalAction.HOLD, "momentum warmup")
        momentum = float(history["close"].iloc[-1] / history["close"].iloc[0] - 1.0)
        if momentum > 0:
            return _signal(prediction, SignalAction.BUY, "positive momentum")
        if momentum < 0 and not portfolio.position(market.symbol).is_flat:
            return _signal(prediction, SignalAction.SELL, "negative momentum")
        return _signal(prediction, SignalAction.HOLD, "flat momentum")


class MovingAverageStrategy(Strategy):
    def __init__(self, data: MarketData, window: int = 5) -> None:
        self.data = data
        self.window = window

    def generate_signal(self, prediction: Prediction, market: Bar, portfolio: Portfolio) -> Signal:
        history = self.data.get_history(market.timestamp, symbol=market.symbol, lookback=self.window)
        if len(history) < self.window:
            return _signal(prediction, SignalAction.HOLD, "ma warmup")
        sma = float(history["close"].mean())
        if market.close > sma:
            return _signal(prediction, SignalAction.BUY, "price above moving average")
        if market.close < sma and not portfolio.position(market.symbol).is_flat:
            return _signal(prediction, SignalAction.SELL, "price below moving average")
        return _signal(prediction, SignalAction.HOLD, "at moving average")
