"""
Chat module exports.

`ChatMessage` is retained as a legacy ride-wide table model.
New threaded chat uses `ChatThread` and `ChatThreadMessage`.
"""

from datetime import datetime
import uuid

from sqlalchemy import Column, Text, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base
from .models import ChatThread, ChatThreadMessage


class ChatMessage(Base):
    """
    Legacy ride-wide chat message model (kept for backward compatibility).
    """

    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ride_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rides.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_chat_ride_created", "ride_id", "created_at"),
        Index("ix_chat_ride_unread", "ride_id", "is_read"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<ChatMessage(id={self.id}, ride_id={self.ride_id}, "
            f"sender_id={self.sender_id})>"
        )


__all__ = ["ChatMessage", "ChatThread", "ChatThreadMessage"]
