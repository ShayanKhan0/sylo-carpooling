"""
In-Memory Publisher for Real-Time Notifications

Replaces Redis pub/sub with direct in-memory message dispatch.
Messages are forwarded directly to the WebSocket manager.

Author: Smart Carpooling Backend Team
"""

import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class NotificationPublisher:
    """
    In-memory publisher for notification messages.

    Instead of publishing to Redis channels, messages are stored in an
    internal queue and can be consumed directly by the WebSocket manager.
    """

    def __init__(self, channel_prefix: str = "notifications"):
        self._channel_prefix = channel_prefix
        self._message_queue: list[Dict[str, Any]] = []
        self._connected = True
        logger.info(f"[NotificationPublisher] Initialized (in-memory, prefix={channel_prefix})")

    async def connect(self):
        """No-op — no external service to connect to."""
        self._connected = True
        logger.info("[NotificationPublisher] Ready (in-memory)")

    async def disconnect(self):
        """Clear internal queue."""
        self._message_queue.clear()
        self._connected = False
        logger.info("[NotificationPublisher] Disconnected")

    async def publish_to_user(self, user_id: str, payload: Dict[str, Any]) -> bool:
        """
        Publish notification to specific user channel.

        The message is stored in an internal queue for immediate consumption
        by the WebSocket manager.
        """
        try:
            if "timestamp" not in payload:
                payload["timestamp"] = datetime.utcnow().isoformat()
            payload["user_id"] = user_id

            channel = f"{self._channel_prefix}:user:{user_id}"
            self._message_queue.append({"channel": channel, "payload": payload})

            logger.debug(
                f"[NotificationPublisher] Queued for {channel}: {payload.get('type')}"
            )
            return True
        except Exception as e:
            logger.error(f"[NotificationPublisher] Error publishing to user {user_id}: {e}")
            return False

    async def publish_broadcast(self, payload: Dict[str, Any]) -> bool:
        """Publish notification to broadcast channel."""
        try:
            if "timestamp" not in payload:
                payload["timestamp"] = datetime.utcnow().isoformat()
            payload["broadcast"] = True

            channel = f"{self._channel_prefix}:broadcast"
            self._message_queue.append({"channel": channel, "payload": payload})

            logger.info(f"[NotificationPublisher] Broadcast queued: {payload.get('type')}")
            return True
        except Exception as e:
            logger.error(f"[NotificationPublisher] Error publishing broadcast: {e}")
            return False

    async def publish(self, user_id: Optional[str], payload: Dict[str, Any]) -> bool:
        """Auto-detect broadcast vs single user."""
        if user_id is None or payload.get("broadcast"):
            return await self.publish_broadcast(payload)
        return await self.publish_to_user(user_id, payload)

    def drain_queue(self) -> list[Dict[str, Any]]:
        """Return and clear all pending messages (for testing/debugging)."""
        items = list(self._message_queue)
        self._message_queue.clear()
        return items


# Global singleton
_publisher: Optional[NotificationPublisher] = None


async def get_publisher(
    redis_url: str = "",
    channel_prefix: str = "notifications",
) -> NotificationPublisher:
    """
    Get or create global notification publisher.

    ``redis_url`` is accepted for backward-compatible call-sites but ignored.
    """
    global _publisher
    if _publisher is None:
        _publisher = NotificationPublisher(channel_prefix)
        await _publisher.connect()
    return _publisher
