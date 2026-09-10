"""Risk engine unit tests."""

from __future__ import annotations

import pytest

from app.trading_agent.risk_engine import (
    ForecastResult,
    PortfolioSnapshot,
    RiskEngine,
    TradeCandidateInput,
)
from app.trading_agent.risk_profiles import get_risk_config, validate_risk_config


def _forecast(**kwargs):
    base = dict(
        symbol="NVDA",
        signal="BUY",
        confidence=0.82,
        forecast_horizon="5d",
        expected_return=0.03,
        downside_risk=0.01,
        forecast_version="v1",
        generated_at="2026-09-10T00:00:00+00:00",
        features_snapshot_id="feat1",
        model_name="hybrid",
    )
    base.update(kwargs)
    return ForecastResult(**base)


def _portfolio(**kwargs):
    base = dict(
        equity=25_000,
        cash=25_000,
        buying_power=25_000,
        positions=[],
        open_orders=[],
        realized_pnl_today=0,
        unrealized_pnl=0,
        trading_fees_today=0,
        starting_daily_equity=25_000,
        peak_equity=25_000,
    )
    base.update(kwargs)
    return PortfolioSnapshot(**base)


def _candidate(**kwargs):
    base = dict(
        symbol="NVDA",
        side="buy",
        asset_type="equity",
        strategy="long_equity",
        quantity=10,
        entry_price=100,
        stop_loss=98,
        take_profit=104,
        trading_mode="mixed",
        market_open=True,
        forecast=_forecast(),
    )
    base.update(kwargs)
    return TradeCandidateInput(**base)


def test_low_risk_rejects_oversized_trade():
    engine = RiskEngine()
    risk = get_risk_config("low")
    # 10% of equity vs 5% max
    decision = engine.evaluate(
        _candidate(quantity=30, entry_price=100),  # $3000 = 12%
        _portfolio(),
        risk,
        agent_status="paper",
    )
    assert decision.approved is False
    assert "Position size" in decision.reason


def test_custom_overrides_preset():
    engine = RiskEngine()
    risk = get_risk_config("low", {"max_position_size_pct": 0.20})
    decision = engine.evaluate(
        _candidate(quantity=30, entry_price=100),
        _portfolio(),
        risk,
        agent_status="paper",
    )
    assert decision.approved is True


def test_daily_loss_blocks_new_trades():
    engine = RiskEngine()
    risk = get_risk_config("medium")
    risk["max_daily_loss_amount"] = 100
    decision = engine.evaluate(
        _candidate(),
        _portfolio(realized_pnl_today=-150, equity=24_850),
        risk,
        agent_status="paper",
    )
    assert decision.approved is False
    assert "daily loss" in decision.reason.lower()
    assert decision.checks.get("daily_loss_blocked") is True


@pytest.mark.parametrize("mode", ["options", "day_trading", "long_term", "mixed"])
def test_daily_loss_blocks_all_modes(mode):
    engine = RiskEngine()
    risk = get_risk_config("medium")
    risk["max_daily_loss_amount"] = 50
    decision = engine.evaluate(
        _candidate(trading_mode=mode, asset_type="option" if mode == "options" else "equity",
                   option_strategy="long_call" if mode == "options" else None,
                   strategy="long_call" if mode == "options" else "long_equity",
                   quantity=1, entry_price=2.0, max_loss=200),
        _portfolio(realized_pnl_today=-80, equity=24_920),
        risk,
        agent_status="paper",
    )
    assert decision.approved is False


def test_weekly_and_monthly_loss_limits():
    engine = RiskEngine()
    risk = get_risk_config("medium")
    risk["max_weekly_loss_percent"] = 1.0
    decision = engine.evaluate(
        _candidate(),
        _portfolio(weekly_pnl=-500),
        risk,
        agent_status="paper",
    )
    assert decision.approved is False
    assert "Weekly loss" in decision.reason

    risk = get_risk_config("medium")
    risk["max_monthly_loss_percent"] = 1.0
    decision = engine.evaluate(
        _candidate(),
        _portfolio(monthly_pnl=-500),
        risk,
        agent_status="paper",
    )
    assert decision.approved is False
    assert "Monthly loss" in decision.reason


def test_drawdown_blocks():
    engine = RiskEngine()
    risk = get_risk_config("low")  # 5% drawdown
    decision = engine.evaluate(
        _candidate(),
        _portfolio(equity=23_000, peak_equity=25_000),
        risk,
        agent_status="paper",
    )
    assert decision.approved is False
    assert "drawdown" in decision.reason.lower()


def test_sector_concentration_blocks():
    engine = RiskEngine()
    risk = get_risk_config("medium")
    risk["max_positions_per_sector"] = 1
    decision = engine.evaluate(
        _candidate(symbol="MSFT", sector="Technology"),
        _portfolio(positions=[{"symbol": "AAPL", "quantity": 5, "sector": "Technology"}]),
        risk,
        agent_status="paper",
    )
    assert decision.approved is False
    assert "Sector" in decision.reason


def test_options_max_loss_check():
    engine = RiskEngine()
    risk = get_risk_config("medium")
    risk["max_loss_per_options_position"] = 100
    risk["max_risk_per_trade_pct"] = 0.10
    risk["max_premium_per_trade"] = 5_000
    decision = engine.evaluate(
        _candidate(
            asset_type="option",
            trading_mode="options",
            strategy="long_call",
            option_strategy="long_call",
            quantity=2,
            entry_price=3.0,
            max_loss=600,
            days_to_expiration=30,
            implied_volatility=0.3,
            bid_ask_spread=0.05,
        ),
        _portfolio(),
        risk,
        agent_status="paper",
    )
    assert decision.approved is False
    assert "Options max loss" in decision.reason


def test_naked_options_rejected_by_default():
    engine = RiskEngine()
    risk = get_risk_config("high")
    decision = engine.evaluate(
        _candidate(
            asset_type="option",
            trading_mode="options",
            strategy="short_call",
            option_strategy="short_call",
            side="sell",
            quantity=1,
            entry_price=2.0,
            is_naked=True,
            days_to_expiration=30,
        ),
        _portfolio(positions=[{"symbol": "NVDA", "quantity": 100}]),
        risk,
        agent_status="paper",
    )
    assert decision.approved is False


def test_invalid_risk_configuration_rejected():
    errors = validate_risk_config({"max_position_size_pct": 2.0})
    assert errors
    engine = RiskEngine()
    decision = engine.evaluate(
        _candidate(),
        _portfolio(),
        {"max_position_size_pct": 2.0, "max_portfolio_exposure": 0.5},
        agent_status="paper",
    )
    assert decision.approved is False
    assert "Invalid risk configuration" in decision.reason


def test_day_trading_requires_market_open():
    engine = RiskEngine()
    risk = get_risk_config("medium")
    decision = engine.evaluate(
        _candidate(trading_mode="day_trading", market_open=False),
        _portfolio(),
        risk,
        agent_status="paper",
    )
    assert decision.approved is False
    assert "Market is closed" in decision.reason


def test_live_requires_explicit_enablement():
    engine = RiskEngine()
    risk = get_risk_config("medium")
    decision = engine.evaluate(
        _candidate(),
        _portfolio(),
        risk,
        agent_status="live",
        live_trading_enabled=False,
    )
    assert decision.approved is False
    assert "Live trading" in decision.reason


def test_paused_and_emergency_stop_block():
    engine = RiskEngine()
    risk = get_risk_config("medium")
    assert engine.evaluate(_candidate(), _portfolio(), risk, agent_status="paused").approved is False
    assert engine.evaluate(_candidate(), _portfolio(), risk, agent_status="emergency_stop").approved is False


def test_duplicate_order_blocked():
    engine = RiskEngine()
    risk = get_risk_config("medium")
    decision = engine.evaluate(
        _candidate(),
        _portfolio(open_orders=[{"symbol": "NVDA", "side": "buy", "status": "pending"}]),
        risk,
        agent_status="paper",
    )
    assert decision.approved is False
    assert "Duplicate" in decision.reason
