from datetime import datetime
from hmac import compare_digest
import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth import (
    credential_status,
    get_current_user,
    get_user_broker_credentials,
    use_trading_credentials,
)
from app.db import get_session
from app.dependencies import Services, enforce_rate_limit, get_services
from app.models import User
from app.schemas import (
    EquityOrderRequest,
    ForecastRequest,
    MoversScanRequest,
    OptionOrderRequest,
    OrderCancelRequest,
    OrderPreviewRequest,
    OrderReplaceRequest,
    TradingMode,
)
from app.services.openai_client import research_llm_available
from app.services.providers import (
    SEARCH_RESULT_LIMIT,
    ProviderUnavailable,
    merge_news,
    local_symbol_search,
    rank_search_results,
)


router = APIRouter()
ServiceDep = Annotated[Services, Depends(get_services)]
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]
SymbolPath = Annotated[str, Path(min_length=1, max_length=16, pattern=r"^[A-Za-z.\-]+$")]
logger = logging.getLogger("app.routes")


def trading_provider_call(
    user: User,
    session: Session,
    services: Services,
    mode: str,
    function: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    credentials = get_user_broker_credentials(session, services.settings, user, mode)
    with use_trading_credentials(credentials):
        return provider_call(function, *args, **kwargs)


def market_provider_call(
    user: User,
    session: Session,
    services: Services,
    function: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    try:
        credentials = get_user_broker_credentials(session, services.settings, user, "paper")
    except HTTPException as exc:
        if exc.status_code != status.HTTP_400_BAD_REQUEST:
            raise
        return provider_call(function, *args, **kwargs)
    with use_trading_credentials(credentials):
        return provider_call(function, *args, **kwargs)


def provider_call(function: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return function(*args, **kwargs)
    except ProviderUnavailable as exc:
        logger.warning(
            "provider_unavailable",
            extra={
                "provider": exc.provider,
                "operation": getattr(function, "__name__", "unknown"),
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"provider": exc.provider, "message": "Provider unavailable"},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "provider_request_failed",
            extra={
                "operation": getattr(function, "__name__", "unknown"),
                "error_type": type(exc).__name__,
            },
        )
        raise HTTPException(status_code=502, detail="Provider request failed") from exc


def enforce_live(mode: TradingMode, token: str | None, services: Services) -> None:
    if mode != TradingMode.live:
        return
    expected = services.settings.live_confirmation_token
    if not services.settings.allow_live_trading:
        raise HTTPException(status_code=403, detail="Live trading is disabled")
    if not expected:
        raise HTTPException(status_code=503, detail="Live confirmation token is not configured")
    if token is None or not compare_digest(
        token.encode("utf-8", errors="surrogatepass"),
        expected.encode("utf-8", errors="surrogatepass"),
    ):
        raise HTTPException(status_code=403, detail="Exact live confirmation token required")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def readiness(services: ServiceDep) -> dict[str, Any]:
    return {
        "status": "ready",
        "services": {
            "alpaca": services.alpaca is not None,
            "finnhub": services.finnhub is not None,
            "kronos": services.kronos is not None,
            "sec": services.sec is not None,
        },
    }


@router.get("/config/status")
def config_status(services: ServiceDep, user: UserDep) -> dict[str, Any]:
    settings = services.settings
    user_alpaca = credential_status(user)
    return {
        "alpaca": {
            "paper_configured": bool(user_alpaca["paper"]["configured"]),
            "live_configured": bool(user_alpaca["live"]["configured"]),
            "paper_key_preview": user_alpaca["paper"]["key_preview"],
            "live_key_preview": user_alpaca["live"]["key_preview"],
            "env_data_configured": settings.alpaca_configured(settings.alpaca_data_credentials_mode),
        },
        "finnhub_configured": bool(settings.finnhub_api_key),
        "sec_enabled": settings.sec_enabled,
        "research_llm_available": research_llm_available(settings),
        "research_llm_enabled": bool(user.research_llm_enabled),
        "data_feed": settings.alpaca_data_feed,
        "data_credentials_mode": settings.alpaca_data_credentials_mode,
        "live_trading_allowed": settings.allow_live_trading,
        "user": {"id": user.id, "email": user.email},
        "kronos": {
            "model_id": settings.kronos_model_id,
            "tokenizer_id": settings.kronos_tokenizer_id,
            "device": settings.kronos_device,
            "loaded": bool(getattr(services.kronos, "loaded", False)),
        },
        "risk": {
            "max_position_pct": settings.risk_max_position_pct,
            "max_option_debit_pct": settings.risk_max_option_debit_pct,
            "max_daily_loss_pct": settings.risk_max_daily_loss_pct,
            "max_spread_bps": settings.risk_max_spread_bps,
            "min_adv_shares": settings.risk_min_adv_shares,
            "max_gross_pct": settings.risk_max_gross_pct,
        },
    }


@router.get("/market/clock")
async def market_clock(services: ServiceDep) -> dict[str, Any]:
    return await run_in_threadpool(provider_call, services.alpaca.market_clock, "paper")


@router.get("/symbols/search")
async def symbol_search(
    services: ServiceDep,
    user: UserDep,
    session: SessionDep,
    q: str = Query(min_length=1, max_length=80),
) -> dict[str, Any]:
    alpaca_results: list[dict[str, Any]] = []
    finnhub_results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    try:
        alpaca_results = await run_in_threadpool(
            market_provider_call, user, session, services, services.alpaca.search_assets, q, "paper"
        )
    except ProviderUnavailable as exc:
        logger.warning(
            "optional_provider_unavailable",
            extra={"provider": exc.provider, "error_type": type(exc).__name__},
        )
        errors.append({"provider": exc.provider, "message": "Provider unavailable"})
    except HTTPException as exc:
        if exc.status_code != status.HTTP_503_SERVICE_UNAVAILABLE:
            raise
        logger.warning(
            "optional_provider_unavailable",
            extra={"provider": "alpaca", "error_type": type(exc).__name__},
        )
        errors.append({"provider": "alpaca", "message": "Provider unavailable"})
    try:
        finnhub_results = await services.finnhub.search(q)
    except ProviderUnavailable as exc:
        logger.warning(
            "optional_provider_unavailable",
            extra={"provider": exc.provider, "error_type": type(exc).__name__},
        )
        errors.append({"provider": exc.provider, "message": "Provider unavailable"})
    except Exception as exc:
        logger.error(
            "optional_provider_failed",
            extra={"provider": "finnhub", "error_type": type(exc).__name__},
        )
        errors.append({"provider": "finnhub", "message": "Provider request failed"})
    if not alpaca_results and not finnhub_results and len(errors) == 2:
        return {"results": local_symbol_search(q), "provider_errors": errors}
    merged: dict[str, dict[str, Any]] = {}
    for item in [*alpaca_results, *finnhub_results]:
        symbol = item.get("symbol")
        if symbol:
            merged[symbol] = {**merged.get(symbol, {}), **item}
    ranked = rank_search_results(q, list(merged.values()))
    return {"results": ranked[:SEARCH_RESULT_LIMIT], "provider_errors": errors}


@router.get("/stocks/{symbol}/overview")
async def stock_overview(
    symbol: SymbolPath,
    services: ServiceDep,
    user: UserDep,
    session: SessionDep,
    news_limit: int = Query(default=8, ge=0, le=20),
) -> dict[str, Any]:
    snapshot = await run_in_threadpool(
        market_provider_call, user, session, services, services.alpaca.snapshot, symbol
    )
    provider_errors: list[dict[str, str]] = []
    alpaca_news: list[dict[str, Any]] = []
    finnhub_news: list[dict[str, Any]] = []
    fundamentals: dict[str, float | None] = {
        "pe_ratio": None,
        "market_cap": None,
        "dividend_yield": None,
        "eps": None,
    }
    public_sentiment: dict[str, Any] | None = None
    ticker = symbol.upper()
    if news_limit:
        try:
            alpaca_news = await run_in_threadpool(
                market_provider_call,
                user,
                session,
                services,
                services.alpaca.news,
                ticker,
                news_limit,
            )
        except Exception as exc:
            logger.error(
                "optional_provider_failed",
                extra={"provider": "alpaca_news", "error_type": type(exc).__name__},
            )
            provider_errors.append({"provider": "alpaca_news", "message": "Provider request failed"})
        try:
            finnhub_news = await services.finnhub.company_news(ticker, news_limit)
        except Exception as exc:
            logger.error(
                "optional_provider_failed",
                extra={"provider": "finnhub_news", "error_type": type(exc).__name__},
            )
            provider_errors.append({"provider": "finnhub_news", "message": "Provider request failed"})
    try:
        fundamentals = await services.finnhub.fundamentals(ticker)
    except Exception as exc:
        logger.error(
            "optional_provider_failed",
            extra={"provider": "finnhub", "error_type": type(exc).__name__},
        )
        provider_errors.append({"provider": "finnhub", "message": "Provider request failed"})
    try:
        public_sentiment = await services.finnhub.news_sentiment(ticker)
    except Exception as exc:
        logger.error(
            "optional_provider_failed",
            extra={"provider": "finnhub_sentiment", "error_type": type(exc).__name__},
        )
        provider_errors.append({"provider": "finnhub_sentiment", "message": "Provider request failed"})
    return {
        **snapshot,
        "fundamentals": fundamentals,
        "public_sentiment": public_sentiment,
        "news": merge_news(finnhub_news, alpaca_news, limit=news_limit),
        "provider_errors": provider_errors,
    }


@router.get("/stocks/{symbol}/bars")
async def stock_bars(
    symbol: SymbolPath,
    services: ServiceDep,
    user: UserDep,
    session: SessionDep,
    timeframe: Literal["1Min", "5Min", "15Min", "1Hour", "1Day"] = "1Day",
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=300, ge=1, le=1000),
) -> dict[str, Any]:
    bars = await run_in_threadpool(
        market_provider_call,
        user,
        session,
        services,
        services.alpaca.bars,
        symbol,
        timeframe,
        start,
        end,
        limit,
    )
    return {"symbol": symbol.upper(), "timeframe": timeframe, "bars": bars}


@router.get("/account")
async def account(
    mode: TradingMode, services: ServiceDep, user: UserDep, session: SessionDep
) -> dict[str, Any]:
    return await run_in_threadpool(
        trading_provider_call, user, session, services, mode.value, services.alpaca.account, mode.value
    )


@router.get("/account/realized-pl")
async def account_realized_pl(
    mode: TradingMode, services: ServiceDep, user: UserDep, session: SessionDep
) -> dict[str, Any]:
    return await run_in_threadpool(
        trading_provider_call,
        user,
        session,
        services,
        mode.value,
        services.alpaca.realized_pl,
        mode.value,
    )


@router.get("/positions")
async def positions(
    mode: TradingMode, services: ServiceDep, user: UserDep, session: SessionDep
) -> dict[str, Any]:
    return {
        "positions": await run_in_threadpool(
            trading_provider_call,
            user,
            session,
            services,
            mode.value,
            services.alpaca.positions,
            mode.value,
        )
    }


@router.get("/orders")
async def orders(
    mode: TradingMode,
    services: ServiceDep,
    user: UserDep,
    session: SessionDep,
    order_status: Literal["open", "closed", "all"] = "open",
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    return {
        "orders": await run_in_threadpool(
            trading_provider_call,
            user,
            session,
            services,
            mode.value,
            services.alpaca.orders,
            mode.value,
            order_status,
            limit,
        )
    }


@router.delete("/orders/{order_id}")
async def cancel_order(
    request: Request,
    cancellation: OrderCancelRequest,
    services: ServiceDep,
    user: UserDep,
    session: SessionDep,
    order_id: str = Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9-]+$"),
) -> dict[str, Any]:
    enforce_rate_limit(request, "orders", services.settings.order_rate_limit_per_minute)
    enforce_live(cancellation.mode, cancellation.live_confirmation_token, services)
    result = await run_in_threadpool(
        trading_provider_call,
        user,
        session,
        services,
        cancellation.mode.value,
        services.alpaca.cancel_order,
        order_id,
        cancellation.mode.value,
    )
    logger.info(
        "order_cancel_requested",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "order_id": order_id,
            "mode": cancellation.mode.value,
        },
    )
    return result


@router.patch("/orders/{order_id}")
async def replace_order(
    request: Request,
    replacement: OrderReplaceRequest,
    services: ServiceDep,
    user: UserDep,
    session: SessionDep,
    order_id: str = Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9-]+$"),
) -> dict[str, Any]:
    enforce_rate_limit(request, "orders", services.settings.order_rate_limit_per_minute)
    enforce_live(replacement.mode, replacement.live_confirmation_token, services)
    result = await run_in_threadpool(
        trading_provider_call,
        user,
        session,
        services,
        replacement.mode.value,
        services.alpaca.replace_order,
        order_id,
        replacement,
    )
    logger.info(
        "order_replace_requested",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "order_id": order_id,
            "mode": replacement.mode.value,
        },
    )
    return result


@router.get("/options/contracts")
async def option_contracts(
    underlying: str,
    mode: TradingMode,
    services: ServiceDep,
    user: UserDep,
    session: SessionDep,
    expiration: str | None = None,
    contract_type: Literal["call", "put"] | None = Query(default=None, alias="type"),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    contracts = await run_in_threadpool(
        trading_provider_call,
        user,
        session,
        services,
        mode.value,
        services.alpaca.option_contracts,
        underlying,
        expiration,
        contract_type,
        limit,
        mode.value,
    )
    return {"underlying": underlying.upper(), "contracts": contracts}


@router.get("/options/chain")
async def option_chain(
    underlying: str,
    services: ServiceDep,
    expiration: str | None = None,
    contract_type: Literal["call", "put"] | None = Query(default=None, alias="type"),
) -> dict[str, Any]:
    return {
        "underlying": underlying.upper(),
        "chain": await run_in_threadpool(
            provider_call,
            services.alpaca.option_chain,
            underlying,
            expiration,
            contract_type,
        ),
    }


@router.post("/orders/preview")
async def preview_order(
    order: OrderPreviewRequest,
    services: ServiceDep,
    request: Request,
    user: UserDep,
    session: SessionDep,
) -> dict[str, Any]:
    enforce_rate_limit(request, "orders", services.settings.order_rate_limit_per_minute)
    return await run_in_threadpool(
        trading_provider_call,
        user,
        session,
        services,
        order.mode.value,
        services.alpaca.preview_order,
        order,
    )


@router.post("/orders/equity", status_code=201)
async def submit_equity(
    order: EquityOrderRequest,
    services: ServiceDep,
    request: Request,
    user: UserDep,
    session: SessionDep,
) -> dict[str, Any]:
    enforce_rate_limit(request, "orders", services.settings.order_rate_limit_per_minute)
    enforce_live(order.mode, order.live_confirmation_token, services)
    logger.info(
        "order_submission_requested",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "kind": "equity",
            "mode": order.mode.value,
            "symbol": order.symbol.upper(),
            "side": order.side.value,
            "order_type": order.type.value,
            "qty": order.qty,
            "notional": order.notional,
        },
    )
    result = await run_in_threadpool(
        trading_provider_call,
        user,
        session,
        services,
        order.mode.value,
        services.alpaca.submit_equity_order,
        order,
    )
    logger.info(
        "order_submission_completed",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "kind": "equity",
            "mode": order.mode.value,
            "symbol": order.symbol.upper(),
            "order_id": result.get("id") if isinstance(result, dict) else None,
            "status": result.get("status") if isinstance(result, dict) else None,
        },
    )
    return result


@router.post("/orders/option", status_code=201)
async def submit_option(
    order: OptionOrderRequest,
    services: ServiceDep,
    request: Request,
    user: UserDep,
    session: SessionDep,
) -> dict[str, Any]:
    enforce_rate_limit(request, "orders", services.settings.order_rate_limit_per_minute)
    enforce_live(order.mode, order.live_confirmation_token, services)
    logger.info(
        "order_submission_requested",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "kind": "option",
            "mode": order.mode.value,
            "symbol": order.contract_symbol.upper(),
            "side": order.side.value,
            "order_type": order.type,
            "qty": order.qty,
            "position_intent": order.position_intent.value if order.position_intent else None,
        },
    )
    result = await run_in_threadpool(
        trading_provider_call,
        user,
        session,
        services,
        order.mode.value,
        services.alpaca.submit_option_order,
        order,
    )
    logger.info(
        "order_submission_completed",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "kind": "option",
            "mode": order.mode.value,
            "symbol": order.contract_symbol.upper(),
            "order_id": result.get("id") if isinstance(result, dict) else None,
            "status": result.get("status") if isinstance(result, dict) else None,
        },
    )
    return result


@router.post("/forecast")
async def forecast(
    forecast_request: ForecastRequest,
    services: ServiceDep,
    request: Request,
    user: UserDep,
    session: SessionDep,
) -> dict[str, Any]:
    enforce_rate_limit(request, "forecast", services.settings.forecast_rate_limit_per_minute)
    return await run_in_threadpool(
        market_provider_call,
        user,
        session,
        services,
        services.kronos.forecast,
        forecast_request.symbol,
        forecast_request.preset,
        forecast_request.timeframe,
        forecast_request.context,
        forecast_request.horizon,
        None,
        True,
        forecast_request.engine == "kronos",
        forecast_request.engine,
    )


@router.post("/forecast/movers")
async def forecast_movers(
    scan_request: MoversScanRequest, services: ServiceDep, request: Request
) -> dict[str, Any]:
    enforce_rate_limit(
        request, "forecast_scan", services.settings.forecast_scan_rate_limit_per_minute
    )
    scan = getattr(services.kronos, "start_movers_scan", services.kronos.scan_movers)
    return provider_call(
        scan,
        scan_request.limit,
        scan_request.refresh,
    )


@router.get("/forecast/movers/status")
def forecast_movers_status(services: ServiceDep) -> dict[str, Any]:
    status_call = getattr(services.kronos, "movers_scan_status", None)
    if status_call is None:
        return {"status": "idle", "movers": [], "gainers": [], "losers": [], "scanned": 0}
    return provider_call(status_call)

