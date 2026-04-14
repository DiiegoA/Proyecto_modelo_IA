from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(..., min_length=5, max_length=255)
    full_name: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=12, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=12, max_length=128)


class SessionUser(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool


class SessionResponse(BaseModel):
    authenticated: bool
    user: SessionUser | None = None


class ChatInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    thread_id: str | None = Field(default=None, max_length=64)
    message: str = Field(..., min_length=1, max_length=8_000)
    language: str = Field(default="es", max_length=12)
    metadata: dict[str, Any] = Field(default_factory=dict)
