from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agent.model_gateway import ModelGateway
from app.clients.oraculo_api import AuthenticatedUser, PredictionApiResult
from app.core.config import Settings
from app.core.exceptions import UpstreamServiceError
from app.main import create_app
from app.rag.service import SourceDocument
from tests.helpers import make_access_token, sqlite_url


class FakeOraculoApiClient:
    def __init__(self) -> None:
        self.predict_calls: list[dict] = []
        self.predict_user_tokens: list[str | None] = []
        self.validated_tokens: list[str] = []
        self.health_checks = 0
        self.raise_on_health = False

    def validate_user_token(self, user_token: str) -> AuthenticatedUser:
        self.validated_tokens.append(user_token)
        return AuthenticatedUser(
            id="remote-user",
            email="remote@example.com",
            full_name="Remote User",
            role="analyst",
            is_active=True,
            access_token=user_token,
        )

    def predict(self, payload: dict, *, user_token: str | None = None) -> PredictionApiResult:
        self.predict_calls.append(payload)
        self.predict_user_tokens.append(user_token)
        return PredictionApiResult(
            prediction_id=str(uuid4()),
            label=">50K",
            probability=0.9123,
            model_version="test-model",
            execution_time_ms=12.5,
            request_id=f"req-{len(self.predict_calls)}",
            input_payload=payload,
            normalized_payload=payload,
        )

    def health_check(self) -> dict:
        self.health_checks += 1
        if self.raise_on_health:
            raise UpstreamServiceError("upstream is unavailable")
        return {"status": "ready", "database_connected": True, "model_loaded": True}


def _default_settings(runtime_dir: Path, **overrides) -> Settings:
    base_values = {
        "environment": "test",
        "debug": False,
        "enable_langserve": False,
        "auto_reindex_on_startup": False,
        "google_api_key": None,
        "langsmith_api_key": None,
        "langsmith_tracing": False,
        "rate_limit_enabled": False,
        "oraculo_api_verify_remote_user": False,
        "admin_api_key": "test-admin-key",
        "oraculo_api_jwt_secret_key": "test-secret-key-that-is-long-enough-32",
        "database_url": sqlite_url(runtime_dir / "agent.db"),
        "checkpoints_db_path": str(runtime_dir / "checkpoints.sqlite"),
        "qdrant_path": str(runtime_dir / "qdrant"),
        "allowed_hosts": ["localhost", "127.0.0.1", "testserver"],
    }
    base_values.update(overrides)
    settings = Settings(**base_values)
    settings.create_runtime_directories()
    return settings


@pytest.fixture
def settings_factory(tmp_path_factory):
    def factory(**overrides) -> Settings:
        runtime_dir = tmp_path_factory.mktemp("agent-runtime")
        return _default_settings(runtime_dir, **overrides)

    return factory


@pytest.fixture
def app_settings(settings_factory) -> Settings:
    return settings_factory()


@pytest.fixture
def token_factory():
    return make_access_token


@pytest.fixture
def auth_headers(app_settings: Settings, token_factory) -> dict[str, str]:
    token = token_factory(app_settings)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def fake_oraculo_api_client() -> FakeOraculoApiClient:
    return FakeOraculoApiClient()


@pytest.fixture
def knowledge_documents() -> list[SourceDocument]:
    return [
        SourceDocument(
            source_id="doc-api",
            source_path="knowledge_base/api_contract.md",
            title="API Contract",
            source_type="md",
            content=(
                "El agente usa FastAPI, LangGraph y LangServe para exponer rutas de chat, salud y administracion. "
                "La ruta POST /api/v1/chat/invoke sirve para solicitudes sin streaming."
            ),
        ),
        SourceDocument(
            source_id="doc-security",
            source_path="knowledge_base/security.md",
            title="Security Notes",
            source_type="md",
            content=(
                "El sistema protege endpoints administrativos con X-Agent-Admin-Key, aplica TrustedHostMiddleware "
                "y agrega headers estrictos para seguridad."
            ),
        ),
    ]


@contextmanager
def _client_context(
    *,
    settings: Settings,
    fake_client: FakeOraculoApiClient | None = None,
    documents: list[SourceDocument] | None = None,
) -> Iterator[tuple[TestClient, Settings]]:
    app = create_app(settings)
    with TestClient(app) as client:
        if fake_client is not None:
            client.app.state.oraculo_api_client = fake_client
            client.app.state.workflow.oraculo_api_client = fake_client
            client.app.state.health_service.oraculo_api_client = fake_client
        if documents is not None:
            knowledge_runtime = client.app.state.knowledge_runtime
            knowledge_runtime._collect_static_documents = lambda: documents
            knowledge_runtime.reindex(mode="full")
        yield client, settings


@pytest.fixture
def client_factory(settings_factory):
    def factory(
        *,
        fake_client: FakeOraculoApiClient | None = None,
        documents: list[SourceDocument] | None = None,
        **settings_overrides,
    ):
        settings = settings_factory(**settings_overrides)
        return _client_context(settings=settings, fake_client=fake_client, documents=documents)

    return factory


@pytest.fixture
def model_gateway(app_settings: Settings) -> ModelGateway:
    return ModelGateway(app_settings)
