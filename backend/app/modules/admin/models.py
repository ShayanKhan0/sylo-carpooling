"""
Module: Admin Analytics & Monitoring
Purpose: Database models for admin dashboard analytics, system logs, and alerts.
         Read-only analytics models populated by background tasks.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: These models store cached metrics and system health data for the admin dashboard.
       Data is populated by background schedulers and aggregation tasks.
"""

from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Boolean, Enum as SQLEnum, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid
import enum

from app.db.base import Base


class LogLevel(str, enum.Enum):
    """
    Log entry severity levels.
    """
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(str, enum.Enum):
    """
    Alert status enumeration.
    """
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class AlertSeverity(str, enum.Enum):
    """
    Alert severity levels for prioritization.
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SystemStats(Base):
    """
    Cached system statistics for admin dashboard.
    Updated periodically by background tasks (every 10 minutes).
    
    Attributes:
        id (UUID): Primary key
        metric_name (str): Name of the metric (e.g., "total_users", "active_rides")
        metric_value (float): Numeric value of the metric
        metric_label (str): Human-readable label for display
        category (str): Grouping category (users, rides, payments, safety)
        metadata (JSONB): Additional context (trends, timestamps, etc.)
        computed_at (datetime): When this metric was last computed
        created_at (datetime): First time this metric was recorded
        updated_at (datetime): Last update timestamp
    
    Example Metrics:
        - total_users: 15420
        - active_rides: 87
        - verified_drivers: 456
        - daily_bookings: 234
        - avg_driver_rating: 4.7
        - total_revenue: 125000.50
    
    Example:
        >>> stat = SystemStats(
        >>>     metric_name="total_users",
        >>>     metric_value=15420.0,
        >>>     metric_label="Total Registered Users",
        >>>     category="users",
        >>>     metadata={"growth_rate": 5.2, "trend": "up"}
        >>> )
    """
    __tablename__ = "system_stats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    metric_name = Column(String(100), unique=True, nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    metric_label = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False, index=True)
    meta_data = Column(JSONB, default={})
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Composite index for fast category queries
    __table_args__ = (
        Index("ix_system_stats_category_name", "category", "metric_name"),
    )

    def __repr__(self):
        return f"<SystemStats(metric={self.metric_name}, value={self.metric_value})>"


class LogEntry(Base):
    """
    Admin event logs for system monitoring and debugging.
    Captures important events from all modules.
    
    Attributes:
        id (UUID): Primary key
        module (str): Source module (auth, rides, payments, etc.)
        level (LogLevel): Severity level (debug, info, warning, error, critical)
        message (Text): Log message content
        user_id (UUID): Optional user ID related to this log
        metadata (JSONB): Additional context (request_id, stack_trace, etc.)
        timestamp (datetime): When this log was created
    
    Example:
        >>> log = LogEntry(
        >>>     module="payments",
        >>>     level=LogLevel.ERROR,
        >>>     message="Payment gateway timeout",
        >>>     metadata={"payment_id": "pay_123", "gateway": "stripe"}
        >>> )
    """
    __tablename__ = "log_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    module = Column(String(50), nullable=False, index=True)
    level = Column(
        SQLEnum(LogLevel, name="log_levels", create_type=True),
        default=LogLevel.INFO,
        nullable=False,
        index=True
    )
    message = Column(Text, nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    meta_data = Column(JSONB, default={})
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Composite indexes for efficient queries
    __table_args__ = (
        Index("ix_log_entries_module_level", "module", "level"),
        Index("ix_log_entries_level_timestamp", "level", "timestamp"),
    )

    def __repr__(self):
        return f"<LogEntry(module={self.module}, level={self.level}, timestamp={self.timestamp})>"


class Alert(Base):
    """
    System alerts for critical issues requiring admin attention.
    Generated by safety AI, matching engine, or other monitoring systems.
    
    Attributes:
        id (UUID): Primary key
        title (str): Short alert title
        description (Text): Detailed alert description
        severity (AlertSeverity): Alert severity (low, medium, high, critical)
        status (AlertStatus): Current status (active, acknowledged, resolved, dismissed)
        source_module (str): Module that generated this alert
        source_id (UUID): Optional ID of related entity (ride_id, user_id, etc.)
        metadata (JSONB): Additional context (error details, affected users, etc.)
        acknowledged_at (datetime): When alert was acknowledged
        resolved_at (datetime): When alert was resolved
        resolved_by (UUID): Admin user who resolved the alert
        created_at (datetime): Alert creation timestamp
        updated_at (datetime): Last update timestamp
    
    Example:
        >>> alert = Alert(
        >>>     title="High Rate of Ride Cancellations",
        >>>     description="10+ ride cancellations in the last hour",
        >>>     severity=AlertSeverity.HIGH,
        >>>     status=AlertStatus.ACTIVE,
        >>>     source_module="rides",
        >>>     metadata={"count": 12, "time_window": "1h"}
        >>> )
    """
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(
        SQLEnum(AlertSeverity, name="alert_severities", create_type=True),
        default=AlertSeverity.MEDIUM,
        nullable=False,
        index=True
    )
    status = Column(
        SQLEnum(AlertStatus, name="alert_statuses", create_type=True),
        default=AlertStatus.ACTIVE,
        nullable=False,
        index=True
    )
    source_module = Column(String(50), nullable=False, index=True)
    source_id = Column(UUID(as_uuid=True), nullable=True)
    meta_data = Column(JSONB, default={})
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Composite indexes for dashboard queries
    __table_args__ = (
        Index("ix_alerts_status_severity", "status", "severity"),
        Index("ix_alerts_status_created", "status", "created_at"),
    )

    def __repr__(self):
        return f"<Alert(title={self.title}, severity={self.severity}, status={self.status})>"

