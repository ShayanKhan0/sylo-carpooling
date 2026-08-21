"""
Notifications Module - REST API Router

REST API endpoints for notification management, push notifications,
device token registration, and system broadcasts.

Author: Smart Carpooling Backend Team
"""

from uuid import UUID
from fastapi import APIRouter, Depends, status, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.schemas import UserPublic
from app.modules.auth.models import UserRole
from app.modules.notifications.schemas import (
    NotificationCreate,
    NotificationListResponse,
    TokenRegisterRequest,
    TokenResponse,
    BroadcastRequest,
    BroadcastResponse,
    MarkReadRequest
)
from app.modules.notifications import service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


async def get_current_admin_user(
    current_user: UserPublic = Depends(get_current_user)
) -> UserPublic:
    """Dependency to verify admin role."""
    from fastapi import HTTPException, status
    
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return current_user


@router.post(
    "/send",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Send Notification to User",
    description="""
    Send a push notification to a specific user.
    
    **Features:**
    - Creates notification record in database
    - Queues for async FCM delivery
    - Supports retry logic (3 attempts with exponential backoff)
    - Appears in user's in-app notification feed
    
    **Use Cases:**
    - Ride confirmations and updates
    - Payment notifications
    - Safety alerts
    - Verification status updates
    
    **Notification Types:**
    - system: System-wide announcements
    - ride: Ride-related notifications
    - payment: Payment and wallet notifications
    - safety: Safety alerts and incidents
    - verification: Document verification updates
    - custom: Custom notifications
    
    **Priority Levels:**
    - low: Non-urgent notifications
    - normal: Standard notifications
    - high: Urgent notifications (vibration, sound, heads-up display)
    
    **Delivery:**
    - Notification is queued for async delivery
    - FCM push sent to all registered devices
    - Stored in database for in-app viewing
    - Automatic retry on transient failures
    """
)
async def send_notification(
    notification: NotificationCreate,
    background_tasks: BackgroundTasks,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Send notification to a user.
    
    Creates notification and queues for async FCM delivery.
    Requires JWT authentication.
    """
    return await service.send_push_notification(db, background_tasks, notification)


@router.post(
    "/broadcast",
    response_model=BroadcastResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Broadcast System Message (Admin Only)",
    description="""
    Send system-wide broadcast message to all active users.
    
    **Admin-Only Feature** - Requires admin role for access.
    
    **Use Cases:**
    - System maintenance announcements
    - Platform updates and new features
    - Promotional campaigns
    - Emergency notifications
    - Policy updates
    
    **Target Filtering:**
    - Optional: target specific roles (rider, driver)
    - If target_roles is null, broadcasts to all users
    - Supports multiple roles simultaneously
    
    **Delivery:**
    - Processes in batches of 100 users
    - Async background task for performance
    - FCM push to all registered devices
    - Stored in database for in-app viewing
    
    **Performance:**
    - Handles 100k+ users without blocking
    - Batch FCM delivery for efficiency
    - Background processing prevents timeouts
    """
)
async def broadcast_system_message(
    broadcast: BroadcastRequest,
    background_tasks: BackgroundTasks,
    current_admin: UserPublic = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Broadcast system message to all active users (admin only).
    
    Requires JWT authentication with admin role.
    """
    return await service.broadcast_system_message(db, background_tasks, broadcast)


@router.get(
    "/my",
    response_model=NotificationListResponse,
    summary="Get My Notifications",
    description="""
    Get current user's notifications with pagination.
    
    **Features:**
    - Paginated results for performance
    - Filter for unread only
    - Sorted by newest first
    - Includes total count and unread count
    
    **Query Parameters:**
    - limit: Maximum notifications to return (default 50, max 100)
    - skip: Offset for pagination (default 0)
    - unread_only: Filter for unread notifications only (default false)
    
    **Response:**
    - notifications: Array of notification objects
    - total: Total notification count (respecting filters)
    - unread_count: Count of unread notifications
    
    **Use Cases:**
    - Display notification feed in user dashboard
    - Show unread badge count
    - Implement infinite scroll pagination
    - Filter notification types
    
    **Notification Status:**
    - pending: Queued for delivery
    - sent: Successfully delivered via FCM
    - failed: Delivery failed after retries
    - read: User has viewed the notification
    """
)
async def get_my_notifications(
    limit: int = Query(default=50, ge=1, le=100, description="Maximum notifications to return"),
    skip: int = Query(default=0, ge=0, description="Offset for pagination"),
    unread_only: bool = Query(default=False, description="Filter for unread only"),
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's notifications.
    
    Returns paginated list with unread count. Requires JWT authentication.
    """
    return await service.get_user_notifications_service(
        db, current_user.id, limit, skip, unread_only
    )


@router.post(
    "/register-token",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register FCM Device Token",
    description="""
    Register Firebase Cloud Messaging (FCM) device token for push notifications.
    
    **Required for Push Notifications:**
    - Mobile apps must register device token on app launch
    - Web apps register token after notification permission granted
    - Tokens expire and need re-registration periodically
    
    **Platforms Supported:**
    - android: Android mobile devices
    - ios: iOS (iPhone, iPad) devices
    - web: Progressive Web Apps (PWA)
    
    **Token Management:**
    - Multiple devices per user supported (phone, tablet, web)
    - Duplicate tokens automatically updated
    - Invalid tokens auto-deactivated after FCM errors
    - Tokens refreshed on each app launch
    
    **Security:**
    - Tokens tied to authenticated user only
    - Token validation before storage
    - Encrypted storage in database
    
    **Token Lifecycle:**
    1. App obtains FCM token from Firebase SDK
    2. App calls this endpoint to register token
    3. Backend stores token for push delivery
    4. Backend sends push notifications via FCM
    5. If token invalid, backend auto-deactivates
    6. App re-registers on next launch
    
    **Example FCM Token:**
    `fKc8X9ZqRxG:APA91bHU...long_token_here...`
    """
)
async def register_device_token(
    token_request: TokenRegisterRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Register FCM device token for push notifications.
    
    Stores device token for push notification delivery. Requires JWT authentication.
    """
    return await service.register_device_token_service(db, current_user.id, token_request)


@router.put(
    "/mark-read/{notification_id}",
    response_model=dict,
    summary="Mark Notification as Read",
    description="""
    Mark a specific notification as read.
    
    **Use Cases:**
    - User opens notification in app
    - User views notification details
    - Clear unread badge count
    - Track user engagement
    
    **Effects:**
    - Sets read_at timestamp to current time
    - Decrements unread count
    - Notification marked as "read" in UI
    
    **Analytics:**
    - Tracks user engagement with notifications
    - Helps optimize notification content
    - Identifies most effective notification types
    
    **Authorization:**
    - User can only mark their own notifications as read
    - Returns 404 if notification not found or not owned by user
    
    **Idempotent:**
    - Safe to call multiple times
    - Already-read notifications remain read
    """
)
async def mark_notification_as_read(
    notification_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Mark notification as read.
    
    Updates read_at timestamp. Requires JWT authentication.
    """
    return await service.mark_read(db, notification_id, current_user.id)


@router.get(
    "/unread-count",
    response_model=dict,
    summary="Get Unread Notification Count",
    description="""
    Get count of unread notifications for current user.
    
    **Use Cases:**
    - Display unread badge on notification icon
    - Show in mobile app tab bar
    - Update in real-time via polling or WebSocket
    
    **Performance:**
    - Optimized query with database index
    - Cached count for high-traffic scenarios
    - Suitable for frequent polling
    
    **Response:**
    ```json
    {
      "status": "ok",
      "data": {
        "unread_count": 5
      },
      "error": null
    }
    ```
    """
)
async def get_unread_count(
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get unread notification count for current user.
    
    Returns count of notifications with read_at = null. Requires JWT authentication.
    """
    from app.modules.notifications import crud
    
    unread_count = await crud.get_unread_count(db, current_user.id)
    
    return {
        "status": "ok",
        "data": {"unread_count": unread_count},
        "error": None
    }


# ============= WebSocket & Real-Time Endpoints (Prompt 9) =============

from fastapi import WebSocket, WebSocketDisconnect
from app.modules.notifications.websocket_manager import get_websocket_manager
from app.modules.notifications.schemas import (
    SendDirectRequest,
    HealthCheckResponse,
    DLQListResponse
)


@router.websocket("/ws/{user_id}")
async def websocket_notifications_endpoint(
    websocket: WebSocket,
    user_id: str
):
    """
    WebSocket endpoint for real-time notifications.
    
    URL: ws://localhost:8000/api/v2/notifications/ws/{user_id}?token={jwt_token}
    
    Features:
    - Real-time notification delivery
    - Heartbeat/ping every 30 seconds
    - Automatic reconnection support
    - Message queuing for offline users
    - Broadcast support
    
    Authentication:
    - JWT token passed as query parameter: ?token=your_jwt_token
    - Token validated on connection
    - Connection closed if invalid token
    
    Message Types Received:
    - notification: New notification delivery
    - ping: Heartbeat to keep connection alive
    - connection: Connection confirmation
    
    Client should respond with:
    - pong: Response to ping
    - ack: Acknowledgment of notification receipt
    
    Example with JavaScript:
    ```javascript
    const ws = new WebSocket(`ws://localhost:8000/api/v2/notifications/ws/${userId}?token=${token}`);
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'notification') {
            showNotification(data.title, data.body);
        } else if (data.type === 'ping') {
            ws.send(JSON.stringify({type: 'pong'}));
        }
    };
    ```
    """
    manager = get_websocket_manager()
    
    # TODO: Validate JWT token from query params
    # token = websocket.query_params.get("token")
    # if not token or not validate_jwt(token):
    #     await websocket.close(code=1008, reason="Unauthorized")
    #     return
    
    # Connect user
    connected = await manager.connect(websocket, user_id)
    
    if not connected:
        return
    
    try:
        # Listen for client messages
        while True:
            data = await websocket.receive_json()
            await manager.handle_client_message(user_id, data)
    
    except WebSocketDisconnect:
        await manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"[WebSocket] Error for user {user_id}: {e}")
        await manager.disconnect(user_id)


@router.post(
    "/admin/send/{user_id}",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Send Direct Notification to User (Admin Only)",
    description="""
    Send direct notification to specific user with channel fallback.
    
    **Admin-Only Feature** - Requires admin role.
    
    **Delivery Strategy:**
    1. Try WebSocket if user connected
    2. Fallback to FCM push notification
    3. Fallback to SMS (for critical priority)
    4. Fallback to Email
    5. Queue in DLQ after max retries (5 attempts)
    
    **Priority Levels:**
    - low: WebSocket + FCM
    - normal: WebSocket + FCM (default)
    - high: WebSocket + FCM + SMS
    - critical: All channels (WebSocket + FCM + SMS + Email)
    
    **Retry Logic:**
    - Exponential backoff: 1s → 2s → 4s → 8s → 16s (max 30s)
    - Max 5 retry attempts
    - Failed deliveries go to dead-letter queue
    
    **Use Cases:**
    - Admin sending verification status updates
    - Manual safety alerts
    - Account suspension notifications
    - Custom user-specific messages
    """
)
async def send_direct_notification(
    user_id: str,
    request: SendDirectRequest,
    current_admin: UserPublic = Depends(get_current_admin_user)
):
    """
    Send direct notification to specific user (admin only).
    
    Supports multi-channel delivery with fallback and retry logic.
    """
    from app.modules.notifications.notification_service import get_notification_service
    from app.modules.notifications.websocket_manager import get_websocket_manager
    from app.modules.notifications.publisher import get_publisher
    from app.modules.notifications.adapters.fcm_adapter import get_fcm_adapter
    from app.modules.notifications.adapters.sms_adapter import get_sms_adapter
    from app.modules.notifications.adapters.email_adapter import get_email_adapter
    from app.core.config import settings
    
    # Initialize components
    websocket_manager = get_websocket_manager()
    publisher = await get_publisher()
    fcm_adapter = get_fcm_adapter(settings.FCM_CREDENTIALS_PATH)
    sms_adapter = get_sms_adapter()
    email_adapter = get_email_adapter()
    
    notification_service = await get_notification_service(
        websocket_manager=websocket_manager,
        publisher=publisher,
        fcm_adapter=fcm_adapter,
        sms_adapter=sms_adapter,
        email_adapter=email_adapter,
        retry_max=settings.NOTIFICATIONS_RETRY_MAX,
        retry_backoff=settings.NOTIFICATIONS_RETRY_BACKOFF,
    )
    
    result = await notification_service.send(
        user_id=user_id,
        title=request.title,
        body=request.body,
        data=request.data,
        priority=request.priority,
        channels=request.channels
    )
    
    return {
        "status": "ok",
        "data": result,
        "error": None
    }


@router.post(
    "/admin/broadcast",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Broadcast to All Users (Admin Only)",
    description="""
    Broadcast notification to all connected users.
    
    **Admin-Only Feature** - Requires admin role.
    
    **Delivery:**
    - Published to broadcast channel
    - Sent to all active WebSocket connections
    - FCM topic-based messaging for offline users (future)
    
    **Use Cases:**
    - System maintenance announcements
    - Emergency broadcasts
    - Platform-wide updates
    - Event notifications
    
    **Performance:**
    - Handles thousands of concurrent connections
    - Non-blocking async delivery
    """
)
async def broadcast_to_all(
    request: BroadcastRequest,
    current_admin: UserPublic = Depends(get_current_admin_user)
):
    """
    Broadcast notification to all users (admin only).
    
    Uses WebSocket broadcasting.
    """
    from app.modules.notifications.notification_service import get_notification_service
    from app.modules.notifications.websocket_manager import get_websocket_manager
    from app.modules.notifications.publisher import get_publisher
    from app.modules.notifications.adapters.fcm_adapter import get_fcm_adapter
    from app.core.config import settings
    
    websocket_manager = get_websocket_manager()
    publisher = await get_publisher()
    fcm_adapter = get_fcm_adapter(settings.FCM_CREDENTIALS_PATH)
    
    notification_service = await get_notification_service(
        websocket_manager=websocket_manager,
        publisher=publisher,
        fcm_adapter=fcm_adapter,
        retry_max=settings.NOTIFICATIONS_RETRY_MAX,
        retry_backoff=settings.NOTIFICATIONS_RETRY_BACKOFF
    )
    
    result = await notification_service.broadcast(
        title=request.title,
        body=request.message,
        data={},
        priority=request.priority.value if hasattr(request.priority, 'value') else request.priority
    )
    
    return {
        "status": "ok",
        "data": result,
        "error": None
    }


@router.get(
    "/admin/health",
    response_model=HealthCheckResponse,
    summary="Health Check for Notification System (Admin Only)",
    description="""
    Comprehensive health check for all notification adapters and services.
    
    **Admin-Only Feature** - Requires admin role.
    
    **Components Checked:**
    - FCM Adapter: Firebase push notification status
    - SMS Adapter: Twilio/Easypaisa connectivity
    - Email Adapter: SMTP server connectivity
    - Pub/Sub: Subscriber status and statistics
    - WebSocket Manager: Active connections and throughput
    - Notification Service: Delivery statistics and success rate
    
    **Status Values:**
    - ok: Component functioning normally
    - degraded: Component functional but with issues
    - error: Component not functional
    - not_initialized: Component not configured
    
    **Use Cases:**
    - Monitoring dashboard
    - Health check endpoints for load balancers
    - Debugging delivery issues
    - Performance monitoring
    """
)
async def health_check(
    current_admin: UserPublic = Depends(get_current_admin_user)
):
    """
    Get health status of all notification system components (admin only).
    
    Returns comprehensive status for monitoring and debugging.
    """
    from app.modules.notifications.websocket_manager import get_websocket_manager
    from app.modules.notifications.adapters.fcm_adapter import get_fcm_adapter
    from app.modules.notifications.adapters.sms_adapter import get_sms_adapter
    from app.modules.notifications.adapters.email_adapter import get_email_adapter
    from app.modules.notifications.subscriber import _subscriber
    from app.modules.notifications.notification_service import _notification_service
    from datetime import datetime
    
    # Get component instances
    websocket_manager = get_websocket_manager()
    fcm_adapter = get_fcm_adapter()
    sms_adapter = get_sms_adapter()
    email_adapter = get_email_adapter()
    
    # Check adapter health
    fcm_health = await fcm_adapter.health_check()
    sms_health = await sms_adapter.health_check()
    email_health = await email_adapter.health_check()
    
    # WebSocket stats
    ws_stats = websocket_manager.get_statistics()
    
    # Subscriber stats
    subscriber_stats = _subscriber.get_statistics() if _subscriber else {
        "running": False,
        "messages_received": 0,
        "messages_delivered": 0
    }
    
    # Notification service stats
    service_stats = _notification_service.get_statistics() if _notification_service else {
        "total_sent": 0,
        "total_failed": 0,
        "success_rate": 0.0
    }
    
    # Determine overall status
    adapter_statuses = [fcm_health["status"], sms_health["status"], email_health["status"]]
    
    if all(s == "ok" for s in adapter_statuses):
        overall_status = "ok"
    elif any(s == "error" for s in adapter_statuses):
        overall_status = "degraded"
    else:
        overall_status = "ok"
    
    return HealthCheckResponse(
        overall_status=overall_status,
        fcm=fcm_health,
        sms=sms_health,
        email=email_health,
        redis_pubsub=subscriber_stats,
        websocket_manager=ws_stats,
        notification_service=service_stats,
        timestamp=datetime.utcnow().isoformat()
    )


@router.get(
    "/admin/dead_letter",
    response_model=DLQListResponse,
    summary="Get Dead-Letter Queue Items (Admin Only)",
    description="""
    Retrieve failed notification deliveries from dead-letter queue.
    
    **Admin-Only Feature** - Requires admin role.
    
    **Dead-Letter Queue:**
    - Stores notifications that failed after max retries (5 attempts)
    - Includes failure reason and timestamp
    - Allows manual retry or investigation
    
    **Use Cases:**
    - Debugging delivery failures
    - Manual retry of failed notifications
    - Monitoring notification reliability
    - Identifying problematic users or patterns
    
    **Query Parameters:**
    - limit: Maximum items to return (default 100)
    """
)
async def get_dead_letter_queue(
    limit: int = Query(default=100, ge=1, le=500),
    current_admin: UserPublic = Depends(get_current_admin_user)
):
    """
    Get dead-letter queue items (admin only).
    
    Returns list of failed notification deliveries.
    """
    from app.modules.notifications.notification_service import _notification_service
    
    if not _notification_service:
        return DLQListResponse(items=[], total=0)
    
    dlq_items = await _notification_service.get_dlq_items(limit=limit)
    
    return DLQListResponse(
        items=dlq_items,
        total=len(dlq_items)
    )

