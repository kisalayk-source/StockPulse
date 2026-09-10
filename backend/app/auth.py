from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_session
from app.dependencies import Services, get_services
from app.models import AlpacaCredential, User
from app.security import decode_access_token, decrypt_secret, mask_key_id


@dataclass(frozen=True)
class BrokerCredentials:
    key: str
    secret: str


_trading_credentials: ContextVar[BrokerCredentials | None] = ContextVar(
    "trading_credentials", default=None
)


@contextmanager
def use_trading_credentials(credentials: BrokerCredentials | None) -> Iterator[None]:
    token = _trading_credentials.set(credentials)
    try:
        yield
    finally:
        _trading_credentials.reset(token)


def current_trading_credentials() -> BrokerCredentials | None:
    return _trading_credentials.get()


bearer_scheme = HTTPBearer(auto_error=False)

PUBLIC_PATH_SUFFIXES = (
    "/health",
    "/ready",
    "/auth/register",
    "/auth/login",
)


def is_public_path(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in PUBLIC_PATH_SUFFIXES)


def get_user_broker_credentials(
    session: Session,
    settings: Settings,
    user: User,
    mode: str,
) -> BrokerCredentials:
    row = (
        session.query(AlpacaCredential)
        .filter(AlpacaCredential.user_id == user.id, AlpacaCredential.mode == mode)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Configure Alpaca {mode} credentials in Settings before trading",
        )
    return BrokerCredentials(key=row.key_id, secret=decrypt_secret(settings, row.secret_encrypted))


def credential_status(user: User) -> dict[str, dict[str, object]]:
    rows = {row.mode: row for row in user.credentials}
    result: dict[str, dict[str, object]] = {}
    for mode in ("paper", "live"):
        row = rows.get(mode)
        result[mode] = {
            "configured": row is not None,
            "key_preview": mask_key_id(row.key_id) if row is not None else None,
        }
    return result


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
    services: Services = Depends(get_services),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        if services.settings.app_environment == "development" and services.settings.dev_auth_bypass:
            email = services.settings.dev_auth_email.lower().strip()
            user = session.query(User).filter(User.email == email).one_or_none()
            if user is None:
                user = User(email=email, password_hash="development-auth-bypass")
                session.add(user)
                session.flush()
            request.state.user = user
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(services.settings, credentials.credentials)
        user_id = int(payload["uid"])
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state.user = user
    return user


def require_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
    services: Services = Depends(get_services),
) -> User | None:
    if is_public_path(request.url.path):
        return None
    return get_current_user(request, credentials, session, services)
