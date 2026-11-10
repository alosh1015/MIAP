from __future__ import annotations

from datetime import timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ids import utcnow

_hasher = PasswordHasher()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(user_id: str, role: str, display_name: str) -> str:
    settings = get_settings()
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "name": display_name,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_ttl_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AppError(401, "token_expired", "Session expired", "Log in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(401, "invalid_token", "Invalid session token") from exc
    if not payload.get("sub") or not payload.get("role"):
        raise AppError(401, "invalid_token", "Session token is missing claims")
    return payload
