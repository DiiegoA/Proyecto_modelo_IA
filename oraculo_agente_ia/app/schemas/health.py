from __future__ import annotations

from typing import Any

from app.schemas.common import BaseSchema


class LiveHealthResponse(BaseSchema):
    status: str
    service: str
    version: str


class ReadyHealthResponse(BaseSchema):
    status: str
    service: str
    version: str
    dependencies: dict[str, Any]
