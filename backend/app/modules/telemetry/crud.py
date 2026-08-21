"""
Telemetry CRUD Operations

Database operations for telemetry points.
"""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry_point import TelemetryPoint

logger = logging.getLogger(__name__)


async def insert_telemetry_point(
    db: AsyncSession,
    ride_id: UUID,
    timestamp: datetime,
    latitude: float,
    longitude: float,
    speed: float,
    bearing: Optional[float] = None,
) -> TelemetryPoint:
    """
    Insert single telemetry point.
    
    Args:
        db: Database session
        ride_id: Ride UUID
        timestamp: Measurement timestamp
        latitude: Latitude (-90 to 90)
        longitude: Longitude (-180 to 180)
        speed: Speed in km/h
        bearing: Bearing in degrees (0-360)
        
    Returns:
        Created TelemetryPoint instance
    """
    point = TelemetryPoint(
        ride_id=ride_id,
        timestamp=timestamp,
        latitude=latitude,
        longitude=longitude,
        speed=speed,
        bearing=bearing,
    )
    
    db.add(point)
    await db.commit()
    await db.refresh(point)
    
    logger.debug(f"Inserted telemetry point for ride {ride_id} at {timestamp}")
    return point


async def bulk_insert_telemetry_points(
    db: AsyncSession,
    ride_id: UUID,
    points: List[dict]
) -> int:
    """
    Bulk insert telemetry points for performance.
    
    Args:
        db: Database session
        ride_id: Ride UUID
        points: List of point dictionaries with timestamp, lat, lng, speed, etc.
        
    Returns:
        Number of inserted points
    """
    telemetry_objects = [
        TelemetryPoint(
            ride_id=ride_id,
            timestamp=point['timestamp'],
            latitude=point['lat'],
            longitude=point['lng'],
            speed=point['speed'],
            bearing=point.get('bearing'),
        )
        for point in points
    ]
    
    db.add_all(telemetry_objects)
    await db.commit()
    
    logger.info(f"Bulk inserted {len(points)} telemetry points for ride {ride_id}")
    return len(points)


async def get_latest_points(
    db: AsyncSession,
    ride_id: UUID,
    limit: int = 25
) -> List[TelemetryPoint]:
    """
    Get latest telemetry points for a ride.
    
    Args:
        db: Database session
        ride_id: Ride UUID
        limit: Maximum number of points to return
        
    Returns:
        List of TelemetryPoint instances, ordered by timestamp desc
    """
    stmt = (
        select(TelemetryPoint)
        .where(TelemetryPoint.ride_id == ride_id)
        .order_by(desc(TelemetryPoint.timestamp))
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    points = result.scalars().all()
    
    return list(points)


async def get_all_points_for_ride(
    db: AsyncSession,
    ride_id: UUID
) -> List[TelemetryPoint]:
    """
    Get all telemetry points for a ride (for replay).
    
    Args:
        db: Database session
        ride_id: Ride UUID
        
    Returns:
        List of all TelemetryPoint instances, ordered by timestamp asc
    """
    stmt = (
        select(TelemetryPoint)
        .where(TelemetryPoint.ride_id == ride_id)
        .order_by(TelemetryPoint.timestamp)
    )
    
    result = await db.execute(stmt)
    points = result.scalars().all()
    
    return list(points)


async def get_points_in_time_range(
    db: AsyncSession,
    ride_id: UUID,
    start_time: datetime,
    end_time: datetime
) -> List[TelemetryPoint]:
    """
    Get telemetry points within a time range.
    
    Args:
        db: Database session
        ride_id: Ride UUID
        start_time: Start of time range
        end_time: End of time range
        
    Returns:
        List of TelemetryPoint instances in time range
    """
    stmt = (
        select(TelemetryPoint)
        .where(
            and_(
                TelemetryPoint.ride_id == ride_id,
                TelemetryPoint.timestamp >= start_time,
                TelemetryPoint.timestamp <= end_time
            )
        )
        .order_by(TelemetryPoint.timestamp)
    )
    
    result = await db.execute(stmt)
    points = result.scalars().all()
    
    return list(points)


async def get_telemetry_count(
    db: AsyncSession,
    ride_id: UUID
) -> int:
    """
    Get total count of telemetry points for a ride.
    
    Args:
        db: Database session
        ride_id: Ride UUID
        
    Returns:
        Count of telemetry points
    """
    from sqlalchemy import func
    
    stmt = (
        select(func.count(TelemetryPoint.id))
        .where(TelemetryPoint.ride_id == ride_id)
    )
    
    result = await db.execute(stmt)
    count = result.scalar()
    
    return count or 0
