"""Explicit order objects. Orders are created at bar T and filled later."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pandas as pd

from kronos_backtest.exceptions import ExecutionError
from kronos_backtest.types import OrderStatus, OrderType, Side


IMPLEMENTED_ORDER_TYPES = {OrderType.MARKET}


@dataclass
class Order:
    symbol: str
    side: Side
    quantity: float
    order_type: OrderType = OrderType.MARKET
    created_at: pd.Timestamp | None = None
    created_bar_index: int | None = None
    status: OrderStatus = OrderStatus.PENDING
    expected_return: float = 0.0
    edge: float = 0.0
    confidence: float = 1.0
    signal: str = ""
    limit_price: float | None = None
    stop_price: float | None = None
    order_id: str = field(default_factory=lambda: uuid4().hex[:12])
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.side, str):
            self.side = Side(self.side.upper())
        if isinstance(self.order_type, str):
            self.order_type = OrderType(self.order_type.upper())
        if self.quantity <= 0:
            raise ExecutionError("Order quantity must be positive")
        if self.order_type not in IMPLEMENTED_ORDER_TYPES:
            raise ExecutionError(
                f"{self.order_type.value} orders are reserved for a future execution "
                "model and are not implemented"
            )

    @property
    def signed_quantity(self) -> float:
        return self.quantity if self.side is Side.BUY else -self.quantity
