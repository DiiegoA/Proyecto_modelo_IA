from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.db.models import ThreadConversation, ThreadMessage


class ThreadRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_or_create(self, *, thread_id: str, user_id: str, title: str = "Conversation") -> ThreadConversation:
        thread = self.session.get(ThreadConversation, thread_id)
        if thread:
            return thread
        thread = ThreadConversation(id=thread_id, user_id=user_id, title=title)
        self.session.add(thread)
        self.session.flush()
        return thread

    def get_for_user(self, *, thread_id: str, user_id: str) -> ThreadConversation:
        thread = self.session.get(ThreadConversation, thread_id)
        if thread is None or thread.user_id != user_id:
            raise ResourceNotFoundError("Thread", thread_id)
        return thread

    def add_message(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        route: str | None = None,
        metadata_json: dict | None = None,
    ) -> ThreadMessage:
        message = ThreadMessage(
            thread_id=thread_id,
            role=role,
            content=content,
            route=route,
            metadata_json=metadata_json or {},
        )
        self.session.add(message)
        self.session.flush()
        return message

    def list_messages(self, *, thread_id: str, limit: int = 50) -> list[ThreadMessage]:
        statement = (
            select(ThreadMessage)
            .where(ThreadMessage.thread_id == thread_id)
            .order_by(ThreadMessage.created_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))
