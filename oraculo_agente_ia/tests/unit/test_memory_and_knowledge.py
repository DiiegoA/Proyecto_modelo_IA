from __future__ import annotations

from app.agent.model_gateway import ModelGateway
from app.memory.service import MemoryService
from app.rag.service import KnowledgeService, SourceDocument
from tests.helpers import build_runtime_db


def test_memory_service_redacts_pii_and_retrieves_memory(settings_factory):
    settings = settings_factory()
    engine, session_factory = build_runtime_db(settings)
    service = MemoryService(
        settings=settings,
        session_factory=session_factory,
        model_gateway=ModelGateway(settings),
    )

    try:
        events = service.remember_from_interaction(
            user_id="user-1",
            thread_id="thread-1",
            user_message="Mi nombre es Diego y mi correo es diego@example.com",
            assistant_message="Entendido",
        )
        matches = service.search_memories(
            user_id="user-1",
            query="Mi nombre es Diego y mi correo es diego@example.com",
            limit=3,
        )
    finally:
        service.qdrant_client.close()
        engine.dispose()

    assert events
    assert "[EMAIL_REDACTED]" in events[0]["content"]
    assert matches
    assert "[EMAIL_REDACTED]" in matches[0]


def test_memory_service_degrades_when_langmem_requires_runtime_config(settings_factory):
    settings = settings_factory()
    engine, session_factory = build_runtime_db(settings)
    service = MemoryService(
        settings=settings,
        session_factory=session_factory,
        model_gateway=ModelGateway(settings),
    )

    class FailingLangMemManager:
        def invoke(self, *_args, **_kwargs):
            raise RuntimeError("Missing key in 'configurable' field: langgraph_user_id")

    service._langmem_manager = FailingLangMemManager()

    try:
        events = service.remember_from_interaction(
            user_id="user-1",
            thread_id="thread-1",
            user_message="Mi nombre es Diego y mi correo es diego@example.com",
            assistant_message="Entendido",
        )
    finally:
        service.qdrant_client.close()
        engine.dispose()

    assert events
    assert "[EMAIL_REDACTED]" in events[0]["content"]


def test_knowledge_service_reindexes_incrementally_and_updates_sources(settings_factory):
    settings = settings_factory()
    engine, session_factory = build_runtime_db(settings)
    service = KnowledgeService(
        settings=settings,
        session_factory=session_factory,
        model_gateway=ModelGateway(settings),
    )
    documents_v1 = [
        SourceDocument(
            source_id="doc-1",
            source_path="knowledge_base/doc_1.md",
            title="Doc 1",
            source_type="md",
            content="FastAPI expone la ruta /api/v1/chat/invoke.",
        ),
        SourceDocument(
            source_id="doc-2",
            source_path="knowledge_base/doc_2.md",
            title="Doc 2",
            source_type="md",
            content="Qdrant guarda chunks y memoria semantica.",
        ),
    ]
    documents_v2 = [
        SourceDocument(
            source_id="doc-1",
            source_path="knowledge_base/doc_1.md",
            title="Doc 1",
            source_type="md",
            content="FastAPI expone la ruta /api/v1/chat/invoke y el endpoint /api/v1/chat/stream.",
        ),
        documents_v1[1],
    ]

    try:
        service._collect_static_documents = lambda: documents_v1
        indexed_sources, total_chunks = service.reindex(mode="full")
        second_indexed_sources, second_total_chunks = service.reindex(mode="incremental")

        service._collect_static_documents = lambda: documents_v2
        updated_sources, updated_chunks = service.reindex(mode="incremental")
        hits = service.retrieve(query="stream", limit=3)
        listed_sources = service.list_sources()
    finally:
        service.qdrant_client.close()
        engine.dispose()

    assert indexed_sources == 2
    assert total_chunks >= 2
    assert second_indexed_sources == 0
    assert second_total_chunks == 0
    assert updated_sources == 1
    assert updated_chunks >= 1
    assert hits
    assert any("stream" in hit["snippet"].lower() for hit in hits)
    assert len(listed_sources) == 2
