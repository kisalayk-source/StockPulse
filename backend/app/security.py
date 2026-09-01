from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

from app.config import Settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(settings: Settings, *, subject: str, user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "uid": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(settings: Settings, token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def _fernet(settings: Settings) -> Fernet:
    return Fernet(settings.credentials_encryption_key.encode("utf-8"))


def encrypt_secret(settings: Settings, secret: str) -> str:
    return _fernet(settings).encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(settings: Settings, token: str) -> str:
    try:
        return _fernet(settings).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt stored credential") from exc


def mask_key_id(key_id: str) -> str:
    if len(key_id) <= 8:
        return "*" * len(key_id)
    return f"{key_id[:4]}…{key_id[-4:]}"
