from __future__ import annotations

from app.schemas.common import BaseSchema


class LiveHealthResponse(BaseSchema):
    status: str
    service: str
    version: str


class ReadyHealthResponse(BaseSchema):
    status: str
    service: str
    version: str
    model_loaded: bool
    database_connected: bool
