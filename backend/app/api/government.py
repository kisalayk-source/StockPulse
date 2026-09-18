"""Government contract analysis API routes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_session
from app.dependencies import Services, enforce_rate_limit, get_services
from app.models import User
from app.services.providers import ProviderUnavailable

logger = logging.getLogger("app.api.government")

router = APIRouter()


async def _annual_revenue_guess(services: Services, symbol: str) -> float | None:
    """Best-effort annual revenue proxy from Finnhub when available."""
    try:
        metrics = await services.finnhub.extended_fundamentals(symbol)
    except ProviderUnavailable:
        return None
    except Exception:
        logger.exception("government_revenue_lookup_failed", extra={"ticker": symbol})
        return None
    if not isinstance(metrics, dict):
        return None
    for key in ("revenue", "annual_revenue", "revenueTTM"):
        value = metrics.get(key)
        if value is not None:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                return number
    # Fall back to market cap as a coarse scale proxy only when revenue missing
    market_cap = metrics.get("market_cap")
    if market_cap is not None:
        try:
            cap = float(market_cap)
        except (TypeError, ValueError):
            return None
        if cap > 0:
            return cap
    return None


@router.get("/stocks/{symbol}/government")
async def stock_government(
    request: Request,
    symbol: str = Path(..., min_length=1, max_length=16),
    sync: bool = False,
    services: Services = Depends(get_services),
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    enforce_rate_limit(
        request,
        "government",
        services.settings.government_rate_limit_per_minute,
    )
    ticker = symbol.upper().strip()
    sync_meta: dict[str, Any] | None = None
    if sync and services.settings.government_enabled:
        try:
            sync_meta = await services.government.sync_ticker(session, ticker)
        except Exception as exc:
            logger.exception("government_sync_failed", extra={"ticker": ticker})
            sync_meta = {
                "ticker": ticker,
                "inserted": 0,
                "provider_errors": [{"provider": "government", "message": type(exc).__name__}],
            }

    bars: list[dict[str, Any]] | None = None
    try:
        bars = services.alpaca.bars(ticker, "1Day", None, None, 60)
    except Exception:
        bars = None

    annual_revenue = await _annual_revenue_guess(services, ticker)
    return services.government.analysis_payload(
        session,
        ticker,
        annual_revenue=annual_revenue,
        bars=bars,
        sync_meta=sync_meta,
    )


@router.post("/stocks/{symbol}/government/sync")
async def sync_government(
    request: Request,
    symbol: str = Path(..., min_length=1, max_length=16),
    services: Services = Depends(get_services),
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    enforce_rate_limit(
        request,
        "government_sync",
        max(1, services.settings.government_rate_limit_per_minute // 2),
    )
    ticker = symbol.upper().strip()
    result = await services.government.sync_ticker(session, ticker)
    payload = services.government.analysis_payload(session, ticker, sync_meta=result)
    payload["sync"] = result
    return payload
