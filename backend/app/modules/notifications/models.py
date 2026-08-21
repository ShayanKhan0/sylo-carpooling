"""
Notifications Module - Database Models

Defines database models for notification management, including push notifications,
in-app alerts, and device token registration for Firebase Cloud Messaging (FCM).

Author: Smart Carpooling Backend Team
"""

from sqlalchemy import Column, String, Text, DateTime, Enum as SQLEnum, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum

from app.db.base import Base


class NotificationTypeEnum(str, enum.Enum):
    """Notification type categories."""
    SYSTEM = "system"
    RIDE = "ride"
    PAYMENT = "payment"
    SAFETY = "safety"
    VERIFICATION = "verification"
    CUSTOM = "custom"


class NotificationPriorityEnum(str, enum.Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class DeliveryStatusEnum(str, enum.Enum):
    """Notification delivery lifecycle statuses."""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    READ = "read"


class DevicePlatformEnum(str, enum.Enum):
    """Device platform types for FCM tokens."""
    ANDROID = "android"
    IOS = "ios"
    WEB = "web"


class Notification(Base):
    """
    Notification model for storing user notifications.
    
    Supports push notifications, in-app alerts, and system broadcasts.
    Tracks delivery status and read receipts for analytics.
    """
    __tablename__ = "notifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    title = Column(String(150), nullable=False)
    message = Column(Text, nullable=False)
    
    type = Column(SQLEnum(NotificationTypeEnum), nullable=False, default=NotificationTypeEnum.CUSTOM)
    priority = Column(SQLEnum(NotificationPriorityEnum), nullable=False, default=NotificationPriorityEnum.NORMAL)
    delivery_status = Column(SQLEnum(DeliveryStatusEnum), nullable=False, default=DeliveryStatusEnum.PENDING, index=True)
    
    sent_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    
    # Optional metadata for additional context (ride_id, payment_id, etc.)
    meta_data = Column(JSON, nullable=True, default=dict)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="notifications")
    
    # Composite index for common queries
    __table_args__ = (
        Index('ix_notifications_user_status', 'user_id', 'delivery_status'),
        Index('ix_notifications_user_created', 'user_id', 'created_at'),
    )
    
    def __repr__(self):
        return f"<Notification(id={self.id}, user_id={self.user_id}, type={self.type.value}, status={self.delivery_status.value})>"


class NotificationToken(Base):
    """
    Device token model for Firebase Cloud Messaging (FCM).
    
    Stores FCM device tokens for push notification delivery.
    Supports multiple devices per user (phone, tablet, web).
    """
    __tablename__ = "notification_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    device_token = Column(String(255), nullable=False, unique=True, index=True)
    platform = Column(SQLEnum(DevicePlatformEnum), nullable=False)
    
    # Kept as string for schema compatibility with existing database rows.
    is_active = Column(String, nullable=False, default="true")  # Deactivate if token becomes invalid
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="notification_tokens")
    
    def __repr__(self):
        return f"<NotificationToken(id={self.id}, user_id={self.user_id}, platform={self.platform.value})>"

