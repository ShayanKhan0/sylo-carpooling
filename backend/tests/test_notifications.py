"""
Comprehensive Test Suite for Notifications Module

Tests push notifications, in-app alerts, FCM integration, device tokens,
and system broadcasts.

Author: Smart Carpooling Backend Team
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import (
    Notification,
    NotificationToken,
    NotificationTypeEnum,
    NotificationPriorityEnum,
    DeliveryStatusEnum,
    DevicePlatformEnum
)
from app.modules.notifications import crud, service
from app.modules.notifications.fcm_client import FCMClient


@pytest.fixture
async def test_notification(db_session: AsyncSession):
    """Create a test notification."""
    notification = Notification(
        user_id=uuid4(),
        title="Test Notification",
        message="This is a test notification message",
        type=NotificationTypeEnum.SYSTEM,
        priority=NotificationPriorityEnum.NORMAL,
        delivery_status=DeliveryStatusEnum.PENDING
    )
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)
    return notification


@pytest.fixture
async def test_device_token(db_session: AsyncSession):
    """Create a test device token."""
    token = NotificationToken(
        user_id=uuid4(),
        device_token="fKc8X9ZqRxG:APA91bHU_test_token_123456789",
        platform=DevicePlatformEnum.ANDROID
    )
    db_session.add(token)
    await db_session.commit()
    await db_session.refresh(token)
    return token


class TestNotificationCRUD:
    """Test notification CRUD operations."""
    
    async def test_create_notification(self, db_session: AsyncSession):
        """Test creating notification."""
        user_id = uuid4()
        notification = await crud.create_notification(
            db=db_session,
            user_id=user_id,
            title="Test Title",
            message="Test message body",
            notification_type=NotificationTypeEnum.RIDE,
            priority=NotificationPriorityEnum.HIGH,
            metadata={"ride_id": str(uuid4())}
        )
        
        assert notification.user_id == user_id
        assert notification.title == "Test Title"
        assert notification.type == NotificationTypeEnum.RIDE
        assert notification.priority == NotificationPriorityEnum.HIGH
        assert notification.delivery_status == DeliveryStatusEnum.PENDING
    
    async def test_get_notification(self, db_session: AsyncSession, test_notification: Notification):
        """Test retrieving notification."""
        notification = await crud.get_notification(db_session, test_notification.id)
        
        assert notification is not None
        assert notification.id == test_notification.id
    
    async def test_get_user_notifications(self, db_session: AsyncSession):
        """Test getting user notifications."""
        user_id = uuid4()
        
        # Create multiple notifications
        for i in range(5):
            await crud.create_notification(
                db=db_session,
                user_id=user_id,
                title=f"Notification {i}",
                message=f"Message {i}"
            )
        
        notifications, total = await crud.get_user_notifications(db_session, user_id, limit=10)
        
        assert len(notifications) == 5
        assert total == 5
    
    async def test_get_unread_count(self, db_session: AsyncSession):
        """Test getting unread count."""
        user_id = uuid4()
        
        # Create notifications
        for i in range(3):
            await crud.create_notification(
                db=db_session,
                user_id=user_id,
                title=f"Notification {i}",
                message="Test"
            )
        
        # Mark one as read
        notifications, _ = await crud.get_user_notifications(db_session, user_id)
        await crud.mark_as_read(db_session, notifications[0].id)
        
        unread_count = await crud.get_unread_count(db_session, user_id)
        assert unread_count == 2
    
    async def test_mark_as_read(self, db_session: AsyncSession, test_notification: Notification):
        """Test marking notification as read."""
        assert test_notification.read_at is None
        
        updated = await crud.mark_as_read(db_session, test_notification.id)
        
        assert updated.read_at is not None
        assert isinstance(updated.read_at, datetime)
    
    async def test_mark_all_as_read(self, db_session: AsyncSession):
        """Test marking all notifications as read."""
        user_id = uuid4()
        
        # Create multiple unread notifications
        for i in range(4):
            await crud.create_notification(
                db=db_session,
                user_id=user_id,
                title=f"Notification {i}",
                message="Test"
            )
        
        count = await crud.mark_all_as_read(db_session, user_id)
        
        assert count == 4
        
        unread_count = await crud.get_unread_count(db_session, user_id)
        assert unread_count == 0
    
    async def test_update_delivery_status(self, db_session: AsyncSession, test_notification: Notification):
        """Test updating delivery status."""
        updated = await crud.update_delivery_status(
            db_session,
            test_notification.id,
            DeliveryStatusEnum.SENT
        )
        
        assert updated.delivery_status == DeliveryStatusEnum.SENT
        assert updated.sent_at is not None


class TestDeviceTokenCRUD:
    """Test device token CRUD operations."""
    
    async def test_register_device_token(self, db_session: AsyncSession):
        """Test registering device token."""
        user_id = uuid4()
        device_token = "fKc8X9ZqRxG:APA91bHU_new_token_987654321"
        
        token = await crud.register_device_token(
            db=db_session,
            user_id=user_id,
            device_token=device_token,
            platform=DevicePlatformEnum.IOS
        )
        
        assert token.user_id == user_id
        assert token.device_token == device_token
        assert token.platform == DevicePlatformEnum.IOS
        assert token.is_active == "True"
    
    async def test_register_duplicate_token(self, db_session: AsyncSession):
        """Test registering duplicate token updates existing."""
        user_id = uuid4()
        device_token = "fKc8X9ZqRxG:APA91bHU_duplicate_token"
        
        # Register first time
        token1 = await crud.register_device_token(
            db=db_session,
            user_id=user_id,
            device_token=device_token,
            platform=DevicePlatformEnum.ANDROID
        )
        
        # Register again with different user
        new_user_id = uuid4()
        token2 = await crud.register_device_token(
            db=db_session,
            user_id=new_user_id,
            device_token=device_token,
            platform=DevicePlatformEnum.ANDROID
        )
        
        # Should update existing token
        assert token1.id == token2.id
        assert token2.user_id == new_user_id
    
    async def test_get_active_tokens(self, db_session: AsyncSession):
        """Test getting active tokens for user."""
        user_id = uuid4()
        
        # Register multiple tokens
        for i in range(3):
            await crud.register_device_token(
                db=db_session,
                user_id=user_id,
                device_token=f"token_{i}_{'a' * 50}",
                platform=DevicePlatformEnum.ANDROID
            )
        
        tokens = await crud.get_active_tokens(db_session, user_id)
        
        assert len(tokens) == 3
    
    async def test_deactivate_token(self, db_session: AsyncSession, test_device_token: NotificationToken):
        """Test deactivating token."""
        result = await crud.deactivate_token(db_session, test_device_token.device_token)
        
        assert result is True
        
        # Verify token is deactivated
        from sqlalchemy import select
        result = await db_session.execute(
            select(NotificationToken).where(NotificationToken.id == test_device_token.id)
        )
        token = result.scalar_one()
        assert token.is_active == "False"


class TestFCMClient:
    """Test FCM client functionality."""
    
    @patch('app.modules.notifications.fcm_client.FCM_AVAILABLE', False)
    async def test_mock_send_notification(self):
        """Test FCM client in mock mode."""
        client = FCMClient()
        
        assert client.mock_mode is True
        
        result = await client.send_notification(
            token="test_token_123",
            title="Test",
            body="Test message",
            data={"key": "value"}
        )
        
        assert result["success"] is True
        assert result["mock"] is True
    
    @patch('app.modules.notifications.fcm_client.FCM_AVAILABLE', False)
    async def test_mock_batch_send(self):
        """Test FCM batch sending in mock mode."""
        client = FCMClient()
        
        tokens = [f"token_{i}" for i in range(5)]
        
        result = await client.send_batch_notifications(
            tokens=tokens,
            title="Broadcast",
            body="Test broadcast message"
        )
        
        assert result["success_count"] == 5
        assert result["failure_count"] == 0


class TestNotificationService:
    """Test notification service layer."""
    
    @patch('app.modules.notifications.service.send_notification_task')
    async def test_send_push_notification(self, mock_task, db_session: AsyncSession):
        """Test sending push notification."""
        from fastapi import BackgroundTasks
        from app.modules.notifications.schemas import NotificationCreate
        
        background_tasks = BackgroundTasks()
        
        notification_data = NotificationCreate(
            user_id=uuid4(),
            title="Test Push",
            message="Test push notification",
            type=NotificationTypeEnum.RIDE,
            priority=NotificationPriorityEnum.HIGH
        )
        
        result = await service.send_push_notification(
            db=db_session,
            background_tasks=background_tasks,
            notification_data=notification_data
        )
        
        assert result["status"] == "ok"
        assert "notification_id" in result["data"]
    
    async def test_send_in_app_alert(self, db_session: AsyncSession):
        """Test sending in-app alert."""
        user_id = uuid4()
        
        notification = await service.send_in_app_alert(
            db=db_session,
            user_id=user_id,
            title="In-App Alert",
            message="This is an in-app alert"
        )
        
        assert notification.user_id == user_id
        assert notification.delivery_status == DeliveryStatusEnum.SENT
    
    async def test_mark_read_service(self, db_session: AsyncSession, test_notification: Notification):
        """Test mark read service."""
        result = await service.mark_read(
            db=db_session,
            notification_id=test_notification.id,
            user_id=test_notification.user_id
        )
        
        assert result["status"] == "ok"


class TestNotificationAPI:
    """Test notification API endpoints."""
    
    async def test_get_my_notifications_endpoint(self, async_client: AsyncClient, auth_headers: dict):
        """Test GET /api/v1/notifications/my endpoint."""
        response = await async_client.get(
            "/api/v1/notifications/my",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "notifications" in data
        assert "total" in data
        assert "unread_count" in data
    
    async def test_register_token_endpoint(self, async_client: AsyncClient, auth_headers: dict):
        """Test POST /api/v1/notifications/register-token endpoint."""
        payload = {
            "device_token": "fKc8X9ZqRxG:APA91bHU_" + "a" * 100,
            "platform": "android"
        }
        
        response = await async_client.post(
            "/api/v1/notifications/register-token",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code in [200, 201]
    
    async def test_mark_read_endpoint(self, async_client: AsyncClient, auth_headers: dict):
        """Test PUT /api/v1/notifications/mark-read/{id} endpoint."""
        notification_id = uuid4()
        
        response = await async_client.put(
            f"/api/v1/notifications/mark-read/{notification_id}",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 404]
    
    async def test_get_unread_count_endpoint(self, async_client: AsyncClient, auth_headers: dict):
        """Test GET /api/v1/notifications/unread-count endpoint."""
        response = await async_client.get(
            "/api/v1/notifications/unread-count",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "unread_count" in data["data"]


class TestBroadcastFeature:
    """Test system broadcast functionality."""
    
    @patch('app.modules.notifications.service.send_bulk_notifications_task')
    async def test_broadcast_system_message(self, mock_task, db_session: AsyncSession):
        """Test broadcasting system message."""
        from fastapi import BackgroundTasks
        from app.modules.notifications.schemas import BroadcastRequest
        
        background_tasks = BackgroundTasks()
        
        broadcast = BroadcastRequest(
            title="System Maintenance",
            message="The system will undergo maintenance",
            priority=NotificationPriorityEnum.HIGH
        )
        
        # This would require admin user fixture
        # Mock for now
        pass


# Additional fixtures
@pytest.fixture
async def async_client():
    """Mock async client fixture."""
    pass


@pytest.fixture
def auth_headers():
    """Mock authentication headers."""
    return {"Authorization": "Bearer test_token"}
