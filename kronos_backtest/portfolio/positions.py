"""Portfolio and position accounting. Strategy code cannot credit cash."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from kronos_backtest.execution import Fill
from kronos_backtest.exceptions import ExecutionError
from kronos_backtest.types import Bar, Side


@dataclass
class Position:
    symbol: str
    quantity: float = 0.0
    average_price: float = 0.0
    realized_pnl: float = 0.0
    market_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.market_price

    @property
    def unrealized_pnl(self) -> float:
        if self.quantity == 0:
            return 0.0
        return (self.market_price - self.average_price) * self.quantity

    @property
    def is_flat(self) -> bool:
        return abs(self.quantity) < 1e-12


class Portfolio:
    """Deterministic long/short book. Cash changes only through ``apply_fill``."""

    def __init__(self, initial_cash: float, *, allow_short: bool = False) -> None:
        if initial_cash <= 0:
            raise ExecutionError("initial_cash must be positive")
        self._cash = float(initial_cash)
        self.initial_cash = float(initial_cash)
        self.allow_short = allow_short
        self._positions: dict[str, Position] = {}
        self.realized_pnl = 0.0
        self.total_commission = 0.0
        self.total_fees = 0.0
        self.total_spread_cost = 0.0
        self.total_slippage_cost = 0.0
        self.total_transaction_costs = 0.0
        self._last_prices: dict[str, float] = {}
        self.marks: list[dict[str, float | str]] = []

    @property
    def cash(self) -> float:
        return self._cash

    def position(self, symbol: str) -> Position:
        return self._positions.get(symbol, Position(symbol=symbol))

    @property
    def positions(self) -> dict[str, Position]:
        return {symbol: pos for symbol, pos in self._positions.items() if not pos.is_flat}

    def market_value(self) -> float:
        return sum(pos.market_value for pos in self._positions.values())

    def unrealized_pnl(self) -> float:
        return sum(pos.unrealized_pnl for pos in self._positions.values())

    def equity(self) -> float:
        return self._cash + self.market_value()

    def gross_exposure(self) -> float:
        return sum(abs(pos.market_value) for pos in self._positions.values())

    def leverage(self) -> float:
        equity = self.equity()
        if equity <= 0:
            return float("inf")
        return self.gross_exposure() / equity

    def apply_fill(self, fill: Fill) -> Position:
        position = self._positions.get(fill.symbol, Position(symbol=fill.symbol))
        fees = fill.commission + fill.exchange_fees + fill.regulatory_fees
        if fill.side is Side.BUY:
            self._cash -= fill.gross_value + fees
            if self._cash < -1e-8:
                raise ExecutionError(
                    f"Cash would go negative ({self._cash:.6f}) buying {fill.symbol}"
                )
            new_qty = position.quantity + fill.quantity
            if position.quantity >= 0:
                total_cost = position.average_price * position.quantity + fill.fill_price * fill.quantity
                position.average_price = total_cost / new_qty if new_qty else 0.0
                position.quantity = new_qty
            else:
                closing = min(fill.quantity, abs(position.quantity))
                realized = (position.average_price - fill.fill_price) * closing - fees * (
                    closing / fill.quantity
                )
                position.realized_pnl += realized
                self.realized_pnl += realized
                leftover = fill.quantity - abs(position.quantity)
                if leftover > 0:
                    position.quantity = leftover
                    position.average_price = fill.fill_price
                else:
                    position.quantity = position.quantity + fill.quantity
                    if abs(position.quantity) < 1e-12:
                        position.quantity = 0.0
                        position.average_price = 0.0
        else:
            if position.quantity <= 0 and not self.allow_short:
                raise ExecutionError(f"Short selling disabled; cannot sell {fill.symbol}")
            if fill.quantity - position.quantity > 1e-9 and not self.allow_short:
                raise ExecutionError(
                    f"Sell quantity {fill.quantity} exceeds long position {position.quantity}"
                )
            self._cash += fill.gross_value - fees
            if position.quantity > 0:
                closing = min(fill.quantity, position.quantity)
                realized = (fill.fill_price - position.average_price) * closing - fees * (
                    closing / fill.quantity
                )
                position.realized_pnl += realized
                self.realized_pnl += realized
            new_qty = position.quantity - fill.quantity
            if new_qty < 0 and self.allow_short:
                position.average_price = fill.fill_price
            elif abs(new_qty) < 1e-12:
                position.average_price = 0.0
                new_qty = 0.0
            position.quantity = new_qty

        position.market_price = self._last_prices.get(fill.symbol, fill.fill_price)
        self._positions[fill.symbol] = position
        self.total_commission += fill.commission
        self.total_fees += fill.exchange_fees + fill.regulatory_fees
        self.total_spread_cost += fill.spread_cost
        self.total_slippage_cost += fill.slippage_cost
        self.total_transaction_costs += fill.total_transaction_cost
        return position

    def mark_to_market(self, bar: Bar) -> float:
        position = self._positions.get(bar.symbol)
        self._last_prices[bar.symbol] = bar.close
        if position is not None:
            position.market_price = bar.close
        equity = self.equity()
        self.marks.append(
            {
                "timestamp": bar.timestamp,
                "symbol": bar.symbol,
                "cash": self._cash,
                "market_value": self.market_value(),
                "equity": equity,
                "realized_pnl": self.realized_pnl,
                "unrealized_pnl": self.unrealized_pnl(),
                "position_qty": 0.0 if position is None else position.quantity,
            }
        )
        return equity

    def snapshot(self, timestamp: pd.Timestamp) -> dict[str, float | str]:
        return {
            "timestamp": timestamp,
            "cash": self._cash,
            "market_value": self.market_value(),
            "equity": self.equity(),
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl(),
            "gross_exposure": self.gross_exposure(),
            "leverage": self.leverage(),
            "transaction_costs": self.total_transaction_costs,
        }
