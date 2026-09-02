"""Hybrid prediction API routes."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from starlette.concurrency import run_in_threadpool

from app.dependencies import Services, enforce_rate_limit, get_services


router = APIRouter(tags=["prediction"])
ServiceDep = Annotated[Services, Depends(get_services)]
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
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Prediction failed: {type(exc).__name__}",
        ) from exc


@router.get("/stocks/{ticker}/prediction")
async def get_prediction(
    ticker: str,
    services: ServiceDep,
    request: Request,
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
    return await run_in_threadpool(_call, service.predict, symbol, horizon=horizon, retrain=retrain)


@router.get("/stocks/{ticker}/features")
async def get_features(ticker: str, services: ServiceDep, request: Request) -> dict[str, Any]:
    enforce_rate_limit(
        request,
        "prediction_features",
        getattr(services.settings, "prediction_rate_limit_per_minute", 30),
    )
    service = _prediction_service(services)
    symbol = _ticker(ticker)
    return await run_in_threadpool(_call, service.features, symbol)


@router.get("/stocks/{ticker}/signals")
async def get_signals(
    ticker: str,
    services: ServiceDep,
    request: Request,
    horizon: str = Query(default="5d", pattern=r"^(1d|5d|20d)$"),
) -> dict[str, Any]:
    enforce_rate_limit(
        request,
        "prediction_signals",
        getattr(services.settings, "prediction_rate_limit_per_minute", 30),
    )
    service = _prediction_service(services)
    symbol = _ticker(ticker)
    return await run_in_threadpool(_call, service.signals, symbol, horizon=horizon)


@router.get("/stocks/{ticker}/risk")
async def get_risk(
    ticker: str,
    services: ServiceDep,
    request: Request,
    horizon: str = Query(default="5d", pattern=r"^(1d|5d|20d)$"),
) -> dict[str, Any]:
    enforce_rate_limit(
        request,
        "prediction_risk",
        getattr(services.settings, "prediction_rate_limit_per_minute", 30),
    )
    service = _prediction_service(services)
    symbol = _ticker(ticker)
    return await run_in_threadpool(_call, service.risk, symbol, horizon=horizon)


@router.get("/stocks/{ticker}/explanation")
async def get_explanation(
    ticker: str,
    services: ServiceDep,
    request: Request,
    horizon: str = Query(default="5d", pattern=r"^(1d|5d|20d)$"),
) -> dict[str, Any]:
    enforce_rate_limit(
        request,
        "prediction_explanation",
        getattr(services.settings, "prediction_rate_limit_per_minute", 30),
    )
    service = _prediction_service(services)
    symbol = _ticker(ticker)
    return await run_in_threadpool(_call, service.explanation, symbol, horizon=horizon)
