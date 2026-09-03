"""Per-user favorite tickers."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_session
from app.models import User, UserFavorite


router = APIRouter(tags=["favorites"])
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]

_TICKER = re.compile(r"^[A-Za-z][A-Za-z.\-]{0,15}$")


class FavoriteItem(BaseModel):
    ticker: str
    created_at: str | None = None


class FavoritesResponse(BaseModel):
    favorites: list[FavoriteItem] = Field(default_factory=list)


def _normalize_ticker(ticker: str) -> str:
    value = ticker.strip().upper()
    if not _TICKER.fullmatch(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid ticker",
        )
    return value


def _favorite_payload(row: UserFavorite) -> dict[str, Any]:
    return {
        "ticker": row.ticker,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/favorites", response_model=FavoritesResponse)
def list_favorites(user: UserDep, session: SessionDep) -> dict[str, Any]:
    rows = (
        session.query(UserFavorite)
        .filter(UserFavorite.user_id == user.id)
        .order_by(UserFavorite.created_at.desc())
        .all()
    )
    return {"favorites": [_favorite_payload(row) for row in rows]}


@router.put("/favorites/{ticker}", response_model=FavoriteItem)
def add_favorite(ticker: str, user: UserDep, session: SessionDep) -> dict[str, Any]:
    symbol = _normalize_ticker(ticker)
    existing = (
        session.query(UserFavorite)
        .filter(UserFavorite.user_id == user.id, UserFavorite.ticker == symbol)
        .one_or_none()
    )
    if existing is not None:
        return _favorite_payload(existing)
    row = UserFavorite(user_id=user.id, ticker=symbol)
    session.add(row)
    session.flush()
    session.refresh(row)
    return _favorite_payload(row)


@router.delete("/favorites/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favorite(ticker: str, user: UserDep, session: SessionDep) -> None:
    symbol = _normalize_ticker(ticker)
    row = (
        session.query(UserFavorite)
        .filter(UserFavorite.user_id == user.id, UserFavorite.ticker == symbol)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Favorite not found")
    session.delete(row)
    session.flush()
