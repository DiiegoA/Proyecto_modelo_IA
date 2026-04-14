from __future__ import annotations

from uuid import uuid4

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class MemoryRecord(TimestampMixin, Base):
    __tablename__ = "memory_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    namespace: Mapped[str] = mapped_column(String(64), default="semantic")
    source_thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    raw_content: Mapped[str] = mapped_column(Text)
    redacted_content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(128), index=True)
    importance: Mapped[float] = mapped_column(default=0.5)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
