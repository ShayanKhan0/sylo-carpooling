"""
Background Tasks for Notifications

Async task processing for notification delivery, retries, and bulk operations.
Uses FastAPI BackgroundTasks for lightweight async processing.

Author: Smart Carpooling Backend Team
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy import text

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications import crud
from app.modules.notifications.models import DeliveryStatusEnum, NotificationPriorityEnum
from app.modules.notifications.fcm_client import send_fcm_message, send_fcm_batch
from app.db.session import get_db

logger = logging.getLogger(__name__)


async def _is_push_delivery_allowed(
    db: AsyncSession,
    user_id: UUID,
    notification_type,
    priority,
) -> bool:
    """Return True when push delivery is allowed for this user/notification."""
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
        push_enabled = True

    if push_enabled:
        return True

    return (
        str(getattr(notification_type, "value", notification_type)) == "safety"
        and str(getattr(priority, "value", priority)) == "high"
    )


async def send_notification_task(
    notification_id: UUID,
    retry_count: int = 0,
    max_retries: int = 3
):
    """
    Background task to send notification with retry logic.
    
    Args:
        notification_id: Notification UUID
        retry_count: Current retry attempt
        max_retries: Maximum retry attempts
    """
    async for db in get_db():
        try:
            # Get notification
            notification = await crud.get_notification(db, notification_id)
            
            if not notification:
                logger.error(f"[TASK] Notification {notification_id} not found")
                return

            push_allowed = await _is_push_delivery_allowed(
                db=db,
                user_id=notification.user_id,
                notification_type=notification.type,
                priority=notification.priority,
            )

            if not push_allowed:
                await crud.update_delivery_status(
                    db,
                    notification_id,
                    DeliveryStatusEnum.SENT,
                    sent_at=datetime.utcnow(),
                )
                logger.info(
                    "[TASK] Push suppressed by preference for notification %s user=%s",
                    notification_id,
                    notification.user_id,
                )
                return
            
            # Get active device tokens for user
            tokens = await crud.get_active_tokens(db, notification.user_id)
            
            if not tokens:
                logger.warning(f"[TASK] No active tokens for user {notification.user_id}. Storing in-app only.")
                await crud.update_delivery_status(db, notification_id, DeliveryStatusEnum.SENT)
                return
            
            # Determine priority
            priority = "high" if notification.priority == NotificationPriorityEnum.HIGH else "normal"
            
            # Prepare data payload
            data = {
                "notification_id": str(notification.id),
                "type": notification.type.value,
                "priority": notification.priority.value
            }
            
            # Add metadata if present
            payload_metadata = getattr(notification, "meta_data", None) or {}
            if payload_metadata:
                for key, value in payload_metadata.items():
                    data[f"meta_{key}"] = str(value)
            
            # Send to all tokens
            success = False
            invalid_tokens = []
            
            for token_record in tokens:
                result = await send_fcm_message(
                    token=token_record.device_token,
                    title=notification.title,
                    body=notification.message,
                    data=data,
                    priority=priority
                )
                
                if result.get("success"):
                    success = True
                    logger.info(f"[TASK] ✅ Notification {notification_id} sent to device {token_record.platform.value}")
                else:
                    error = result.get("error", "unknown")
                    logger.warning(f"[TASK] ❌ Failed to send to token: {error}")
                    
                    # Mark token as invalid if unregistered
                    if error == "unregistered_token":
                        invalid_tokens.append(token_record.device_token)
            
            # Deactivate invalid tokens
            for invalid_token in invalid_tokens:
                await crud.deactivate_token(db, invalid_token)
            
            # Update delivery status
            if success:
                await crud.update_delivery_status(
                    db,
                    notification_id,
                    DeliveryStatusEnum.SENT,
                    sent_at=datetime.utcnow()
                )
                logger.info(f"[TASK] ✅ Notification {notification_id} delivered successfully")
            else:
                # Retry logic
                if retry_count < max_retries:
                    logger.warning(f"[TASK] ⚠️ Retry #{retry_count + 1} for notification {notification_id}")
                    
                    # Exponential backoff
                    delay = 2 ** retry_count  # 1s, 2s, 4s
                    await asyncio.sleep(delay)
                    
                    # Retry
                    await send_notification_task(notification_id, retry_count + 1, max_retries)
                else:
                    await crud.update_delivery_status(db, notification_id, DeliveryStatusEnum.FAILED)
                    logger.error(f"[TASK] ❌ Notification {notification_id} failed after {max_retries} retries")
        
        except Exception as e:
            logger.exception(f"[TASK] Exception in send_notification_task: {e}")
            
            # Update to failed status
            try:
                async for db in get_db():
                    await crud.update_delivery_status(db, notification_id, DeliveryStatusEnum.FAILED)
            except:
                pass
        
        finally:
            break  # Exit after first iteration


async def send_bulk_notifications_task(
    user_ids: List[UUID],
    title: str,
    message: str,
    notification_type: str = "system",
    priority: str = "normal",
    metadata: Optional[Dict[str, Any]] = None
):
    """
    Background task to send notifications to multiple users.
    
    Args:
        user_ids: List of user UUIDs
        title: Notification title
        message: Notification message
        notification_type: Notification type
        priority: Priority level
        metadata: Optional metadata
    """
    async for db in get_db():
        try:
            logger.info(f"[BULK TASK] Starting bulk send to {len(user_ids)} users")
            
            created_count = 0
            sent_count = 0
            
            # Process in batches of 100
            batch_size = 100
            
            for i in range(0, len(user_ids), batch_size):
                batch = user_ids[i:i + batch_size]
                
                # Create notifications for batch
                notifications = []
                for user_id in batch:
                    try:
                        notification = await crud.create_notification(
                            db=db,
                            user_id=user_id,
                            title=title,
                            message=message,
                            notification_type=notification_type,
                            priority=priority,
                            metadata=metadata
                        )
                        notifications.append(notification)
                        created_count += 1
                    except Exception as e:
                        logger.error(f"[BULK TASK] Failed to create notification for user {user_id}: {e}")
                
                # Collect all tokens for batch
                all_tokens = []
                notification_map = {}  # token -> notification_id
                
                for notification in notifications:
                    push_allowed = await _is_push_delivery_allowed(
                        db=db,
                        user_id=notification.user_id,
                        notification_type=notification.type,
                        priority=notification.priority,
                    )

                    if not push_allowed:
                        await crud.update_delivery_status(
                            db,
                            notification.id,
                            DeliveryStatusEnum.SENT,
                            sent_at=datetime.utcnow(),
                        )
                        continue

                    tokens = await crud.get_active_tokens(db, notification.user_id)
                    for token in tokens:
                        all_tokens.append(token.device_token)
                        notification_map[token.device_token] = notification.id
                
                # Send batch FCM
                if all_tokens:
                    data = {
                        "type": notification_type,
                        "priority": priority
                    }
                    
                    result = await send_fcm_batch(
                        tokens=all_tokens,
                        title=title,
                        body=message,
                        data=data,
                        priority=priority
                    )
                    
                    sent_count += result.get("success_count", 0)
                    
                    # Update delivery statuses
                    for notification in notifications:
                        # Keep already-marked statuses unchanged for suppressed users.
                        refreshed = await crud.get_notification(db, notification.id)
                        if refreshed and refreshed.delivery_status != DeliveryStatusEnum.SENT:
                            await crud.update_delivery_status(
                                db,
                                notification.id,
                                DeliveryStatusEnum.SENT,
                                sent_at=datetime.utcnow()
                            )
                
                logger.info(f"[BULK TASK] Batch {i // batch_size + 1} completed: {len(batch)} notifications")
            
            logger.info(f"[BULK TASK] ✅ Bulk send completed: {created_count} created, {sent_count} sent")
        
        except Exception as e:
            logger.exception(f"[BULK TASK] Exception in bulk send: {e}")
        
        finally:
            break


async def cleanup_old_notifications_task(days: int = 90):
    """
    Background task to cleanup old notifications.
    
    Args:
        days: Number of days to retain notifications
    """
    async for db in get_db():
        try:
            logger.info(f"[CLEANUP TASK] Starting cleanup of notifications older than {days} days")
            
            deleted_count = await crud.delete_old_notifications(db, days)
            
            logger.info(f"[CLEANUP TASK] ✅ Cleanup completed: {deleted_count} notifications deleted")
        
        except Exception as e:
            logger.exception(f"[CLEANUP TASK] Exception in cleanup: {e}")
        
        finally:
            break


async def retry_failed_notifications_task():
    """
    Background task to retry failed notifications.
    
    Finds all notifications with FAILED status from the last 24 hours
    and attempts to resend them.
    """
    async for db in get_db():
        try:
            from datetime import timedelta
            from sqlalchemy import select, and_
            from app.modules.notifications.models import Notification
            
            logger.info("[RETRY TASK] Starting retry of failed notifications")
            
            # Get failed notifications from last 24 hours
            cutoff = datetime.utcnow() - timedelta(hours=24)
            
            result = await db.execute(
                select(Notification).where(
                    and_(
                        Notification.delivery_status == DeliveryStatusEnum.FAILED,
                        Notification.created_at >= cutoff
                    )
                )
            )
            
            failed_notifications = result.scalars().all()
            
            logger.info(f"[RETRY TASK] Found {len(failed_notifications)} failed notifications to retry")
            
            for notification in failed_notifications:
                # Reset to pending and retry
                await crud.update_delivery_status(db, notification.id, DeliveryStatusEnum.PENDING)
                await send_notification_task(notification.id, retry_count=0, max_retries=2)
            
            logger.info(f"[RETRY TASK] ✅ Retry task completed")
        
        except Exception as e:
            logger.exception(f"[RETRY TASK] Exception in retry task: {e}")
        
        finally:
            break
