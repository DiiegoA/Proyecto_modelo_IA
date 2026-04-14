from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

PREDICTION_FIELD_ORDER = [
    "age",
    "workclass",
    "fnlwgt",
    "education",
    "education_num",
    "marital_status",
    "occupation",
    "relationship",
    "race",
    "sex",
    "capital_gain",
    "capital_loss",
    "hours_per_week",
    "native_country",
]

FIELD_DISPLAY_NAMES = {
    "age": "edad",
    "workclass": "tipo de trabajo",
    "fnlwgt": "fnlwgt",
    "education": "educación",
    "education_num": "education.num",
    "marital_status": "estado civil",
    "occupation": "ocupación",
    "relationship": "relación",
    "race": "raza",
    "sex": "sexo",
    "capital_gain": "capital.gain",
    "capital_loss": "capital.loss",
    "hours_per_week": "hours.per.week",
    "native_country": "país de origen",
}

KEY_ALIASES = {
    "age": {"age", "edad"},
    "workclass": {"workclass", "tipo_trabajo", "tipo_de_trabajo"},
    "fnlwgt": {"fnlwgt"},
    "education": {"education", "educacion"},
    "education_num": {"educationnum", "education_num", "education.num", "nivel_educacion_num"},
    "marital_status": {"maritalstatus", "marital_status", "marital.status", "estado_civil"},
    "occupation": {"occupation", "ocupacion"},
    "relationship": {"relationship", "relacion"},
    "race": {"race", "raza"},
    "sex": {"sex", "sexo", "genero"},
    "capital_gain": {"capitalgain", "capital_gain", "capital.gain", "ganancia_capital"},
    "capital_loss": {"capitalloss", "capital_loss", "capital.loss", "perdida_capital"},
    "hours_per_week": {"hoursperweek", "hours_per_week", "hours.per.week", "horas_por_semana"},
    "native_country": {"nativecountry", "native_country", "native.country", "pais", "pais_origen"},
}

VALUE_NORMALIZERS = {
    "sex": {
        "male": "Male",
        "masculino": "Male",
        "hombre": "Male",
        "female": "Female",
        "femenino": "Female",
        "mujer": "Female",
    }
}

JSON_PATTERN = re.compile(r"\{.*\}", re.DOTALL)
TEXT_CAPTURE_PATTERN = r"(?P<value>[^,.;\n]+)"

NATURAL_LANGUAGE_PATTERNS = {
    "age": (
        re.compile(r"\btengo\s+(?P<value>\d{1,3})\s+anos\b", re.IGNORECASE),
        re.compile(r"\bedad\s*(?:es|:)?\s*(?P<value>\d{1,3})\b", re.IGNORECASE),
    ),
    "workclass": (
        re.compile(r"\b(?:mi\s+)?workclass\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?tipo\s+de\s+trabajo\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
    ),
    "fnlwgt": (
        re.compile(r"\b(?:mi\s+)?fnlwgt\s*(?:es|:)\s*(?P<value>\d+)\b", re.IGNORECASE),
    ),
    "education": (
        re.compile(r"\bestudie\s+" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?education\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?educacion\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
    ),
    "education_num": (
        re.compile(r"\b(?:mi\s+)?education(?:\.num|_num)?\s*(?:es|:)\s*(?P<value>\d+)\b", re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?nivel\s+de\s+educacion\s*(?:es|:)\s*(?P<value>\d+)\b", re.IGNORECASE),
    ),
    "marital_status": (
        re.compile(r"\b(?:mi\s+)?marital(?:\.status|_status)?\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?estado\s+civil\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
    ),
    "occupation": (
        re.compile(r"\btrabajo\s+como\s+" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?occupation\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?ocupacion\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
    ),
    "relationship": (
        re.compile(r"\b(?:mi\s+)?relationship\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?relacion\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
    ),
    "race": (
        re.compile(r"\b(?:mi\s+)?race\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?raza\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
    ),
    "sex": (
        re.compile(r"\bsoy\s+(?P<value>hombre|mujer)\b", re.IGNORECASE),
        re.compile(r"\bsexo\s*(?:es|:)?\s*(?P<value>male|female|hombre|mujer|masculino|femenino)\b", re.IGNORECASE),
    ),
    "capital_gain": (
        re.compile(r"\bganancia\s+de\s+capital\s+(?:de\s+)?(?P<value>\d+)\b", re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?capital(?:\.gain|_gain)?\s*(?:es|:)\s*(?P<value>\d+)\b", re.IGNORECASE),
    ),
    "capital_loss": (
        re.compile(r"\bperdida\s+de\s+capital\s+(?:de\s+)?(?P<value>\d+)\b", re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?capital(?:\.loss|_loss)?\s*(?:es|:)\s*(?P<value>\d+)\b", re.IGNORECASE),
    ),
    "hours_per_week": (
        re.compile(r"\btrabajo\s+(?P<value>\d{1,2})\s+horas\s+por\s+semana\b", re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?horas\s+por\s+semana\s*(?:son|es|:)?\s*(?P<value>\d{1,2})\b", re.IGNORECASE),
        re.compile(r"\bhours(?:\.per\.week|_per_week)?\s*(?:es|:)\s*(?P<value>\d{1,2})\b", re.IGNORECASE),
    ),
    "native_country": (
        re.compile(r"\bnaci\s+en\s+" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?native(?:\.country|_country)?\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
        re.compile(r"\b(?:mi\s+)?pais(?:\s+de\s+origen)?\s*(?:es|:)\s*" + TEXT_CAPTURE_PATTERN, re.IGNORECASE),
    ),
}


def _validate_category_text(value: str) -> str:
    clean_value = value.strip()
    if not clean_value:
        raise ValueError("Value must not be blank.")
    if len(clean_value) > 64:
        raise ValueError("Value exceeds the maximum allowed length.")
    if any(ord(character) < 32 for character in clean_value):
        raise ValueError("Control characters are not allowed.")
    return clean_value


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(character for character in normalized if not unicodedata.combining(character))


class PredictionPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)

    age: int = Field(..., ge=17, le=100)
    workclass: str = Field(..., min_length=1, max_length=64)
    fnlwgt: int = Field(..., ge=1, le=2_000_000)
    education: str = Field(..., min_length=1, max_length=64)
    education_num: int = Field(..., alias="education.num", ge=1, le=16)
    marital_status: str = Field(..., alias="marital.status", min_length=1, max_length=64)
    occupation: str = Field(..., min_length=1, max_length=64)
    relationship: str = Field(..., min_length=1, max_length=64)
    race: str = Field(..., min_length=1, max_length=64)
    sex: str = Field(..., min_length=4, max_length=6)
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


class PredictionExtractionCandidate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid", str_strip_whitespace=True)

    age: int | None = None
    workclass: str | None = None
    fnlwgt: int | None = None
    education: str | None = None
    education_num: int | None = Field(default=None, alias="education.num")
    marital_status: str | None = Field(default=None, alias="marital.status")
    occupation: str | None = None
    relationship: str | None = None
    race: str | None = None
    sex: str | None = None
    capital_gain: int | None = Field(default=None, alias="capital.gain")
    capital_loss: int | None = Field(default=None, alias="capital.loss")
    hours_per_week: int | None = Field(default=None, alias="hours.per.week")
    native_country: str | None = Field(default=None, alias="native.country")


def normalize_prediction_key(key: str) -> str | None:
    candidate = re.sub(r"[^a-z0-9._]+", "_", _strip_accents(key).lower()).strip("_")
    candidate_no_punctuation = candidate.replace(".", "").replace("_", "")
    for canonical_key, aliases in KEY_ALIASES.items():
        if candidate in aliases or candidate_no_punctuation in aliases:
            return canonical_key
    return None


def normalize_prediction_value(field_name: str, value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {'"', "'"}:
            stripped = stripped[1:-1].strip()
        mapped_value = VALUE_NORMALIZERS.get(field_name, {}).get(stripped.lower())
        if mapped_value:
            return mapped_value
        if field_name in {"age", "fnlwgt", "education_num", "capital_gain", "capital_loss", "hours_per_week"}:
            numeric_candidate = stripped.replace(",", "").strip()
            if numeric_candidate.isdigit():
                return int(numeric_candidate)
        return stripped
    return value


def normalize_extracted_fields(raw_fields: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in raw_fields.items():
        normalized_key = normalize_prediction_key(str(key))
        if normalized_key is None or value is None:
            continue
        normalized_value = normalize_prediction_value(normalized_key, value)
        if isinstance(normalized_value, str) and not normalized_value.strip():
            continue
        normalized[normalized_key] = normalized_value
    return normalized


def _extract_natural_language_fields(message: str) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    normalized_message = _strip_accents(message)

    for field_name, patterns in NATURAL_LANGUAGE_PATTERNS.items():
        for pattern in patterns:
            match = pattern.search(normalized_message)
            if not match:
                continue
            value = match.group("value").strip()
            if value:
                extracted[field_name] = normalize_prediction_value(field_name, value)
                break

    return extracted


def extract_prediction_fields(message: str) -> dict[str, Any]:
    extracted: dict[str, Any] = {}
    message_without_json = message

    json_match = JSON_PATTERN.search(message)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, dict):
                extracted.update(normalize_extracted_fields(parsed))
                message_without_json = message.replace(json_match.group(0), " ")
        except json.JSONDecodeError:
            pass

    segments = re.split(r"[\n;,]+", message_without_json)
    for segment in segments:
        if ":" not in segment and "=" not in segment:
            continue
        key, _, value = segment.replace("=", ":", 1).partition(":")
        normalized_key = normalize_prediction_key(key)
        if normalized_key and value.strip():
            extracted[normalized_key] = normalize_prediction_value(normalized_key, value)

    for field_name, value in _extract_natural_language_fields(message_without_json).items():
        extracted.setdefault(field_name, value)

    return extracted


def compute_missing_fields(extracted_fields: dict[str, Any]) -> list[str]:
    return [field_name for field_name in PREDICTION_FIELD_ORDER if field_name not in extracted_fields]


def validate_prediction_fields(extracted_fields: dict[str, Any]) -> tuple[bool, list[str], PredictionPayload | None]:
    missing_fields = compute_missing_fields(extracted_fields)
    if missing_fields:
        return False, missing_fields, None
    try:
        payload = PredictionPayload(**extracted_fields)
    except Exception:
        return False, PREDICTION_FIELD_ORDER, None
    return True, [], payload


def alias_payload(payload: PredictionPayload) -> dict[str, Any]:
    return payload.model_dump(by_alias=True)
