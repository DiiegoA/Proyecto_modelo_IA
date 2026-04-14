from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class FakeGateway:
    def __init__(self) -> None:
        self.register_calls: list[dict] = []
        self.login_calls: list[dict] = []
        self.me_calls: list[str] = []
        self.chat_calls: list[dict] = []

    def register(self, payload):
        self.register_calls.append(payload.model_dump())
        return {
            "id": "user-1",
            "email": payload.email,
            "full_name": payload.full_name,
            "role": "user",
            "is_active": True,
        }

    def login(self, payload):
        self.login_calls.append(payload.model_dump())
        return {
            "access_token": "session-token",
            "token_type": "bearer",
            "expires_in_seconds": 3600,
            "user": {
                "id": "user-1",
                "email": payload.email,
                "full_name": "Diego Aguirre",
                "role": "user",
                "is_active": True,
            },
        }

    def me(self, token: str):
        self.me_calls.append(token)
        return {
            "id": "user-1",
            "email": "diiegoaguirrel@gmail.com",
            "full_name": "Diego Aguirre",
            "role": "user",
            "is_active": True,
        }

    def invoke_chat(self, *, token: str, payload: dict):
        self.chat_calls.append({"token": token, "payload": payload})
        return {
            "thread_id": payload.get("thread_id") or "thread-1",
            "route": "prediction",
            "answer": "La prediccion fue >50K.",
            "citations": [],
            "missing_fields": [],
            "prediction_result": {
                "prediction_id": "pred-1",
                "label": ">50K",
                "probability": 0.88,
                "model_version": "test-model",
                "execution_time_ms": 10.0,
                "request_id": "req-1",
            },
            "confidence": 0.88,
            "safety_flags": [],
            "trace_id": "trace-1",
        }


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        debug=False,
        docs_enabled=False,
        session_secret_key="test-session-secret-key",
        session_cookie_https_only=False,
        allowed_hosts=["localhost", "127.0.0.1", "testserver"],
    )


@pytest.fixture
def fake_gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def client(settings: Settings, fake_gateway: FakeGateway) -> Iterator[TestClient]:
    app = create_app(settings=settings, gateway=fake_gateway)
    with TestClient(app) as test_client:
        yield test_client
