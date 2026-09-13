"""Client (browser) log ingest for Elastic-backed observability."""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.dependencies import enforce_rate_limit


router = APIRouter(tags=["logging"])
logger = logging.getLogger("app.frontend")


class ClientLogEvent(BaseModel):
    level: Literal["debug", "info", "warn", "warning", "error"] = "info"
    message: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] | None = None
    stack: str | None = Field(default=None, max_length=20_000)
    request_id: str | None = Field(default=None, max_length=128)
    path: str | None = Field(default=None, max_length=512)
    user_agent: str | None = Field(default=None, max_length=512)


class ClientLogBatch(BaseModel):
    events: list[ClientLogEvent] = Field(min_length=1, max_length=50)


@router.post("/logs/client")
def ingest_client_logs(body: ClientLogBatch, request: Request) -> dict[str, Any]:
    enforce_rate_limit(request, "client-logs", 120)
    accepted = 0
    for event in body.events:
        level_name = "WARNING" if event.level in {"warn", "warning"} else event.level.upper()
        level = getattr(logging, level_name, logging.INFO)
        extras: dict[str, Any] = {
            "source": "frontend",
            "event.dataset": "stockpulse.frontend",
            "user.agent": event.user_agent or request.headers.get("user-agent"),
            "url.path": event.path,
            "request_id": event.request_id or getattr(request.state, "request_id", None),
        }
        if event.context:
            extras["labels"] = event.context
        if event.stack:
            extras["error.stack_trace"] = event.stack
        logger.log(level, event.message, extra={k: v for k, v in extras.items() if v is not None})
        accepted += 1
    return {"accepted": accepted}
