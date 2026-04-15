from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ORACULO_WEB_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Oraculo Web"
    app_version: str = "1.0.0"
    environment: Literal["local", "development", "test", "staging", "production"] = "development"
    debug: bool = False

    docs_enabled: bool = True
    openapi_url: str = "/openapi.json"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"

    request_timeout_seconds: int = Field(default=30, ge=5, le=120)
    oraculo_api_base_url: str = "https://diiegoal-oraculo-api.hf.space"
    oraculo_agent_base_url: str = "https://diiegoal-oraculo-agente-ia.hf.space"
    oraculo_agent_admin_api_key: str = "change-this-agent-admin-key"

    session_secret_key: str = "change-this-session-secret-key"
    session_cookie_name: str = "oraculo_web_session"
    session_cookie_https_only: bool = False
    session_max_age_seconds: int = Field(default=86_400, ge=3_600, le=604_800)

    allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "localhost",
            "127.0.0.1",
            "testserver",
        ]
    )

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def split_csv_values(cls, value: str | list[str]) -> list[str]:
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
    def normalize_allowed_hosts(cls, value: list[str]) -> list[str]:
        normalized_hosts: list[str] = []
        for raw_host in value:
            normalized_host = cls.normalize_host(raw_host)
            if normalized_host and normalized_host not in normalized_hosts:
                normalized_hosts.append(normalized_host)
        return normalized_hosts

    @field_validator("oraculo_api_base_url", "oraculo_agent_base_url", mode="after")
    @classmethod
    def normalize_base_url(cls, value: str) -> str:
        return value.rstrip("/")

    @staticmethod
    def normalize_host(value: str) -> str:
        normalized_value = value.strip()
        if not normalized_value or normalized_value == "*":
            return normalized_value
        candidate = normalized_value if "://" in normalized_value else f"//{normalized_value}"
        parsed = urlsplit(candidate)
        hostname = parsed.hostname or parsed.netloc
        if hostname:
            return hostname.strip().lower()
        return normalized_value.split("/", 1)[0].strip().lower()


@lru_cache
def get_settings() -> Settings:
    return Settings()
