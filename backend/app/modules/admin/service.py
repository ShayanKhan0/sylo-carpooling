"""
Module: Admin Analytics & Monitoring
Purpose: Business logic layer for admin dashboard (data aggregation, computations, formatting).
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Aggregates data from multiple modules for dashboard visualizations.
"""

from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Any
from datetime import datetime, timedelta
from uuid import UUID

from app.modules.admin import crud
from app.modules.admin.models import LogLevel, AlertStatus, AlertSeverity
from app.modules.admin.schemas import (
    SystemStatsSummary,
    TrendData,
    TrendDataPoint,
    AlertsListResponse,
    LogsListResponse
)
from app.modules.auth.models import User
from app.modules.drivers.models import Driver
from app.models.enums import DriverVerificationStatus, RideStatus, TransactionStatus
from app.models.ride import Ride
from app.modules.payments.models import Transaction


# ==================== System Stats Aggregation ====================

async def compute_system_summary(db: AsyncSession) -> SystemStatsSummary:
    """
    Compute live system statistics summary for dashboard overview.
    
    Args:
        db: Database session
    
    Returns:
        SystemStatsSummary with aggregated platform stats
    
    Example:
        >>> summary = await compute_system_summary(db)
        >>> print(f"Total users: {summary.total_users}")
        >>> print(f"Active rides: {summary.active_rides}")
    """
    # Total users
    total_users_query = select(func.count(User.id))
    total_users_result = await db.execute(total_users_query)
    total_users = total_users_result.scalar() or 0
    
    # Total verified drivers
    total_drivers_query = select(func.count(Driver.user_id)).where(
        Driver.status == DriverVerificationStatus.VERIFIED
    )
    total_drivers_result = await db.execute(total_drivers_query)
    total_drivers = total_drivers_result.scalar() or 0
    
    # Active rides (in_progress status)
    active_rides_query = select(func.count(Ride.id)).where(
        Ride.status == RideStatus.IN_PROGRESS
    )
    active_rides_result = await db.execute(active_rides_query)
    active_rides = active_rides_result.scalar() or 0
    
    # Completed rides today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    completed_today_query = select(func.count(Ride.id)).where(
        and_(
            Ride.status == RideStatus.COMPLETED,
            Ride.updated_at >= today_start
        )
    )
    completed_today_result = await db.execute(completed_today_query)
    completed_rides_today = completed_today_result.scalar() or 0
    
    # Average driver rating
    avg_rating_query = select(func.avg(Driver.average_rating)).where(
        Driver.average_rating.isnot(None)
    )
    avg_rating_result = await db.execute(avg_rating_query)
    avg_driver_rating = avg_rating_result.scalar() or 0.0
    avg_driver_rating = round(float(avg_driver_rating), 2)
    
    # Total revenue (sum of completed payments)
    total_revenue_query = select(func.sum(Transaction.amount)).where(
        Transaction.status == TransactionStatus.COMPLETED
    )
    total_revenue_result = await db.execute(total_revenue_query)
    total_revenue = total_revenue_result.scalar() or 0.0
    total_revenue = float(total_revenue)
    
    # Pending driver verifications
    pending_verifications_query = select(func.count(Driver.user_id)).where(
        Driver.status == DriverVerificationStatus.PENDING
    )
    pending_verifications_result = await db.execute(pending_verifications_query)
    pending_verifications = pending_verifications_result.scalar() or 0
    
    # Active alerts
    active_alerts = await crud.get_alerts_summary(db)
    active_alerts_count = active_alerts.get("total_active", 0)
    
    return SystemStatsSummary(
        total_users=total_users,
        total_drivers=total_drivers,
        active_rides=active_rides,
        completed_rides_today=completed_rides_today,
        avg_driver_rating=avg_driver_rating,
        total_revenue=total_revenue,
        pending_verifications=pending_verifications,
        active_alerts=active_alerts_count,
        last_updated=datetime.utcnow()
    )


async def get_user_growth_trend(
    db: AsyncSession,
    days: int = 7
) -> TrendData:
    """
    Compute user registration trend over last N days.
    
    Args:
        db: Database session
        days: Number of days to look back
    
    Returns:
        TrendData with daily user registration counts
    
    Example:
        >>> trend = await get_user_growth_trend(db, days=7)
        >>> for point in trend.data_points:
        >>>     print(f"{point.label}: {point.value} new users")
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Query users grouped by date
    query = (
        select(
            func.date(User.created_at).label("date"),
            func.count(User.id).label("count")
        )
        .where(User.created_at >= start_date)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    # Build data points
    data_points = []
    total = 0
    for row in rows:
        count = row.count
        total += count
        data_points.append(
            TrendDataPoint(
                label=row.date.strftime("%Y-%m-%d"),
                value=float(count),
                timestamp=datetime.combine(row.date, datetime.min.time())
            )
        )
    
    # Calculate average and trend
    average = total / len(data_points) if data_points else 0.0
    trend = "stable"
    if len(data_points) >= 2:
        first_half_avg = sum(p.value for p in data_points[:len(data_points)//2]) / (len(data_points)//2)
        second_half_avg = sum(p.value for p in data_points[len(data_points)//2:]) / (len(data_points) - len(data_points)//2)
        if second_half_avg > first_half_avg * 1.1:
            trend = "up"
        elif second_half_avg < first_half_avg * 0.9:
            trend = "down"
    
    return TrendData(
        metric_name="user_registrations",
        metric_label="Daily User Registrations",
        data_points=data_points,
        total=float(total),
        average=round(average, 2),
        trend=trend
    )


async def get_rides_trend(
    db: AsyncSession,
    days: int = 7
) -> TrendData:
    """
    Compute ride bookings trend over last N days.
    
    Args:
        db: Database session
        days: Number of days to look back
    
    Returns:
        TrendData with daily ride counts
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Query rides grouped by date (completed or in progress)
    query = (
        select(
            func.date(Ride.created_at).label("date"),
            func.count(Ride.id).label("count")
        )
        .where(
            and_(
                Ride.created_at >= start_date,
                Ride.status.in_([RideStatus.COMPLETED, RideStatus.IN_PROGRESS, RideStatus.SCHEDULED])
            )
        )
        .group_by(func.date(Ride.created_at))
        .order_by(func.date(Ride.created_at))
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    # Build data points
    data_points = []
    total = 0
    for row in rows:
        count = row.count
        total += count
        data_points.append(
            TrendDataPoint(
                label=row.date.strftime("%Y-%m-%d"),
                value=float(count),
                timestamp=datetime.combine(row.date, datetime.min.time())
            )
        )
    
    # Calculate average and trend
    average = total / len(data_points) if data_points else 0.0
    trend = "stable"
    if len(data_points) >= 2:
        first_half_avg = sum(p.value for p in data_points[:len(data_points)//2]) / (len(data_points)//2)
        second_half_avg = sum(p.value for p in data_points[len(data_points)//2:]) / (len(data_points) - len(data_points)//2)
        if second_half_avg > first_half_avg * 1.1:
            trend = "up"
        elif second_half_avg < first_half_avg * 0.9:
            trend = "down"
    
    return TrendData(
        metric_name="ride_bookings",
        metric_label="Daily Ride Bookings",
        data_points=data_points,
        total=float(total),
        average=round(average, 2),
        trend=trend
    )


async def get_revenue_trend(
    db: AsyncSession,
    days: int = 7
) -> TrendData:
    """
    Compute revenue trend over last N days.
    
    Args:
        db: Database session
        days: Number of days to look back
    
    Returns:
        TrendData with daily revenue totals
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Query payments grouped by date (completed only)
    query = (
        select(
            func.date(Transaction.created_at).label("date"),
            func.sum(Transaction.amount).label("total")
        )
        .where(
            and_(
                Transaction.created_at >= start_date,
                Transaction.status == TransactionStatus.COMPLETED
            )
        )
        .group_by(func.date(Transaction.created_at))
        .order_by(func.date(Transaction.created_at))
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    # Build data points
    data_points = []
    total = 0.0
    for row in rows:
        amount = float(row.total or 0.0)
        total += amount
        data_points.append(
            TrendDataPoint(
                label=row.date.strftime("%Y-%m-%d"),
                value=amount,
                timestamp=datetime.combine(row.date, datetime.min.time())
            )
        )
    
    # Calculate average and trend
    average = total / len(data_points) if data_points else 0.0
    trend = "stable"
    if len(data_points) >= 2:
        first_half_avg = sum(p.value for p in data_points[:len(data_points)//2]) / (len(data_points)//2)
        second_half_avg = sum(p.value for p in data_points[len(data_points)//2:]) / (len(data_points) - len(data_points)//2)
        if second_half_avg > first_half_avg * 1.1:
            trend = "up"
        elif second_half_avg < first_half_avg * 0.9:
            trend = "down"
    
    return TrendData(
        metric_name="daily_revenue",
        metric_label="Daily Platform Revenue",
        data_points=data_points,
        total=round(total, 2),
        average=round(average, 2),
        trend=trend
    )


# ==================== Alerts Service ====================

async def get_alerts_list(db: AsyncSession) -> AlertsListResponse:
    """
    Get formatted list of active alerts with summary.
    
    Args:
        db: Database session
    
    Returns:
        AlertsListResponse with alerts and severity breakdown
    """
    alerts = await crud.get_active_alerts(db)
    summary = await crud.get_alerts_summary(db)
    
    return AlertsListResponse(
        alerts=[alert for alert in alerts],
        total=len(alerts),
        by_severity={
            "critical": summary.get("critical", 0),
            "high": summary.get("high", 0),
            "medium": summary.get("medium", 0),
            "low": summary.get("low", 0)
        }
    )


async def resolve_alert_with_notes(
    db: AsyncSession,
    alert_id: UUID,
    resolved_by: UUID,
    resolution_notes: str = None
) -> Dict[str, Any]:
    """
    Resolve an alert and return formatted response.
    
    Args:
        db: Database session
        alert_id: Alert UUID
        resolved_by: Admin user UUID
        resolution_notes: Optional resolution notes
    
    Returns:
        Dict with alert_id, status, resolved_at, resolved_by, message
    
    Raises:
        ValueError: If alert not found
    """
    alert = await crud.resolve_alert(db, alert_id, resolved_by, resolution_notes)
    
    if not alert:
        raise ValueError(f"Alert {alert_id} not found")
    
    return {
        "alert_id": alert.id,
        "status": alert.status.value,
        "resolved_at": alert.resolved_at,
        "resolved_by": alert.resolved_by,
        "message": "Alert resolved successfully"
    }


# ==================== Logs Service ====================

async def get_logs_with_pagination(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    module: str = None,
    level: LogLevel = None
) -> LogsListResponse:
    """
    Get formatted logs list with pagination.
    
    Args:
        db: Database session
        limit: Page size
        offset: Offset for pagination
        module: Optional module filter
        level: Optional log level filter
    
    Returns:
        LogsListResponse with logs and pagination metadata
    """
    logs, total = await crud.get_recent_logs(
        db,
        limit=limit,
        offset=offset,
        module=module,
        level=level
    )
    
    return LogsListResponse(
        logs=[log for log in logs],
        total=total,
        limit=limit,
        offset=offset
    )
