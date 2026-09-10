"""Pydantic schemas for trading agent and risk management APIs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentConfigUpdate(BaseModel):
    name: str | None = None
    trading_type: Literal["options", "day_trading", "long_term", "mixed"] | None = None
    risk_profile: Literal["low", "medium", "high", "custom"] | None = None
    risk_config: dict[str, Any] | None = None
    capital_allocation: float | None = Field(default=None, gt=0)
    forecast_enabled: bool | None = None
    universe: list[str] | None = None
    live_trading_enabled: bool | None = None
    live_confirmation: str | None = None


class DailyLossUpdate(BaseModel):
    max_daily_loss_enabled: bool | None = None
    max_daily_loss_amount: float | None = Field(default=None, ge=0)
    max_daily_loss_percent: float | None = Field(default=None, ge=0, le=100)
    daily_loss_calculation: (
        Literal[
            "realized_only",
            "realized_plus_unrealized",
            "realized_plus_unrealized_plus_fees",
        ]
        | None
    ) = None
    daily_loss_reset_time: str | None = None
    daily_loss_timezone: str | None = None
    daily_loss_action: (
        Literal[
            "pause_agent",
            "cancel_open_orders",
            "cancel_orders_and_pause",
            "emergency_stop",
        ]
        | None
    ) = None
    daily_loss_warning_pct: float | None = Field(default=None, ge=0, le=100)
    daily_loss_critical_pct: float | None = Field(default=None, ge=0, le=100)


class RiskManagementUpdate(BaseModel):
    risk_profile: Literal["low", "medium", "high", "custom"] | None = None
    risk_config: dict[str, Any] | None = None


class AgentStartRequest(BaseModel):
    mode: Literal["paper", "live"] = "paper"
    live_confirmation: str | None = None


class CycleRequest(BaseModel):
    symbols: list[str] | None = None
    execute: bool = True
