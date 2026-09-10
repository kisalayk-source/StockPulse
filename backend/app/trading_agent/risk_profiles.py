"""Low / Medium / High / Custom risk profile defaults for the trading agent."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

RiskProfileName = Literal["low", "medium", "high", "custom"]

DailyLossCalculation = Literal[
    "realized_only",
    "realized_plus_unrealized",
    "realized_plus_unrealized_plus_fees",
]

DailyLossAction = Literal[
    "pause_agent",
    "cancel_open_orders",
    "cancel_orders_and_pause",
    "emergency_stop",
]


def _base_config() -> dict[str, Any]:
    return {
        # Portfolio risk
        "starting_capital": 25_000.0,
        "max_portfolio_exposure": 0.60,
        "max_invested_capital": None,
        "max_margin_usage": 0.0,
        "max_leverage": 1.0,
        "max_portfolio_drawdown": 0.10,
        "max_daily_loss_enabled": True,
        "max_daily_loss_amount": 500.0,
        "max_daily_loss_percent": 2.0,
        "daily_loss_calculation": "realized_plus_unrealized_plus_fees",
        "daily_loss_reset_time": "00:00",
        "daily_loss_timezone": "America/Los_Angeles",
        "daily_loss_action": "cancel_orders_and_pause",
        "daily_loss_warning_pct": 50.0,
        "daily_loss_critical_pct": 80.0,
        "max_weekly_loss_percent": 5.0,
        "max_monthly_loss_percent": 10.0,
        # Position risk
        "max_position_size_pct": 0.10,
        "max_position_size_amount": None,
        "max_risk_per_trade_pct": 0.01,
        "max_risk_per_trade_amount": None,
        "max_open_positions": 10,
        "max_positions_per_sector": 3,
        "max_positions_per_industry": 2,
        "max_correlation_exposure": 0.40,
        # Trade risk
        "default_stop_loss_pct": 0.02,
        "default_take_profit_pct": 0.04,
        "min_risk_reward_ratio": 1.5,
        "trailing_stop_enabled": False,
        "trailing_stop_pct": 0.01,
        "max_holding_period_days": 30,
        "min_forecast_confidence": 0.55,
        "min_expected_return": 0.005,
        # Options risk
        "allow_options": True,
        "allowed_option_strategies": [
            "long_call",
            "long_put",
            "covered_call",
            "cash_secured_put",
            "bull_call_spread",
            "bear_put_spread",
        ],
        "max_premium_per_trade": 500.0,
        "max_total_options_exposure": 0.20,
        "max_loss_per_options_position": 250.0,
        "max_options_loss_per_day": 500.0,
        "max_days_to_expiration": 60,
        "min_days_to_expiration": 7,
        "max_implied_volatility": 1.5,
        "max_bid_ask_spread": 0.15,
        "allow_assignment": False,
        "allow_exercise": False,
        "allow_naked_options": False,
        # Day trading risk
        "allow_day_trading": True,
        "max_trades_per_day": 10,
        "day_trading_max_daily_loss": None,
        "max_consecutive_losses": 3,
        "max_position_holding_minutes": 240,
        "close_positions_before_market_close": True,
        "min_liquidity": 200_000.0,
        "min_average_volume": 200_000.0,
        # Long-term risk
        "min_holding_period_days": 5,
        "long_term_max_holding_period_days": 365,
        "rebalancing_frequency_days": 30,
        "max_portfolio_turnover": 0.50,
        "forecast_deterioration_threshold": 0.20,
        "allow_averaging_down": False,
        "max_averaging_down_attempts": 0,
        # Agent safety
        "paper_trading_default": True,
        "require_confirmation_before_live": True,
        "require_confirmation_before_first_live_trade": True,
        "emergency_stop_enabled": True,
        "pause_after_consecutive_losses": True,
        "pause_after_drawdown_threshold": True,
        "pause_after_broker_errors": True,
        "max_order_value": 10_000.0,
        "max_order_quantity": 1_000.0,
        "capital_allocation": 10_000.0,
        "leverage_enabled": False,
        "short_selling_enabled": False,
        "defined_risk_options_only": True,
    }


RISK_PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    "low": {
        **_base_config(),
        "max_portfolio_exposure": 0.30,
        "max_position_size_pct": 0.05,
        "max_risk_per_trade_pct": 0.005,
        "max_daily_loss_percent": 1.0,
        "max_portfolio_drawdown": 0.05,
        "max_open_positions": 5,
        "defined_risk_options_only": True,
        "allow_naked_options": False,
        "leverage_enabled": False,
        "max_leverage": 1.0,
        "short_selling_enabled": False,
        "allow_day_trading": False,
        "min_forecast_confidence": 0.65,
    },
    "medium": {
        **_base_config(),
        "max_portfolio_exposure": 0.60,
        "max_position_size_pct": 0.10,
        "max_risk_per_trade_pct": 0.01,
        "max_daily_loss_percent": 2.0,
        "max_portfolio_drawdown": 0.10,
        "max_open_positions": 10,
        "defined_risk_options_only": True,
        "allow_naked_options": False,
        "leverage_enabled": True,
        "max_leverage": 1.5,
        "short_selling_enabled": False,
        "allow_day_trading": True,
        "min_forecast_confidence": 0.55,
    },
    "high": {
        **_base_config(),
        "max_portfolio_exposure": 1.0,
        "max_position_size_pct": 0.20,
        "max_risk_per_trade_pct": 0.02,
        "max_daily_loss_percent": 3.0,
        "max_portfolio_drawdown": 0.20,
        "max_open_positions": 20,
        "defined_risk_options_only": False,
        "allow_naked_options": False,
        "leverage_enabled": True,
        "max_leverage": 2.0,
        "short_selling_enabled": True,
        "allow_day_trading": True,
        "min_forecast_confidence": 0.50,
        "max_trades_per_day": 20,
    },
    "custom": _base_config(),
}


def get_risk_config(profile: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    key = (profile or "medium").lower()
    if key not in RISK_PROFILE_DEFAULTS:
        raise ValueError(f"Invalid risk profile: {profile}")
    config = deepcopy(RISK_PROFILE_DEFAULTS[key])
    if overrides:
        config = merge_risk_config(config, overrides)
    return config


def merge_risk_config(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overrides.items():
        if value is None:
            continue
        merged[key] = deepcopy(value)
    return merged


def validate_risk_config(config: dict[str, Any]) -> list[str]:
    """Return validation error messages (empty if valid)."""
    errors: list[str] = []
    pct_fields = (
        "max_portfolio_exposure",
        "max_position_size_pct",
        "max_risk_per_trade_pct",
        "max_portfolio_drawdown",
        "max_total_options_exposure",
    )
    for field in pct_fields:
        value = config.get(field)
        if value is not None and (float(value) < 0 or float(value) > 1.0):
            errors.append(f"{field} must be between 0 and 1")
    if config.get("max_daily_loss_percent") is not None:
        pct = float(config["max_daily_loss_percent"])
        if pct < 0 or pct > 100:
            errors.append("max_daily_loss_percent must be between 0 and 100")
    if config.get("max_daily_loss_amount") is not None and float(config["max_daily_loss_amount"]) < 0:
        errors.append("max_daily_loss_amount must be >= 0")
    if config.get("max_open_positions") is not None and int(config["max_open_positions"]) < 1:
        errors.append("max_open_positions must be >= 1")
    if config.get("allow_naked_options") and config.get("defined_risk_options_only"):
        errors.append("allow_naked_options conflicts with defined_risk_options_only")
    calc = config.get("daily_loss_calculation")
    if calc is not None and calc not in (
        "realized_only",
        "realized_plus_unrealized",
        "realized_plus_unrealized_plus_fees",
    ):
        errors.append(f"Invalid daily_loss_calculation: {calc}")
    action = config.get("daily_loss_action")
    if action is not None and action not in (
        "pause_agent",
        "cancel_open_orders",
        "cancel_orders_and_pause",
        "emergency_stop",
    ):
        errors.append(f"Invalid daily_loss_action: {action}")
    return errors
