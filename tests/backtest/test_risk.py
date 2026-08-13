from __future__ import annotations

import pandas as pd
import pytest

from kronos_backtest.config import PositionSizingConfig, RiskConfig
from kronos_backtest.portfolio import Portfolio
from kronos_backtest.risk import RiskManager
from kronos_backtest.strategy.position_sizing import PositionSizer
from kronos_backtest.types import Bar, Signal, SignalAction


def _bar(close: float = 100.0) -> Bar:
    return Bar(
        timestamp=pd.Timestamp("2020-01-01"),
        symbol="TEST",
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000,
    )


def _buy(confidence: float = 1.0) -> Signal:
    return Signal(
        timestamp=pd.Timestamp("2020-01-01"),
        symbol="TEST",
        action=SignalAction.BUY,
        expected_return=0.05,
        edge=0.04,
        confidence=confidence,
    )


def _manager(**kwargs) -> RiskManager:
    risk = RiskConfig(**kwargs)
    return RiskManager(risk, PositionSizer(PositionSizingConfig(max_position_pct=risk.max_position_pct)))


def test_max_position_size() -> None:
    manager = _manager(max_position_pct=0.10)
    book = Portfolio(10_000)
    decision = manager.validate(_buy(), book, _bar(100))
    assert decision.accepted
    assert decision.order.quantity == pytest.approx(10)

    from kronos_backtest.execution import Fill
    from kronos_backtest.types import Side

    fill = Fill(
        timestamp=pd.Timestamp("2020-01-02"),
        symbol="TEST",
        side=Side.BUY,
        quantity=10,
        order_id="a",
        created_at=pd.Timestamp("2020-01-01"),
        created_bar_index=0,
        filled_bar_index=1,
        reference_price=100,
        fill_price=100,
        price_after_spread=100,
        commission=0,
        exchange_fees=0,
        regulatory_fees=0,
        spread_cost=0,
        slippage_cost=0,
        gross_value=1000,
        total_transaction_cost=0,
        net_value=1000,
    )
    book.apply_fill(fill)
    book.mark_to_market(_bar(100))
    again = manager.validate(_buy(), book, _bar(100))
    assert not again.accepted


def test_max_exposure_and_leverage() -> None:
    manager = _manager(max_position_pct=1.0, max_total_exposure_pct=0.10, max_leverage=0.10)
    book = Portfolio(10_000)
    decision = manager.validate(_buy(), book, _bar(100))
    # sizer uses max_position_pct 1.0 so wants 100% but exposure cap is 10%
    assert not decision.accepted
    assert "exposure" in decision.reason or "leverage" in decision.reason


def test_daily_loss_halts_new_positions_not_exits() -> None:
    manager = _manager(max_daily_loss_pct=0.02)
    book = Portfolio(10_000)
    from kronos_backtest.execution import Fill
    from kronos_backtest.types import Side

    book.apply_fill(
        Fill(
            timestamp=pd.Timestamp("2020-01-01"),
            symbol="TEST",
            side=Side.BUY,
            quantity=10,
            order_id="b",
            created_at=pd.Timestamp("2019-12-31"),
            created_bar_index=0,
            filled_bar_index=1,
            reference_price=100,
            fill_price=100,
            price_after_spread=100,
            commission=0,
            exchange_fees=0,
            regulatory_fees=0,
            spread_cost=0,
            slippage_cost=0,
            gross_value=1_000,
            total_transaction_cost=0,
            net_value=1_000,
        )
    )
    morning = Bar(
        timestamp=pd.Timestamp("2020-01-01 09:30"),
        symbol="TEST",
        open=100,
        high=101,
        low=99,
        close=100,
        volume=1,
    )
    crash = Bar(
        timestamp=pd.Timestamp("2020-01-01 15:00"),
        symbol="TEST",
        open=80,
        high=80,
        low=78,
        close=79,
        volume=1,
    )
    book.mark_to_market(morning)
    manager.observe_equity(morning.timestamp, book.equity())
    book.mark_to_market(crash)
    manager.observe_equity(crash.timestamp, book.equity())
    blocked = manager.validate(_buy(), book, crash)
    assert not blocked.accepted
    assert "halted" in blocked.reason

    sell = Signal(
        timestamp=crash.timestamp,
        symbol="TEST",
        action=SignalAction.SELL,
        expected_return=-0.05,
        edge=-0.04,
    )
    exit_decision = manager.validate(sell, book, crash)
    assert exit_decision.accepted


def test_max_drawdown_halts_entries() -> None:
    manager = _manager(max_drawdown_pct=0.15)
    book = Portfolio(10_000)
    manager.observe_equity(pd.Timestamp("2020-01-01"), book.equity())
    book._cash = 8_400
    decision = manager.validate(
        _buy(),
        book,
        Bar(
            timestamp=pd.Timestamp("2020-01-02"),
            symbol="TEST",
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
        ),
    )
    assert not decision.accepted
    assert "halted" in decision.reason


def test_confidence_scaling() -> None:
    sizer = PositionSizer(PositionSizingConfig(max_position_pct=0.10, confidence_scaling=True))
    book = Portfolio(10_000)
    qty = sizer.target_quantity(_buy(confidence=0.5), book, 100)
    assert qty == pytest.approx(5)
