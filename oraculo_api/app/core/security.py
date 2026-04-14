from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any

import bcrypt
import jwt
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import Settings
from app.core.exceptions import AuthenticationError


bearer_scheme = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    sub: str
    role: str = "user"
    exp: int


def hash_password(password: str) -> str:
    password_bytes = _password_to_bytes(password)
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = _password_to_bytes(plain_password)
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


def _password_to_bytes(password: str) -> bytes:
    raw_bytes = password.encode("utf-8")
    if len(raw_bytes) <= 72:
        return raw_bytes
    return hashlib.sha256(raw_bytes).hexdigest().encode("utf-8")


def create_access_token(
    *,
    subject: str,
    role: str,
    settings: Settings,
    expires_delta: timedelta | None = None,
) -> str:
    expire_at = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expire_at,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token expired.") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid access token.") from exc


def extract_bearer_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token.")
    return credentials.credentials
