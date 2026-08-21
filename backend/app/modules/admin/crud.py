"""
Module: Admin Analytics & Monitoring
Purpose: CRUD operations for admin dashboard (read-only, data populated by background tasks).
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: All functions are async and read-only. SystemStats populated by background scheduler.
"""

from sqlalchemy import select, func, desc, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from uuid import UUID

from app.modules.admin.models import SystemStats, LogEntry, Alert, AlertStatus, LogLevel


# ==================== System Stats CRUD ====================

async def get_system_stats(
    db: AsyncSession,
    category: Optional[str] = None
) -> List[SystemStats]:
    """
    Fetch all or filtered system statistics.
    
    Args:
        db: Database session
        category: Optional category filter (users, rides, payments, etc.)
    
    Returns:
        List of SystemStats records
    
    Example:
        >>> stats = await get_system_stats(db, category="users")
        >>> for stat in stats:
        >>>     print(f"{stat.metric_label}: {stat.metric_value}")
    """
    query = select(SystemStats).order_by(SystemStats.category, SystemStats.metric_name)
    
    if category:
        query = query.where(SystemStats.category == category)
    
    result = await db.execute(query)
    return result.scalars().all()


async def get_system_stat_by_name(
    db: AsyncSession,
    metric_name: str
) -> Optional[SystemStats]:
    """
    Fetch a single system statistic by metric name.
    
    Args:
        db: Database session
        metric_name: Unique metric identifier (e.g., 'total_users')
    
    Returns:
        SystemStats record or None if not found
    
    Example:
        >>> stat = await get_system_stat_by_name(db, "total_users")
        >>> if stat:
        >>>     print(f"Total users: {stat.metric_value}")
    """
    query = select(SystemStats).where(SystemStats.metric_name == metric_name)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_latest_stats(
    db: AsyncSession,
    limit: int = 10
) -> List[SystemStats]:
    """
    Fetch most recently computed statistics.
    
    Args:
        db: Database session
        limit: Maximum number of stats to return
    
    Returns:
        List of most recent SystemStats records
    """
    query = (
        select(SystemStats)
        .order_by(desc(SystemStats.computed_at))
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


# ==================== Log Entry CRUD ====================

async def get_recent_logs(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    module: Optional[str] = None,
    level: Optional[LogLevel] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> tuple[List[LogEntry], int]:
    """
    Fetch recent log entries with optional filters and pagination.
    
    Args:
        db: Database session
        limit: Page size (max 200)
        offset: Offset for pagination
        module: Filter by module (e.g., 'rides', 'payments')
        level: Filter by log level (e.g., LogLevel.ERROR)
        start_time: Start of time range
        end_time: End of time range
    
    Returns:
        Tuple of (log entries, total count)
    
    Example:
        >>> logs, total = await get_recent_logs(
        >>>     db, limit=50, module="payments", level=LogLevel.ERROR
        >>> )
        >>> print(f"Found {total} error logs in payments module")
    """
    # Enforce max limit
    limit = min(limit, 200)
    
    # Build query with filters
    query = select(LogEntry).order_by(desc(LogEntry.timestamp))
    count_query = select(func.count(LogEntry.id))
    
    filters = []
    if module:
        filters.append(LogEntry.module == module)
    if level:
        filters.append(LogEntry.level == level)
    if start_time:
        filters.append(LogEntry.timestamp >= start_time)
    if end_time:
        filters.append(LogEntry.timestamp <= end_time)
    
    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))
    
    # Get total count
    count_result = await db.execute(count_query)
    total = count_result.scalar()
    
    # Get paginated logs
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    logs = result.scalars().all()
    
    return logs, total


async def get_error_logs_count(
    db: AsyncSession,
    module: Optional[str] = None,
    hours: int = 24
) -> int:
    """
    Count error logs in the last N hours.
    
    Args:
        db: Database session
        module: Optional module filter
        hours: Time window in hours
    
    Returns:
        Count of error logs
    """
    time_threshold = datetime.utcnow() - timedelta(hours=hours)
    query = select(func.count(LogEntry.id)).where(
        and_(
            LogEntry.level.in_([LogLevel.ERROR, LogLevel.CRITICAL]),
            LogEntry.timestamp >= time_threshold
        )
    )
    
    if module:
        query = query.where(LogEntry.module == module)
    
    result = await db.execute(query)
    return result.scalar()


# ==================== Alert CRUD ====================

async def get_active_alerts(
    db: AsyncSession,
    severity: Optional[str] = None
) -> List[Alert]:
    """
    Fetch all active system alerts.
    
    Args:
        db: Database session
        severity: Optional severity filter (low, medium, high, critical)
    
    Returns:
        List of active Alert records
    
    Example:
        >>> alerts = await get_active_alerts(db, severity="high")
        >>> print(f"Found {len(alerts)} high-severity alerts")
    """
    query = (
        select(Alert)
        .where(Alert.status == AlertStatus.ACTIVE)
        .order_by(desc(Alert.severity), desc(Alert.created_at))
    )
    
    if severity:
        query = query.where(Alert.severity == severity)
    
    result = await db.execute(query)
    return result.scalars().all()


async def get_alert_by_id(
    db: AsyncSession,
    alert_id: UUID
) -> Optional[Alert]:
    """
    Fetch a single alert by ID.
    
    Args:
        db: Database session
        alert_id: Alert UUID
    
    Returns:
        Alert record or None if not found
    """
    query = select(Alert).where(Alert.id == alert_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_alerts_summary(db: AsyncSession) -> Dict[str, int]:
    """
    Get count of alerts grouped by status and severity.
    
    Args:
        db: Database session
    
    Returns:
        Dictionary with counts by status and severity
    
    Example:
        >>> summary = await get_alerts_summary(db)
        >>> print(f"Active critical alerts: {summary.get('critical', 0)}")
    """
    # Count by severity (active only)
    query = (
        select(
            Alert.severity,
            func.count(Alert.id).label("count")
        )
        .where(Alert.status == AlertStatus.ACTIVE)
        .group_by(Alert.severity)
    )
    result = await db.execute(query)
    rows = result.all()
    
    summary = {
        "total_active": sum(row.count for row in rows),
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0
    }
    
    for row in rows:
        summary[row.severity.value] = row.count
    
    return summary


async def resolve_alert(
    db: AsyncSession,
    alert_id: UUID,
    resolved_by: UUID,
    resolution_notes: Optional[str] = None
) -> Optional[Alert]:
    """
    Mark an alert as resolved.
    
    Args:
        db: Database session
        alert_id: Alert UUID
        resolved_by: Admin user UUID
        resolution_notes: Optional notes about resolution
    
    Returns:
        Updated Alert record or None if not found
    
    Example:
        >>> alert = await resolve_alert(
        >>>     db, alert_id=alert_id, resolved_by=admin_id,
        >>>     resolution_notes="Increased pool size to 30"
        >>> )
        >>> if alert:
        >>>     print(f"Alert resolved at {alert.resolved_at}")
    """
    alert = await get_alert_by_id(db, alert_id)
    
    if not alert:
        return None
    
    alert.status = AlertStatus.RESOLVED
    alert.resolved_at = datetime.utcnow()
    alert.resolved_by = resolved_by
    
    if resolution_notes:
        if not alert.metadata:
            alert.metadata = {}
        alert.metadata["resolution_notes"] = resolution_notes
    
    await db.commit()
    await db.refresh(alert)
    
    return alert


async def acknowledge_alert(
    db: AsyncSession,
    alert_id: UUID,
    acknowledged_by: UUID
) -> Optional[Alert]:
    """
    Mark an alert as acknowledged (admin has seen it).
    
    Args:
        db: Database session
        alert_id: Alert UUID
        acknowledged_by: Admin user UUID
    
    Returns:
        Updated Alert record or None if not found
    """
    alert = await get_alert_by_id(db, alert_id)
    
    if not alert:
        return None
    
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_at = datetime.utcnow()
    
    if not alert.metadata:
        alert.metadata = {}
    alert.metadata["acknowledged_by"] = str(acknowledged_by)
    
    await db.commit()
    await db.refresh(alert)
    
    return alert
