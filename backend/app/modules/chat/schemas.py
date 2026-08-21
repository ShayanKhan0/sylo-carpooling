"""
Chat Module - Pydantic Schemas (thread-based).
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ChatThreadEnsureRequest(BaseModel):
    """Create/get a private thread for a specific booking context."""

    ride_id: UUID
    booking_id: Optional[UUID] = None
    passenger_id: Optional[UUID] = None

    @model_validator(mode="after")
    def _validate_booking_or_passenger(self):
        if self.booking_id is None and self.passenger_id is None:
            raise ValueError("Either booking_id or passenger_id is required")
        return self


class ChatMessageCreate(BaseModel):
    """Request schema for sending a chat message."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Message content",
    )


class ChatThreadOut(BaseModel):
    """Thread metadata for list/detail views."""

    id: UUID
    ride_id: UUID
    booking_id: UUID
    booking_source: str
    driver_id: UUID
    passenger_id: UUID
    status: str
    lock_reason: Optional[str] = None
    locked_at: Optional[datetime] = None
    can_send: bool = False
    message_count: int = 0
    unread_count: int = 0
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    counterpart_user_id: UUID
    counterpart_name: str
    counterpart_profile_photo: Optional[str] = None
    ride_origin: Optional[str] = None
    ride_destination: Optional[str] = None
    ride_departure_time: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ChatMessageOut(BaseModel):
    """Response schema for a chat message."""

    id: UUID
    thread_id: UUID
    ride_id: UUID
    sender_id: UUID
    sender_name: Optional[str] = None
    receiver_id: UUID
    content: str
    is_read: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatConversation(BaseModel):
    """Thread conversation payload."""

    thread: ChatThreadOut
    messages: list[ChatMessageOut] = []
    total: int = 0


class ChatThreadListResponse(BaseModel):
    """Thread listing payload."""

    threads: list[ChatThreadOut] = []
    total: int = 0
    unread_total: int = 0
