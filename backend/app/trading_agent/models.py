"""SQLAlchemy models for the Autonomous Trading Agent."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="Default Agent")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # disabled | configured | paper | paused | live | emergency_stop
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="disabled")
    # paper | live
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="paper")
    # options | day_trading | long_term | mixed
    trading_type: Mapped[str] = mapped_column(String(32), nullable=False, default="mixed")
    risk_profile: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    risk_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    capital_allocation: Mapped[float] = mapped_column(Float, nullable=False, default=10_000.0)
    forecast_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    live_trading_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    live_confirmation_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    broker_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    universe: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    runs: Mapped[list["AgentRun"]] = relationship(back_populates="config", cascade="all, delete-orphan")
    events: Mapped[list["AgentEvent"]] = relationship(back_populates="config", cascade="all, delete-orphan")
    daily_loss_records: Mapped[list["DailyLossRecord"]] = relationship(
        back_populates="config", cascade="all, delete-orphan"
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_config_id: Mapped[int] = mapped_column(
        ForeignKey("agent_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    forecast_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    summary: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    config: Mapped[AgentConfig] = relationship(back_populates="runs")
    candidates: Mapped[list["TradeCandidate"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class TradeCandidate(Base):
    __tablename__ = "trade_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_run_id: Mapped[int] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False, default="equity")
    strategy: Mapped[str] = mapped_column(String(64), nullable=False, default="long_equity")
    forecast_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    risk_decision: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    run: Mapped[AgentRun] = relationship(back_populates="candidates")
    plans: Mapped[list["TradePlan"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")


class TradePlan(Base):
    __tablename__ = "trade_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_candidate_id: Mapped[int] = mapped_column(
        ForeignKey("trade_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position_size: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    risk_reward_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    plan_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    candidate: Mapped[TradeCandidate] = relationship(back_populates="plans")
    orders: Mapped[list["AgentOrder"]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class AgentOrder(Base):
    __tablename__ = "agent_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_plan_id: Mapped[int] = mapped_column(
        ForeignKey("trade_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    broker_order_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    average_fill_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False, default="buy")
    order_type: Mapped[str] = mapped_column(String(16), nullable=False, default="market")
    requested_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    plan: Mapped[TradePlan] = relationship(back_populates="orders")


class AgentPosition(Base):
    __tablename__ = "agent_positions"
    __table_args__ = (UniqueConstraint("user_id", "symbol", "asset_type", name="uq_agent_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_config_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("agent_configs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False, default="equity")
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    average_entry_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sector: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )


class DailyLossRecord(Base):
    __tablename__ = "daily_loss_records"
    __table_args__ = (
        UniqueConstraint("agent_config_id", "trading_date", "timezone", name="uq_daily_loss_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_config_id: Mapped[int] = mapped_column(
        ForeignKey("agent_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="America/Los_Angeles")
    starting_equity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_equity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trading_fees: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    daily_loss: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    daily_loss_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_daily_loss_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_daily_loss_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # active | warning | critical | blocked
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    trades_blocked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    config: Mapped[AgentConfig] = relationship(back_populates="daily_loss_records")


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_config_id: Mapped[int] = mapped_column(
        ForeignKey("agent_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)

    config: Mapped[AgentConfig] = relationship(back_populates="events")
