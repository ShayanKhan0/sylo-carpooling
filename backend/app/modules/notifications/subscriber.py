"""
In-Memory Subscriber for Real-Time Notifications

Replaces Redis pub/sub with a lightweight in-process message relay.
The subscriber is kept as a thin wrapper around the WebSocket manager
so that startup/shutdown call-sites remain unchanged.

Author: Smart Carpooling Backend Team
"""

import asyncio
import json
import logging
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime

from app.modules.notifications.websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)


class NotificationSubscriber:
    """
    In-memory notification subscriber.

    Provides the same start/stop/statistics API as the old Redis-backed
    subscriber so that the rest of the codebase needs no changes.
    """

    def __init__(
        self,
        websocket_manager: WebSocketManager,
        channel_prefix: str = "notifications",
        dlq_handler: Optional[Callable] = None,
        **kwargs,
    ):
        self._websocket_manager = websocket_manager
        self._channel_prefix = channel_prefix
        self._dlq_handler = dlq_handler
        self._running = False

        # Statistics
        self._messages_received = 0
        self._messages_delivered = 0
        self._messages_queued = 0

        logger.info(f"[NotificationSubscriber] Initialized (in-memory, prefix={channel_prefix})")

    async def start(self):
        """Mark the subscriber as running."""
        if self._running:
            logger.warning("[NotificationSubscriber] Already running")
            return
        self._running = True
        logger.info("[NotificationSubscriber] Started (in-memory)")

    async def stop(self):
        """Stop the subscriber."""
        self._running = False
        logger.info("[NotificationSubscriber] Stopped")

    # ------- Message delivery helpers (called directly, no Redis) -------

    async def deliver_to_user(self, user_id: str, payload: Dict[str, Any]):
        """Deliver notification to a specific user via WebSocket."""
        self._messages_received += 1

        if self._websocket_manager.is_connected(user_id):
            success = await self._websocket_manager.send_to_user(user_id, payload)
            if success:
                self._messages_delivered += 1
            else:
                self._messages_queued += 1
                if self._dlq_handler:
                    await self._dlq_handler(user_id, payload, "websocket_send_failed")
        else:
            self._messages_queued += 1
            if self._dlq_handler:
                await self._dlq_handler(user_id, payload, "user_offline")

    async def deliver_broadcast(self, payload: Dict[str, Any]):
        """Broadcast notification to all connected users."""
        self._messages_received += 1
        await self._websocket_manager.broadcast(payload)
        self._messages_delivered += 1

    def get_statistics(self) -> Dict[str, Any]:
        """Get subscriber statistics."""
        return {
            "running": self._running,
            "messages_received": self._messages_received,
            "messages_delivered": self._messages_delivered,
            "messages_queued": self._messages_queued,
            "reconnect_count": 0,
            "subscribed_channels": 0,
        }


# Global singleton
_subscriber: Optional[NotificationSubscriber] = None


async def get_subscriber(
    websocket_manager: WebSocketManager,
    channel_prefix: str = "notifications",
    dlq_handler: Optional[Callable] = None,
    redis_url: str = "",
    **kwargs,
) -> NotificationSubscriber:
    """
    Get or create global notification subscriber.

    ``redis_url`` is accepted for backward-compatible call-sites but ignored.
    """
    global _subscriber

    if _subscriber is None:
        _subscriber = NotificationSubscriber(
            websocket_manager=websocket_manager,
            channel_prefix=channel_prefix,
            dlq_handler=dlq_handler,
        )

    return _subscriber
