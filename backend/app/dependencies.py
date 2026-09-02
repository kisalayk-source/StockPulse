from dataclasses import dataclass
from collections import defaultdict, deque
from hmac import compare_digest
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import Header, HTTPException, Request, status

from app.config import Settings
from app.services.kronos import KronosService
from app.services.prediction import PredictionService
from app.services.providers import AlpacaService, FinnhubService
from app.sec.service import SecService


@dataclass
class Services:
    settings: Settings
    alpaca: Any
    finnhub: Any
    kronos: Any
    sec: Any
    prediction: Any = None


class RateLimiter:
    """Small per-process sliding-window limiter for expensive and mutating routes."""

    def __init__(self) -> None:
        self._requests: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, bucket: str, identity: str, limit: int) -> None:
        if limit <= 0:
            return
        now = monotonic()
        key = (bucket, identity)
        with self._lock:
            entries = self._requests[key]
            while entries and entries[0] <= now - 60:
                entries.popleft()
            if len(entries) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": "60"},
                )
            entries.append(now)


def build_services(settings: Settings) -> Services:
    alpaca = AlpacaService(settings)
    return Services(
        settings=settings,
        alpaca=alpaca,
        finnhub=FinnhubService(settings),
        kronos=KronosService(settings, alpaca),
        sec=SecService(settings),
        prediction=PredictionService(settings, alpaca),
    )


def get_services(request: Request) -> Services:
    return request.app.state.services


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    if request.url.path.endswith("/health"):
        return
    expected = request.app.state.services.settings.api_key
    if not expected:
        return
    supplied = x_api_key or ""
    if not compare_digest(
        supplied.encode("utf-8", errors="surrogatepass"),
        expected.encode("utf-8", errors="surrogatepass"),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


def enforce_rate_limit(request: Request, bucket: str, limit: int) -> None:
    client = request.client.host if request.client else "unknown"
    request.app.state.rate_limiter.check(bucket, client, limit)
