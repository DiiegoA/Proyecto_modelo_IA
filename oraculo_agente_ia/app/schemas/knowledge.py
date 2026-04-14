from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import ConfigDict

from app.schemas.common import BaseSchema


class ReindexRequest(BaseSchema):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["full", "incremental"] = "incremental"


class ReindexResponse(BaseSchema):
    mode: str
    indexed_sources: int
    total_chunks: int
    status: str


class KnowledgeSourceResponse(BaseSchema):
    id: str
    source_path: str
    source_type: str
    title: str
    content_hash: str
    status: str
    chunk_count: int
    last_indexed_at: datetime


class KnowledgeSourceListResponse(BaseSchema):
    items: list[KnowledgeSourceResponse]
