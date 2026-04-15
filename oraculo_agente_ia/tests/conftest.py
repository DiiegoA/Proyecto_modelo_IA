from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.agent.prediction_contract import extract_prediction_fields
from app.agent.types import IntentDecision
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


class _FakeStructuredModel:
    def __init__(self, parent: "FakeConversationalModel", schema):
        self.parent = parent
        self.schema = schema

    def invoke(self, messages):
        return self.parent.invoke_structured(messages, self.schema)


class FakeConversationalModel:
    def with_structured_output(self, schema):
        return _FakeStructuredModel(self, schema)

    def invoke(self, messages):
        system_prompt = str(getattr(messages[0], "content", "")) if messages else ""
        raw_payload = str(getattr(messages[-1], "content", "")) if messages else ""
        try:
            payload = json.loads(raw_payload)
        except Exception:
            payload = {"message": raw_payload}

        question = str(
            payload.get("question")
            or payload.get("message")
            or ""
        )
        question_lower = question.lower()

        if "Reescribe la consulta" in system_prompt:
            return payload.get("question") or payload.get("message") or ""

        if "Debes rechazar" in system_prompt:
            return "No puedo ayudarte con esa solicitud porque compromete la seguridad del sistema."

        if "Explica una prediccion" in system_prompt:
            result = payload.get("prediction_result") or {}
            label = result.get("label", "desconocida")
            probability = float(result.get("probability", 0.0))
            return (
                f"Con los datos que me compartiste, el modelo estima una mayor afinidad con la clase {label} "
                f"y una confianza aproximada de {probability:.2%}."
            )

        if "Estas guiando una prediccion" in system_prompt:
            next_field = payload.get("next_field", "el siguiente dato")
            return f"Perfecto, ya guardé lo anterior. Para seguir con la predicción necesito {next_field}."

        if "Integra en una sola respuesta natural" in system_prompt:
            return f"{payload.get('prediction_answer', '')} {payload.get('rag_answer', '')}".strip()

        if "Responde usando solo la evidencia" in system_prompt:
            evidence = payload.get("evidence") or []
            if not evidence:
                return "No tengo respaldo suficiente en la base documental para responder con seguridad."
            first = evidence[0]
            return (
                f"Según {first.get('title', 'la evidencia disponible')}, "
                f"{str(first.get('snippet', '')).strip()}"
            )

        if "El objetivo del usuario no es del todo claro" in system_prompt:
            return (
                "Puedo conversar contigo, ayudarte a reunir los datos para una predicción "
                "o responder preguntas documentales del proyecto. ¿Qué quieres hacer primero?"
            )

        if "Responde como AdultBot" in system_prompt:
            if any(token in question_lower for token in ["hola", "buenas", "hello", "hi"]):
                return "Hola, soy AdultBot, tu asistente IA. ¿En qué te puedo ayudar?"
            if any(token in question_lower for token in ["que sabes hacer", "qué sabes hacer", "que puedes hacer", "qué puedes hacer"]):
                return (
                    "Puedo conversar contigo, guiar una predicción del dataset Adult Income paso a paso "
                    "y responder preguntas del proyecto con respaldo documental."
                )
            if any(token in question_lower for token in ["como me puedes ayudar", "cómo me puedes ayudar", "en que me puedes ayudar", "explícame qué hago"]):
                return "Hola, soy AdultBot, tu asistente IA. Puedo conversar contigo, ayudarte con predicciones o responder dudas del proyecto."
            if "gracias" in question_lower:
                return "Con gusto. Si quieres, seguimos conversando o avanzamos con una predicción."
            return "Estoy aquí para ayudarte con conversación, predicciones y preguntas documentales."

        return "Respuesta conversacional generada por el cerebro de prueba."

    def invoke_structured(self, messages, schema):
        raw_payload = str(getattr(messages[-1], "content", "")) if messages else ""
        try:
            payload = json.loads(raw_payload)
        except Exception:
            payload = {"message": raw_payload}

        schema_name = getattr(schema, "__name__", "")
        message = str(payload.get("message") or payload.get("question") or "").lower()

        if schema_name == "IntentDecision":
            if any(token in message for token in ["ignore previous", "system prompt", "bypass security"]):
                return schema(intent="unsafe", confidence=0.98, rationale="unsafe", needs_prediction=False, needs_retrieval=False)
            if any(token in message for token in ["hola", "buenas", "hello", "hi", "gracias", "que sabes hacer", "qué sabes hacer", "que puedes hacer", "qué puedes hacer", "quien eres", "quién eres"]):
                return schema(intent="chat", confidence=0.92, rationale="chat", needs_prediction=False, needs_retrieval=False)
            if "predic" in message and any(token in message for token in ["api", "endpoint", "arquitectura", "proyecto", "document"]):
                return schema(intent="hybrid", confidence=0.9, rationale="hybrid", needs_prediction=True, needs_retrieval=True)
            if "predic" in message or any(token in message for token in ["edad", "sexo", "age", "hours.per.week", "education.num"]):
                return schema(intent="prediction", confidence=0.9, rationale="prediction", needs_prediction=True, needs_retrieval=False)
            if any(token in message for token in ["api", "endpoint", "arquitectura", "proyecto", "document", "rag", "agente"]):
                return schema(intent="rag", confidence=0.88, rationale="rag", needs_prediction=False, needs_retrieval=True)
            return schema(intent="chat", confidence=0.75, rationale="chat", needs_prediction=False, needs_retrieval=False)

        if schema_name == "PredictionExtractionCandidate":
            return schema(**extract_prediction_fields(str(payload.get("message", ""))))

        if schema_name == "ReflectionReview":
            question = str(payload.get("question") or "").lower()
            draft_answer = str(payload.get("draft_answer") or "")
            if any(token in question for token in ["como me puedes ayudar", "cómo me puedes ayudar", "en que me puedes ayudar", "explícame qué hago"]) and "Hola, soy AdultBot" in draft_answer:
                return schema(
                    should_revise=True,
                    issues=["The draft answer is too generic for the user's concrete question."],
                    reflection_note="Cuando el usuario pide ayuda concreta, debo responder con opciones accionables en vez de repetir una presentación genérica.",
                    improved_answer=(
                        "Puedo ayudarte de tres formas principales: conversar contigo para orientarte, "
                        "armar una predicción del dataset Adult con los datos que me des en un solo mensaje "
                        "o responder preguntas del proyecto con respaldo documental. "
                        "Si quieres, dime cuál de esas tres rutas te sirve y empezamos."
                    ),
                )
            return schema(
                should_revise=False,
                issues=[],
                reflection_note="La respuesta ya estaba alineada con la intención del usuario.",
                improved_answer=None,
            )

        raise RuntimeError(f"Unsupported structured schema in fake model: {schema_name}")


def _default_settings(runtime_dir: Path, **overrides) -> Settings:
    base_values = {
        "environment": "test",
        "debug": False,
        "enable_langserve": False,
        "auto_reindex_on_startup": False,
        "google_api_key": None,
        "chatgpt_api_key": None,
        "chatgpt_base_url": None,
        "chatgpt_chat_model": None,
        "chatgpt_embedding_model": None,
        "chatgpt_temperature": None,
        "openai_api_key": None,
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
def settings_factory():
    runtime_root = Path(__file__).resolve().parents[1] / "tmp_runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    created_dirs: list[Path] = []

    def factory(**overrides) -> Settings:
        runtime_dir = runtime_root / f"agent-runtime-{uuid4().hex}"
        runtime_dir.mkdir(parents=True, exist_ok=False)
        created_dirs.append(runtime_dir)
        return _default_settings(runtime_dir, **overrides)

    yield factory

    for runtime_dir in created_dirs:
        shutil.rmtree(runtime_dir, ignore_errors=True)


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
    fake_chat_model: FakeConversationalModel | None = None,
) -> Iterator[tuple[TestClient, Settings]]:
    app = create_app(settings)
    with TestClient(app) as client:
        if fake_client is not None:
            client.app.state.oraculo_api_client = fake_client
            client.app.state.workflow.oraculo_api_client = fake_client
            client.app.state.health_service.oraculo_api_client = fake_client
        if fake_chat_model is not None:
            client.app.state.model_gateway._chat_model = fake_chat_model
            client.app.state.workflow.model_gateway._chat_model = fake_chat_model
            client.app.state.knowledge_runtime.model_gateway._chat_model = fake_chat_model
            client.app.state.memory_service.model_gateway._chat_model = fake_chat_model
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
        fake_chat_model: FakeConversationalModel | None = None,
        **settings_overrides,
    ):
        settings = settings_factory(**settings_overrides)
        return _client_context(
            settings=settings,
            fake_client=fake_client,
            documents=documents,
            fake_chat_model=fake_chat_model,
        )

    return factory


@pytest.fixture
def model_gateway(app_settings: Settings) -> ModelGateway:
    return ModelGateway(app_settings)


@pytest.fixture
def fake_chat_model() -> FakeConversationalModel:
    return FakeConversationalModel()
