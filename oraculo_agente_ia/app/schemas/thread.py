from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.chat import RouteName
from app.schemas.common import BaseSchema, Citation


class ThreadMessageResponse(BaseSchema):
    role: str
    content: str
    route: RouteName | None = None
    metadata: dict[str, Any]
    citations: list[Citation] = Field(default_factory=list)


class ThreadResponse(BaseSchema):
    thread_id: str
    user_id: str
    current_route: str
    title: str
    last_trace_id: str | None
    messages: list[ThreadMessageResponse]
