from __future__ import annotations

import pytest

from kronos_backtest.config import BacktestConfig, SlippageConfig, SpreadConfig
from kronos_backtest.costs import BidAskOrSyntheticSpread, TransactionCostModel
from kronos_backtest.slippage import ProportionalSlippage
from kronos_backtest.types import Bar, Side
import pandas as pd


def _bar(open_px: float = 100.0, bid: float | None = None, ask: float | None = None) -> Bar:
    return Bar(
        timestamp=pd.Timestamp("2020-01-02"),
        symbol="TEST",
        open=open_px,
        high=open_px + 1,
        low=open_px - 1,
        close=open_px + 0.5,
        volume=1000,
        bid=bid,
        ask=ask,
    )


def test_slippage_buy_and_sell() -> None:
    model = ProportionalSlippage(rate=0.0005, enabled=True)
    buy, buy_cost = model.apply(100.0, Side.BUY)
    sell, sell_cost = model.apply(100.0, Side.SELL)
    assert buy == pytest.approx(100.05)
    assert sell == pytest.approx(99.95)
    assert buy_cost == pytest.approx(0.05)
    assert sell_cost == pytest.approx(0.05)


def test_synthetic_spread() -> None:
    quoted_buy, buy_cost = BidAskOrSyntheticSpread(rate=0.0005).quote(_bar(), Side.BUY, 100.0)
    quoted_sell, sell_cost = BidAskOrSyntheticSpread(rate=0.0005).quote(_bar(), Side.SELL, 100.0)
    assert quoted_buy == pytest.approx(100.025)
    assert quoted_sell == pytest.approx(99.975)
    assert buy_cost == pytest.approx(0.025)
    assert sell_cost == pytest.approx(0.025)


def test_actual_bid_ask_used_when_present() -> None:
    bar = _bar(100.0, bid=99.9, ask=100.1)
    buy, _ = BidAskOrSyntheticSpread(rate=0.5).quote(bar, Side.BUY, 100.0)
    sell, _ = BidAskOrSyntheticSpread(rate=0.5).quote(bar, Side.SELL, 100.0)
    assert buy == pytest.approx(100.1)
    assert sell == pytest.approx(99.9)


def test_commission_and_total_cost() -> None:
    model = TransactionCostModel.from_config(
        BacktestConfig(
            slippage=SlippageConfig(enabled=True, rate=0.0005),
            spread=SpreadConfig(enabled=True, rate=0.0005),
        )
    )
    costs = model.price_and_costs(_bar(100.0), Side.BUY, 10)
    # spread then slippage then fees
    after_spread = 100.025
    fill = after_spread * 1.0005
    gross = fill * 10
    commission = gross * 0.0001
    exchange = gross * 0.00005
    spread_cost = 0.025 * 10
    slippage_cost = (fill - after_spread) * 10
    assert costs.fill_price == pytest.approx(fill)
    assert costs.commission == pytest.approx(commission)
    assert costs.exchange_fees == pytest.approx(exchange)
    assert costs.spread_cost == pytest.approx(spread_cost)
    assert costs.slippage_cost == pytest.approx(slippage_cost)
    assert costs.gross_value == pytest.approx(gross)
    assert costs.total_transaction_cost == pytest.approx(
        commission + exchange + spread_cost + slippage_cost
    )
    assert costs.net_value == pytest.approx(gross + commission + exchange)
