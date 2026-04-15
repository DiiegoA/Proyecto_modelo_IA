from __future__ import annotations

from langchain_core.embeddings import Embeddings

from app.agent.dialogue import (
    build_recent_summary,
    load_conversation_state,
    merge_prediction_slots,
    next_prediction_field,
)
from app.agent.model_gateway import ModelGateway
from app.agent.routing import IntentRouter


def test_compose_chat_answer_falls_back_to_brain_connection_without_llm(settings_factory):
    settings = settings_factory()
    gateway = ModelGateway(settings)

    envelope = gateway.compose_chat_answer(
        question="Hola",
        history=[],
        memories=[],
        language="es",
        conversation_state={},
    )

    assert "cerebro" in envelope.answer.lower()


def test_router_uses_chat_route_for_greeting_with_fake_llm(settings_factory, fake_chat_model):
    settings = settings_factory()
    gateway = ModelGateway(settings)
    gateway._chat_model = fake_chat_model
    router = IntentRouter(gateway)

    decision = router.route(
        "Hola",
        extracted_field_count=0,
        conversation_state={},
        history=[],
        language="es",
    )

    assert decision.intent == "chat"


def test_dialogue_state_is_restored_from_last_assistant_metadata():
    messages = [
        {"role": "user", "content": "Hola", "metadata": {}},
        {
            "role": "assistant",
            "content": "Hola, soy AdultBot.",
            "metadata": {
                "conversation_state": {
                    "assistant_name": "AdultBot",
                    "conversation_goal": "prediction",
                    "active_route": "prediction",
                    "prediction_slots": {"age": 39},
                    "next_slot_to_ask": "workclass",
                    "conversation_summary": "user: Hola",
                    "last_reflection": "Responder de forma mas concreta.",
                    "reflection_notes": ["Responder de forma mas concreta."],
                    "language": "es",
                    "turn_count": 1,
                }
            },
        },
    ]

    state = load_conversation_state(messages, assistant_name="AdultBot", default_language="es")

    assert state.active_route == "prediction"
    assert state.prediction_slots["age"] == 39
    assert state.next_slot_to_ask == "workclass"
    assert state.last_reflection == "Responder de forma mas concreta."
    assert state.reflection_notes == ["Responder de forma mas concreta."]


def test_prediction_slots_merge_and_next_field_work():
    merged = merge_prediction_slots({"age": 39}, {"workclass": "Private"})

    assert merged["age"] == 39
    assert merged["workclass"] == "Private"
    assert next_prediction_field(merged) == "fnlwgt"


def test_recent_summary_uses_latest_messages():
    summary = build_recent_summary(
        [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola, soy AdultBot."},
            {"role": "user", "content": "Quiero una prediccion"},
        ]
    )

    assert "user: Hola" in summary
    assert "assistant: Hola, soy AdultBot." in summary


def test_embedding_model_falls_back_to_openai_when_google_provider_fails(settings_factory, monkeypatch):
    settings = settings_factory(
        google_api_key="google-key",
        openai_api_key="openai-key",
    )
    gateway = ModelGateway(settings)
    calls = {"google": 0, "openai": 0}

    class FailingEmbeddings(Embeddings):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            calls["google"] += 1
            raise RuntimeError("google invalid")

        def embed_query(self, text: str) -> list[float]:
            calls["google"] += 1
            raise RuntimeError("google invalid")

    class WorkingEmbeddings(Embeddings):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            calls["openai"] += 1
            return [[0.25, 0.75] for _ in texts]

        def embed_query(self, text: str) -> list[float]:
            calls["openai"] += 1
            return [0.25, 0.75]

    monkeypatch.setattr(gateway, "_build_google_embeddings", lambda: FailingEmbeddings())
    monkeypatch.setattr(gateway, "_build_openai_embeddings", lambda: WorkingEmbeddings())

    first_vector = gateway.embedding_model.embed_query("Hola")
    second_vector = gateway.embedding_model.embed_query("Hola otra vez")

    assert first_vector == [0.25, 0.75]
    assert second_vector == [0.25, 0.75]
    assert calls["google"] == 1
    assert calls["openai"] == 2


def test_reflection_review_revises_generic_chat_answer_with_fake_llm(settings_factory, fake_chat_model):
    settings = settings_factory()
    gateway = ModelGateway(settings)
    gateway._chat_model = fake_chat_model

    review = gateway.reflect_answer(
        route="chat",
        question="Como me puedes ayudar?",
        draft_answer="Hola, soy AdultBot, tu asistente IA. Puedo conversar contigo, ayudarte con predicciones o responder dudas del proyecto.",
        citations=[],
        missing_fields=[],
        prediction_result=None,
        safety_flags=[],
        language="es",
        history=[],
        conversation_state={},
    )

    assert review is not None
    assert review.should_revise is True
    assert "accionables" in review.reflection_note.lower()
    assert "tres formas principales" in (review.improved_answer or "").lower()
