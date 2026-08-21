"""
Module: Admin Analytics & Monitoring
Purpose: Pydantic schemas for admin dashboard API requests and responses.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: All schemas include example payloads for Swagger documentation.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID

from app.modules.admin.models import LogLevel, AlertStatus, AlertSeverity


# ==================== System Stats Schemas ====================

class SystemStatsPublic(BaseModel):
    """
    Public representation of system statistics for admin dashboard.
    """
    id: UUID
    metric_name: str = Field(..., description="Unique metric identifier")
    metric_value: float = Field(..., description="Numeric value of the metric")
    metric_label: str = Field(..., description="Human-readable label")
    category: str = Field(..., description="Metric category (users, rides, payments, etc.)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context")
    computed_at: datetime = Field(..., description="Last computation timestamp")
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "metric_name": "total_users",
                "metric_value": 15420.0,
                "metric_label": "Total Registered Users",
                "category": "users",
                "metadata": {
                    "growth_rate": 5.2,
                    "trend": "up",
                    "prev_value": 14650.0
                },
                "computed_at": "2025-11-08T10:30:00Z",
                "created_at": "2025-11-01T00:00:00Z",
                "updated_at": "2025-11-08T10:30:00Z"
            }
        }
    )


class SystemStatsSummary(BaseModel):
    """
    Aggregated system statistics summary for dashboard overview.
    """
    total_users: int = Field(..., description="Total registered users")
    total_drivers: int = Field(..., description="Total verified drivers")
    active_rides: int = Field(..., description="Currently active rides")
    completed_rides_today: int = Field(..., description="Rides completed today")
    avg_driver_rating: float = Field(..., description="Average driver rating (0-5)")
    total_revenue: float = Field(..., description="Total platform revenue")
    pending_verifications: int = Field(..., description="Pending driver verifications")
    active_alerts: int = Field(..., description="Active system alerts")
    last_updated: datetime = Field(..., description="Last update timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
    )


class TrendDataPoint(BaseModel):
    """
    Single data point for trend charts.
    """
    label: str = Field(..., description="Label (date, hour, etc.)")
    value: float = Field(..., description="Metric value")
    timestamp: datetime = Field(..., description="Data point timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "label": "2025-11-08",
                "value": 234.0,
                "timestamp": "2025-11-08T00:00:00Z"
            }
        }
    )


class TrendData(BaseModel):
    """
    Trend data for time-series charts.
    """
    metric_name: str = Field(..., description="Metric identifier")
    metric_label: str = Field(..., description="Human-readable label")
    data_points: List[TrendDataPoint] = Field(..., description="Time-series data")
    total: float = Field(..., description="Total value across all data points")
    average: float = Field(..., description="Average value")
    trend: str = Field(..., description="Trend direction (up, down, stable)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "metric_name": "daily_bookings",
                "metric_label": "Daily Ride Bookings",
                "data_points": [
                    {"label": "2025-11-01", "value": 210.0, "timestamp": "2025-11-01T00:00:00Z"},
                    {"label": "2025-11-02", "value": 225.0, "timestamp": "2025-11-02T00:00:00Z"},
                    {"label": "2025-11-03", "value": 234.0, "timestamp": "2025-11-03T00:00:00Z"}
                ],
                "total": 669.0,
                "average": 223.0,
                "trend": "up"
            }
        }
    )


# ==================== Log Entry Schemas ====================

class LogEntryPublic(BaseModel):
    """
    Public representation of system log entries.
    """
    id: UUID
    module: str = Field(..., description="Source module")
    level: LogLevel = Field(..., description="Log severity level")
    message: str = Field(..., description="Log message")
    user_id: Optional[UUID] = Field(None, description="Related user ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context")
    timestamp: datetime = Field(..., description="Log timestamp")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "module": "payments",
                "level": "error",
                "message": "Payment gateway timeout after 30s",
                "user_id": "987e6543-e89b-12d3-a456-426614174999",
                "metadata": {
                    "payment_id": "pay_ABC123",
                    "gateway": "stripe",
                    "retry_count": 3,
                    "error_code": "GATEWAY_TIMEOUT"
                },
                "timestamp": "2025-11-08T10:25:00Z"
            }
        }
    )


class LogsListResponse(BaseModel):
    """
    Paginated list of log entries.
    """
    logs: List[LogEntryPublic] = Field(..., description="Log entries")
    total: int = Field(..., description="Total log count")
    limit: int = Field(..., description="Page size")
    offset: int = Field(..., description="Offset for pagination")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "logs": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "module": "rides",
                        "level": "info",
                        "message": "Ride completed successfully",
                        "metadata": {"ride_id": "ride_123"},
                        "timestamp": "2025-11-08T10:30:00Z"
                    }
                ],
                "total": 1250,
                "limit": 50,
                "offset": 0
            }
        }
    )


# ==================== Alert Schemas ====================

class AlertPublic(BaseModel):
    """
    Public representation of system alerts.
    """
    id: UUID
    title: str = Field(..., description="Alert title")
    description: str = Field(..., description="Detailed description")
    severity: AlertSeverity = Field(..., description="Alert severity")
    status: AlertStatus = Field(..., description="Current status")
    source_module: str = Field(..., description="Source module")
    source_id: Optional[UUID] = Field(None, description="Related entity ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context")
    acknowledged_at: Optional[datetime] = Field(None, description="Acknowledgment timestamp")
    resolved_at: Optional[datetime] = Field(None, description="Resolution timestamp")
    resolved_by: Optional[UUID] = Field(None, description="Admin who resolved")
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "title": "High Rate of Ride Cancellations",
                "description": "Detected 12 ride cancellations in the last hour, exceeding normal threshold of 5",
                "severity": "high",
                "status": "active",
                "source_module": "rides",
                "source_id": None,
                "metadata": {
                    "count": 12,
                    "threshold": 5,
                    "time_window": "1h",
                    "affected_drivers": ["driver_1", "driver_2"]
                },
                "acknowledged_at": None,
                "resolved_at": None,
                "resolved_by": None,
                "created_at": "2025-11-08T10:00:00Z",
                "updated_at": "2025-11-08T10:00:00Z"
            }
        }
    )


class AlertsListResponse(BaseModel):
    """
    List of active system alerts.
    """
    alerts: List[AlertPublic] = Field(..., description="Active alerts")
    total: int = Field(..., description="Total alert count")
    by_severity: Dict[str, int] = Field(..., description="Count by severity")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
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
    )


class AlertResolveRequest(BaseModel):
    """
    Request to resolve an alert.
    """
    resolution_notes: Optional[str] = Field(None, description="Notes about resolution")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resolution_notes": "Increased database connection pool size to 30. Monitoring for 24 hours."
            }
        }
    )


class AlertResolveResponse(BaseModel):
    """
    Response after resolving an alert.
    """
    alert_id: UUID
    status: str = Field(..., description="New status (resolved)")
    resolved_at: datetime
    resolved_by: UUID
    message: str = Field(..., description="Success message")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "alert_id": "123e4567-e89b-12d3-a456-426614174000",
                "status": "resolved",
                "resolved_at": "2025-11-08T10:30:00Z",
                "resolved_by": "admin_123",
                "message": "Alert resolved successfully"
            }
        }
    )
