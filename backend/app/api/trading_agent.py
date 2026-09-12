"""Autonomous Trading Agent API routes."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Annotated, Any, Iterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_user_broker_credentials, use_trading_credentials
from app.db import get_session
from app.dependencies import enforce_rate_limit, get_services
from app.models import User
from app.trading_agent.schemas import AgentConfigUpdate, AgentStartRequest, CycleRequest, DailyLossUpdate
from app.trading_agent.service import TradingAgentService, build_trading_agent_service


router = APIRouter(tags=["trading-agent"])
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]


def _agent(request: Request) -> TradingAgentService:
    services = get_services(request)
    existing = getattr(services, "trading_agent", None)
    if existing is None:
        existing = build_trading_agent_service(services)
        services.trading_agent = existing  # type: ignore[attr-defined]
    return existing


def _config(session: Session, user: User, agent: TradingAgentService):
    return agent.get_or_create_config(session, user.id)


def _broker_mode(config: Any, *, requested_mode: str | None = None) -> str:
    mode = requested_mode or getattr(config, "mode", None) or "paper"
    if mode == "live" and bool(getattr(config, "live_trading_enabled", False)):
        return "live"
    return "paper"


@contextmanager
def _trading_credentials(
    request: Request,
    session: Session,
    user: User,
    config: Any,
    *,
    requested_mode: str | None = None,
) -> Iterator[None]:
    """Bind Settings Alpaca keys when the agent routes orders through Alpaca."""
    agent = _agent(request)
    if getattr(agent, "alpaca", None) is None:
        yield
        return
    services = get_services(request)
    mode = _broker_mode(config, requested_mode=requested_mode)
    credentials = get_user_broker_credentials(session, services.settings, user, mode)
    with use_trading_credentials(credentials):
        yield


@router.get("/trading-agent/config")
def get_config(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    agent = _agent(request)
    config = _config(session, user, agent)
    return agent.config_payload(session, config)


@router.put("/trading-agent/config")
def put_config(
    body: AgentConfigUpdate,
    request: Request,
    user: UserDep,
    session: SessionDep,
) -> dict[str, Any]:
    enforce_rate_limit(request, "trading-agent-config", 60)
    agent = _agent(request)
    config = _config(session, user, agent)
    try:
        agent.update_config(session, config, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return agent.config_payload(session, config)


@router.post("/trading-agent/start")
def start_agent(
    body: AgentStartRequest,
    request: Request,
    user: UserDep,
    session: SessionDep,
) -> dict[str, Any]:
    enforce_rate_limit(request, "trading-agent-lifecycle", 30)
    agent = _agent(request)
    config = _config(session, user, agent)
    try:
        with _trading_credentials(request, session, user, config, requested_mode=body.mode):
            agent.start(session, config, mode=body.mode, live_confirmation=body.live_confirmation)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return agent.config_payload(session, config)


@router.post("/trading-agent/pause")
def pause_agent(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    enforce_rate_limit(request, "trading-agent-lifecycle", 30)
    agent = _agent(request)
    config = _config(session, user, agent)
    try:
        agent.pause(session, config)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return agent.config_payload(session, config)


@router.post("/trading-agent/resume")
def resume_agent(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    enforce_rate_limit(request, "trading-agent-lifecycle", 30)
    agent = _agent(request)
    config = _config(session, user, agent)
    try:
        with _trading_credentials(request, session, user, config):
            agent.resume(session, config)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return agent.config_payload(session, config)


@router.post("/trading-agent/emergency-stop")
def emergency_stop(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    enforce_rate_limit(request, "trading-agent-lifecycle", 30)
    agent = _agent(request)
    config = _config(session, user, agent)
    with _trading_credentials(request, session, user, config):
        agent.emergency_stop(session, config)
    return agent.config_payload(session, config)


@router.post("/trading-agent/cycle")
def run_cycle(
    body: CycleRequest,
    request: Request,
    user: UserDep,
    session: SessionDep,
) -> dict[str, Any]:
    enforce_rate_limit(request, "trading-agent-cycle", 20)
    agent = _agent(request)
    config = _config(session, user, agent)
    market_open = True
    services = get_services(request)
    try:
        with _trading_credentials(request, session, user, config):
            clock = services.alpaca.market_clock("paper")
            market_open = bool(clock.get("is_open")) if isinstance(clock, dict) else True
    except HTTPException:
        raise
    except Exception:
        market_open = True
    try:
        with _trading_credentials(request, session, user, config):
            return agent.run_cycle(
                session,
                config,
                symbols=body.symbols,
                execute=body.execute,
                market_open=market_open,
            )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/trading-agent/forecasts")
def get_forecasts(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    agent = _agent(request)
    config = _config(session, user, agent)
    return {"forecasts": agent.list_forecasts(session, config)}


@router.get("/trading-agent/candidates")
def get_candidates(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    agent = _agent(request)
    config = _config(session, user, agent)
    return {"candidates": agent.list_candidates(session, config)}


@router.get("/trading-agent/trade-plans")
def get_trade_plans(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    agent = _agent(request)
    config = _config(session, user, agent)
    return {"trade_plans": agent.list_trade_plans(session, config)}


@router.get("/trading-agent/orders")
def get_orders(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    agent = _agent(request)
    config = _config(session, user, agent)
    return {"orders": agent.list_orders(session, config)}


@router.get("/trading-agent/positions")
def get_positions(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    agent = _agent(request)
    config = _config(session, user, agent)
    return {"positions": agent.list_positions(session, config)}


@router.get("/trading-agent/events")
def get_events(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    agent = _agent(request)
    config = _config(session, user, agent)
    return {"events": agent.list_events(session, config)}


@router.get("/trading-agent/performance")
def get_performance(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    agent = _agent(request)
    config = _config(session, user, agent)
    return agent.performance(session, config)


@router.get("/trading-agent/daily-loss")
def get_daily_loss(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    agent = _agent(request)
    config = _config(session, user, agent)
    with _trading_credentials(request, session, user, config):
        return agent.get_daily_loss_snapshot(session, config)


@router.put("/trading-agent/daily-loss")
def put_daily_loss(
    body: DailyLossUpdate,
    request: Request,
    user: UserDep,
    session: SessionDep,
) -> dict[str, Any]:
    enforce_rate_limit(request, "trading-agent-config", 60)
    agent = _agent(request)
    config = _config(session, user, agent)
    try:
        with _trading_credentials(request, session, user, config):
            agent.update_daily_loss(session, config, body.model_dump(exclude_unset=True))
            return agent.get_daily_loss_snapshot(session, config)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/trading-agent/daily-loss/reset")
def reset_daily_loss(request: Request, user: UserDep, session: SessionDep) -> dict[str, Any]:
    enforce_rate_limit(request, "trading-agent-lifecycle", 10)
    agent = _agent(request)
    config = _config(session, user, agent)
    with _trading_credentials(request, session, user, config):
        return agent.reset_daily_loss(session, config)
