from __future__ import annotations

import re
from typing import Any

from app.agent.dialogue import is_prediction_in_progress
from app.agent.model_gateway import ModelGateway
from app.agent.types import IntentDecision

PREDICTION_KEYWORDS = {
    "predic",
    "prediccion",
    "prediction",
    "ingreso",
    "salary",
    "income",
    ">50k",
    "<=50k",
    "hours.per.week",
    "education.num",
}

RAG_PATTERNS = [
    r"\bapi\b",
    r"\bendpoints?\b",
    r"\bdocument\w*",
    r"\breadme\b",
    r"\barquitectura\b",
    r"\btecnolog\w*",
    r"\bmodelo\b",
    r"\brag\b",
    r"\bagente\b",
    r"\bproyecto\b",
    r"\bbase de conocimiento\b",
    r"\bknowledge base\b",
]

CHAT_PATTERNS = [
    r"^(hola|buenas|hey|hello|hi)\b",
    r"\bquien eres\b",
    r"\bqu[eé] sabes hacer\b",
    r"\bque puedes hacer\b",
    r"\bc[oó]mo me puedes ayudar\b",
    r"\bgracias\b",
    r"^(ok|vale|perfecto|entendido)\b",
]

UNSAFE_PATTERNS = [
    r"ignore (all )?previous instructions",
    r"reveal (the )?system prompt",
    r"bypass security",
    r"exfiltrate",
    r"tool call",
    r"prompt injection",
]


class IntentRouter:
    def __init__(self, model_gateway: ModelGateway):
        self.model_gateway = model_gateway

    def route(
        self,
        message: str,
        *,
        extracted_field_count: int = 0,
        conversation_state: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
        language: str = "es",
    ) -> IntentDecision:
        llm_decision = self.model_gateway.decide_intent_with_llm(
            message,
            history=history,
            conversation_state=conversation_state,
            language=language,
        )
        prediction_active = is_prediction_in_progress(conversation_state)
        if llm_decision is not None and prediction_active and extracted_field_count > 0 and llm_decision.intent == "chat":
            return IntentDecision(
                intent="prediction",
                confidence=max(llm_decision.confidence, 0.85),
                rationale="The thread is already collecting prediction fields and the current turn adds more profile data.",
                needs_prediction=True,
            )
        if llm_decision is not None and prediction_active and llm_decision.intent == "clarification":
            return IntentDecision(
                intent="prediction",
                confidence=max(llm_decision.confidence, 0.7),
                rationale="The thread remains in prediction mode and should continue gathering fields.",
                needs_prediction=True,
            )
        if llm_decision is not None:
            return llm_decision
        return self._heuristic_route(
            message,
            extracted_field_count=extracted_field_count,
            conversation_state=conversation_state,
        )

    def _heuristic_route(
        self,
        message: str,
        *,
        extracted_field_count: int,
        conversation_state: dict[str, Any] | None,
    ) -> IntentDecision:
        lower_message = message.lower().strip()
        if any(re.search(pattern, lower_message) for pattern in UNSAFE_PATTERNS):
            return IntentDecision(
                intent="unsafe",
                confidence=0.95,
                rationale="Potential prompt injection or unsafe manipulation attempt detected.",
            )

        prediction_active = is_prediction_in_progress(conversation_state)
        has_prediction_signal = extracted_field_count >= 4 or any(
            keyword in lower_message for keyword in PREDICTION_KEYWORDS
        )
        has_rag_signal = any(re.search(pattern, lower_message) for pattern in RAG_PATTERNS)
        has_chat_signal = any(re.search(pattern, lower_message) for pattern in CHAT_PATTERNS)

        if prediction_active and extracted_field_count > 0:
            return IntentDecision(
                intent="prediction",
                confidence=0.82,
                rationale="The thread is already collecting prediction fields and the user supplied more data.",
                needs_prediction=True,
            )

        if prediction_active and len(lower_message.split()) <= 10 and not has_rag_signal and not has_chat_signal:
            return IntentDecision(
                intent="prediction",
                confidence=0.62,
                rationale="The user appears to be continuing an in-progress prediction flow.",
                needs_prediction=True,
            )

        if has_prediction_signal and has_rag_signal:
            return IntentDecision(
                intent="hybrid",
                confidence=0.82,
                rationale="The request mixes prediction needs with documentary context.",
                needs_prediction=True,
                needs_retrieval=True,
            )
        if has_prediction_signal:
            return IntentDecision(
                intent="prediction",
                confidence=0.78,
                rationale="The request appears to ask for a model prediction.",
                needs_prediction=True,
            )
        if has_chat_signal:
            return IntentDecision(
                intent="chat",
                confidence=0.8,
                rationale="The user is greeting, asking for capabilities or continuing social conversation.",
            )
        if has_rag_signal:
            return IntentDecision(
                intent="rag",
                confidence=0.7,
                rationale="The request appears to ask for documentary or factual information.",
                needs_retrieval=True,
            )
        if "?" in message:
            return IntentDecision(
                intent="chat",
                confidence=0.55,
                rationale="The question does not clearly require prediction or retrieval, so a conversational reply is safer.",
            )
        return IntentDecision(
            intent="chat",
            confidence=0.5,
            rationale="Defaulting to a conversational response when no stronger task signal is present.",
        )
