from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import KnowledgeSource


class KnowledgeSourceRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert(
        self,
        *,
        source_id: str,
        source_path: str,
        source_type: str,
        title: str,
        content_hash: str,
        status: str,
        chunk_count: int,
        metadata_json: dict | None = None,
        error_message: str | None = None,
    ) -> KnowledgeSource:
        source = self.session.get(KnowledgeSource, source_id)
        if source is None:
            source = KnowledgeSource(id=source_id, source_path=source_path, source_type=source_type, title=title)
            self.session.add(source)
        source.content_hash = content_hash
        source.status = status
        source.chunk_count = chunk_count
        source.metadata_json = metadata_json or {}
        source.error_message = error_message
        return source

    def list_all(self) -> list[KnowledgeSource]:
        statement = select(KnowledgeSource).order_by(KnowledgeSource.source_path.asc())
        return list(self.session.scalars(statement))

    def get_by_path(self, source_path: str) -> KnowledgeSource | None:
        statement = select(KnowledgeSource).where(KnowledgeSource.source_path == source_path)
        return self.session.scalars(statement).first()
