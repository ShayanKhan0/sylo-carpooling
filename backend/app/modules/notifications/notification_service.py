"""
Notification Service Orchestrator

Coordinates notification delivery across multiple channels with retry logic,
fallback strategies, and dead-letter queue management.

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import UUID

from app.modules.notifications.websocket_manager import WebSocketManager
from app.modules.notifications.publisher import NotificationPublisher
from app.modules.notifications.adapters.fcm_adapter import FCMAdapter
from app.modules.notifications.adapters.sms_adapter import SMSAdapter
from app.modules.notifications.adapters.email_adapter import EmailAdapter

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Orchestrates notification delivery across multiple channels.
    
    Delivery Strategy:
    1. Try WebSocket if user connected
    2. Fallback to FCM push notification
    3. Fallback to SMS (for critical notifications)
    4. Fallback to Email
    5. Queue in DLQ after max retries
    
    Features:
    - Multi-channel delivery
    - Exponential backoff retry (1s → 2s → 4s → 8s → 16s → max 30s)
    - Dead-letter queue for failed deliveries
    - Priority-based routing
    - Delivery tracking
    """
    
    def __init__(
        self,
        websocket_manager: WebSocketManager,
        publisher: NotificationPublisher,
        fcm_adapter: FCMAdapter,
        sms_adapter: Optional[SMSAdapter] = None,
        email_adapter: Optional[EmailAdapter] = None,
        retry_max: int = 5,
        retry_backoff: float = 2.0,
        **kwargs,
    ):
        """
        Initialize notification service.

        Args:
            websocket_manager: WebSocket manager instance
            publisher: Publisher instance
            fcm_adapter: FCM adapter instance
            sms_adapter: Optional SMS adapter
            email_adapter: Optional email adapter
            retry_max: Maximum retry attempts
            retry_backoff: Exponential backoff multiplier
        """
        self._websocket_manager = websocket_manager
        self._publisher = publisher
        self._fcm_adapter = fcm_adapter
        self._sms_adapter = sms_adapter
        self._email_adapter = email_adapter
        self._retry_max = retry_max
        self._retry_backoff = retry_backoff

        # In-memory dead-letter queue
        self._dlq: List[Dict[str, Any]] = []
        
        # Statistics
        self._total_sent = 0
        self._total_failed = 0
        self._total_retries = 0
        self._total_dlq = 0
        self._channel_stats = {
            "websocket": 0,
            "fcm": 0,
            "sms": 0,
            "email": 0
        }
        
        logger.info(
            f"[NotificationService] Initialized (retry_max={retry_max}, "
            f"retry_backoff={retry_backoff})"
        )
    
    async def send(
        self,
        user_id: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        priority: str = "normal",
        channels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Send notification to user with automatic channel fallback.
        
        Args:
            user_id: User ID
            title: Notification title
            body: Notification body/message
            data: Optional additional data payload
            priority: Priority level (low, normal, high, critical)
            channels: Optional list of channels to try (default: all)
        
        Returns:
            Dict with delivery status and metadata
        """
        payload = {
            "type": "notification",
            "user_id": user_id,
            "title": title,
            "body": body,
            "data": data or {},
            "priority": priority,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Default channels based on priority
        if channels is None:
            if priority == "critical":
                channels = ["websocket", "fcm", "sms", "email"]
            elif priority == "high":
                channels = ["websocket", "fcm", "sms"]
            else:
                channels = ["websocket", "fcm"]
        
        logger.info(
            f"[NotificationService] Sending to user {user_id}: "
            f"priority={priority}, channels={channels}"
        )
        
        # Try delivery with retries
        result = await self._try_delivery_with_retry(
            user_id, payload, channels, attempt=1
        )
        
        if result["success"]:
            self._total_sent += 1
        else:
            self._total_failed += 1
        
        return result
    
    async def _try_delivery_with_retry(
        self,
        user_id: str,
        payload: Dict[str, Any],
        channels: List[str],
        attempt: int
    ) -> Dict[str, Any]:
        """
        Try delivery with exponential backoff retry.
        
        Args:
            user_id: User ID
            payload: Notification payload
            channels: List of channels to try
            attempt: Current attempt number
        
        Returns:
            Dict with success status and metadata
        """
        # Try each channel in order
        for channel in channels:
            try:
                success = await self._try_channel(user_id, payload, channel)
                
                if success:
                    return {
                        "success": True,
                        "channel": channel,
                        "attempt": attempt,
                        "user_id": user_id
                    }
            
            except Exception as e:
                logger.error(
                    f"[NotificationService] Error on channel {channel} "
                    f"for user {user_id}: {e}"
                )
        
        # All channels failed, retry with backoff
        if attempt < self._retry_max:
            self._total_retries += 1
            
            # Exponential backoff: 1s, 2s, 4s, 8s, 16s (max 30s)
            delay = min(self._retry_backoff ** (attempt - 1), 30.0)
            
            logger.warning(
                f"[NotificationService] All channels failed for user {user_id}, "
                f"retrying in {delay}s (attempt {attempt}/{self._retry_max})"
            )
            
            await asyncio.sleep(delay)
            
            return await self._try_delivery_with_retry(
                user_id, payload, channels, attempt + 1
            )
        
        # Max retries reached, send to DLQ
        logger.error(
            f"[NotificationService] Max retries reached for user {user_id}, "
            f"sending to DLQ"
        )
        
        await self._send_to_dlq(user_id, payload, "max_retries_exceeded")
        
        return {
            "success": False,
            "reason": "max_retries_exceeded",
            "attempts": attempt,
            "user_id": user_id
        }
    
    async def _try_channel(
        self,
        user_id: str,
        payload: Dict[str, Any],
        channel: str
    ) -> bool:
        """
        Try delivery via specific channel.
        
        Args:
            user_id: User ID
            payload: Notification payload
            channel: Channel name (websocket, fcm, sms, email)
        
        Returns:
            True if successful
        """
        if channel == "websocket":
            # Try WebSocket first (fastest)
            if self._websocket_manager.is_connected(user_id):
                success = await self._websocket_manager.send_to_user(user_id, payload)
                
                if success:
                    self._channel_stats["websocket"] += 1
                    logger.debug(f"[NotificationService] Delivered via WebSocket to {user_id}")
                    return True
            
            # User offline, queue for later delivery
            await self._publisher.publish_to_user(user_id, payload)
            return False
        
        elif channel == "fcm":
            # Send FCM push notification
            success = await self._fcm_adapter.send_push(
                user_id=user_id,
                title=payload.get("title"),
                body=payload.get("body"),
                data=payload.get("data")
            )
            
            if success:
                self._channel_stats["fcm"] += 1
                logger.debug(f"[NotificationService] Delivered via FCM to {user_id}")
            
            return success
        
        elif channel == "sms" and self._sms_adapter:
            # Send SMS (requires phone number lookup)
            # For now, just log - would need to fetch phone from DB
            logger.warning(
                f"[NotificationService] SMS delivery requested for {user_id} "
                f"but phone lookup not implemented"
            )
            return False
        
        elif channel == "email" and self._email_adapter:
            # Send email (requires email lookup)
            # For now, just log - would need to fetch email from DB
            logger.warning(
                f"[NotificationService] Email delivery requested for {user_id} "
                f"but email lookup not implemented"
            )
            return False
        
        else:
            logger.warning(f"[NotificationService] Unknown or unavailable channel: {channel}")
            return False
    
    async def _send_to_dlq(
        self,
        user_id: str,
        payload: Dict[str, Any],
        reason: str
    ):
        """
        Send failed notification to in-memory dead-letter queue.

        Args:
            user_id: User ID
            payload: Notification payload
            reason: Failure reason
        """
        try:
            dlq_entry = {
                "user_id": user_id,
                "payload": payload,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat(),
                "attempts": self._retry_max
            }

            self._dlq.insert(0, dlq_entry)

            # Cap DLQ size to prevent unbounded memory growth
            if len(self._dlq) > 10000:
                self._dlq = self._dlq[:10000]

            self._total_dlq += 1

            logger.warning(
                f"[NotificationService] Sent to DLQ: user={user_id}, "
                f"reason={reason}"
            )

        except Exception as e:
            logger.error(f"[NotificationService] Error sending to DLQ: {e}")
    
    async def broadcast(
        self,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """
        Broadcast notification to all connected users.
        
        Args:
            title: Notification title
            body: Notification body
            data: Optional additional data
            priority: Priority level
        
        Returns:
            Dict with delivery statistics
        """
        payload = {
            "type": "notification",
            "broadcast": True,
            "title": title,
            "body": body,
            "data": data or {},
            "priority": priority,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        logger.info(f"[NotificationService] Broadcasting: '{title}'")
        
        # Publish to broadcast channel
        await self._publisher.publish_broadcast(payload)
        
        # Also send directly to WebSocket (for immediate delivery)
        await self._websocket_manager.broadcast(payload)
        
        # Send FCM broadcast (for offline users)
        # TODO: Implement FCM topic-based messaging
        
        return {
            "success": True,
            "broadcast": True,
            "connected_users": self._websocket_manager.get_connection_count()
        }
    
    async def get_dlq_items(
        self,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get items from in-memory dead-letter queue.

        Args:
            limit: Maximum number of items to retrieve

        Returns:
            List of DLQ entries
        """
        return self._dlq[:limit]
    
    async def retry_dlq_item(self, index: int = 0) -> bool:
        """
        Retry delivery of specific DLQ item.

        Args:
            index: Index in DLQ (0 = oldest)

        Returns:
            True if retry successful
        """
        try:
            if index < 0 or index >= len(self._dlq):
                return False

            dlq_entry = self._dlq[index]

            # Retry delivery
            result = await self.send(
                user_id=dlq_entry["user_id"],
                title=dlq_entry["payload"]["title"],
                body=dlq_entry["payload"]["body"],
                data=dlq_entry["payload"].get("data"),
                priority=dlq_entry["payload"].get("priority", "normal")
            )

            if result["success"]:
                self._dlq.pop(index)
                logger.info("[NotificationService] DLQ item retry successful, removed from queue")
                return True

            return False

        except Exception as e:
            logger.error(f"[NotificationService] Error retrying DLQ item: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get notification service statistics."""
        return {
            "total_sent": self._total_sent,
            "total_failed": self._total_failed,
            "total_retries": self._total_retries,
            "total_dlq": self._total_dlq,
            "success_rate": (
                self._total_sent / (self._total_sent + self._total_failed)
                if (self._total_sent + self._total_failed) > 0
                else 0.0
            ),
            "channel_stats": self._channel_stats,
            "retry_max": self._retry_max,
            "retry_backoff": self._retry_backoff
        }


# Global singleton
_notification_service: Optional[NotificationService] = None


async def get_notification_service(
    websocket_manager: WebSocketManager,
    publisher: NotificationPublisher,
    fcm_adapter: FCMAdapter,
    sms_adapter: Optional[SMSAdapter] = None,
    email_adapter: Optional[EmailAdapter] = None,
    retry_max: int = 5,
    retry_backoff: float = 2.0,
    **kwargs,
) -> NotificationService:
    """
    Get or create global notification service singleton.

    Args:
        websocket_manager: WebSocket manager
        publisher: Publisher
        fcm_adapter: FCM adapter
        sms_adapter: SMS adapter
        email_adapter: Email adapter
        retry_max: Max retry attempts
        retry_backoff: Backoff multiplier

    Returns:
        NotificationService instance
    """
    global _notification_service

    if _notification_service is None:
        _notification_service = NotificationService(
            websocket_manager=websocket_manager,
            publisher=publisher,
            fcm_adapter=fcm_adapter,
            sms_adapter=sms_adapter,
            email_adapter=email_adapter,
            retry_max=retry_max,
            retry_backoff=retry_backoff,
        )

    return _notification_service
