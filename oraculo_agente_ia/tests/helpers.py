from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

from app.core.config import Settings
from app.db.session import build_engine, build_session_factory, create_tables


def sqlite_url(path: Path) -> str:
    return path.resolve().as_uri().replace("file:///", "sqlite:///")


def build_runtime_db(settings: Settings):
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    create_tables(engine)
    return engine, session_factory


def make_access_token(
    settings: Settings,
    *,
    user_id: str = "user-123",
    role: str = "analyst",
    expires_delta: timedelta = timedelta(minutes=30),
) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": int((datetime.now(timezone.utc) + expires_delta).timestamp()),
    }
    return jwt.encode(
        payload,
        settings.oraculo_api_jwt_secret_key,
        algorithm=settings.oraculo_api_jwt_algorithm,
    )
