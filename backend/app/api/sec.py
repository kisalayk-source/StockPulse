from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.dependencies import Services, enforce_rate_limit, get_services
from app.sec.schemas import ResearchQueryRequest, ResearchQueryResponse
from app.services.providers import ProviderUnavailable

logger = logging.getLogger("app.api.sec")

router = APIRouter()


def _maybe_auto_scan(services: Services, session: Session) -> None:
    services.sec.maybe_auto_scan(session, services)


@router.get("/stocks/{symbol}/sec")
async def stock_sec(
    symbol: str,
    services: Services = Depends(get_services),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    provider_errors: list[dict[str, str]] = []
    accumulation = await services.sec.accumulation_for_ticker(
        session,
        symbol,
        services.alpaca,
        services.finnhub,
        sync=True,
    )
    provider_errors.extend(accumulation.pop("provider_errors", []))
    payload = services.sec.sec_intelligence(session, symbol, accumulation)
    payload["provider_errors"] = provider_errors
    return payload


@router.get("/stocks/{symbol}/institutional")
async def stock_institutional(
    symbol: str,
    services: Services = Depends(get_services),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        await services.sec.sync_ticker(session, symbol, services.finnhub)
    except ProviderUnavailable:
        pass
    except Exception as exc:
        logger.error("sec_institutional_sync_failed", extra={"error_type": type(exc).__name__})
    return services.sec.institutional_payload(session, symbol)


@router.get("/stocks/{symbol}/insiders")
async def stock_insiders(
    symbol: str,
    services: Services = Depends(get_services),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        await services.sec.sync_ticker(session, symbol, services.finnhub)
    except ProviderUnavailable:
        pass
    return services.sec.insiders_payload(session, symbol)


@router.get("/stocks/{symbol}/accumulation")
async def stock_accumulation(
    symbol: str,
    services: Services = Depends(get_services),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    return await services.sec.accumulation_for_ticker(
        session,
        symbol,
        services.alpaca,
        services.finnhub,
        sync=True,
    )


@router.get("/stocks/{symbol}/filings")
async def stock_filings(
    symbol: str,
    services: Services = Depends(get_services),
    session: Session = Depends(get_session),
    months: int = Query(default=6, ge=1, le=24),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    return await services.sec.recent_filings_payload(
        session,
        symbol,
        services.finnhub,
        months=months,
        limit=limit,
    )


@router.get("/sectors")
async def list_sectors(
    services: Services = Depends(get_services),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _maybe_auto_scan(services, session)
    return {"sectors": services.sec.list_sectors(session)}


@router.get("/sectors/{sector}/accumulation")
async def sector_accumulation(
    sector: str = Path(min_length=1, max_length=80),
    services: Services = Depends(get_services),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _maybe_auto_scan(services, session)
    return services.sec.sector_accumulation(session, sector)


@router.get("/accumulation/top")
async def top_accumulation(
    services: Services = Depends(get_services),
    session: Session = Depends(get_session),
    sector: str | None = Query(default=None, max_length=80),
    min_score: float = Query(default=0.0, ge=0.0, le=100.0),
    limit: int = Query(default=25, ge=1, le=100),
) -> dict[str, Any]:
    _maybe_auto_scan(services, session)
    rows = services.sec.top_accumulation(session, sector=sector, min_score=min_score, limit=limit)
    return {"results": rows, "sector": sector, "min_score": min_score}


@router.post("/accumulation/scan")
async def start_accumulation_scan(
    services: Services = Depends(get_services),
    refresh: bool = Query(default=False),
) -> dict[str, Any]:
    return services.sec.start_accumulation_scan(services, refresh=refresh)


@router.get("/accumulation/scan/status")
async def accumulation_scan_status(
    services: Services = Depends(get_services),
) -> dict[str, Any]:
    return services.sec.scan_status()


@router.post("/research/query")
async def research_query(
    request: Request,
    body: ResearchQueryRequest,
    services: Services = Depends(get_services),
    session: Session = Depends(get_session),
) -> ResearchQueryResponse:
    enforce_rate_limit(request, "research", services.settings.sec_rate_limit_per_minute)
    from app.services.research_query import run_research_query

    result = await run_research_query(
        body.query,
        session=session,
        services=services,
    )
    return ResearchQueryResponse(**result)
