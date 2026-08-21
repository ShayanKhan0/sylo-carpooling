"""
Module: Admin Analytics & Monitoring - Tests
Purpose: Comprehensive tests for admin dashboard endpoints.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from uuid import uuid4

from app.main import app
from app.modules.auth.models import User, UserRole
from app.modules.drivers.models import Driver, DriverStatus
from app.models.ride import Ride, RideStatus
from app.modules.payments.models import Payment, PaymentStatus
from app.modules.admin.models import SystemStats, LogEntry, Alert, LogLevel, AlertStatus, AlertSeverity


# ==================== Fixtures ====================

@pytest.fixture
async def admin_user(db_session: AsyncSession):
    """Create an admin user for testing."""
    user = User(
        id=uuid4(),
        email="admin@smartcarpool.com",
        full_name="Admin User",
        phone_number="+1234567890",
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
        hashed_password="hashedpassword123"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def regular_user(db_session: AsyncSession):
    """Create a regular student user for testing auth enforcement."""
    user = User(
        id=uuid4(),
        email="student@university.edu",
        full_name="Student User",
        phone_number="+1234567891",
        role=UserRole.STUDENT,
        is_active=True,
        is_verified=True,
        hashed_password="hashedpassword123"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def mock_system_stats(db_session: AsyncSession):
    """Create mock system statistics."""
    stats = [
        SystemStats(
            id=uuid4(),
            metric_name="total_users",
            metric_value=15420.0,
            metric_label="Total Registered Users",
            category="users",
            metadata={"growth_rate": 5.2, "trend": "up"},
            computed_at=datetime.utcnow()
        ),
        SystemStats(
            id=uuid4(),
            metric_name="total_drivers",
            metric_value=456.0,
            metric_label="Total Verified Drivers",
            category="drivers",
            metadata={"growth_rate": 3.1, "trend": "up"},
            computed_at=datetime.utcnow()
        ),
        SystemStats(
            id=uuid4(),
            metric_name="active_rides",
            metric_value=87.0,
            metric_label="Currently Active Rides",
            category="rides",
            metadata={},
            computed_at=datetime.utcnow()
        )
    ]
    for stat in stats:
        db_session.add(stat)
    await db_session.commit()
    return stats


@pytest.fixture
async def mock_logs(db_session: AsyncSession, admin_user: User):
    """Create mock log entries."""
    logs = [
        LogEntry(
            id=uuid4(),
            module="payments",
            level=LogLevel.ERROR,
            message="Payment gateway timeout after 30s",
            user_id=admin_user.id,
            metadata={"payment_id": "pay_ABC123", "gateway": "stripe"},
            timestamp=datetime.utcnow()
        ),
        LogEntry(
            id=uuid4(),
            module="rides",
            level=LogLevel.INFO,
            message="Ride completed successfully",
            metadata={"ride_id": "ride_123"},
            timestamp=datetime.utcnow() - timedelta(hours=1)
        ),
        LogEntry(
            id=uuid4(),
            module="auth",
            level=LogLevel.WARNING,
            message="Multiple failed login attempts",
            metadata={"ip": "192.168.1.1", "attempts": 3},
            timestamp=datetime.utcnow() - timedelta(hours=2)
        )
    ]
    for log in logs:
        db_session.add(log)
    await db_session.commit()
    return logs


@pytest.fixture
async def mock_alerts(db_session: AsyncSession):
    """Create mock system alerts."""
    alerts = [
        Alert(
            id=uuid4(),
            title="Database Connection Pool Exhausted",
            description="Connection pool reached maximum capacity of 30 connections",
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.ACTIVE,
            source_module="database",
            metadata={"pool_size": 30, "active_connections": 30},
            created_at=datetime.utcnow()
        ),
        Alert(
            id=uuid4(),
            title="High Rate of Ride Cancellations",
            description="Detected 12 cancellations in the last hour",
            severity=AlertSeverity.HIGH,
            status=AlertStatus.ACTIVE,
            source_module="rides",
            metadata={"count": 12, "threshold": 5},
            created_at=datetime.utcnow() - timedelta(minutes=30)
        )
    ]
    for alert in alerts:
        db_session.add(alert)
    await db_session.commit()
    return alerts


@pytest.fixture
def admin_token(admin_user: User):
    """Generate JWT token for admin user (mock)."""
    # In real tests, you'd use your JWT generation function
    return "mock_admin_jwt_token"


@pytest.fixture
def user_token(regular_user: User):
    """Generate JWT token for regular user (mock)."""
    return "mock_user_jwt_token"


# ==================== Test Analytics Endpoints ====================

class TestAnalyticsEndpoints:
    """Test admin analytics endpoints."""

    @pytest.mark.asyncio
    async def test_get_stats_summary_success(self, admin_token: str):
        """Test getting platform statistics summary as admin."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/analytics/stats/summary",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "total_users" in data["data"]
            assert "total_drivers" in data["data"]
            assert "active_rides" in data["data"]
            assert "avg_driver_rating" in data["data"]
            assert "total_revenue" in data["data"]
            assert "last_updated" in data["data"]

    @pytest.mark.asyncio
    async def test_get_stats_summary_unauthorized(self):
        """Test accessing stats summary without authentication."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/admin/analytics/stats/summary")
            
            assert response.status_code == 401  # Unauthorized

    @pytest.mark.asyncio
    async def test_get_stats_summary_forbidden(self, user_token: str):
        """Test accessing stats summary as non-admin user."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/analytics/stats/summary",
                headers={"Authorization": f"Bearer {user_token}"}
            )
            
            assert response.status_code == 403  # Forbidden

    @pytest.mark.asyncio
    async def test_get_users_trend_success(self, admin_token: str):
        """Test getting user growth trend as admin."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/analytics/stats/users?days=7",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "metric_name" in data["data"]
            assert "data_points" in data["data"]
            assert "total" in data["data"]
            assert "average" in data["data"]
            assert "trend" in data["data"]

    @pytest.mark.asyncio
    async def test_get_users_trend_invalid_days(self, admin_token: str):
        """Test getting user trend with invalid days parameter."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/analytics/stats/users?days=100",  # Exceeds max 90
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_get_rides_trend_success(self, admin_token: str):
        """Test getting rides trend as admin."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/analytics/stats/rides?days=7",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["data"]["metric_name"] == "ride_bookings"


# ==================== Test Alerts Endpoints ====================

class TestAlertsEndpoints:
    """Test admin alerts endpoints."""

    @pytest.mark.asyncio
    async def test_get_active_alerts_success(self, admin_token: str, mock_alerts):
        """Test getting active alerts as admin."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/analytics/alerts",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "alerts" in data["data"]
            assert "total" in data["data"]
            assert "by_severity" in data["data"]
            assert data["data"]["total"] >= 2  # At least our 2 mock alerts

    @pytest.mark.asyncio
    async def test_get_active_alerts_forbidden(self, user_token: str):
        """Test accessing alerts as non-admin."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/analytics/alerts",
                headers={"Authorization": f"Bearer {user_token}"}
            )
            
            assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_resolve_alert_success(self, admin_token: str, mock_alerts):
        """Test resolving an alert as admin."""
        alert_id = mock_alerts[0].id
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.put(
                f"/api/v1/admin/analytics/alerts/{alert_id}/resolve",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"resolution_notes": "Increased pool size to 50"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["data"]["alert_id"] == str(alert_id)
            assert data["data"]["status"] == "resolved"
            assert "resolved_at" in data["data"]
            assert "resolved_by" in data["data"]

    @pytest.mark.asyncio
    async def test_resolve_alert_not_found(self, admin_token: str):
        """Test resolving non-existent alert."""
        fake_alert_id = uuid4()
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.put(
                f"/api/v1/admin/analytics/alerts/{fake_alert_id}/resolve",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"resolution_notes": "Test"}
            )
            
            assert response.status_code == 404


# ==================== Test Logs Endpoints ====================

class TestLogsEndpoints:
    """Test admin logs endpoints."""

    @pytest.mark.asyncio
    async def test_get_logs_success(self, admin_token: str, mock_logs):
        """Test getting system logs as admin."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/analytics/logs",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "logs" in data["data"]
            assert "total" in data["data"]
            assert "limit" in data["data"]
            assert "offset" in data["data"]
            assert data["data"]["total"] >= 3  # At least our 3 mock logs

    @pytest.mark.asyncio
    async def test_get_logs_with_filters(self, admin_token: str, mock_logs):
        """Test getting logs with module and level filters."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/analytics/logs?module=payments&level=error",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            # Should only return error logs from payments module
            for log in data["data"]["logs"]:
                assert log["module"] == "payments"
                assert log["level"] == "error"

    @pytest.mark.asyncio
    async def test_get_logs_pagination(self, admin_token: str, mock_logs):
        """Test logs pagination."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/analytics/logs?limit=2&offset=0",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["data"]["limit"] == 2
            assert data["data"]["offset"] == 0
            assert len(data["data"]["logs"]) <= 2

    @pytest.mark.asyncio
    async def test_get_logs_forbidden(self, user_token: str):
        """Test accessing logs as non-admin."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/analytics/logs",
                headers={"Authorization": f"Bearer {user_token}"}
            )
            
            assert response.status_code == 403


# ==================== Test Authentication Enforcement ====================

class TestAuthenticationEnforcement:
    """Test that all admin endpoints require admin authentication."""

    @pytest.mark.asyncio
    async def test_all_endpoints_require_auth(self):
        """Test that all admin endpoints reject unauthenticated requests."""
        endpoints = [
            "/api/v1/admin/analytics/stats/summary",
            "/api/v1/admin/analytics/stats/users",
            "/api/v1/admin/analytics/stats/rides",
            "/api/v1/admin/analytics/alerts",
            "/api/v1/admin/analytics/logs"
        ]
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            for endpoint in endpoints:
                response = await client.get(endpoint)
                assert response.status_code == 401, f"Endpoint {endpoint} should require auth"

    @pytest.mark.asyncio
    async def test_all_endpoints_require_admin_role(self, user_token: str):
        """Test that all admin endpoints reject non-admin users."""
        endpoints = [
            "/api/v1/admin/analytics/stats/summary",
            "/api/v1/admin/analytics/stats/users",
            "/api/v1/admin/analytics/stats/rides",
            "/api/v1/admin/analytics/alerts",
            "/api/v1/admin/analytics/logs"
        ]
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            for endpoint in endpoints:
                response = await client.get(
                    endpoint,
                    headers={"Authorization": f"Bearer {user_token}"}
                )
                assert response.status_code == 403, f"Endpoint {endpoint} should require admin role"


# ==================== Test Data Aggregation ====================

class TestDataAggregation:
    """Test data aggregation logic in service layer."""

    @pytest.mark.asyncio
    async def test_system_summary_computation(self, db_session: AsyncSession):
        """Test that system summary aggregates data correctly."""
        from app.modules.admin.service import compute_system_summary
        
        # Create test data
        user1 = User(
            id=uuid4(), email="user1@test.com", full_name="User 1",
            phone_number="+1111111111", role=UserRole.STUDENT,
            is_active=True, hashed_password="hash1"
        )
        user2 = User(
            id=uuid4(), email="user2@test.com", full_name="User 2",
            phone_number="+2222222222", role=UserRole.STUDENT,
            is_active=True, hashed_password="hash2"
        )
        db_session.add_all([user1, user2])
        await db_session.commit()
        
        # Compute summary
        summary = await compute_system_summary(db_session)
        
        assert summary.total_users >= 2
        assert summary.total_drivers >= 0
        assert summary.active_rides >= 0
        assert summary.avg_driver_rating >= 0.0
        assert summary.total_revenue >= 0.0
        assert summary.last_updated is not None

    @pytest.mark.asyncio
    async def test_trend_computation(self, db_session: AsyncSession):
        """Test that trend data is computed correctly."""
        from app.modules.admin.service import get_user_growth_trend
        
        # Create users with different timestamps
        for i in range(5):
            user = User(
                id=uuid4(),
                email=f"user{i}@test.com",
                full_name=f"User {i}",
                phone_number=f"+111111111{i}",
                role=UserRole.STUDENT,
                is_active=True,
                hashed_password="hash",
                created_at=datetime.utcnow() - timedelta(days=i)
            )
            db_session.add(user)
        await db_session.commit()
        
        # Compute trend
        trend = await get_user_growth_trend(db_session, days=7)
        
        assert trend.metric_name == "user_registrations"
        assert len(trend.data_points) >= 1
        assert trend.total >= 5
        assert trend.average > 0
        assert trend.trend in ["up", "down", "stable"]
