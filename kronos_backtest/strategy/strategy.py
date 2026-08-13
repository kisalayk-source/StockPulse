"""Strategy interface and the default expected-return threshold policy."""

from __future__ import annotations

from kronos_backtest.config import BacktestConfig
from kronos_backtest.portfolio import Portfolio
from kronos_backtest.types import Bar, Prediction, Signal, SignalAction


class Strategy:
    def generate_signal(
        self,
        prediction: Prediction,
        market: Bar,
        portfolio: Portfolio,
    ) -> Signal:
        raise NotImplementedError


class ExpectedReturnStrategy(Strategy):
    """BUY/SELL only when expected return clears estimated costs plus a buffer.

    The strategy never computes actual fill costs. It uses the configured
    one-way cost estimate so that tiny edges are not traded.
    """

    def __init__(self, minimum_edge: float, estimated_cost: float) -> None:
        self.minimum_edge = minimum_edge
        self.estimated_cost = estimated_cost

    @classmethod
    def from_config(cls, config: BacktestConfig) -> "ExpectedReturnStrategy":
        return cls(config.strategy.minimum_edge, config.estimated_one_way_cost)

    def generate_signal(
        self,
        prediction: Prediction,
        market: Bar,
        portfolio: Portfolio,
    ) -> Signal:
        edge = prediction.expected_return - self.estimated_cost
        if edge > self.minimum_edge:
            action = SignalAction.BUY
            reason = "expected return exceeds costs and minimum edge"
        elif edge < -self.minimum_edge:
            action = SignalAction.SELL
            reason = "expected return below negative edge after costs"
        else:
            action = SignalAction.HOLD
            reason = "edge inside dead zone"
        return Signal(
            timestamp=prediction.timestamp,
            symbol=prediction.symbol,
            action=action,
            expected_return=prediction.expected_return,
            edge=edge,
            confidence=prediction.confidence,
            estimated_cost=self.estimated_cost,
            reason=reason,
        )
