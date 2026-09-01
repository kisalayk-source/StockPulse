from contextlib import asynccontextmanager
import logging
import re
import threading
from time import perf_counter
from typing import AsyncIterator
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.routes import router
from app.api.sec import router as sec_router
from app.auth import require_user
from app.config import Settings, get_settings
from app.db import init_db
from app.dependencies import RateLimiter, Services, build_services, require_api_key
from app.logging import configure_logging


logger = logging.getLogger("app.requests")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.services = services or build_services(settings)
        app.state.rate_limiter = RateLimiter()
        init_db(settings)
        if settings.sec_scan_on_startup and settings.sec_enabled:
            services_ref = app.state.services

            def _startup_scan() -> None:
                try:
                    services_ref.sec.start_accumulation_scan(services_ref, refresh=False)
                except Exception:
                    logger.exception("sec_startup_scan_failed")

            threading.Thread(target=_startup_scan, name="sec-startup-scan", daemon=True).start()
        yield
        for service_name in ("finnhub", "sec"):
            service = getattr(app.state.services, service_name, None)
            client = getattr(service, "client", None) if service is not None else None
            if client is not None and hasattr(client, "aclose"):
                await client.aclose()
            elif service is not None and hasattr(service, "aclose"):
                await service.aclose()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "PATCH", "PUT", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "X-Request-ID", "Authorization"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        candidate = request.headers.get("x-request-id", "")
        request_id = candidate if _REQUEST_ID.fullmatch(candidate) else uuid4().hex
        request.state.request_id = request_id
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "error_type": type(exc).__name__,
                },
            )
            raise
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            },
        )
        return response

    app.include_router(
        auth_router,
        prefix=settings.api_prefix,
        dependencies=[Depends(require_api_key)],
    )
    app.include_router(
        router,
        prefix=settings.api_prefix,
        dependencies=[Depends(require_api_key), Depends(require_user)],
    )
    app.include_router(
        sec_router,
        prefix=settings.api_prefix,
        dependencies=[Depends(require_api_key), Depends(require_user)],
    )
    return app


app = create_app()
