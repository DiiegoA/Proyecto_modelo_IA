from __future__ import annotations

from app.core.exceptions import ResourceNotFoundError
from app.db.repositories import ThreadRepository
from app.schemas.thread import ThreadMessageResponse, ThreadResponse


class ThreadService:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    def list_message_dicts(self, *, thread_id: str, user_id: str, limit: int = 50) -> list[dict]:
        with self.session_factory() as session:
            repository = ThreadRepository(session)
            try:
                repository.get_for_user(thread_id=thread_id, user_id=user_id)
            except ResourceNotFoundError:
                return []
            messages = repository.list_messages(thread_id=thread_id, limit=limit)
            return [
                {
                    "role": message.role,
                    "content": message.content,
                    "route": message.route,
                    "metadata": message.metadata_json,
                }
                for message in messages
            ]

    def record_turn(
        self,
        *,
        thread_id: str,
        user_id: str,
        user_message: str,
        assistant_message: str,
        route: str,
        citations: list[dict],
        trace_id: str,
        assistant_metadata: dict | None = None,
    ) -> None:
        with self.session_factory() as session:
            repository = ThreadRepository(session)
            thread = repository.get_or_create(thread_id=thread_id, user_id=user_id)
            repository.add_message(thread_id=thread_id, role="user", content=user_message, metadata_json={})
            repository.add_message(
                thread_id=thread_id,
                role="assistant",
                content=assistant_message,
                route=route,
                metadata_json={"citations": citations, "trace_id": trace_id, **(assistant_metadata or {})},
            )
            thread.current_route = route
            thread.last_trace_id = trace_id
            session.commit()

    def get_thread(self, *, thread_id: str, user_id: str) -> ThreadResponse:
        with self.session_factory() as session:
            repository = ThreadRepository(session)
            thread = repository.get_for_user(thread_id=thread_id, user_id=user_id)
            messages = repository.list_messages(thread_id=thread_id, limit=200)
            response = ThreadResponse(
                thread_id=thread.id,
                user_id=thread.user_id,
                current_route=thread.current_route,
                title=thread.title,
                last_trace_id=thread.last_trace_id,
                messages=[
                    ThreadMessageResponse(
                        role=message.role,
                        content=message.content,
                        route=message.route,
                        metadata=message.metadata_json,
                        citations=message.metadata_json.get("citations", []),
                    )
                    for message in messages
                ],
            )
            session.commit()
            return response
