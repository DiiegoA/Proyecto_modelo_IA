from __future__ import annotations

import hashlib
import importlib
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient, models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.agent.model_gateway import ModelGateway
from app.agent.prediction_contract import FIELD_DISPLAY_NAMES
from app.core.config import Settings
from app.db.repositories import KnowledgeSourceRepository

logger = logging.getLogger("oraculo_agent.knowledge")


@dataclass
class SourceDocument:
    source_id: str
    source_path: str
    title: str
    source_type: str
    content: str


class KnowledgeService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory,
        model_gateway: ModelGateway,
        qdrant_client: QdrantClient | None = None,
    ):
        self.settings = settings
        self.session_factory = session_factory
        self.model_gateway = model_gateway
        self.qdrant_client = qdrant_client or QdrantClient(path=str(self.settings.resolved_qdrant_path))
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.settings.rag_chunk_size,
            chunk_overlap=self.settings.rag_chunk_overlap,
        )
        self._vector_size: int | None = None

    def _ensure_collection(self) -> None:
        if self._vector_size is None:
            self._vector_size = len(self.model_gateway.embedding_model.embed_query("knowledge health"))
        if not self.qdrant_client.collection_exists(self.settings.qdrant_collection_name):
            self.qdrant_client.create_collection(
                collection_name=self.settings.qdrant_collection_name,
                vectors_config=models.VectorParams(size=self._vector_size, distance=models.Distance.COSINE),
            )

    @staticmethod
    def _hash_content(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _chunk_point_id(source_id: str, chunk_index: int) -> str:
        return str(uuid5(NAMESPACE_URL, f"{source_id}:{chunk_index}"))

    def _vector_store(self) -> QdrantVectorStore:
        self._ensure_collection()
        return QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=self.settings.qdrant_collection_name,
            embedding=self.model_gateway.embedding_model,
            validate_collection_config=False,
        )

    def _bootstrap_generated_sources(self) -> None:
        self.settings.generated_dir.mkdir(parents=True, exist_ok=True)
        self._write_prediction_schema_glossary()
        self._write_openapi_snapshot()

    def _write_prediction_schema_glossary(self) -> None:
        glossary_path = self.settings.generated_dir / "prediction_schema_glossary.md"
        lines = ["# Glosario del contrato de predicción", ""]
        for canonical_field, display_name in FIELD_DISPLAY_NAMES.items():
            lines.append(f"- `{canonical_field}`: {display_name}")
        glossary_path.write_text("\n".join(lines), encoding="utf-8")

    def _write_openapi_snapshot(self) -> None:
        snapshot_path = self.settings.generated_dir / "openapi_snapshot.json"
        try:
            response = httpx.get(
                f"{self.settings.oraculo_api_base_url}/openapi.json",
                timeout=min(self.settings.oraculo_api_timeout_seconds, 5),
            )
            response.raise_for_status()
            payload = response.json()
            snapshot_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            return
        except Exception as exc:
            logger.info("Remote OpenAPI snapshot was not available: %s", exc)

        try:
            if str(self.settings.project_root) not in sys.path:
                sys.path.insert(0, str(self.settings.project_root))
            module = importlib.import_module("oraculo_api.app.main")
            payload = module.app.openapi()
            snapshot_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not generate local OpenAPI snapshot: %s", exc)

    def _collect_static_documents(self) -> list[SourceDocument]:
        self._bootstrap_generated_sources()
        documents: list[SourceDocument] = []

        candidate_paths: list[Path] = []
        candidate_paths.extend(self.settings.knowledge_base_dir.rglob("*.md"))
        candidate_paths.extend(self.settings.generated_dir.glob("*.*"))
        api_readme = self.settings.project_root / "oraculo_api" / "README.md"
        if api_readme.exists():
            candidate_paths.append(api_readme)

        for path in candidate_paths:
            if path.suffix.lower() not in {".md", ".txt", ".json"}:
                continue
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8", errors="ignore").strip()
            if not content:
                continue
            relative_path = path.relative_to(self.settings.project_root) if path.is_relative_to(self.settings.project_root) else path
            source_id = self._hash_content(str(relative_path))[:16]
            documents.append(
                SourceDocument(
                    source_id=source_id,
                    source_path=str(relative_path).replace("\\", "/"),
                    title=path.stem.replace("_", " ").title(),
                    source_type=path.suffix.lower().lstrip("."),
                    content=content,
                )
            )
        return documents

    def reindex(self, *, mode: str = "incremental") -> tuple[int, int]:
        source_documents = self._collect_static_documents()

        if mode == "full":
            try:
                self.qdrant_client.delete_collection(self.settings.qdrant_collection_name)
            except (UnexpectedResponse, ValueError):
                logger.info(
                    "Knowledge collection '%s' did not exist during full reindex.",
                    self.settings.qdrant_collection_name,
                )
            self._vector_size = None

        vector_store = self._vector_store()

        indexed_sources = 0
        total_chunks = 0

        for source in source_documents:
            content_hash = self._hash_content(source.content)
            with self.session_factory() as session:
                repository = KnowledgeSourceRepository(session)
                existing = repository.get_by_path(source.source_path)
                if mode == "incremental" and existing and existing.content_hash == content_hash:
                    session.commit()
                    continue

                if existing:
                    self.qdrant_client.delete(
                        collection_name=self.settings.qdrant_collection_name,
                        points_selector=models.FilterSelector(
                            filter=models.Filter(
                                must=[
                                    models.FieldCondition(
                                        key="metadata.source_id",
                                        match=models.MatchValue(value=existing.id),
                                    )
                                ]
                            )
                        ),
                    )

                chunks = self.splitter.split_text(source.content)
                documents = [
                    Document(
                        page_content=chunk,
                        metadata={
                            "source_id": source.source_id,
                            "source_path": source.source_path,
                            "title": source.title,
                            "source_type": source.source_type,
                            "chunk_index": index,
                        },
                    )
                    for index, chunk in enumerate(chunks)
                ]
                if documents:
                    vector_store.add_documents(
                        documents,
                        ids=[self._chunk_point_id(source.source_id, index) for index in range(len(documents))],
                    )

                repository.upsert(
                    source_id=source.source_id,
                    source_path=source.source_path,
                    source_type=source.source_type,
                    title=source.title,
                    content_hash=content_hash,
                    status="indexed",
                    chunk_count=len(documents),
                )
                session.commit()

                indexed_sources += 1
                total_chunks += len(documents)

        return indexed_sources, total_chunks

    def retrieve(self, *, query: str, limit: int | None = None) -> list[dict]:
        vector_store = self._vector_store()
        results = vector_store.similarity_search_with_score(query, k=limit or self.settings.rag_top_k)
        hits: list[dict] = []
        for document, score in results:
            normalized_score = max(0.0, float(score))
            hits.append(
                {
                    "source_id": document.metadata.get("source_id", ""),
                    "source_path": document.metadata.get("source_path", ""),
                    "title": document.metadata.get("title", "Fuente"),
                    "snippet": document.page_content[:500],
                    "score": normalized_score,
                }
            )
        return hits

    def list_sources(self):
        with self.session_factory() as session:
            repository = KnowledgeSourceRepository(session)
            sources = repository.list_all()
            session.commit()
        return sources
