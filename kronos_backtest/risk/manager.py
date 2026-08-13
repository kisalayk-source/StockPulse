"""Hard risk limits. Daily-loss and drawdown halt new entries, not exits."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from kronos_backtest.config import RiskConfig
from kronos_backtest.orders import Order
from kronos_backtest.portfolio import Portfolio
from kronos_backtest.strategy.position_sizing import PositionSizer
from kronos_backtest.types import Bar, OrderType, Side, Signal, SignalAction


@dataclass
class RiskDecision:
    order: Order | None
    accepted: bool
    reason: str
    halt_new_positions: bool = False


class RiskManager:
    def __init__(self, config: RiskConfig, sizer: PositionSizer) -> None:
        self.config = config
        self.sizer = sizer
        self._day_start_equity: float | None = None
        self._current_day: pd.Timestamp | None = None
        self._peak_equity: float | None = None
        self._halt_new = False

    def observe_equity(self, timestamp: pd.Timestamp, equity: float) -> None:
        day = pd.Timestamp(timestamp).normalize()
        if self._current_day is None or day != self._current_day:
            self._current_day = day
            self._day_start_equity = equity
        if self._peak_equity is None or equity > self._peak_equity:
            self._peak_equity = equity
        self._halt_new = self._should_halt(equity)

    def halt_new_positions(self) -> bool:
        return self._halt_new

    def _should_halt(self, equity: float) -> bool:
        if self._day_start_equity and self._day_start_equity > 0:
            daily = equity / self._day_start_equity - 1.0
            if daily <= -self.config.max_daily_loss_pct:
                return True
        if self._peak_equity and self._peak_equity > 0:
            drawdown = equity / self._peak_equity - 1.0
            if drawdown <= -self.config.max_drawdown_pct:
                return True
        return False

    def validate(self, signal: Signal, portfolio: Portfolio, market: Bar) -> RiskDecision:
        if signal.action is SignalAction.HOLD:
            return RiskDecision(None, False, "hold")
        self.observe_equity(market.timestamp, portfolio.equity())
        is_entry = self._is_entry(signal, portfolio)
        if is_entry and self._halt_new:
            return RiskDecision(None, False, "new positions halted by risk limits", halt_new_positions=True)
        if signal.action is SignalAction.SELL and not self.config.allow_short:
            held = portfolio.position(signal.symbol).quantity
            if held <= 0:
                return RiskDecision(None, False, "short selling disabled")
        quantity = self.sizer.target_quantity(signal, portfolio, market.close)
        if quantity <= 0:
            return RiskDecision(None, False, "position sizer returned zero quantity")
        side = Side.BUY if signal.action is SignalAction.BUY else Side.SELL
        estimated_price = market.close
        notional = quantity * estimated_price
        equity = portfolio.equity()
        if equity <= 0:
            return RiskDecision(None, False, "non-positive equity")

        current_position_value = abs(portfolio.position(signal.symbol).market_value)
        projected_position = current_position_value + (notional if side is Side.BUY else 0.0)
        if side is Side.BUY and projected_position / equity > self.config.max_position_pct + 1e-9:
            return RiskDecision(None, False, "max position size exceeded")

        projected_exposure = portfolio.gross_exposure() + (notional if side is Side.BUY else 0.0)
        if side is Side.BUY and projected_exposure / equity > self.config.max_total_exposure_pct + 1e-9:
            return RiskDecision(None, False, "max portfolio exposure exceeded")

        projected_leverage = projected_exposure / equity if equity else float("inf")
        if side is Side.BUY and projected_leverage > self.config.max_leverage + 1e-9:
            return RiskDecision(None, False, "max leverage exceeded")

        if side is Side.BUY and notional > portfolio.cash + 1e-9:
            return RiskDecision(None, False, "insufficient cash")

        order = Order(
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.MARKET,
            expected_return=signal.expected_return,
            edge=signal.edge,
            confidence=signal.confidence,
            signal=signal.action.value,
        )
        return RiskDecision(order, True, "accepted", halt_new_positions=self._halt_new)

    def _is_entry(self, signal: Signal, portfolio: Portfolio) -> bool:
        held = portfolio.position(signal.symbol).quantity
        if signal.action is SignalAction.BUY:
            return held >= 0
        return held <= 0
