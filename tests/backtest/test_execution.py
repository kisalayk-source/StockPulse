from __future__ import annotations

import pandas as pd
import pytest

from kronos_backtest.config import ExecutionConfig
from kronos_backtest.costs import TransactionCostModel
from kronos_backtest.exceptions import ExecutionError
from kronos_backtest.execution import ExecutionEngine
from kronos_backtest.orders import Order
from kronos_backtest.types import Bar, OrderType, Side


def _bar(stamp: str, open_px: float, close_px: float, symbol: str = "TEST") -> Bar:
    return Bar(
        timestamp=pd.Timestamp(stamp),
        symbol=symbol,
        open=open_px,
        high=max(open_px, close_px) + 1,
        low=min(open_px, close_px) - 1,
        close=close_px,
        volume=1000,
    )


def test_limit_orders_are_reserved() -> None:
    with pytest.raises(ExecutionError, match="LIMIT"):
        Order(symbol="TEST", side=Side.BUY, quantity=1, order_type=OrderType.LIMIT)


def test_same_bar_close_cannot_be_used() -> None:
    engine = ExecutionEngine(TransactionCostModel(), ExecutionConfig(delay_bars=1))
    created = _bar("2020-01-01", 100, 999)
    nxt = _bar("2020-01-02", 102, 50)
    order = Order(symbol="TEST", side=Side.BUY, quantity=1)
    order.created_at = created.timestamp
    order.created_bar_index = 0
    engine.submit(order)
    assert engine.process_orders(created, 0) == []
    fills = engine.process_orders(nxt, 1)
    assert len(fills) == 1
    fill = fills[0]
    assert fill.reference_price == nxt.open == 102
    assert fill.fill_price != created.close
    assert fill.fill_price != nxt.close
    assert fill.created_at == created.timestamp
    assert fill.timestamp == nxt.timestamp


def test_next_bar_open_execution() -> None:
    engine = ExecutionEngine(
        TransactionCostModel(spread_model=None, slippage_model=None, commission_rate=0, exchange_fee_rate=0),
        ExecutionConfig(delay_bars=1),
    )
    order = Order(symbol="TEST", side=Side.BUY, quantity=2)
    order.created_at = pd.Timestamp("2020-01-01")
    order.created_bar_index = 0
    engine.submit(order)
    fills = engine.process_orders(_bar("2020-01-02", 105, 110), 1)
    assert fills[0].fill_price == pytest.approx(105)
    assert fills[0].reference_price == 105


def test_execution_delay_bars() -> None:
    engine = ExecutionEngine(
        TransactionCostModel(commission_rate=0, exchange_fee_rate=0),
        ExecutionConfig(delay_bars=2),
    )
    order = Order(symbol="TEST", side=Side.BUY, quantity=1)
    order.created_at = pd.Timestamp("2020-01-01")
    order.created_bar_index = 0
    engine.submit(order)
    assert engine.process_orders(_bar("2020-01-02", 101, 101), 1) == []
    fills = engine.process_orders(_bar("2020-01-03", 108, 90), 2)
    assert len(fills) == 1
    assert fills[0].reference_price == 108


def test_order_cannot_fill_on_or_before_creation_timestamp() -> None:
    engine = ExecutionEngine(TransactionCostModel(), ExecutionConfig(delay_bars=1))
    order = Order(symbol="TEST", side=Side.BUY, quantity=1)
    order.created_at = pd.Timestamp("2020-01-02")
    order.created_bar_index = 0
    with pytest.raises(ExecutionError, match="on or before"):
        engine.execute(order, _bar("2020-01-02", 100, 100), 1)
