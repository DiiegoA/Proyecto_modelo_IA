from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MemoryRecord


class MemoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        *,
        user_id: str,
        namespace: str,
        raw_content: str,
        redacted_content: str,
        content_hash: str,
        importance: float,
        source_thread_id: str | None = None,
        metadata_json: dict | None = None,
    ) -> MemoryRecord:
        memory = MemoryRecord(
            user_id=user_id,
            namespace=namespace,
            raw_content=raw_content,
            redacted_content=redacted_content,
            content_hash=content_hash,
            importance=importance,
            source_thread_id=source_thread_id,
            metadata_json=metadata_json or {},
        )
        self.session.add(memory)
        self.session.flush()
        return memory

    def list_for_user(self, *, user_id: str, limit: int = 10) -> list[MemoryRecord]:
        statement = (
            select(MemoryRecord)
            .where(MemoryRecord.user_id == user_id)
            .order_by(MemoryRecord.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))
