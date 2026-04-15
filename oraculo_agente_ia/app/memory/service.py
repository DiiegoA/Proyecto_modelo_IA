from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient, models

from app.agent.model_gateway import ModelGateway
from app.core.config import Settings
from app.db.repositories import MemoryRepository

logger = logging.getLogger("oraculo_agent.memory")

EMAIL_PATTERN = re.compile(r"\b[\w\.-]+@[\w\.-]+\.\w+\b")
PHONE_PATTERN = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\d{3}[-.\s]?){2,4}\d{2,4}\b")


class MemoryExtractionItem(BaseModel):
    content: str = Field(min_length=1, max_length=300)


class MemoryExtractionResponse(BaseModel):
    memories: list[MemoryExtractionItem] = Field(default_factory=list, max_length=3)


class MemoryService:
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
        self._vector_size: int | None = None
        self._langmem_manager = None
        self._bootstrap_langmem()

    def _bootstrap_langmem(self) -> None:
        if self.model_gateway.chat_model is None:
            return
        try:
            from langmem import create_memory_store_manager

            self._langmem_manager = create_memory_store_manager(
                self.model_gateway.chat_model,
                store=InMemoryStore(),
                query_limit=3,
            )
        except Exception as exc:
            logger.warning("LangMem was not initialized and heuristics will be used instead: %s", exc)
            self._langmem_manager = None

    def _ensure_collection(self) -> None:
        if self._vector_size is None:
            self._vector_size = len(self.model_gateway.embedding_model.embed_query("semantic memory health"))
        if not self.qdrant_client.collection_exists(self.settings.qdrant_memory_collection_name):
            self.qdrant_client.create_collection(
                collection_name=self.settings.qdrant_memory_collection_name,
                vectors_config=models.VectorParams(size=self._vector_size, distance=models.Distance.COSINE),
            )

    @staticmethod
    def redact_pii(text: str) -> str:
        redacted = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)
        redacted = PHONE_PATTERN.sub("[PHONE_REDACTED]", redacted)
        return redacted

    @staticmethod
    def _hash_content(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _heuristic_candidates(self, user_message: str) -> list[str]:
        lower_message = user_message.lower()
        candidates: list[str] = []
        if "mi nombre es" in lower_message:
            candidates.append(user_message.strip())
        if "prefiero" in lower_message or "me gusta" in lower_message:
            candidates.append(user_message.strip())
        if "llámame" in lower_message or "llamame" in lower_message:
            candidates.append(user_message.strip())
        return candidates

    def _langmem_candidates(
        self,
        *,
        user_id: str,
        thread_id: str,
        user_message: str,
        assistant_message: str,
    ) -> list[str]:
        if self._langmem_manager is None:
            return []
        try:
            raw_items = self._langmem_manager.invoke(
                [HumanMessage(content=user_message), AIMessage(content=assistant_message)],
                config={
                    "configurable": {
                        "langgraph_user_id": user_id,
                        "thread_id": thread_id,
                    }
                },
            )
        except Exception as exc:
            logger.info("LangMem extraction failed and fallback extraction will be used: %s", exc)
            return []

        candidates: list[str] = []
        for item in raw_items or []:
            if not isinstance(item, dict):
                continue
            for key in ("memory", "value", "content", "text"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
                    break
        return candidates

    def _llm_candidates(self, *, user_message: str, assistant_message: str) -> list[str]:
        chat_model = self.model_gateway.chat_model
        if chat_model is None:
            return []
        try:
            structured_model = chat_model.with_structured_output(MemoryExtractionResponse)
            response = structured_model.invoke(
                [
                    HumanMessage(
                        content=(
                            "Extrae solo recuerdos de largo plazo que sea util conservar del usuario. "
                            "Sirven nombre preferido, preferencias estables, objetivos persistentes o datos de perfil "
                            "explicitamente declarados. No guardes secretos, no guardes datos inferidos y no dupliques "
                            "informacion trivial del turno.\n\n"
                            f"Usuario: {user_message}\n"
                            f"Asistente: {assistant_message}"
                        )
                    )
                ]
            )
            return [item.content.strip() for item in response.memories if item.content.strip()]
        except Exception as exc:
            logger.info("LLM memory extraction fell back to heuristics: %s", exc)
            return []

    def remember_from_interaction(self, *, user_id: str, thread_id: str, user_message: str, assistant_message: str) -> list[dict]:
        try:
            self._ensure_collection()
            candidates = self._langmem_candidates(
                user_id=user_id,
                thread_id=thread_id,
                user_message=user_message,
                assistant_message=assistant_message,
            ) or self._llm_candidates(
                user_message=user_message,
                assistant_message=assistant_message,
            ) or self._heuristic_candidates(user_message)
            memory_events: list[dict] = []

            for candidate in candidates:
                raw_content = candidate.strip()
                if not raw_content:
                    continue
                redacted_content = self.redact_pii(raw_content) if self.settings.redact_pii else raw_content
                content_hash = self._hash_content(redacted_content)

                with self.session_factory() as session:
                    repository = MemoryRepository(session)
                    memory = repository.create(
                        user_id=user_id,
                        namespace="semantic",
                        raw_content=raw_content,
                        redacted_content=redacted_content,
                        content_hash=content_hash,
                        importance=0.6,
                        source_thread_id=thread_id,
                        metadata_json={"extraction_engine": "langmem" if self._langmem_manager else "heuristic"},
                    )
                    session.commit()

                document = Document(
                    page_content=redacted_content,
                    metadata={"memory_id": memory.id, "user_id": user_id, "source_thread_id": thread_id},
                )
                from langchain_qdrant import QdrantVectorStore

                vector_store = QdrantVectorStore(
                    client=self.qdrant_client,
                    collection_name=self.settings.qdrant_memory_collection_name,
                    embedding=self.model_gateway.embedding_model,
                    validate_collection_config=False,
                )
                vector_store.add_documents([document], ids=[memory.id])
                memory_events.append({"memory_id": memory.id, "content": redacted_content})

            return memory_events
        except Exception as exc:
            logger.warning("Memory persistence failed and will be skipped for this turn: %s", exc)
            return []

    def search_memories(self, *, user_id: str, query: str, limit: int = 3) -> list[str]:
        self._ensure_collection()
        from langchain_qdrant import QdrantVectorStore

        vector_store = QdrantVectorStore(
            client=self.qdrant_client,
            collection_name=self.settings.qdrant_memory_collection_name,
            embedding=self.model_gateway.embedding_model,
            validate_collection_config=False,
        )
        results = vector_store.similarity_search_with_score(
            query,
            k=limit,
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="metadata.user_id",
                        match=models.MatchValue(value=user_id),
                    )
                ]
            ),
        )
        return [document.page_content for document, _ in results]
