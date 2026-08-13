"""Position sizing helpers. Exposure limits are enforced again by RiskManager."""

from __future__ import annotations

from kronos_backtest.config import PositionSizingConfig
from kronos_backtest.portfolio import Portfolio
from kronos_backtest.types import Signal, SignalAction


class PositionSizer:
    def __init__(self, config: PositionSizingConfig) -> None:
        self.config = config

    def target_quantity(
        self,
        signal: Signal,
        portfolio: Portfolio,
        last_price: float,
    ) -> float:
        if last_price <= 0 or signal.action is SignalAction.HOLD:
            return 0.0
        equity = portfolio.equity()
        confidence = signal.confidence if self.config.confidence_scaling else 1.0
        confidence = max(0.0, min(1.0, confidence))
        target_value = equity * self.config.max_position_pct * confidence
        quantity = target_value / last_price
        if self.config.integer_shares:
            quantity = float(int(quantity))
        current = portfolio.position(signal.symbol).quantity
        if signal.action is SignalAction.BUY:
            additional = max(0.0, quantity - max(current, 0.0))
            affordable = portfolio.cash / last_price
            additional = min(additional, max(0.0, affordable))
            if self.config.integer_shares:
                additional = float(int(additional))
            return additional
        if current > 0:
            closing = current
            if self.config.integer_shares:
                closing = float(int(closing))
            return max(closing, 0.0)
        if current < 0:
            return 0.0
        return quantity
