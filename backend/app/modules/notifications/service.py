"""
Notifications Module - Service Layer

Business logic for notification management, including push notification delivery,
in-app alerts, system broadcasts, and delivery tracking.

Author: Smart Carpooling Backend Team
"""

import asyncio
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from uuid import UUID
from fastapi import HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.modules.notifications import crud
from app.modules.notifications.schemas import (
    NotificationCreate,
    NotificationResponse,
    NotificationListResponse,
    TokenRegisterRequest,
    TokenResponse,
    BroadcastRequest,
    BroadcastResponse
)
from app.modules.notifications.models import (
    NotificationTypeEnum,
    NotificationPriorityEnum,
    DeliveryStatusEnum,
    DevicePlatformEnum
)
from app.modules.notifications.tasks import (
    send_notification_task,
    send_bulk_notifications_task
)

logger = logging.getLogger(__name__)

# Environment configuration
NOTIFICATION_RETRY_COUNT = int(os.getenv("NOTIFICATION_RETRY_COUNT", "3"))
NOTIFICATION_DEFAULT_PRIORITY = os.getenv("NOTIFICATION_DEFAULT_PRIORITY", "normal")


def _notification_to_response(notification: Any) -> NotificationResponse:
    """Serialize Notification ORM object safely for API responses."""
    def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    return NotificationResponse.model_validate(
        {
            "id": notification.id,
            "user_id": notification.user_id,
            "title": notification.title,
            "message": notification.message,
            "type": notification.type,
            "priority": notification.priority,
            "delivery_status": notification.delivery_status,
            "sent_at": _as_utc(notification.sent_at),
            "read_at": _as_utc(notification.read_at),
            "metadata": notification.meta_data,
            "created_at": _as_utc(notification.created_at),
            "updated_at": _as_utc(notification.updated_at),
        }
    )


async def _is_push_delivery_allowed(
    db: AsyncSession,
    user_id: UUID,
    notification_type: NotificationTypeEnum,
    priority: NotificationPriorityEnum,
) -> bool:
    """
    Respect user push preference, but always allow critical safety alerts.

    Critical safety alert policy:
    - type = safety
    - priority = high
    """
    try:
        result = await db.execute(
            text(
                """
                SELECT COALESCE(push_notifications_enabled, TRUE) AS push_enabled
                FROM user_profiles
                WHERE user_id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
        row = result.first()
        push_enabled = bool(row[0]) if row else True
    except Exception:
        # Fail open so notification pipeline remains available on legacy schemas.
        push_enabled = True

    if push_enabled:
        return True

    return (
        notification_type == NotificationTypeEnum.SAFETY
        and priority == NotificationPriorityEnum.HIGH
    )


async def send_push_notification(
    db: AsyncSession,
    background_tasks: Optional[BackgroundTasks],
    notification_data: NotificationCreate
) -> Dict[str, Any]:
    """
    Send push notification to a user.
    
    Creates notification record and queues for async FCM delivery.
    
    Args:
        db: Database session
        background_tasks: FastAPI background tasks (optional)
        notification_data: Notification data
    
    Returns:
        Response with notification details
    """
    try:
        # Create notification in database
        notification = await crud.create_notification(
            db=db,
            user_id=notification_data.user_id,
            title=notification_data.title,
            message=notification_data.message,
            notification_type=notification_data.type,
            priority=notification_data.priority,
            metadata=notification_data.metadata
        )

        push_allowed = await _is_push_delivery_allowed(
            db=db,
            user_id=notification_data.user_id,
            notification_type=notification_data.type,
            priority=notification_data.priority,
        )

        if not push_allowed:
            # Keep in-app notification feed active, but suppress push delivery.
            await crud.update_delivery_status(
                db,
                notification.id,
                DeliveryStatusEnum.SENT,
            )

            logger.info(
                "[NOTIFY] Push suppressed by user preference for notification %s user=%s",
                notification.id,
                notification_data.user_id,
            )

            return {
                "status": "ok",
                "data": {
                    "notification_id": notification.id,
                    "user_id": notification.user_id,
                    "title": notification.title,
                    "message": notification.message,
                    "type": notification.type.value,
                    "priority": notification.priority.value,
                    "delivery_status": DeliveryStatusEnum.SENT.value,
                    "queued_for_delivery": False,
                    "push_suppressed": True,
                },
                "error": None,
            }
        
        # Queue for async sending. If called outside a request context,
        # schedule directly on the running event loop.
        if background_tasks is not None:
            background_tasks.add_task(
                send_notification_task,
                notification.id,
                retry_count=0,
                max_retries=NOTIFICATION_RETRY_COUNT
            )
        else:
            asyncio.create_task(
                send_notification_task(
                    notification.id,
                    retry_count=0,
                    max_retries=NOTIFICATION_RETRY_COUNT,
                )
            )
        
        logger.info(f"[NOTIFY] Queued notification {notification.id} for user {notification_data.user_id}")
        
        return {
            "status": "ok",
            "data": {
                "notification_id": notification.id,
                "user_id": notification.user_id,
                "title": notification.title,
                "message": notification.message,
                "type": notification.type.value,
                "priority": notification.priority.value,
                "delivery_status": notification.delivery_status.value,
                "queued_for_delivery": True
            },
            "error": None
        }
    
    except Exception as e:
        logger.exception(f"[NOTIFY] Failed to send notification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send notification"
        )


async def send_in_app_alert(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    message: str,
    notification_type: NotificationTypeEnum = NotificationTypeEnum.CUSTOM,
    priority: NotificationPriorityEnum = NotificationPriorityEnum.NORMAL,
    metadata: Optional[Dict[str, Any]] = None
) -> NotificationResponse:
    """
    Create in-app alert (stored in DB, appears in dashboard feed).
    
    Does NOT send push notification - only stores for in-app display.
    
    Args:
        db: Database session
        user_id: User UUID
        title: Alert title
        message: Alert message
        notification_type: Notification type
        priority: Priority level
        metadata: Optional metadata
    
    Returns:
        NotificationResponse
    """
    notification = await crud.create_notification(
        db=db,
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        priority=priority,
        metadata=metadata
    )
    
    # Mark as "sent" immediately (in-app only, no FCM)
    await crud.update_delivery_status(db, notification.id, DeliveryStatusEnum.SENT)
    
    logger.info(f"[NOTIFY] In-app alert created: {notification.id} for user {user_id}")
    
    return _notification_to_response(notification)


async def broadcast_system_message(
    db: AsyncSession,
    background_tasks: BackgroundTasks,
    broadcast_data: BroadcastRequest
) -> BroadcastResponse:
    """
    Send system-wide broadcast message to all active users.
    
    Admin-only feature for maintenance announcements, promotions, etc.
    
    Args:
        db: Database session
        background_tasks: FastAPI background tasks
        broadcast_data: Broadcast message data
    
    Returns:
        BroadcastResponse with recipient count
    """
    try:
        # Get all active users (optionally filtered by role)
        user_ids = await crud.get_all_active_users(db, broadcast_data.target_roles)
        
        if not user_ids:
            return BroadcastResponse(
                success=True,
                total_recipients=0,
                notifications_created=0,
                message="No active users found"
            )
        
        # Queue bulk notification task
        background_tasks.add_task(
            send_bulk_notifications_task,
            user_ids=user_ids,
            title=broadcast_data.title,
            message=broadcast_data.message,
            notification_type="system",
            priority=broadcast_data.priority.value,
            metadata={"broadcast": True}
        )
        
        logger.info(f"[NOTIFY] Broadcast queued for {len(user_ids)} users: {broadcast_data.title}")
        
        return BroadcastResponse(
            success=True,
            total_recipients=len(user_ids),
            notifications_created=len(user_ids),
            message=f"Broadcast queued for delivery to {len(user_ids)} users"
        )
    
    except Exception as e:
        logger.exception(f"[NOTIFY] Broadcast failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Broadcast failed"
        )


async def mark_read(
    db: AsyncSession,
    notification_id: UUID,
    user_id: UUID
) -> Dict[str, Any]:
    """
    Mark notification as read.
    
    Args:
        db: Database session
        notification_id: Notification UUID
        user_id: User UUID (for verification)
    
    Returns:
        Response with updated notification
    
    Raises:
        HTTPException: If notification not found or unauthorized
    """
    try:
        notification = await crud.mark_as_read(db, notification_id, user_id)
        
        logger.info(f"[NOTIFY] Notification {notification_id} marked as read by user {user_id}")
        
        return {
            "status": "ok",
            "data": _notification_to_response(notification),
            "error": None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[NOTIFY] Failed to mark as read: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark notification as read"
        )


async def get_user_notifications_service(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 50,
    skip: int = 0,
    unread_only: bool = False
) -> NotificationListResponse:
    """
    Get user's notifications with pagination.
    
    Args:
        db: Database session
        user_id: User UUID
        limit: Maximum records to return
        skip: Offset for pagination
        unread_only: Filter for unread only
    
    Returns:
        NotificationListResponse with pagination info
    """
    notifications, total = await crud.get_user_notifications(
        db, user_id, limit, skip, unread_only
    )
    
    unread_count = await crud.get_unread_count(db, user_id)
    
    notification_responses = [_notification_to_response(n) for n in notifications]
    
    return NotificationListResponse(
        notifications=notification_responses,
        total=total,
        unread_count=unread_count
    )


async def register_device_token_service(
    db: AsyncSession,
    user_id: UUID,
    token_data: TokenRegisterRequest
) -> TokenResponse:
    """
    Register FCM device token for push notifications.
    
    Args:
        db: Database session
        user_id: User UUID
        token_data: Token registration data
    
    Returns:
        TokenResponse
    """
    try:
        token = await crud.register_device_token(
            db=db,
            user_id=user_id,
            device_token=token_data.device_token,
            platform=token_data.platform
        )
        
        logger.info(f"[NOTIFY] Device token registered for user {user_id} platform={token_data.platform.value}")
        
        return TokenResponse.model_validate(token)
    
    except Exception as e:
        logger.exception(f"[NOTIFY] Token registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register device token"
        )


async def log_delivery_status(
    notification_id: UUID,
    status: DeliveryStatusEnum,
    error_message: Optional[str] = None
):
    """
    Log notification delivery status.
    
    Args:
        notification_id: Notification UUID
        status: Delivery status
        error_message: Optional error message
    """
    if status == DeliveryStatusEnum.SENT:
        logger.info(f"[NOTIFY] ✅ Notification {notification_id} delivered successfully")
    elif status == DeliveryStatusEnum.FAILED:
        logger.error(f"[NOTIFY] ❌ Notification {notification_id} failed: {error_message or 'Unknown error'}")
    elif status == DeliveryStatusEnum.PENDING:
        logger.debug(f"[NOTIFY] ⏳ Notification {notification_id} pending delivery")
    elif status == DeliveryStatusEnum.READ:
        logger.info(f"[NOTIFY] 📖 Notification {notification_id} read by user")
