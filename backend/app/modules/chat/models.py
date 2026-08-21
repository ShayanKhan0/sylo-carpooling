"""
Chat Module - Threaded Chat Models

Thread model supports one private conversation per ride booking
(driver <-> passenger). Message model stores per-thread messages.
"""

from datetime import datetime
import uuid

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Boolean,
    Integer,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ChatThread(Base):
    """
    Private chat thread between a ride's driver and one passenger booking.

    A ride with multiple passengers will therefore have multiple threads.
    """

    __tablename__ = "chat_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ride_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rides.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    booking_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    booking_source = Column(String(20), nullable=False, default="ride_bookings")

    driver_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    passenger_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status = Column(String(20), nullable=False, default="active", index=True)
    lock_reason = Column(String(50), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)

    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_message_preview = Column(String(280), nullable=True)
    message_count = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ux_chat_threads_ride_booking_source",
            "ride_id",
            "booking_id",
            "booking_source",
            unique=True,
        ),
        Index("ix_chat_threads_driver_status", "driver_id", "status"),
        Index("ix_chat_threads_passenger_status", "passenger_id", "status"),
        Index("ix_chat_threads_status_last_message", "status", "last_message_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<ChatThread(id={self.id}, ride_id={self.ride_id}, "
            f"driver_id={self.driver_id}, passenger_id={self.passenger_id}, "
            f"status={self.status})>"
        )


class ChatThreadMessage(Base):
    """
    Message row for one private chat thread.
    """

    __tablename__ = "chat_thread_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
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
    receiver_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    content = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_chat_thread_messages_thread_created", "thread_id", "created_at"),
        Index("ix_chat_thread_messages_receiver_unread", "receiver_id", "is_read"),
        Index("ix_chat_thread_messages_ride_created", "ride_id", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<ChatThreadMessage(id={self.id}, thread_id={self.thread_id}, "
            f"sender_id={self.sender_id}, receiver_id={self.receiver_id})>"
        )

