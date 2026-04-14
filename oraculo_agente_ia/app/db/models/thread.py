from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class ThreadConversation(TimestampMixin, Base):
    __tablename__ = "thread_conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    current_route: Mapped[str] = mapped_column(String(32), default="clarification")
    title: Mapped[str] = mapped_column(String(255), default="Conversation")
    last_trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    messages = relationship("ThreadMessage", back_populates="thread", cascade="all, delete-orphan")
