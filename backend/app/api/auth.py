from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth import (
    BrokerCredentials,
    credential_status,
    get_current_user,
    use_trading_credentials,
)
from app.db import get_session
from app.dependencies import Services, get_services
from app.models import AlpacaCredential, User
from app.security import (
    create_access_token,
    encrypt_secret,
    hash_password,
    verify_password,
)
from app.services.providers import ProviderUnavailable


router = APIRouter(prefix="/auth", tags=["auth"])
ServiceDep = Annotated[Services, Depends(get_services)]
SessionDep = Annotated[Session, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]


class AuthCredentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class AlpacaKeysBody(BaseModel):
    mode: Literal["paper", "live"] = "paper"
    key_id: str = Field(min_length=8, max_length=128)
    secret: str = Field(min_length=8, max_length=256)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


def _user_payload(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "alpaca": credential_status(user),
    }


def _token_response(services: Services, user: User) -> dict[str, Any]:
    return {
        "access_token": create_access_token(
            services.settings, subject=user.email, user_id=user.id
        ),
        "token_type": "bearer",
        "user": _user_payload(user),
    }


@router.post("/register", status_code=201)
def register(
    body: AuthCredentials,
    session: SessionDep,
    services: ServiceDep,
) -> dict[str, Any]:
    email = body.email.lower().strip()
    existing = session.query(User).filter(User.email == email).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(email=email, password_hash=hash_password(body.password))
    session.add(user)
    session.flush()
    return _token_response(services, user)


@router.post("/login")
def login(
    body: AuthCredentials,
    session: SessionDep,
    services: ServiceDep,
) -> dict[str, Any]:
    email = body.email.lower().strip()
    user = session.query(User).filter(User.email == email).one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return _token_response(services, user)


@router.get("/me")
def me(user: UserDep) -> dict[str, Any]:
    return _user_payload(user)


def _validate_alpaca_keys(services: Services, mode: str, key_id: str, secret: str) -> None:
    try:
        with use_trading_credentials(BrokerCredentials(key=key_id, secret=secret)):
            services.alpaca.account(mode)
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc) or "Alpaca credentials are invalid",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alpaca rejected these credentials",
        ) from exc


@router.put("/alpaca")
async def save_alpaca(
    body: AlpacaKeysBody,
    user: UserDep,
    session: SessionDep,
    services: ServiceDep,
) -> dict[str, Any]:
    if body.mode == "live" and not services.settings.allow_live_trading:
        raise HTTPException(status_code=403, detail="Live trading is disabled")
    await run_in_threadpool(
        _validate_alpaca_keys, services, body.mode, body.key_id.strip(), body.secret.strip()
    )
    row = (
        session.query(AlpacaCredential)
        .filter(AlpacaCredential.user_id == user.id, AlpacaCredential.mode == body.mode)
        .one_or_none()
    )
    encrypted = encrypt_secret(services.settings, body.secret.strip())
    if row is None:
        row = AlpacaCredential(
            user_id=user.id,
            mode=body.mode,
            key_id=body.key_id.strip(),
            secret_encrypted=encrypted,
        )
        session.add(row)
    else:
        row.key_id = body.key_id.strip()
        row.secret_encrypted = encrypted
    session.flush()
    session.refresh(user)
    return _user_payload(user)


@router.delete("/alpaca")
def delete_alpaca(
    user: UserDep,
    session: SessionDep,
    mode: Literal["paper", "live"] = Query(default="paper"),
) -> dict[str, Any]:
    row = (
        session.query(AlpacaCredential)
        .filter(AlpacaCredential.user_id == user.id, AlpacaCredential.mode == mode)
        .one_or_none()
    )
    if row is not None:
        session.delete(row)
        session.flush()
    session.refresh(user)
    return _user_payload(user)
