from __future__ import annotations

import re

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
    r"\bhow\b",
    r"\bwhat\b",
    r"\bqu[eé]\b",
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

    def route(self, message: str, extracted_field_count: int = 0) -> IntentDecision:
        llm_decision = self.model_gateway.decide_intent_with_llm(message)
        if llm_decision is not None:
            return llm_decision
        return self._heuristic_route(message, extracted_field_count)

    def _heuristic_route(self, message: str, extracted_field_count: int) -> IntentDecision:
        lower_message = message.lower()
        if any(re.search(pattern, lower_message) for pattern in UNSAFE_PATTERNS):
            return IntentDecision(
                intent="unsafe",
                confidence=0.95,
                rationale="Potential prompt injection or unsafe manipulation attempt detected.",
            )

        has_prediction_signal = extracted_field_count >= 4 or any(
            keyword in lower_message for keyword in PREDICTION_KEYWORDS
        )
        has_rag_signal = any(re.search(pattern, lower_message) for pattern in RAG_PATTERNS)

        if has_prediction_signal and has_rag_signal:
            return IntentDecision(
                intent="hybrid",
                confidence=0.8,
                rationale="The request mixes prediction needs with documentary context.",
                needs_prediction=True,
                needs_retrieval=True,
            )
        if has_prediction_signal:
            return IntentDecision(
                intent="prediction",
                confidence=0.75,
                rationale="The request appears to ask for a model prediction.",
                needs_prediction=True,
            )
        if has_rag_signal or "?" in message:
            return IntentDecision(
                intent="rag",
                confidence=0.65,
                rationale="The request appears to ask for documentary or factual information.",
                needs_retrieval=True,
            )
        return IntentDecision(
            intent="clarification",
            confidence=0.4,
            rationale="The request does not yet expose a clear prediction or retrieval goal.",
        )
