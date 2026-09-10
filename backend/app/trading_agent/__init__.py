"""Autonomous Trading Agent — forecast-driven paper/live execution with risk controls."""

from app.trading_agent.risk_profiles import RISK_PROFILE_DEFAULTS, get_risk_config, merge_risk_config

__all__ = [
    "RISK_PROFILE_DEFAULTS",
    "get_risk_config",
    "merge_risk_config",
]
