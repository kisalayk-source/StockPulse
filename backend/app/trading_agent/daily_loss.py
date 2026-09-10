"""Centralized daily loss calculation and enforcement helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

DailyLossStatus = Literal["active", "warning", "critical", "blocked"]
DailyLossCalculation = Literal[
    "realized_only",
    "realized_plus_unrealized",
    "realized_plus_unrealized_plus_fees",
]


@dataclass
class DailyLossSnapshot:
    trading_date: date
    timezone: str
    starting_equity: float
    current_equity: float
    realized_pnl: float
    unrealized_pnl: float
    trading_fees: float
    today_pnl: float
    daily_loss: float
    daily_loss_percent: float
    max_daily_loss_amount: float | None
    max_daily_loss_percent: float | None
    effective_limit: float | None
    remaining_daily_loss: float | None
    status: DailyLossStatus
    limit_reached: bool
    enabled: bool
    calculation: str
    action: str
    last_reset_at: datetime | None
    next_reset_at: datetime | None
    warning_threshold_pct: float = 50.0
    critical_threshold_pct: float = 80.0
    utilization_pct: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trading_date": self.trading_date.isoformat(),
            "timezone": self.timezone,
            "starting_equity": self.starting_equity,
            "current_equity": self.current_equity,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "trading_fees": self.trading_fees,
            "today_pnl": self.today_pnl,
            "daily_loss": self.daily_loss,
            "daily_loss_percent": self.daily_loss_percent,
            "max_daily_loss_amount": self.max_daily_loss_amount,
            "max_daily_loss_percent": self.max_daily_loss_percent,
            "effective_limit": self.effective_limit,
            "remaining_daily_loss": self.remaining_daily_loss,
            "status": self.status,
            "limit_reached": self.limit_reached,
            "enabled": self.enabled,
            "calculation": self.calculation,
            "action": self.action,
            "last_reset_at": self.last_reset_at.isoformat() if self.last_reset_at else None,
            "next_reset_at": self.next_reset_at.isoformat() if self.next_reset_at else None,
            "warning_threshold_pct": self.warning_threshold_pct,
            "critical_threshold_pct": self.critical_threshold_pct,
            "utilization_pct": self.utilization_pct,
            "warnings": self.warnings,
        }


def parse_reset_time(value: str) -> time:
    hour_s, minute_s = value.split(":", 1)
    return time(hour=int(hour_s), minute=int(minute_s))


def trading_date_for(now: datetime, tz_name: str, reset_hhmm: str) -> date:
    tz = ZoneInfo(tz_name)
    local = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=timezone.utc).astimezone(tz)
    reset = parse_reset_time(reset_hhmm)
    boundary = datetime.combine(local.date(), reset, tzinfo=tz)
    if local < boundary:
        return local.date() - timedelta(days=1)
    return local.date()


def next_reset_datetime(now: datetime, tz_name: str, reset_hhmm: str) -> datetime:
    tz = ZoneInfo(tz_name)
    local = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=timezone.utc).astimezone(tz)
    reset = parse_reset_time(reset_hhmm)
    candidate = datetime.combine(local.date(), reset, tzinfo=tz)
    if local >= candidate:
        candidate = candidate + timedelta(days=1)
    return candidate


def compute_daily_loss_amount(
    *,
    realized_pnl: float,
    unrealized_pnl: float,
    trading_fees: float,
    calculation: DailyLossCalculation,
) -> float:
    """Return loss as a non-negative number (0 when flat or profitable)."""
    if calculation == "realized_only":
        pnl = realized_pnl
    elif calculation == "realized_plus_unrealized":
        pnl = realized_pnl + unrealized_pnl
    else:
        pnl = realized_pnl + unrealized_pnl - abs(trading_fees)
    return max(0.0, -pnl)


def compute_today_pnl(
    *,
    realized_pnl: float,
    unrealized_pnl: float,
    trading_fees: float,
    calculation: DailyLossCalculation,
) -> float:
    if calculation == "realized_only":
        return realized_pnl
    if calculation == "realized_plus_unrealized":
        return realized_pnl + unrealized_pnl
    return realized_pnl + unrealized_pnl - abs(trading_fees)


def effective_daily_loss_limit(
    *,
    starting_equity: float,
    max_daily_loss_amount: float | None,
    max_daily_loss_percent: float | None,
) -> float | None:
    limits: list[float] = []
    if max_daily_loss_amount is not None and max_daily_loss_amount > 0:
        limits.append(float(max_daily_loss_amount))
    if max_daily_loss_percent is not None and max_daily_loss_percent > 0 and starting_equity > 0:
        limits.append(starting_equity * float(max_daily_loss_percent) / 100.0)
    if not limits:
        return None
    return min(limits)


def classify_daily_loss_status(
    *,
    daily_loss: float,
    limit: float | None,
    warning_pct: float = 50.0,
    critical_pct: float = 80.0,
) -> tuple[DailyLossStatus, float, list[str]]:
    warnings: list[str] = []
    if limit is None or limit <= 0:
        return "active", 0.0, warnings
    utilization = (daily_loss / limit) * 100.0
    if daily_loss >= limit:
        warnings.append("Max daily loss limit reached; new trades are blocked")
        return "blocked", utilization, warnings
    if utilization >= critical_pct:
        warnings.append(f"Critical: daily loss at {utilization:.0f}% of limit")
        return "critical", utilization, warnings
    if utilization >= warning_pct:
        warnings.append(f"Warning: daily loss at {utilization:.0f}% of limit")
        return "warning", utilization, warnings
    return "active", utilization, warnings


class DailyLossService:
    """Pure calculation service — persistence is handled by the agent service."""

    def evaluate(
        self,
        *,
        starting_equity: float,
        current_equity: float,
        realized_pnl: float,
        unrealized_pnl: float,
        trading_fees: float,
        risk_config: dict[str, Any],
        now: datetime | None = None,
        last_reset_at: datetime | None = None,
        enabled: bool | None = None,
    ) -> DailyLossSnapshot:
        now = now or datetime.now(timezone.utc)
        tz_name = str(risk_config.get("daily_loss_timezone") or "America/Los_Angeles")
        reset_hhmm = str(risk_config.get("daily_loss_reset_time") or "00:00")
        calculation = str(
            risk_config.get("daily_loss_calculation") or "realized_plus_unrealized_plus_fees"
        )
        max_amount = risk_config.get("max_daily_loss_amount")
        max_pct = risk_config.get("max_daily_loss_percent")
        warning_pct = float(risk_config.get("daily_loss_warning_pct") or 50.0)
        critical_pct = float(risk_config.get("daily_loss_critical_pct") or 80.0)
        enabled_flag = (
            bool(risk_config.get("max_daily_loss_enabled", True)) if enabled is None else enabled
        )
        action = str(risk_config.get("daily_loss_action") or "cancel_orders_and_pause")

        trading_day = trading_date_for(now, tz_name, reset_hhmm)
        daily_loss = compute_daily_loss_amount(
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            trading_fees=trading_fees,
            calculation=calculation,  # type: ignore[arg-type]
        )
        today_pnl = compute_today_pnl(
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            trading_fees=trading_fees,
            calculation=calculation,  # type: ignore[arg-type]
        )
        daily_loss_pct = (daily_loss / starting_equity * 100.0) if starting_equity > 0 else 0.0
        limit = (
            effective_daily_loss_limit(
                starting_equity=starting_equity,
                max_daily_loss_amount=float(max_amount) if max_amount is not None else None,
                max_daily_loss_percent=float(max_pct) if max_pct is not None else None,
            )
            if enabled_flag
            else None
        )
        status, utilization, warnings = classify_daily_loss_status(
            daily_loss=daily_loss,
            limit=limit,
            warning_pct=warning_pct,
            critical_pct=critical_pct,
        )
        if not enabled_flag:
            status = "active"
            utilization = 0.0
            warnings = []
            limit = None

        remaining = None if limit is None else max(0.0, limit - daily_loss)
        return DailyLossSnapshot(
            trading_date=trading_day,
            timezone=tz_name,
            starting_equity=starting_equity,
            current_equity=current_equity,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            trading_fees=trading_fees,
            today_pnl=today_pnl,
            daily_loss=daily_loss,
            daily_loss_percent=daily_loss_pct,
            max_daily_loss_amount=float(max_amount) if max_amount is not None else None,
            max_daily_loss_percent=float(max_pct) if max_pct is not None else None,
            effective_limit=limit,
            remaining_daily_loss=remaining,
            status=status,
            limit_reached=status == "blocked",
            enabled=enabled_flag,
            calculation=calculation,
            action=action,
            last_reset_at=last_reset_at,
            next_reset_at=next_reset_datetime(now, tz_name, reset_hhmm),
            warning_threshold_pct=warning_pct,
            critical_threshold_pct=critical_pct,
            utilization_pct=utilization,
            warnings=warnings,
        )
