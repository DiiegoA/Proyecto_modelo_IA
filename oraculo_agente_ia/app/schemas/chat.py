from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from app.schemas.common import BaseSchema, Citation, SafetyFlag

RouteName = Literal["prediction", "rag", "hybrid", "clarification", "unsafe"]


class ChatRequest(BaseSchema):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    thread_id: str | None = Field(default=None, max_length=64)
    message: str = Field(..., min_length=1, max_length=8_000)
    user_id: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)
    language: str = Field(default="es", max_length=12)


class PredictionResult(BaseSchema):
    prediction_id: str
    label: str
    probability: float
    model_version: str
    execution_time_ms: float
    request_id: str


class ChatResponse(BaseSchema):
    thread_id: str
    route: RouteName
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    prediction_result: PredictionResult | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    safety_flags: list[SafetyFlag] = Field(default_factory=list)
    trace_id: str


class StreamEvent(BaseSchema):
    event: str
    data: dict[str, Any]
