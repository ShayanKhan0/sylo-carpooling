"""
Safety AI CRUD Operations

This module provides async database operations for telemetry data and incident reports.
Supports batch telemetry insertion, incident tracking, and statistics queries.

Author: Smart Carpooling Backend Team
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
import json
from sqlalchemy import select, func, and_, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.modules.safety_ai.models import TelemetryData, IncidentReport, IncidentTypeEnum, SeverityEnum
from app.models.ride import Ride

import logging

logger = logging.getLogger(__name__)


async def create_telemetry(
    db: AsyncSession,
    ride_id: UUID,
    driver_id: UUID,
    speed: float,
    acceleration: float,
    gps_lat: float,
    gps_lng: float,
    harsh_brake_detected: bool = False,
    device_info: Optional[str] = None
) -> TelemetryData:
    """
    Create a single telemetry data record.
    
    Args:
        db: Database session
        ride_id: Ride UUID
        driver_id: Driver UUID
        speed: Current speed in km/h
        acceleration: Current acceleration in m/s²
        gps_lat: GPS latitude
        gps_lng: GPS longitude
        harsh_brake_detected: Whether harsh braking detected
        device_info: Optional device information
    
    Returns:
        Created TelemetryData record
    """
    telemetry = TelemetryData(
        ride_id=ride_id,
        driver_id=driver_id,
        speed=speed,
        acceleration=acceleration,
        gps_lat=gps_lat,
        gps_lng=gps_lng,
        harsh_brake_detected=harsh_brake_detected,
        device_info=device_info
    )
    
    db.add(telemetry)
    await db.commit()
    await db.refresh(telemetry)
    
    logger.info(f"Telemetry created for ride {ride_id}")
    return telemetry


async def batch_insert_telemetry(
    db: AsyncSession,
    telemetry_list: List[Dict[str, Any]]
) -> int:
    """
    Batch insert multiple telemetry records for performance.
    
    Args:
        db: Database session
        telemetry_list: List of telemetry data dictionaries
    
    Returns:
        Number of records inserted
    """
    if not telemetry_list:
        return 0
    
    telemetry_objects = [
        TelemetryData(**data) for data in telemetry_list
    ]
    
    db.add_all(telemetry_objects)
    await db.commit()
    
    logger.info(f"Batch inserted {len(telemetry_objects)} telemetry records")
    return len(telemetry_objects)


async def get_ride_telemetry(
    db: AsyncSession,
    ride_id: UUID,
    limit: int = 100
) -> List[TelemetryData]:
    """
    Get telemetry data for a specific ride.
    
    Args:
        db: Database session
        ride_id: Ride UUID
        limit: Maximum number of records to return
    
    Returns:
        List of TelemetryData records ordered by timestamp descending
    """
    result = await db.execute(
        select(TelemetryData)
        .where(TelemetryData.ride_id == ride_id)
        .order_by(desc(TelemetryData.timestamp))
        .limit(limit)
    )
    
    return result.scalars().all()


async def get_telemetry_stats(
    db: AsyncSession,
    ride_id: UUID
) -> Dict[str, Any]:
    """
    Get aggregated telemetry statistics for a ride.
    
    Args:
        db: Database session
        ride_id: Ride UUID
    
    Returns:
        Dictionary with max_speed, avg_speed, harsh_brake_count
    """
    result = await db.execute(
        select(
            func.max(TelemetryData.speed).label("max_speed"),
            func.avg(TelemetryData.speed).label("avg_speed"),
            func.sum(func.cast(TelemetryData.harsh_brake_detected, db.bind.dialect.BIGINT if hasattr(db.bind.dialect, 'BIGINT') else int)).label("harsh_brake_count")
        )
        .where(TelemetryData.ride_id == ride_id)
    )
    
    row = result.one_or_none()
    
    if row:
        return {
            "max_speed": float(row.max_speed) if row.max_speed else 0.0,
            "avg_speed": float(row.avg_speed) if row.avg_speed else 0.0,
            "harsh_brake_count": int(row.harsh_brake_count) if row.harsh_brake_count else 0
        }
    
    return {"max_speed": 0.0, "avg_speed": 0.0, "harsh_brake_count": 0}


async def create_incident(
    db: AsyncSession,
    ride_id: UUID,
    driver_id: UUID,
    incident_type: IncidentTypeEnum,
    severity: SeverityEnum,
    ai_score: float,
    description: str,
    gps_lat: float,
    gps_lng: float,
    metadata: Optional[Dict[str, Any]] = None
) -> IncidentReport:
    """
    Create a new incident report.
    
    Args:
        db: Database session
        ride_id: Ride UUID
        driver_id: Driver UUID
        incident_type: Type of incident
        severity: Severity level
        ai_score: AI anomaly score (0-1)
        description: Incident description
        gps_lat: GPS latitude
        gps_lng: GPS longitude
        metadata: Optional additional metadata
    
    Returns:
        Created IncidentReport record
    """
    incident = IncidentReport(
        ride_id=ride_id,
        driver_id=driver_id,
        type=incident_type,
        severity=severity,
        ai_score=ai_score,
        description=description,
        location_lat=gps_lat,
        location_lng=gps_lng,
        meta_data=json.dumps(metadata or {}),
    )
    
    db.add(incident)
    await db.commit()
    await db.refresh(incident)
    
    logger.warning(f"Incident created: {incident_type.value} for ride {ride_id} with severity {severity.value}")
    return incident


async def get_ride_incidents(
    db: AsyncSession,
    ride_id: UUID
) -> List[IncidentReport]:
    """
    Get all incidents for a specific ride.
    
    Args:
        db: Database session
        ride_id: Ride UUID
    
    Returns:
        List of IncidentReport records ordered by detected_at descending
    """
    result = await db.execute(
        select(IncidentReport)
        .where(IncidentReport.ride_id == ride_id)
        .order_by(desc(IncidentReport.detected_at))
    )
    
    return result.scalars().all()


async def get_driver_incidents(
    db: AsyncSession,
    driver_id: UUID,
    days: int = 30,
    severity: Optional[SeverityEnum] = None
) -> List[IncidentReport]:
    """
    Get incidents for a driver within a time period.
    
    Args:
        db: Database session
        driver_id: Driver UUID
        days: Number of days to look back (default 30)
        severity: Optional filter by severity level
    
    Returns:
        List of IncidentReport records
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    query = select(IncidentReport).where(
        and_(
            IncidentReport.driver_id == driver_id,
            IncidentReport.detected_at >= cutoff
        )
    )
    
    if severity:
        query = query.where(IncidentReport.severity == severity)
    
    query = query.order_by(desc(IncidentReport.detected_at))
    
    result = await db.execute(query)
    return result.scalars().all()


async def update_incident_status(
    db: AsyncSession,
    incident_id: UUID,
    resolved: bool
) -> IncidentReport:
    """
    Update incident resolution status.
    
    Args:
        db: Database session
        incident_id: Incident UUID
        resolved: Whether incident is resolved
    
    Returns:
        Updated IncidentReport
    
    Raises:
        HTTPException: If incident not found
    """
    result = await db.execute(
        select(IncidentReport).where(IncidentReport.id == incident_id)
    )
    
    incident = result.scalar_one_or_none()
    
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found"
        )
    
    incident.resolved_at = datetime.utcnow() if resolved else None
    incident.reviewed = bool(resolved)
    await db.commit()
    await db.refresh(incident)
    
    logger.info(f"Incident {incident_id} marked as {'resolved' if resolved else 'unresolved'}")
    return incident


async def get_unresolved_incidents(
    db: AsyncSession,
    severity: Optional[SeverityEnum] = None,
    limit: int = 50
) -> List[IncidentReport]:
    """
    Get unresolved incidents, optionally filtered by severity.
    
    Args:
        db: Database session
        severity: Optional filter by severity level
        limit: Maximum number of records to return
    
    Returns:
        List of unresolved IncidentReport records
    """
    query = select(IncidentReport).where(IncidentReport.resolved_at.is_(None))
    
    if severity:
        query = query.where(IncidentReport.severity == severity)
    
    query = query.order_by(desc(IncidentReport.detected_at)).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()


async def get_incident_stats(
    db: AsyncSession,
    driver_id: Optional[UUID] = None,
    days: int = 30
) -> Dict[str, Any]:
    """
    Get aggregated incident statistics.
    
    Args:
        db: Database session
        driver_id: Optional filter by driver
        days: Number of days to look back
    
    Returns:
        Dictionary with incident counts by type and severity
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    query = select(IncidentReport).where(IncidentReport.detected_at >= cutoff)
    
    if driver_id:
        query = query.where(IncidentReport.driver_id == driver_id)
    
    result = await db.execute(query)
    incidents = result.scalars().all()
    
    # Aggregate by type and severity
    type_counts = {}
    severity_counts = {}
    
    for incident in incidents:
        # Count by type
        type_key = incident.type.value if hasattr(incident.type, "value") else str(incident.type)
        type_counts[type_key] = type_counts.get(type_key, 0) + 1
        
        # Count by severity
        severity_key = incident.severity.value
        severity_counts[severity_key] = severity_counts.get(severity_key, 0) + 1
    
    return {
        "total_incidents": len(incidents),
        "by_type": type_counts,
        "by_severity": severity_counts,
        "period_days": days
    }


async def create_unlinked_sos_incident(
    db: AsyncSession,
    *,
    user_id: UUID,
    full_name: str,
    email: str,
    phone: Optional[str],
    role: str,
    gps_lat: Optional[float],
    gps_lng: Optional[float],
    message: Optional[str],
) -> UUID:
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS unlinked_sos_incidents (
                id UUID PRIMARY KEY,
                user_id UUID NOT NULL,
                full_name VARCHAR(120) NOT NULL,
                email VARCHAR(255) NOT NULL,
                phone VARCHAR(30),
                role VARCHAR(40) NOT NULL,
                gps_lat NUMERIC(10,7),
                gps_lng NUMERIC(10,7),
                message TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                resolved_at TIMESTAMP WITH TIME ZONE NULL,
                reviewed BOOLEAN NOT NULL DEFAULT FALSE,
                meta_data TEXT NULL
            )
            """
        )
    )

    # Generate UUID in Python to avoid DB extension assumptions.
    import uuid as _uuid
    incident_id = _uuid.uuid4()

    payload = {
        "source": "sos_without_ride",
        "created_at": datetime.utcnow().isoformat(),
    }
    await db.execute(
        text(
            """
            INSERT INTO unlinked_sos_incidents (
                id, user_id, full_name, email, phone, role, gps_lat, gps_lng, message, meta_data
            ) VALUES (
                :id, :user_id, :full_name, :email, :phone, :role, :gps_lat, :gps_lng, :message, :meta_data
            )
            """
        ),
        {
            "id": incident_id,
            "user_id": user_id,
            "full_name": full_name,
            "email": email,
            "phone": phone,
            "role": role,
            "gps_lat": gps_lat,
            "gps_lng": gps_lng,
            "message": message,
            "meta_data": json.dumps(payload),
        },
    )
    await db.commit()
    return incident_id
