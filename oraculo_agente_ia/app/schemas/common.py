from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ErrorBody(BaseSchema):
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)
    request_id: str
    timestamp: datetime


class ErrorResponse(BaseSchema):
    error: ErrorBody


class Citation(BaseSchema):
    source_id: str
    source_path: str
    title: str
    snippet: str
    score: float = Field(..., ge=0.0)


class SafetyFlag(BaseSchema):
    code: str
    message: str


class PaginationMeta(BaseSchema):
    total: int
    limit: int
    skip: int
