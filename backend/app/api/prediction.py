"""Hybrid prediction API routes."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth import (
    BrokerCredentials,
    get_current_user,
    resolve_market_broker_credentials,
    use_trading_credentials,
)
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


def _safe_exception_detail(exc: BaseException) -> str:
    """Return a short, non-sensitive detail for API clients."""
    message = str(exc).strip()
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        missing = getattr(exc, "name", None) or message or type(exc).__name__
        return (
            f"Prediction dependency missing ({missing}). "
            "Install backend/requirements.txt (includes xgboost) and restart the API."
        )
    if message and len(message) <= 240:
        return f"Prediction failed: {type(exc).__name__}: {message}"
    return f"Prediction failed: {type(exc).__name__}"


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ProviderUnavailable as exc:
        message = str(exc) or "Provider unavailable"
        # Surface missing Settings keys clearly (same wording users already see).
        if "credentials are not configured" in message.casefold():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Configure Alpaca paper credentials in Settings before loading hybrid prediction",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"provider": exc.provider, "message": message},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except (ImportError, ModuleNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_safe_exception_detail(exc),
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_safe_exception_detail(exc),
        ) from exc


def _prediction_with_credentials(
    credentials: BrokerCredentials | None,
    function: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run prediction under saved Alpaca keys resolved on the request thread."""
    with use_trading_credentials(credentials):
        return _call(function, *args, **kwargs)


async def _run_prediction(
    user: User,
    session: Session,
    services: Services,
    function: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    # Resolve credentials before threadpool so DB access stays on the request thread
    # (same keys overview/chart already use via market_provider_call).
    credentials = resolve_market_broker_credentials(session, services.settings, user)
    return await run_in_threadpool(
        _prediction_with_credentials,
        credentials,
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
    return await _run_prediction(
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
    return await _run_prediction(user, session, services, service.features, symbol)


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
    return await _run_prediction(
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
    return await _run_prediction(
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
    return await _run_prediction(
        user,
        session,
        services,
        service.explanation,
        symbol,
        horizon=horizon,
    )
