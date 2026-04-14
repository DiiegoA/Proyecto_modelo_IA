from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import jwt
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, AuthorizationError

bearer_scheme = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    sub: str
    role: str = "user"
    exp: int


def extract_bearer_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token.")
    return credentials.credentials


def decode_user_token(token: str, settings: Settings) -> TokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.oraculo_api_jwt_secret_key,
            algorithms=[settings.oraculo_api_jwt_algorithm],
        )
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token expired.") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid access token.") from exc


def require_admin_key(provided_key: str | None, settings: Settings) -> None:
    if not provided_key or provided_key != settings.admin_api_key:
        raise AuthorizationError("Invalid or missing administrative key.")


def utc_timestamp() -> datetime:
    return datetime.now(timezone.utc)


def redact_sensitive_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    redacted = dict(metadata)
    for key in list(redacted.keys()):
        lowered = key.lower()
        if any(fragment in lowered for fragment in ("password", "token", "secret", "api_key")):
            redacted[key] = "***"
    return redacted
