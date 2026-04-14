from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

RouteName = Literal["prediction", "rag", "hybrid", "clarification", "unsafe"]


class IntentDecision(BaseModel):
    intent: RouteName
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    needs_prediction: bool = False
    needs_retrieval: bool = False


class PredictionFieldExtraction(BaseModel):
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    is_complete: bool = False


class ToolCallPlan(BaseModel):
    tools: list[str] = Field(default_factory=list)
    reasoning: str = ""


class ReflectionVerdict(BaseModel):
    is_safe: bool = True
    has_sufficient_evidence: bool = True
    needs_clarification: bool = False
    issues: list[str] = Field(default_factory=list)
    suggested_answer: str | None = None


class AnswerEnvelope(BaseModel):
    answer: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    safety_flags: list[dict[str, str]] = Field(default_factory=list)


class AgentState(TypedDict, total=False):
    thread_id: str
    user_id: str
    user_token: str | None
    language: str
    current_input: str
    messages: list[dict[str, Any]]
    intent: RouteName
    missing_prediction_fields: list[str]
    extracted_prediction_fields: dict[str, Any]
    retrieval_hits: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    tool_results: dict[str, Any]
    reflection_report: dict[str, Any]
    memory_events: list[dict[str, Any]]
    safety_flags: list[dict[str, str]]
    answer: str
    response_mode: str
    trace_id: str
    confidence: float
