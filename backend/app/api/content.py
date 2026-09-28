"""Content endpoints for downstream video production."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.content.daily_digest import digest_payload
from app.db import get_session

router = APIRouter(tags=["content"])


@router.get("/content/daily-digest")
def daily_digest(
    day: date | None = Query(default=None, alias="date"),
    session: Session = Depends(get_session),
) -> dict:
    return digest_payload(session, day)
