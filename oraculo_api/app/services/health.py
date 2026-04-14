from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import check_database_connection
from app.ml.model_manager import ModelManager
from app.schemas.health import LiveHealthResponse, ReadyHealthResponse


class HealthService:
    def __init__(self, *, settings: Settings, model_manager: ModelManager):
        self.settings = settings
        self.model_manager = model_manager

    def live(self) -> LiveHealthResponse:
        return LiveHealthResponse(
            status="ok",
            service=self.settings.app_name,
            version=self.settings.app_version,
        )

    def ready(self, session: Session) -> ReadyHealthResponse:
        database_connected = check_database_connection(session)
        model_loaded = self.model_manager.is_loaded
        status = "ready" if database_connected and model_loaded else "degraded"
        return ReadyHealthResponse(
            status=status,
            service=self.settings.app_name,
            version=self.settings.app_version,
            model_loaded=model_loaded,
            database_connected=database_connected,
        )
