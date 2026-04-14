from __future__ import annotations

from app.agent.model_gateway import ModelGateway
from app.core.config import get_settings
from app.db.session import build_engine, build_session_factory, create_tables
from app.rag.service import KnowledgeService
from qdrant_client import QdrantClient


def main() -> None:
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    create_tables(engine)
    qdrant_client = QdrantClient(path=str(settings.resolved_qdrant_path))

    knowledge_service = KnowledgeService(
        settings=settings,
        session_factory=session_factory,
        model_gateway=ModelGateway(settings),
        qdrant_client=qdrant_client,
    )
    try:
        indexed_sources, total_chunks = knowledge_service.reindex(mode="incremental")
        print(f"indexed_sources={indexed_sources}")
        print(f"total_chunks={total_chunks}")
    finally:
        qdrant_client.close()
        engine.dispose()


if __name__ == "__main__":
    main()
