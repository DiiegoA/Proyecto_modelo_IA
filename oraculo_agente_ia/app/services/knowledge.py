from __future__ import annotations

from app.rag.service import KnowledgeService
from app.schemas.knowledge import (
    KnowledgeSourceListResponse,
    KnowledgeSourceResponse,
    ReindexResponse,
    UploadKnowledgeResponse,
)


class KnowledgeAdminService:
    def __init__(self, knowledge_service: KnowledgeService):
        self.knowledge_service = knowledge_service

    def reindex(self, *, mode: str) -> ReindexResponse:
        indexed_sources, total_chunks = self.knowledge_service.reindex(mode=mode)
        return ReindexResponse(
            mode=mode,
            indexed_sources=indexed_sources,
            total_chunks=total_chunks,
            status="completed",
        )

    def list_sources(self) -> KnowledgeSourceListResponse:
        return KnowledgeSourceListResponse(
            items=[KnowledgeSourceResponse.model_validate(source) for source in self.knowledge_service.list_sources()]
        )

    def upload_document(self, *, file_name: str, content: bytes) -> UploadKnowledgeResponse:
        document = self.knowledge_service.store_uploaded_document(file_name=file_name, content=content)
        indexed_sources, total_chunks = self.knowledge_service.reindex(mode="incremental")
        return UploadKnowledgeResponse(
            **document,
            indexed_sources=indexed_sources,
            total_chunks=total_chunks,
            status="uploaded",
        )
