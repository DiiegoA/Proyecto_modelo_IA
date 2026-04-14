from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator

from app.schemas.common import BaseSchema, PaginationMeta

PredictionLabel = Literal["<=50K", ">50K"]


def _validate_category_text(value: str) -> str:
    if not isinstance(value, str):
        return value
    clean_value = value.strip()
    if not clean_value:
        raise ValueError("Value must not be blank.")
    if len(clean_value) > 64:
        raise ValueError("Value exceeds the maximum allowed length.")
    if any(ord(character) < 32 for character in clean_value):
        raise ValueError("Control characters are not allowed.")
    return clean_value


class PredictionInput(BaseSchema):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    age: int = Field(..., ge=17, le=100)
    workclass: str = Field(..., min_length=1, max_length=64)
    fnlwgt: int = Field(..., ge=1, le=2_000_000)
    education: str = Field(..., min_length=1, max_length=64)
    education_num: int = Field(..., alias="education.num", ge=1, le=16)
    marital_status: str = Field(..., alias="marital.status", min_length=1, max_length=64)
    occupation: str = Field(..., min_length=1, max_length=64)
    relationship: str = Field(..., min_length=1, max_length=64)
    race: str = Field(..., min_length=1, max_length=64)
    sex: Literal["Male", "Female"]
    capital_gain: int = Field(..., alias="capital.gain", ge=0, le=100_000)
    capital_loss: int = Field(..., alias="capital.loss", ge=0, le=10_000)
    hours_per_week: int = Field(..., alias="hours.per.week", ge=1, le=99)
    native_country: str = Field(..., alias="native.country", min_length=1, max_length=64)

    @field_validator(
        "workclass",
        "education",
        "marital_status",
        "occupation",
        "relationship",
        "race",
        "native_country",
    )
    @classmethod
    def validate_category_fields(cls, value: str) -> str:
        return _validate_category_text(value)


class PredictionResponse(BaseSchema):
    id: str
    prediction: PredictionLabel
    probability: float = Field(..., ge=0.0, le=1.0)
    is_counterfactual_applied: bool = False
    execution_time_ms: float = Field(..., ge=0.0)
    model_version: str
    request_id: str
    created_at: datetime


class PredictionDetailResponse(PredictionResponse):
    input_payload: dict[str, Any]
    normalized_payload: dict[str, Any]


class PredictionListResponse(BaseSchema):
    items: list[PredictionDetailResponse]
    pagination: PaginationMeta
