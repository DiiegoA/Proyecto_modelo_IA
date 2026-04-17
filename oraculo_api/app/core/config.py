from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ORACULO_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Oráculo Adult Income API"
    app_version: str = "2.0.0"
    environment: Literal["local", "development", "test", "staging", "production"] = "development"
    debug: bool = False

    api_v1_prefix: str = "/api/v1"
    docs_enabled: bool = True
    openapi_url: str = "/openapi.json"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"

    database_url: str = "sqlite:///./oraculo.db"
    database_echo: bool = False
    auto_create_tables: bool = True
    auto_seed_admin: bool = True
    seed_admin_email: str | None = None
    seed_admin_password: str | None = None
    seed_admin_name: str = "Administrator"

    model_path: str = "app/ml/pipeline_produccion.pkl"

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "localhost",
            "127.0.0.1",
            "testserver",
            "*.hf.space",
            "*.huggingface.co",
        ]
    )
    cors_allow_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    max_request_size_bytes: int = 32_768
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    rate_limit_exempt_paths: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "/",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/v1/health/live",
            "/api/v1/health/ready",
        ]
    )
    security_headers_enabled: bool = True

    prediction_history_default_limit: int = 20
    prediction_history_max_limit: int = 100

    @field_validator("allowed_hosts", "cors_allow_origins", "rate_limit_exempt_paths", mode="before")
    @classmethod
    def _split_csv_values(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        if not value:
            return []
        normalized_value = value.strip()
        if normalized_value.startswith("["):
            parsed_value = json.loads(normalized_value)
            if isinstance(parsed_value, list):
                return [str(item).strip() for item in parsed_value if str(item).strip()]
        return [item.strip() for item in value.split(",") if item.strip()]

    @field_validator("allowed_hosts", mode="after")
    @classmethod
    def _normalize_allowed_hosts(cls, value: list[str]) -> list[str]:
        normalized_hosts: list[str] = []
        for raw_host in value:
            normalized_host = cls._normalize_allowed_host(raw_host)
            if normalized_host and normalized_host not in normalized_hosts:
                normalized_hosts.append(normalized_host)
        return normalized_hosts

    @field_validator("cors_allow_origins", mode="after")
    @classmethod
    def _normalize_cors_allow_origins(cls, value: list[str]) -> list[str]:
        normalized_origins: list[str] = []
        for raw_origin in value:
            normalized_origin = cls._normalize_origin(raw_origin)
            if normalized_origin and normalized_origin not in normalized_origins:
                normalized_origins.append(normalized_origin)
        return normalized_origins

    @staticmethod
    def _normalize_allowed_host(value: str) -> str:
        normalized_value = value.strip()
        if not normalized_value or normalized_value == "*":
            return normalized_value

        candidate = normalized_value if "://" in normalized_value else f"//{normalized_value}"
        parsed = urlsplit(candidate)
        hostname = parsed.hostname or parsed.netloc
        if hostname:
            return hostname.strip().lower()

        host_candidate = normalized_value.split("/", 1)[0].strip()
        if "@" in host_candidate:
            host_candidate = host_candidate.rsplit("@", 1)[-1]
        return host_candidate.lower()

    @staticmethod
    def _normalize_origin(value: str) -> str:
        normalized_value = value.strip().rstrip("/")
        if not normalized_value or normalized_value == "*" or "://" not in normalized_value:
            return normalized_value

        parsed = urlsplit(normalized_value)
        if not parsed.scheme or not parsed.netloc:
            return normalized_value
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"

    @property
    def base_dir(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def resolved_model_path(self) -> Path:
        model_path = Path(self.model_path)
        if model_path.is_absolute():
            return model_path
        return self.base_dir / model_path

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
