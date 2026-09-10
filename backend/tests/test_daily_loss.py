"""Unit tests for daily loss calculation and reset rules."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.trading_agent.daily_loss import (
    DailyLossService,
    classify_daily_loss_status,
    compute_daily_loss_amount,
    effective_daily_loss_limit,
    next_reset_datetime,
    trading_date_for,
)
from app.trading_agent.risk_profiles import get_risk_config


def test_realized_only_calculation():
    loss = compute_daily_loss_amount(
        realized_pnl=-200,
        unrealized_pnl=-300,
        trading_fees=10,
        calculation="realized_only",
    )
    assert loss == 200


def test_realized_plus_unrealized_calculation():
    loss = compute_daily_loss_amount(
        realized_pnl=-100,
        unrealized_pnl=-150,
        trading_fees=25,
        calculation="realized_plus_unrealized",
    )
    assert loss == 250


def test_fees_included_when_configured():
    loss = compute_daily_loss_amount(
        realized_pnl=-100,
        unrealized_pnl=-100,
        trading_fees=50,
        calculation="realized_plus_unrealized_plus_fees",
    )
    assert loss == 250


def test_profitable_day_has_zero_loss():
    loss = compute_daily_loss_amount(
        realized_pnl=100,
        unrealized_pnl=50,
        trading_fees=10,
        calculation="realized_plus_unrealized_plus_fees",
    )
    assert loss == 0


def test_dollar_and_percent_limits_use_minimum():
    # 2% of 25k = 500; dollar limit 400 → effective 400
    assert effective_daily_loss_limit(
        starting_equity=25_000,
        max_daily_loss_amount=400,
        max_daily_loss_percent=2.0,
    ) == 400
    # 2% of 25k = 500; dollar 600 → effective 500
    assert effective_daily_loss_limit(
        starting_equity=25_000,
        max_daily_loss_amount=600,
        max_daily_loss_percent=2.0,
    ) == 500


def test_percentage_based_daily_loss_blocks():
    svc = DailyLossService()
    risk = get_risk_config("medium")
    risk["max_daily_loss_amount"] = None
    risk["max_daily_loss_percent"] = 2.0
    snap = svc.evaluate(
        starting_equity=25_000,
        current_equity=24_500,
        realized_pnl=-400,
        unrealized_pnl=-100,
        trading_fees=0,
        risk_config=risk,
    )
    assert snap.daily_loss == 500
    assert snap.limit_reached is True
    assert snap.status == "blocked"
    assert snap.remaining_daily_loss == 0


def test_warning_and_critical_thresholds():
    status, util, warnings = classify_daily_loss_status(daily_loss=250, limit=500, warning_pct=50, critical_pct=80)
    assert status == "warning"
    assert util == 50
    status, util, warnings = classify_daily_loss_status(daily_loss=400, limit=500, warning_pct=50, critical_pct=80)
    assert status == "critical"
    status, util, warnings = classify_daily_loss_status(daily_loss=500, limit=500)
    assert status == "blocked"


def test_trading_date_respects_timezone_and_reset():
    # 11pm PT on Sep 9 → still Sep 9 if reset is midnight
    now = datetime(2026, 9, 10, 6, 30, tzinfo=ZoneInfo("UTC"))  # 11:30pm PT Sep 9
    day = trading_date_for(now, "America/Los_Angeles", "00:00")
    assert day.isoformat() == "2026-09-09"
    # After midnight PT
    now2 = datetime(2026, 9, 10, 8, 0, tzinfo=ZoneInfo("UTC"))  # 1am PT Sep 10
    day2 = trading_date_for(now2, "America/Los_Angeles", "00:00")
    assert day2.isoformat() == "2026-09-10"


def test_next_reset_datetime():
    now = datetime(2026, 9, 10, 15, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    nxt = next_reset_datetime(now, "America/Los_Angeles", "00:00")
    assert nxt.day == 11
    assert nxt.hour == 0


def test_service_snapshot_includes_today_pnl_and_remaining():
    svc = DailyLossService()
    risk = get_risk_config("low")
    risk["max_daily_loss_amount"] = 500
    risk["max_daily_loss_percent"] = 5.0
    snap = svc.evaluate(
        starting_equity=25_000,
        current_equity=24_875,
        realized_pnl=-100,
        unrealized_pnl=-25,
        trading_fees=0,
        risk_config=risk,
    )
    assert snap.today_pnl == -125
    assert snap.daily_loss == 125
    assert snap.remaining_daily_loss == 375
    assert snap.status == "active"
    payload = snap.to_dict()
    assert payload["remaining_daily_loss"] == 375
    assert payload["enabled"] is True


@pytest.mark.parametrize(
    "mode",
    ["options", "day_trading", "long_term", "mixed"],
)
def test_daily_loss_applies_conceptually_to_all_modes(mode):
    # Mode-agnostic calculation — enforcement is in RiskEngine
    svc = DailyLossService()
    risk = get_risk_config("medium")
    risk["max_daily_loss_amount"] = 100
    snap = svc.evaluate(
        starting_equity=10_000,
        current_equity=9_850,
        realized_pnl=-150,
        unrealized_pnl=0,
        trading_fees=0,
        risk_config=risk,
    )
    assert snap.limit_reached is True
    assert mode  # parametrize ensures we cover naming for all modes
