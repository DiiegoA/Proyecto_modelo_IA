from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from app.schemas.common import BaseSchema

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseSchema):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(..., max_length=255)
    full_name: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        lowered = value.lower()
        if not EMAIL_PATTERN.match(lowered):
            raise ValueError("Invalid email format.")
        return lowered

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        checks = [
            any(char.islower() for char in value),
            any(char.isupper() for char in value),
            any(char.isdigit() for char in value),
            any(not char.isalnum() for char in value),
        ]
        if not all(checks):
            raise ValueError(
                "Password must contain uppercase, lowercase, numeric, and special characters."
            )
        return value


class LoginRequest(BaseSchema):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        lowered = value.lower()
        if not EMAIL_PATTERN.match(lowered):
            raise ValueError("Invalid email format.")
        return lowered


class UserResponse(BaseSchema):
    id: str
    email: str
    full_name: str
    role: Literal["admin", "user"]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseSchema):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int
    user: UserResponse
