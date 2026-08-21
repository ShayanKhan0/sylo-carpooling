"""
Module: Admin Analytics & Monitoring
Purpose: API routes for admin dashboard (analytics, alerts, logs).
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: All endpoints require admin authentication via JWT.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from app.db.session import get_db
from app.core.responses import success_response, error_response, not_found_response
from app.modules.admin import service, crud
from app.modules.admin.schemas import (
    SystemStatsSummary,
    TrendData,
    AlertsListResponse,
    AlertResolveRequest,
    AlertResolveResponse,
    LogsListResponse,
    LogLevel
)
from app.modules.auth.models import User, UserRole
from app.modules.auth.deps import get_current_user

router = APIRouter()


# ==================== Admin Authentication Dependency ====================

async def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Verify that current user has admin role.
    
    Args:
        current_user: Authenticated user from JWT token
    
    Returns:
        User object if admin
    
    Raises:
        HTTPException 403: If user is not an admin
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return current_user


# ==================== Analytics Endpoints ====================

@router.get(
    "/analytics/stats/summary",
    response_model=None,
    summary="Get Platform Summary Statistics",
    description="Returns aggregated platform statistics including users, rides, drivers, revenue, and alerts.",
    tags=["Admin Analytics"]
)
async def get_stats_summary(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Get platform summary statistics for admin dashboard overview.
    
    **Admin only** - Requires JWT token with ADMIN role.
    
    Returns:
        - total_users: Total registered users count
        - total_drivers: Verified drivers count
        - active_rides: Currently in-progress rides
        - completed_rides_today: Rides completed today
        - avg_driver_rating: Average driver rating (0-5)
        - total_revenue: Total platform revenue
        - pending_verifications: Pending driver verifications
        - active_alerts: Active system alerts count
        - last_updated: Timestamp of data computation
    
    Example response:
    ```json
    {
        "status": "ok",
        "data": {
            "total_users": 15420,
            "total_drivers": 456,
            "active_rides": 87,
            "completed_rides_today": 234,
            "avg_driver_rating": 4.7,
            "total_revenue": 125000.50,
            "pending_verifications": 12,
            "active_alerts": 3,
            "last_updated": "2025-11-08T10:30:00Z"
        }
    }
    ```
    """
    try:
        summary = await service.compute_system_summary(db)
        return success_response(
            data=summary.model_dump(),
            message="Platform statistics retrieved successfully"
        )
    except Exception as e:
        return error_response(
            message="Failed to compute platform statistics",
            details={"error": str(e)}
        )


@router.get(
    "/analytics/stats/users",
    response_model=None,
    summary="Get User Growth Trend",
    description="Returns daily user registration trend over specified time period.",
    tags=["Admin Analytics"]
)
async def get_users_trend(
    days: int = Query(7, ge=1, le=90, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Get user registration trend for the last N days.
    
    **Admin only** - Requires JWT token with ADMIN role.
    
    Query Parameters:
        - days: Number of days to look back (1-90, default: 7)
    
    Returns:
        - metric_name: Metric identifier
        - metric_label: Human-readable label
        - data_points: Array of {label, value, timestamp}
        - total: Total count across all data points
        - average: Average daily count
        - trend: Trend direction (up, down, stable)
    
    Example response:
    ```json
    {
        "status": "ok",
        "data": {
            "metric_name": "user_registrations",
            "metric_label": "Daily User Registrations",
            "data_points": [
                {"label": "2025-11-01", "value": 210, "timestamp": "2025-11-01T00:00:00Z"},
                {"label": "2025-11-02", "value": 225, "timestamp": "2025-11-02T00:00:00Z"}
            ],
            "total": 669,
            "average": 223,
            "trend": "up"
        }
    }
    ```
    """
    try:
        trend = await service.get_user_growth_trend(db, days=days)
        return success_response(
            data=trend.model_dump(),
            message=f"User growth trend for last {days} days retrieved successfully"
        )
    except Exception as e:
        return error_response(
            message="Failed to compute user growth trend",
            details={"error": str(e)}
        )


@router.get(
    "/analytics/stats/rides",
    response_model=None,
    summary="Get Rides Trend",
    description="Returns daily ride bookings trend over specified time period.",
    tags=["Admin Analytics"]
)
async def get_rides_trend(
    days: int = Query(7, ge=1, le=90, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Get ride bookings trend for the last N days.
    
    **Admin only** - Requires JWT token with ADMIN role.
    
    Query Parameters:
        - days: Number of days to look back (1-90, default: 7)
    
    Returns:
        - metric_name: Metric identifier
        - metric_label: Human-readable label
        - data_points: Array of {label, value, timestamp}
        - total: Total rides across all data points
        - average: Average daily ride count
        - trend: Trend direction (up, down, stable)
    """
    try:
        trend = await service.get_rides_trend(db, days=days)
        return success_response(
            data=trend.model_dump(),
            message=f"Rides trend for last {days} days retrieved successfully"
        )
    except Exception as e:
        return error_response(
            message="Failed to compute rides trend",
            details={"error": str(e)}
        )


# ==================== Alerts Endpoints ====================

@router.get(
    "/analytics/alerts",
    response_model=None,
    summary="Get Active Alerts",
    description="Returns list of active system alerts requiring admin attention.",
    tags=["Admin Alerts"]
)
async def get_active_alerts(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Get all active system alerts.
    
    **Admin only** - Requires JWT token with ADMIN role.
    
    Returns:
        - alerts: Array of alert objects
        - total: Total active alerts count
        - by_severity: Count breakdown by severity (critical, high, medium, low)
    
    Example response:
    ```json
    {
        "status": "ok",
        "data": {
            "alerts": [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "title": "Database Connection Pool Exhausted",
                    "severity": "critical",
                    "status": "active",
                    "created_at": "2025-11-08T10:00:00Z"
                }
            ],
            "total": 5,
            "by_severity": {
                "critical": 1,
                "high": 2,
                "medium": 1,
                "low": 1
            }
        }
    }
    ```
    """
    try:
        alerts_response = await service.get_alerts_list(db)
        return success_response(
            data=alerts_response.model_dump(),
            message="Active alerts retrieved successfully"
        )
    except Exception as e:
        return error_response(
            message="Failed to retrieve alerts",
            details={"error": str(e)}
        )


@router.put(
    "/analytics/alerts/{alert_id}/resolve",
    response_model=None,
    summary="Resolve Alert",
    description="Mark an alert as resolved with optional resolution notes.",
    tags=["Admin Alerts"]
)
async def resolve_alert(
    alert_id: UUID,
    request: AlertResolveRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Resolve an alert.
    
    **Admin only** - Requires JWT token with ADMIN role.
    
    Path Parameters:
        - alert_id: UUID of the alert to resolve
    
    Request Body:
        - resolution_notes: Optional notes about the resolution
    
    Returns:
        - alert_id: Resolved alert UUID
        - status: New status (resolved)
        - resolved_at: Resolution timestamp
        - resolved_by: Admin user UUID
        - message: Success message
    
    Example response:
    ```json
    {
        "status": "ok",
        "data": {
            "alert_id": "123e4567-e89b-12d3-a456-426614174000",
            "status": "resolved",
            "resolved_at": "2025-11-08T10:30:00Z",
            "resolved_by": "admin_123",
            "message": "Alert resolved successfully"
        }
    }
    ```
    """
    try:
        result = await service.resolve_alert_with_notes(
            db,
            alert_id=alert_id,
            resolved_by=admin.id,
            resolution_notes=request.resolution_notes
        )
        return success_response(
            data=result,
            message="Alert resolved successfully"
        )
    except ValueError as e:
        return not_found_response(message=str(e))
    except Exception as e:
        return error_response(
            message="Failed to resolve alert",
            details={"error": str(e)}
        )


# ==================== Logs Endpoints ====================

@router.get(
    "/analytics/logs",
    response_model=None,
    summary="Get System Logs",
    description="Returns recent system log entries with optional filters.",
    tags=["Admin Logs"]
)
async def get_logs(
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    module: Optional[str] = Query(None, description="Filter by module (e.g., rides, payments)"),
    level: Optional[LogLevel] = Query(None, description="Filter by log level"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Get recent system log entries.
    
    **Admin only** - Requires JWT token with ADMIN role.
    
    Query Parameters:
        - limit: Page size (1-200, default: 50)
        - offset: Offset for pagination (default: 0)
        - module: Filter by module (optional)
        - level: Filter by log level (optional: debug, info, warning, error, critical)
    
    Returns:
        - logs: Array of log entry objects
        - total: Total matching logs count
        - limit: Page size used
        - offset: Offset used
    
    Example response:
    ```json
    {
        "status": "ok",
        "data": {
            "logs": [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "module": "payments",
                    "level": "error",
                    "message": "Payment gateway timeout",
                    "metadata": {"payment_id": "pay_ABC123"},
                    "timestamp": "2025-11-08T10:25:00Z"
                }
            ],
            "total": 1250,
            "limit": 50,
            "offset": 0
        }
    }
    ```
    """
    try:
        logs_response = await service.get_logs_with_pagination(
            db,
            limit=limit,
            offset=offset,
            module=module,
            level=level
        )
        return success_response(
            data=logs_response.model_dump(),
            message="System logs retrieved successfully"
        )
    except Exception as e:
        return error_response(
            message="Failed to retrieve logs",
            details={"error": str(e)}
        )
