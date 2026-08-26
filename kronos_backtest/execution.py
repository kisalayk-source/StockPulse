"""Delayed execution: signals at T fill on a later bar's open."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from kronos_backtest.config import ExecutionConfig
from kronos_backtest.costs import FillCosts, TransactionCostModel
from kronos_backtest.exceptions import ExecutionError
from kronos_backtest.orders import Order
from kronos_backtest.types import Bar, OrderStatus, Side


@dataclass
class Fill:
    timestamp: pd.Timestamp
    symbol: str
    side: Side
    quantity: float
    order_id: str
    created_at: pd.Timestamp | None
    created_bar_index: int | None
    filled_bar_index: int
    reference_price: float
    fill_price: float
    price_after_spread: float
    commission: float
    exchange_fees: float
    regulatory_fees: float
    spread_cost: float
    slippage_cost: float
    gross_value: float
    total_transaction_cost: float
    net_value: float
    expected_return: float = 0.0
    edge: float = 0.0
    confidence: float = 1.0
    signal: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    def as_audit_row(self, *, position_after: float, equity: float) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "prediction": self.expected_return,
            "expected_return": self.expected_return,
            "edge": self.edge,
            "signal": self.signal or self.side.value,
            "reference_price": self.reference_price,
            "fill_price": self.fill_price,
            "price_after_spread": self.price_after_spread,
            "slippage": self.slippage_cost,
            "spread": self.spread_cost,
            "commission": self.commission,
            "exchange_fees": self.exchange_fees,
            "regulatory_fees": self.regulatory_fees,
            "total_cost": self.total_transaction_cost,
            "gross_value": self.gross_value,
            "net_value": self.net_value,
            "position_after_trade": position_after,
            "portfolio_equity": equity,
            "order_id": self.order_id,
            "created_at": self.created_at,
            "created_bar_index": self.created_bar_index,
            "filled_bar_index": self.filled_bar_index,
        }


def _fill_from_costs(
    order: Order,
    bar: Bar,
    bar_index: int,
    costs: FillCosts,
) -> Fill:
    return Fill(
        timestamp=bar.timestamp,
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        order_id=order.order_id,
        created_at=order.created_at,
        created_bar_index=order.created_bar_index,
        filled_bar_index=bar_index,
        reference_price=costs.reference_price,
        fill_price=costs.fill_price,
        price_after_spread=costs.price_after_spread,
        commission=costs.commission,
        exchange_fees=costs.exchange_fees,
        regulatory_fees=costs.regulatory_fees,
        spread_cost=costs.spread_cost,
        slippage_cost=costs.slippage_cost,
        gross_value=costs.gross_value,
        total_transaction_cost=costs.total_transaction_cost,
        net_value=costs.net_value,
        expected_return=order.expected_return,
        edge=order.edge,
        confidence=order.confidence,
        signal=order.signal,
    )


class ExecutionEngine:
    """Queue orders at bar T and fill them on T+delay using the next open.

    Event contract:
    - An order submitted while processing bar index ``i`` is not eligible
      until bar index ``i + delay_bars``.
    - The fill reference is the later bar's **open**, never that later bar's
      close, and never the originating bar's close.
    """

    def __init__(
        self,
        cost_model: TransactionCostModel,
        config: ExecutionConfig | None = None,
    ) -> None:
        self.cost_model = cost_model
        self.config = config or ExecutionConfig()
        if self.config.delay_bars < 1 and not self.config.allow_same_bar_execution:
            raise ExecutionError("delay_bars must be >= 1 to prevent same-bar fills")
        self._queue: list[Order] = []

    def submit(self, order: Order) -> None:
        if order.created_at is None or order.created_bar_index is None:
            raise ExecutionError("Orders must be stamped with created_at and created_bar_index")
        self._queue.append(order)

    def pending(self) -> list[Order]:
        return list(self._queue)

    def process_orders(self, bar: Bar, bar_index: int) -> list[Fill]:
        remaining: list[Order] = []
        fills: list[Fill] = []
        for order in self._queue:
            if order.created_bar_index is None:
                raise ExecutionError("Queued order missing created_bar_index")
            if bar_index < order.created_bar_index + self.config.delay_bars:
                remaining.append(order)
                continue
            if bar_index == order.created_bar_index and not self.config.allow_same_bar_execution:
                raise ExecutionError(
                    "Refusing same-bar execution: order created at "
                    f"{order.created_at} cannot fill on {bar.timestamp}"
                )
            fills.append(self.execute(order, bar, bar_index))
        self._queue = remaining
        return fills

    def execute(self, order: Order, market_bar: Bar, bar_index: int) -> Fill:
        if order.symbol != market_bar.symbol:
            raise ExecutionError(
                f"Order symbol {order.symbol} does not match bar {market_bar.symbol}"
            )
        if order.created_at is not None and market_bar.timestamp <= order.created_at:
            raise ExecutionError(
                "Order cannot fill on or before its creation timestamp "
                f"(created {order.created_at}, bar {market_bar.timestamp})"
            )
        if self.config.fill_on != "open":
            raise ExecutionError("Only next-bar open execution is implemented")
        costs = self.cost_model.price_and_costs(
            market_bar,
            order.side,
            order.quantity,
            reference_price=market_bar.open,
        )
        order.status = OrderStatus.FILLED
        return _fill_from_costs(order, market_bar, bar_index, costs)
