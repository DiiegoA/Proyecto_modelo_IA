from __future__ import annotations

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, utcnow


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    source_path: Mapped[str] = mapped_column(String(1_024), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="indexed")
    chunk_count: Mapped[int] = mapped_column(default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_indexed_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
