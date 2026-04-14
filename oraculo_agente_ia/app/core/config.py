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
        env_prefix="ORACULO_AGENT_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Oraculo Agente IA"
    app_version: str = "1.0.0"
    environment: Literal["local", "development", "test", "staging", "production"] = "development"
    debug: bool = False

    api_v1_prefix: str = "/api/v1"
    docs_enabled: bool = True
    openapi_url: str = "/openapi.json"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"

    database_url: str = "sqlite:///./data/oraculo_agent.db"
    database_echo: bool = False
    checkpoints_db_path: str = "data/langgraph_checkpoints.sqlite"
    qdrant_path: str = "data/qdrant"
    qdrant_collection_name: str = "knowledge_chunks"
    qdrant_memory_collection_name: str = "semantic_memory"

    google_api_key: str | None = None
    google_chat_model: str = "gemini-2.5-flash"
    google_embedding_model: str = "models/gemini-embedding-001"
    google_temperature: float = Field(default=0.1, ge=0.0, le=1.0)

    oraculo_api_base_url: str = "https://diiegoal-oraculo-api.hf.space"
    oraculo_api_timeout_seconds: int = Field(default=20, ge=1, le=120)
    oraculo_api_jwt_secret_key: str = "replace-this-with-the-same-secret-used-by-oraculo-api"
    oraculo_api_jwt_algorithm: str = "HS256"
    oraculo_api_verify_remote_user: bool = True
    oraculo_api_service_email: str = "admin@example.com"
    oraculo_api_service_password: str = "ChangeMe!12345"

    admin_api_key: str = "change-this-admin-key"
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
    max_request_size_bytes: int = 65_536
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
    redact_pii: bool = True

    rag_top_k: int = Field(default=5, ge=1, le=20)
    rag_chunk_size: int = Field(default=900, ge=200, le=4_000)
    rag_chunk_overlap: int = Field(default=180, ge=0, le=800)
    auto_reindex_on_startup: bool = False

    enable_langserve: bool = True
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None

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

    @field_validator("oraculo_api_base_url", mode="after")
    @classmethod
    def _normalize_api_base_url(cls, value: str) -> str:
        return value.rstrip("/")

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
        return normalized_value.split("/", 1)[0].strip().lower()

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
    def project_root(self) -> Path:
        return self.base_dir.parent

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def generated_dir(self) -> Path:
        return self.data_dir / "generated"

    @property
    def knowledge_base_dir(self) -> Path:
        return self.base_dir / "knowledge_base"

    @property
    def resolved_checkpoints_db_path(self) -> Path:
        path = Path(self.checkpoints_db_path)
        return path if path.is_absolute() else self.base_dir / path

    @property
    def resolved_qdrant_path(self) -> Path:
        path = Path(self.qdrant_path)
        return path if path.is_absolute() else self.base_dir / path

    @property
    def can_use_google_models(self) -> bool:
        return bool(self.google_api_key)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def create_runtime_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_base_dir.mkdir(parents=True, exist_ok=True)
        self.resolved_qdrant_path.mkdir(parents=True, exist_ok=True)
        self.resolved_checkpoints_db_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.create_runtime_directories()
    return settings
