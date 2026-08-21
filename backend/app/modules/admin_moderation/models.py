"""
Database models for Admin Moderation (Prompt 12B).

Includes dispute tracking and attachment metadata.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum as SQLEnum, Index, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class DisputeCategoryEnum(str, enum.Enum):
    PAYMENT = "payment"
    SAFETY = "safety"
    CONDUCT = "conduct"
    CANCELLATION = "cancellation"
    OTHER = "other"


class DisputeStatusEnum(str, enum.Enum):
    OPEN = "open"
    UNDER_REVIEW = "under_review"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class DisputePriorityEnum(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Dispute(Base):
    """
    Dispute record for admin moderation.

    Notes:
    - Attachment file content is not stored here, only metadata.
    - Related to users and optional ride.
    """
    __tablename__ = "disputes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    reporter_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reported_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    ride_id = Column(UUID(as_uuid=True), ForeignKey("rides.id", ondelete="SET NULL"), nullable=True, index=True)

    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(SQLEnum(DisputeCategoryEnum), nullable=False, index=True)
    status = Column(SQLEnum(DisputeStatusEnum), nullable=False, default=DisputeStatusEnum.OPEN, index=True)
    priority = Column(SQLEnum(DisputePriorityEnum), nullable=False, default=DisputePriorityEnum.MEDIUM, index=True)

    admin_notes = Column(Text, nullable=True)
    resolution = Column(Text, nullable=True)
    action_taken = Column(String(100), nullable=True)

    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    resolved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    reporter = relationship("User", foreign_keys=[reporter_id])
    reported_user = relationship("User", foreign_keys=[reported_user_id])
    resolver = relationship("User", foreign_keys=[resolved_by])
    attachments = relationship("DisputeAttachment", back_populates="dispute", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_dispute_status", "status"),
        Index("idx_dispute_category", "category"),
        Index("idx_dispute_priority", "priority"),
        Index("idx_dispute_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<Dispute(id={self.id}, status={self.status}, category={self.category})>"


class DisputeAttachment(Base):
    """
    Attachment metadata for disputes.
    """
    __tablename__ = "dispute_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    dispute_id = Column(UUID(as_uuid=True), ForeignKey("disputes.id", ondelete="CASCADE"), nullable=False, index=True)

    file_name = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    content_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)
    meta_data = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    dispute = relationship("Dispute", back_populates="attachments")

    __table_args__ = (
        Index("idx_dispute_attachment_dispute", "dispute_id"),
    )

    def __repr__(self):
        return f"<DisputeAttachment(id={self.id}, dispute_id={self.dispute_id})>"
