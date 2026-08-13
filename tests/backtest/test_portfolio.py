from __future__ import annotations

import pandas as pd
import pytest

from kronos_backtest.costs import TransactionCostModel
from kronos_backtest.execution import Fill
from kronos_backtest.portfolio import Portfolio
from kronos_backtest.types import Bar, Side


def _fill(side: Side, qty: float, price: float, stamp: str = "2020-01-02", fees: float = 1.0) -> Fill:
    gross = price * qty
    return Fill(
        timestamp=pd.Timestamp(stamp),
        symbol="TEST",
        side=side,
        quantity=qty,
        order_id="x",
        created_at=pd.Timestamp("2020-01-01"),
        created_bar_index=0,
        filled_bar_index=1,
        reference_price=price,
        fill_price=price,
        price_after_spread=price,
        commission=fees,
        exchange_fees=0.0,
        regulatory_fees=0.0,
        spread_cost=0.0,
        slippage_cost=0.0,
        gross_value=gross,
        total_transaction_cost=fees,
        net_value=gross + fees if side is Side.BUY else gross - fees,
    )


def test_buy_accounting_and_cash_reconciliation() -> None:
    book = Portfolio(10_000)
    book.apply_fill(_fill(Side.BUY, 10, 100, fees=2))
    pos = book.position("TEST")
    assert pos.quantity == 10
    assert pos.average_price == pytest.approx(100)
    assert book.cash == pytest.approx(10_000 - 1000 - 2)
    bar = Bar(
        timestamp=pd.Timestamp("2020-01-02"),
        symbol="TEST",
        open=100,
        high=111,
        low=99,
        close=110,
        volume=1,
    )
    book.mark_to_market(bar)
    assert book.unrealized_pnl() == pytest.approx(100)
    assert book.equity() == pytest.approx(book.cash + 10 * 110)


def test_sell_realized_pnl() -> None:
    book = Portfolio(10_000)
    book.apply_fill(_fill(Side.BUY, 10, 100, fees=0))
    book.apply_fill(_fill(Side.SELL, 10, 110, stamp="2020-01-03", fees=0))
    assert book.position("TEST").quantity == 0
    assert book.realized_pnl == pytest.approx(100)
    assert book.cash == pytest.approx(10_000 + 100)
    assert book.equity() == pytest.approx(book.cash)


def test_partial_sell_average_price() -> None:
    book = Portfolio(10_000)
    book.apply_fill(_fill(Side.BUY, 10, 100, fees=0))
    book.apply_fill(_fill(Side.SELL, 4, 120, stamp="2020-01-03", fees=0))
    pos = book.position("TEST")
    assert pos.quantity == pytest.approx(6)
    assert pos.average_price == pytest.approx(100)
    assert book.realized_pnl == pytest.approx(80)


def test_short_disabled() -> None:
    book = Portfolio(10_000, allow_short=False)
    with pytest.raises(Exception, match="Short selling"):
        book.apply_fill(_fill(Side.SELL, 1, 100, fees=0))


def test_cost_model_not_used_by_portfolio_directly() -> None:
    assert not hasattr(Portfolio, "calculate")
    assert hasattr(TransactionCostModel, "calculate")
