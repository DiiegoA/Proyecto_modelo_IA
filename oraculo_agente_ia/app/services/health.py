from __future__ import annotations

from pathlib import Path

from app.clients.oraculo_api import OraculoApiClient
from app.core.config import Settings
from app.db.session import check_database_connection
from app.rag.service import KnowledgeService
from app.schemas.health import LiveHealthResponse, ReadyHealthResponse


class HealthService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory,
        knowledge_service: KnowledgeService,
        oraculo_api_client: OraculoApiClient,
    ):
        self.settings = settings
        self.session_factory = session_factory
        self.knowledge_service = knowledge_service
        self.oraculo_api_client = oraculo_api_client

    def live(self) -> LiveHealthResponse:
        return LiveHealthResponse(
            status="ok",
            service=self.settings.app_name,
            version=self.settings.app_version,
        )

    def ready(self) -> ReadyHealthResponse:
        dependencies: dict[str, object] = {}

        with self.session_factory() as session:
            dependencies["database"] = {"ok": check_database_connection(session)}

        dependencies["checkpointer"] = {"ok": Path(self.settings.resolved_checkpoints_db_path).parent.exists()}

        try:
            self.knowledge_service._ensure_collection()
            self.knowledge_service.qdrant_client.get_collection(self.settings.qdrant_collection_name)
            dependencies["qdrant"] = {"ok": True}
        except Exception as exc:
            dependencies["qdrant"] = {"ok": False, "error": str(exc)}

        try:
            sources = self.knowledge_service.list_sources()
            dependencies["knowledge_index"] = {"ok": True, "sources": len(sources)}
        except Exception as exc:
            dependencies["knowledge_index"] = {"ok": False, "error": str(exc)}

        try:
            dependencies["oraculo_api"] = {"ok": True, "payload": self.oraculo_api_client.health_check()}
        except Exception as exc:
            dependencies["oraculo_api"] = {"ok": False, "error": str(exc)}

        dependencies["google_api"] = {"ok": bool(self.settings.google_api_key)}
        status = "ready" if all(item.get("ok") for item in dependencies.values()) else "degraded"
        return ReadyHealthResponse(
            status=status,
            service=self.settings.app_name,
            version=self.settings.app_version,
            dependencies=dependencies,
        )
