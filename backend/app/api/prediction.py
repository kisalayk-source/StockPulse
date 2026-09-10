"""Hybrid prediction API routes."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.routes import market_provider_call
from app.auth import get_current_user
from app.db import get_session
from app.dependencies import Services, enforce_rate_limit, get_services
from app.models import User
from app.services.providers import ProviderUnavailable


router = APIRouter(tags=["prediction"])
ServiceDep = Annotated[Services, Depends(get_services)]
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]
_TICKER = re.compile(r"^[A-Za-z][A-Za-z.\-]{0,15}$")


def _ticker(symbol: str) -> str:
    value = symbol.strip().upper()
    if not _TICKER.fullmatch(value):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid ticker")
    return value


def _prediction_service(services: Services):
    service = getattr(services, "prediction", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Prediction service unavailable",
        )
    return service


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ProviderUnavailable:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Prediction failed: {type(exc).__name__}",
        ) from exc


def _prediction_provider_call(
    user: User,
    session: Session,
    services: Services,
    function: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run prediction with the caller's saved Alpaca keys (same as market data)."""
    return market_provider_call(
        user,
        session,
        services,
        _call,
        function,
        *args,
        **kwargs,
    )


@router.get("/stocks/{ticker}/prediction")
async def get_prediction(
    ticker: str,
    services: ServiceDep,
    request: Request,
    user: UserDep,
    session: SessionDep,
    horizon: str = Query(default="5d", pattern=r"^(1d|5d|20d)$"),
    retrain: bool = Query(default=False),
) -> dict[str, Any]:
    enforce_rate_limit(
        request,
        "prediction",
        getattr(services.settings, "prediction_rate_limit_per_minute", 30),
    )
    service = _prediction_service(services)
    symbol = _ticker(ticker)
    return await run_in_threadpool(
        _prediction_provider_call,
        user,
        session,
        services,
        service.predict,
        symbol,
        horizon=horizon,
        retrain=retrain,
    )


@router.get("/stocks/{ticker}/features")
async def get_features(
    ticker: str,
    services: ServiceDep,
    request: Request,
    user: UserDep,
    session: SessionDep,
) -> dict[str, Any]:
    enforce_rate_limit(
        request,
        "prediction_features",
        getattr(services.settings, "prediction_rate_limit_per_minute", 30),
    )
    service = _prediction_service(services)
    symbol = _ticker(ticker)
    return await run_in_threadpool(
        _prediction_provider_call,
        user,
        session,
        services,
        service.features,
        symbol,
    )


@router.get("/stocks/{ticker}/signals")
async def get_signals(
    ticker: str,
    services: ServiceDep,
    request: Request,
    user: UserDep,
    session: SessionDep,
    horizon: str = Query(default="5d", pattern=r"^(1d|5d|20d)$"),
) -> dict[str, Any]:
    enforce_rate_limit(
        request,
        "prediction_signals",
        getattr(services.settings, "prediction_rate_limit_per_minute", 30),
    )
    service = _prediction_service(services)
    symbol = _ticker(ticker)
    return await run_in_threadpool(
        _prediction_provider_call,
        user,
        session,
        services,
        service.signals,
        symbol,
        horizon=horizon,
    )


@router.get("/stocks/{ticker}/risk")
async def get_risk(
    ticker: str,
    services: ServiceDep,
    request: Request,
    user: UserDep,
    session: SessionDep,
    horizon: str = Query(default="5d", pattern=r"^(1d|5d|20d)$"),
) -> dict[str, Any]:
    enforce_rate_limit(
        request,
        "prediction_risk",
        getattr(services.settings, "prediction_rate_limit_per_minute", 30),
    )
    service = _prediction_service(services)
    symbol = _ticker(ticker)
    return await run_in_threadpool(
        _prediction_provider_call,
        user,
        session,
        services,
        service.risk,
        symbol,
        horizon=horizon,
    )


@router.get("/stocks/{ticker}/explanation")
async def get_explanation(
    ticker: str,
    services: ServiceDep,
    request: Request,
    user: UserDep,
    session: SessionDep,
    horizon: str = Query(default="5d", pattern=r"^(1d|5d|20d)$"),
) -> dict[str, Any]:
    enforce_rate_limit(
        request,
        "prediction_explanation",
        getattr(services.settings, "prediction_rate_limit_per_minute", 30),
    )
    service = _prediction_service(services)
    symbol = _ticker(ticker)
    return await run_in_threadpool(
        _prediction_provider_call,
        user,
        session,
        services,
        service.explanation,
        symbol,
        horizon=horizon,
    )
