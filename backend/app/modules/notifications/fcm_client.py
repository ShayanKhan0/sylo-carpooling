"""
Firebase Cloud Messaging (FCM) Client

Helper module for sending push notifications via Firebase Cloud Messaging.
Supports structured logging, error handling, and retry mechanisms.

Author: Smart Carpooling Backend Team
"""

import logging
from typing import Optional, Dict, Any, List
import asyncio
from app.core.firebase_admin import initialize_firebase

# Firebase Admin SDK (optional - install with: pip install firebase-admin)
try:
    import firebase_admin
    from firebase_admin import credentials, messaging
    FCM_AVAILABLE = True
except ImportError:
    FCM_AVAILABLE = False
    logging.warning("Firebase Admin SDK not installed. Push notifications will be mocked.")

logger = logging.getLogger(__name__)


class FCMClient:
    """
    Firebase Cloud Messaging client for push notifications.
    
    Features:
    - Async message sending
    - Batch messaging support
    - Error handling with structured logging
    - Mock mode when Firebase SDK not available
    """
    
    def __init__(self):
        """Initialize FCM client with credentials from environment."""
        self.initialized = False
        self.mock_mode = not FCM_AVAILABLE
        
        if FCM_AVAILABLE:
            self._initialize_firebase()
        else:
            logger.warning("[FCM] Running in MOCK mode - no actual notifications will be sent")
    
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK using shared backend configuration."""
        try:
            # Reuse an already initialized Firebase app when available.
            if firebase_admin._apps:
                self.initialized = True
                self.mock_mode = False
                logger.info("[FCM] Using existing Firebase Admin SDK instance")
                return

            # Use centralized initialization so auth and notifications read the same
            # credentials source (FCM_CREDENTIALS_PATH / GOOGLE_APPLICATION_CREDENTIALS).
            fb_app = initialize_firebase()
            if fb_app:
                self.initialized = True
                self.mock_mode = False
                logger.info("[FCM] Firebase Admin SDK initialized successfully for notifications")
                return

            logger.error(
                "[FCM] Firebase credentials are not configured for notifications. "
                "Set FCM_CREDENTIALS_PATH or GOOGLE_APPLICATION_CREDENTIALS. "
                "Running in MOCK mode."
            )
            self.mock_mode = True
        except Exception as e:
            logger.error(f"[FCM] Failed to initialize Firebase for notifications: {e}")
            self.mock_mode = True
    
    async def send_notification(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None,
        priority: str = "high"
    ) -> Dict[str, Any]:
        """
        Send a push notification to a single device.
        
        Args:
            token: FCM device token
            title: Notification title
            body: Notification message body
            data: Optional data payload (must be dict with string values)
            priority: Priority level ('normal' or 'high')
        
        Returns:
            Dictionary with success status and message_id or error
        """
        if self.mock_mode:
            return await self._send_mock_notification(token, title, body, data)
        
        try:
            # Construct FCM message
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body
                ),
                data=data or {},
                token=token,
                android=messaging.AndroidConfig(
                    priority=priority,
                    notification=messaging.AndroidNotification(
                        sound='default',
                        priority='high' if priority == 'high' else 'default'
                    )
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound='default',
                            badge=1
                        )
                    )
                )
            )
            
            # Send message (blocking call - wrap in async)
            loop = asyncio.get_event_loop()
            message_id = await loop.run_in_executor(None, messaging.send, message)
            
            logger.info(f"[FCM] ✅ Sent notification: {title[:30]}... | Token: {token[:20]}... | ID: {message_id}")
            
            return {
                "success": True,
                "message_id": message_id,
                "token": token
            }
        
        except messaging.UnregisteredError:
            logger.warning(f"[FCM] ❌ Token unregistered: {token[:20]}...")
            return {
                "success": False,
                "error": "unregistered_token",
                "token": token
            }
        
        except messaging.InvalidArgumentError as e:
            logger.error(f"[FCM] ❌ Invalid argument: {e}")
            return {
                "success": False,
                "error": "invalid_argument",
                "token": token
            }
        
        except Exception as e:
            logger.error(f"[FCM] ❌ Failed to send notification: {e}")
            return {
                "success": False,
                "error": str(e),
                "token": token
            }
    
    async def send_batch_notifications(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None,
        priority: str = "high"
    ) -> Dict[str, Any]:
        """
        Send push notifications to multiple devices in batch.
        
        Args:
            tokens: List of FCM device tokens
            title: Notification title
            body: Notification message body
            data: Optional data payload
            priority: Priority level
        
        Returns:
            Dictionary with success count, failure count, and results
        """
        if not tokens:
            return {
                "success_count": 0,
                "failure_count": 0,
                "results": []
            }
        
        if self.mock_mode:
            return await self._send_batch_mock_notifications(tokens, title, body, data)
        
        # Send notifications concurrently
        tasks = [
            self.send_notification(token, title, body, data, priority)
            for token in tokens
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
        failure_count = len(results) - success_count
        
        logger.info(f"[FCM] Batch send completed: {success_count} success, {failure_count} failed out of {len(tokens)}")
        
        return {
            "success_count": success_count,
            "failure_count": failure_count,
            "results": results
        }
    
    async def _send_mock_notification(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Mock notification sending for testing."""
        logger.info(f"[FCM MOCK] 📤 Would send: '{title}' to token {token[:20]}...")
        logger.debug(f"[FCM MOCK] Body: {body[:50]}...")
        
        # Simulate network delay
        await asyncio.sleep(0.1)
        
        return {
            "success": True,
            "message_id": f"mock_msg_{token[:10]}",
            "token": token,
            "mock": True
        }
    
    async def _send_batch_mock_notifications(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Mock batch notification sending for testing."""
        logger.info(f"[FCM MOCK] 📤 Would send batch: '{title}' to {len(tokens)} devices")
        
        # Simulate network delay
        await asyncio.sleep(0.2)
        
        return {
            "success_count": len(tokens),
            "failure_count": 0,
            "results": [
                {
                    "success": True,
                    "message_id": f"mock_msg_{token[:10]}",
                    "token": token,
                    "mock": True
                }
                for token in tokens
            ]
        }


# Singleton instance
_fcm_client: Optional[FCMClient] = None


def get_fcm_client() -> FCMClient:
    """
    Get or create FCM client singleton.
    
    Returns:
        FCMClient instance
    """
    global _fcm_client
    
    if _fcm_client is None:
        _fcm_client = FCMClient()
    
    return _fcm_client


async def send_fcm_message(
    token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None,
    priority: str = "high"
) -> Dict[str, Any]:
    """
    Convenience function to send FCM notification.
    
    Args:
        token: FCM device token
        title: Notification title
        body: Notification message body
        data: Optional data payload
        priority: Priority level ('normal' or 'high')
    
    Returns:
        Dictionary with success status and message_id or error
    """
    client = get_fcm_client()
    return await client.send_notification(token, title, body, data, priority)


async def send_fcm_batch(
    tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None,
    priority: str = "high"
) -> Dict[str, Any]:
    """
    Convenience function to send batch FCM notifications.
    
    Args:
        tokens: List of FCM device tokens
        title: Notification title
        body: Notification message body
        data: Optional data payload
        priority: Priority level
    
    Returns:
        Dictionary with success count, failure count, and results
    """
    client = get_fcm_client()
    return await client.send_batch_notifications(tokens, title, body, data, priority)
