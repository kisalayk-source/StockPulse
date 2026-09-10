"""Risk management configuration API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_session
from app.dependencies import enforce_rate_limit, get_services
from app.models import User
from app.trading_agent.risk_profiles import RISK_PROFILE_DEFAULTS
from app.trading_agent.schemas import RiskManagementUpdate
from app.trading_agent.service import TradingAgentService, build_trading_agent_service


router = APIRouter(tags=["risk-management"])
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]


def _agent(request: Request) -> TradingAgentService:
    services = get_services(request)
    existing = getattr(services, "trading_agent", None)
    if existing is None:
        existing = build_trading_agent_service(services)
        services.trading_agent = existing  # type: ignore[attr-defined]
    return existing


@router.get("/risk-management/config")
def get_risk_config(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    agent = _agent(request)
    config = agent.get_or_create_config(session, user.id)
    return {
        "risk_profile": config.risk_profile,
        "risk_config": agent.resolved_risk_config(config),
        "profiles": {name: defaults for name, defaults in RISK_PROFILE_DEFAULTS.items()},
        "daily_loss": agent.get_daily_loss_snapshot(session, config),
    }


@router.put("/risk-management/config")
def put_risk_config(
    body: RiskManagementUpdate,
    request: Request,
    user: UserDep,
    session: SessionDep,
) -> dict[str, Any]:
    enforce_rate_limit(request, "risk-management", 60)
    agent = _agent(request)
    config = agent.get_or_create_config(session, user.id)
    try:
        agent.update_config(
            session,
            config,
            {
                "risk_profile": body.risk_profile,
                "risk_config": body.risk_config,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {
        "risk_profile": config.risk_profile,
        "risk_config": agent.resolved_risk_config(config),
        "daily_loss": agent.get_daily_loss_snapshot(session, config),
    }


@router.post("/risk-management/reset")
def reset_risk_config(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    """Reset risk config to the selected profile defaults (does not reset daily loss state)."""
    enforce_rate_limit(request, "risk-management", 20)
    agent = _agent(request)
    config = agent.get_or_create_config(session, user.id)
    profile = config.risk_profile or "medium"
    from app.trading_agent.risk_profiles import get_risk_config

    # Preserve daily-loss runtime state; only reset config values
    daily_keys = {
        "max_daily_loss_enabled",
        "max_daily_loss_amount",
        "max_daily_loss_percent",
        "daily_loss_calculation",
        "daily_loss_reset_time",
        "daily_loss_timezone",
        "daily_loss_action",
        "daily_loss_warning_pct",
        "daily_loss_critical_pct",
    }
    previous = dict(config.risk_config or {})
    fresh = get_risk_config(profile)
    for key in daily_keys:
        if key in previous:
            fresh[key] = previous[key]
    config.risk_config = fresh
    session.flush()
    return {
        "risk_profile": config.risk_profile,
        "risk_config": agent.resolved_risk_config(config),
        "daily_loss": agent.get_daily_loss_snapshot(session, config),
        "note": "Risk profile defaults restored; daily loss state was not reset",
    }
