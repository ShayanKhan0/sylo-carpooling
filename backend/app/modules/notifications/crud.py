"""
Notifications Module - CRUD Operations

Async database operations for notification management, device token registration,
and delivery status tracking.

Author: Smart Carpooling Backend Team
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.modules.notifications.models import (
    Notification,
    NotificationToken,
    NotificationTypeEnum,
    NotificationPriorityEnum,
    DeliveryStatusEnum,
    DevicePlatformEnum
)
from app.modules.auth.models import User

import logging

logger = logging.getLogger(__name__)

_ACTIVE_TOKEN_VALUES = ("true", "1", "yes", "y", "t", "active")


def _active_token_filter():
    """String-safe active-token predicate for backward-compatible rows."""
    normalized = func.lower(func.trim(func.coalesce(NotificationToken.is_active, "")))
    return normalized.in_(_ACTIVE_TOKEN_VALUES)


async def create_notification(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    message: str,
    notification_type: NotificationTypeEnum = NotificationTypeEnum.CUSTOM,
    priority: NotificationPriorityEnum = NotificationPriorityEnum.NORMAL,
    metadata: Optional[Dict[str, Any]] = None
) -> Notification:
    """
    Create a new notification record.
    
    Args:
        db: Database session
        user_id: Receiver user UUID
        title: Notification title
        message: Notification message body
        notification_type: Notification category
        priority: Priority level
        metadata: Optional additional context
    
    Returns:
        Created Notification record
    """
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=notification_type,
        priority=priority,
        meta_data=metadata or {},
        delivery_status=DeliveryStatusEnum.PENDING
    )
    
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    
    logger.info(f"Notification created: {notification.id} for user {user_id} type={notification_type.value}")
    return notification


async def get_notification(
    db: AsyncSession,
    notification_id: UUID
) -> Optional[Notification]:
    """
    Get a single notification by ID.
    
    Args:
        db: Database session
        notification_id: Notification UUID
    
    Returns:
        Notification record or None
    """
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    return result.scalar_one_or_none()


async def get_user_notifications(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 50,
    skip: int = 0,
    unread_only: bool = False
) -> tuple[List[Notification], int]:
    """
    Get paginated notifications for a user.
    
    Args:
        db: Database session
        user_id: User UUID
        limit: Maximum number of records
        skip: Offset for pagination
        unread_only: If True, only return unread notifications
    
    Returns:
        Tuple of (notifications list, total count)
    """
    query = select(Notification).where(Notification.user_id == user_id)
    
    if unread_only:
        query = query.where(Notification.read_at == None)
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get paginated results
    query = query.order_by(desc(Notification.created_at)).offset(skip).limit(limit)
    result = await db.execute(query)
    notifications = result.scalars().all()
    
    return notifications, total


async def get_unread_count(
    db: AsyncSession,
    user_id: UUID
) -> int:
    """
    Get count of unread notifications for a user.
    
    Args:
        db: Database session
        user_id: User UUID
    
    Returns:
        Count of unread notifications
    """
    result = await db.execute(
        select(func.count()).where(
            and_(
                Notification.user_id == user_id,
                Notification.read_at == None
            )
        )
    )
    return result.scalar() or 0


async def mark_as_read(
    db: AsyncSession,
    notification_id: UUID,
    user_id: Optional[UUID] = None
) -> Notification:
    """
    Mark a notification as read.
    
    Args:
        db: Database session
        notification_id: Notification UUID
        user_id: Optional user UUID for verification
    
    Returns:
        Updated Notification record
    
    Raises:
        HTTPException: If notification not found or unauthorized
    """
    query = select(Notification).where(Notification.id == notification_id)
    
    if user_id:
        query = query.where(Notification.user_id == user_id)
    
    result = await db.execute(query)
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
    
    if notification.read_at is None:
        notification.read_at = datetime.utcnow()
        await db.commit()
        await db.refresh(notification)
        
        logger.info(f"Notification {notification_id} marked as read")
    
    return notification


async def mark_all_as_read(
    db: AsyncSession,
    user_id: UUID
) -> int:
    """
    Mark all unread notifications as read for a user.
    
    Args:
        db: Database session
        user_id: User UUID
    
    Returns:
        Number of notifications updated
    """
    result = await db.execute(
        select(Notification).where(
            and_(
                Notification.user_id == user_id,
                Notification.read_at == None
            )
        )
    )
    
    notifications = result.scalars().all()
    count = len(notifications)
    
    for notification in notifications:
        notification.read_at = datetime.utcnow()
    
    await db.commit()
    
    logger.info(f"Marked {count} notifications as read for user {user_id}")
    return count


async def update_delivery_status(
    db: AsyncSession,
    notification_id: UUID,
    delivery_status: DeliveryStatusEnum,
    sent_at: Optional[datetime] = None
) -> Notification:
    """
    Update notification delivery status.
    
    Args:
        db: Database session
        notification_id: Notification UUID
        delivery_status: New delivery status
        sent_at: Optional sent timestamp
    
    Returns:
        Updated Notification record
    
    Raises:
        HTTPException: If notification not found
    """
    result = await db.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    
    notification = result.scalar_one_or_none()
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification {notification_id} not found"
        )
    
    notification.delivery_status = delivery_status
    
    if sent_at:
        notification.sent_at = sent_at
    elif delivery_status == DeliveryStatusEnum.SENT and notification.sent_at is None:
        notification.sent_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(notification)
    
    logger.info(f"Notification {notification_id} status updated to {delivery_status.value}")
    return notification


async def register_device_token(
    db: AsyncSession,
    user_id: UUID,
    device_token: str,
    platform: DevicePlatformEnum
) -> NotificationToken:
    """
    Register or update FCM device token.
    
    Args:
        db: Database session
        user_id: User UUID
        device_token: Firebase Cloud Messaging token
        platform: Device platform (android/ios/web)
    
    Returns:
        NotificationToken record
    """
    # Check if token already exists
    result = await db.execute(
        select(NotificationToken).where(NotificationToken.device_token == device_token)
    )
    
    existing_token = result.scalar_one_or_none()
    
    if existing_token:
        # Update existing token
        existing_token.user_id = user_id
        existing_token.platform = platform
        existing_token.is_active = "true"
        existing_token.last_used_at = datetime.utcnow()
        await db.commit()
        await db.refresh(existing_token)
        
        logger.info(f"Updated existing device token for user {user_id}")
        return existing_token
    
    # Create new token
    token = NotificationToken(
        user_id=user_id,
        device_token=device_token,
        platform=platform,
        is_active="true",
    )
    
    db.add(token)
    await db.commit()
    await db.refresh(token)
    
    logger.info(f"Registered new device token for user {user_id} platform={platform.value}")
    return token


async def get_active_tokens(
    db: AsyncSession,
    user_id: UUID
) -> List[NotificationToken]:
    """
    Get all active device tokens for a user.
    
    Args:
        db: Database session
        user_id: User UUID
    
    Returns:
        List of active NotificationToken records
    """
    result = await db.execute(
        select(NotificationToken).where(
            and_(
                NotificationToken.user_id == user_id,
                _active_token_filter(),
            )
        )
    )
    
    return result.scalars().all()


async def deactivate_token(
    db: AsyncSession,
    device_token: str
) -> bool:
    """
    Deactivate a device token (e.g., when FCM returns invalid token error).
    
    Args:
        db: Database session
        device_token: FCM device token to deactivate
    
    Returns:
        True if token was deactivated, False if not found
    """
    result = await db.execute(
        select(NotificationToken).where(NotificationToken.device_token == device_token)
    )
    
    token = result.scalar_one_or_none()
    
    if token:
        token.is_active = "false"
        await db.commit()
        logger.warning(f"Deactivated invalid device token: {device_token[:20]}...")
        return True
    
    return False


async def get_all_active_users(
    db: AsyncSession,
    target_roles: Optional[List[str]] = None
) -> List[UUID]:
    """
    Get all active user IDs for system broadcast.
    
    Args:
        db: Database session
        target_roles: Optional list of roles to filter (e.g., ['rider', 'driver'])
    
    Returns:
        List of user UUIDs
    """
    query = select(User.id).where(User.is_active == True)
    
    if target_roles:
        from app.modules.auth.models import UserRole
        role_enums = [UserRole(role) for role in target_roles if role in UserRole.__members__.values()]
        if role_enums:
            query = query.where(User.role.in_(role_enums))
    
    result = await db.execute(query)
    return [row[0] for row in result.all()]


async def delete_old_notifications(
    db: AsyncSession,
    days: int = 90
) -> int:
    """
    Delete notifications older than specified days (cleanup task).
    
    Args:
        db: Database session
        days: Number of days to retain notifications
    
    Returns:
        Number of notifications deleted
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    result = await db.execute(
        select(Notification).where(Notification.created_at < cutoff_date)
    )
    
    notifications = result.scalars().all()
    count = len(notifications)
    
    for notification in notifications:
        await db.delete(notification)
    
    await db.commit()
    
    logger.info(f"Deleted {count} old notifications (older than {days} days)")
    return count

