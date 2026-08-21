"""
Notifications Module - Pydantic Schemas

Request/response validation schemas for notification management API.

Author: Smart Carpooling Backend Team
"""

from pydantic import BaseModel, Field, ConfigDict, field_validator, AliasChoices
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

from app.modules.notifications.models import (
    NotificationTypeEnum,
    NotificationPriorityEnum,
    DeliveryStatusEnum,
    DevicePlatformEnum
)


class NotificationCreate(BaseModel):
    """Schema for creating a new notification."""
    user_id: UUID = Field(..., description="Receiver user UUID")
    title: str = Field(..., min_length=1, max_length=150, description="Notification title")
    message: str = Field(..., min_length=1, max_length=1000, description="Notification message body")
    type: NotificationTypeEnum = Field(default=NotificationTypeEnum.CUSTOM, description="Notification category")
    priority: NotificationPriorityEnum = Field(default=NotificationPriorityEnum.NORMAL, description="Priority level")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional additional context")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "title": "Ride Confirmed",
                "message": "Your ride has been confirmed! Driver will arrive in 5 minutes.",
                "type": "ride",
                "priority": "high",
                "metadata": {"ride_id": "987e6543-e89b-12d3-a456-426614174999"}
            }
        }
    )


class NotificationResponse(BaseModel):
    """Schema for notification response."""
    id: UUID
    user_id: UUID
    title: str
    message: str
    type: NotificationTypeEnum
    priority: NotificationPriorityEnum
    delivery_status: DeliveryStatusEnum
    sent_at: Optional[datetime]
    read_at: Optional[datetime]
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        validation_alias=AliasChoices("metadata", "meta_data"),
        serialization_alias="metadata",
    )
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    """Schema for paginated notification list."""
    notifications: List[NotificationResponse]
    total: int
    unread_count: int
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "notifications": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "user_id": "987e6543-e89b-12d3-a456-426614174999",
                        "title": "Payment Received",
                        "message": "Your payment of PKR 500 has been processed.",
                        "type": "payment",
                        "priority": "normal",
                        "delivery_status": "sent",
                        "sent_at": "2025-11-08T10:30:00",
                        "read_at": None,
                        "metadata": {"transaction_id": "TXN_123"},
                        "created_at": "2025-11-08T10:30:00",
                        "updated_at": "2025-11-08T10:30:00"
                    }
                ],
                "total": 25,
                "unread_count": 8
            }
        }
    )


class TokenRegisterRequest(BaseModel):
    """Schema for registering FCM device token."""
    device_token: str = Field(..., min_length=50, max_length=255, description="Firebase Cloud Messaging token")
    platform: DevicePlatformEnum = Field(..., description="Device platform (android/ios/web)")
    
    @field_validator('device_token')
    @classmethod
    def validate_token(cls, v: str) -> str:
        """Validate FCM token format."""
        if len(v.strip()) < 50:
            raise ValueError("Device token appears invalid (too short)")
        return v.strip()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "device_token": "fKc8X9ZqRxG:APA91bHU...long_fcm_token_here...",
                "platform": "android"
            }
        }
    )


class TokenResponse(BaseModel):
    """Schema for device token response."""
    id: UUID
    user_id: UUID
    device_token: str
    platform: DevicePlatformEnum
    is_active: bool
    created_at: datetime
    last_used_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class BroadcastRequest(BaseModel):
    """Schema for system-wide broadcast message (admin only)."""
    title: str = Field(..., min_length=1, max_length=150, description="Broadcast title")
    message: str = Field(..., min_length=1, max_length=1000, description="Broadcast message")
    priority: NotificationPriorityEnum = Field(default=NotificationPriorityEnum.NORMAL, description="Priority level")
    target_roles: Optional[List[str]] = Field(default=None, description="Optional: target specific roles (rider, driver)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "System Maintenance",
                "message": "The system will undergo maintenance on Nov 10, 2025 from 2 AM to 4 AM.",
                "priority": "high",
                "target_roles": ["rider", "driver"]
            }
        }
    )


class BroadcastResponse(BaseModel):
    """Schema for broadcast response."""
    success: bool
    total_recipients: int
    notifications_created: int
    message: str
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "total_recipients": 1500,
                "notifications_created": 1500,
                "message": "Broadcast queued for delivery"
            }
        }
    )


class MarkReadRequest(BaseModel):
    """Schema for marking notification as read."""
    notification_id: UUID = Field(..., description="Notification UUID to mark as read")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "notification_id": "123e4567-e89b-12d3-a456-426614174000"
            }
        }
    )


class DeliveryStatusUpdate(BaseModel):
    """Schema for updating notification delivery status (internal use)."""
    notification_id: UUID
    status: DeliveryStatusEnum
    error_message: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


# ============= WebSocket & Real-Time Schemas (Prompt 9) =============

class WebSocketMessage(BaseModel):
    """Schema for WebSocket message envelope."""
    type: str = Field(..., description="Message type (notification, ping, pong, connection, etc.)")
    user_id: Optional[str] = Field(None, description="User ID (for user-specific messages)")
    title: Optional[str] = Field(None, description="Notification title")
    body: Optional[str] = Field(None, description="Notification body")
    data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional data payload")
    timestamp: str = Field(..., description="ISO8601 timestamp")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "notification",
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "title": "New Ride Request",
                "body": "You have a new ride request from Sarah",
                "data": {"ride_id": "987e6543"},
                "timestamp": "2025-12-08T10:30:00Z"
            }
        }
    )


class SendDirectRequest(BaseModel):
    """Schema for sending direct notification to specific user (admin only)."""
    title: str = Field(..., min_length=1, max_length=150, description="Notification title")
    body: str = Field(..., min_length=1, max_length=1000, description="Notification body/message")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Optional additional data")
    priority: str = Field(default="normal", description="Priority: low, normal, high, critical")
    channels: Optional[List[str]] = Field(
        default=None,
        description="Channels to try (websocket, fcm, sms, email). Defaults based on priority."
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Important Update",
                "body": "Your verification has been approved!",
                "data": {"verification_id": "VER_123"},
                "priority": "high",
                "channels": ["websocket", "fcm"]
            }
        }
    )


class AdapterHealthStatus(BaseModel):
    """Schema for individual adapter health status."""
    adapter: str
    status: str  # ok, degraded, error, not_initialized
    mode: Optional[str] = None  # placeholder, production
    total_sent: int = 0
    total_failed: int = 0
    success_rate: float = 0.0
    timestamp: str
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "adapter": "fcm",
                "status": "ok",
                "mode": "placeholder",
                "total_sent": 1250,
                "total_failed": 15,
                "success_rate": 0.988,
                "timestamp": "2025-12-08T10:30:00Z"
            }
        }
    )


class HealthCheckResponse(BaseModel):
    """Schema for notifications system health check (admin only)."""
    overall_status: str = Field(..., description="Overall health status: ok, degraded, error")
    fcm: AdapterHealthStatus
    sms: AdapterHealthStatus
    email: AdapterHealthStatus
    redis_pubsub: Dict[str, Any] = Field(default_factory=dict, alias="pubsub", description="Pub/Sub statistics")
    websocket_manager: Dict[str, Any]
    notification_service: Dict[str, Any]
    timestamp: str
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "overall_status": "ok",
                "fcm": {
                    "adapter": "fcm",
                    "status": "ok",
                    "mode": "placeholder",
                    "total_sent": 1250,
                    "total_failed": 15,
                    "success_rate": 0.988,
                    "timestamp": "2025-12-08T10:30:00Z"
                },
                "sms": {
                    "adapter": "sms",
                    "status": "ok",
                    "mode": "placeholder",
                    "total_sent": 50,
                    "total_failed": 2,
                    "success_rate": 0.96,
                    "timestamp": "2025-12-08T10:30:00Z"
                },
                "email": {
                    "adapter": "email",
                    "status": "ok",
                    "mode": "placeholder",
                    "total_sent": 300,
                    "total_failed": 5,
                    "success_rate": 0.983,
                    "timestamp": "2025-12-08T10:30:00Z"
                },
                "pubsub": {
                    "running": True,
                    "messages_received": 5000,
                    "messages_delivered": 4950,
                    "reconnect_count": 0
                },
                "websocket_manager": {
                    "active_connections": 45,
                    "total_messages_sent": 12000
                },
                "notification_service": {
                    "total_sent": 15000,
                    "total_failed": 50,
                    "success_rate": 0.997
                },
                "timestamp": "2025-12-08T10:30:00Z"
            }
        }
    )


class DLQItemResponse(BaseModel):
    """Schema for dead-letter queue item."""
    user_id: str
    payload: Dict[str, Any]
    reason: str
    attempts: int
    timestamp: str
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "123e4567",
                "payload": {
                    "title": "Ride Update",
                    "body": "Your ride status has changed",
                    "type": "notification"
                },
                "reason": "max_retries_exceeded",
                "attempts": 5,
                "timestamp": "2025-12-08T10:15:00Z"
            }
        }
    )


class DLQListResponse(BaseModel):
    """Schema for dead-letter queue list response."""
    items: List[DLQItemResponse]
    total: int
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [],
                "total": 0
            }
        }
    )
