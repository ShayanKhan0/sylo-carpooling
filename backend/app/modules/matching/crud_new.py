"""
CRUD Operations for Matching Engine

Fast spatial queries optimized for < 50ms prefilter performance.
Supports PostGIS (preferred) with fallback to bounding-box queries.

Performance:
- PostGIS ST_DWithin: < 20ms typical
- Bounding box fallback: < 50ms typical
- Returns minimal columns for fast serialization
"""

import logging
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ride import Ride
from app.modules.auth.models import User

logger = logging.getLogger(__name__)


# ============================================================================
# GEOSPATIAL UTILITIES
# ============================================================================

def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate great-circle distance between two points using Haversine formula.
    
    Args:
        lat1, lng1: First point coordinates
        lat2, lng2: Second point coordinates
        
    Returns:
        Distance in kilometers
        
    Example:
        >>> haversine_distance(31.4697, 74.2728, 31.5204, 74.3587)
        9.234  # km
    """
    R = 6371.0  # Earth radius in kilometers

    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)

    a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlng / 2) ** 2
    c = 2 * asin(sqrt(a))

    return R * c


def bounding_box(lat: float, lng: float, radius_km: float) -> Tuple[float, float, float, float]:
    """
    Calculate bounding box for a circle of given radius.
    
    Args:
        lat, lng: Center point
        radius_km: Radius in kilometers
        
    Returns:
        (lat_min, lat_max, lng_min, lng_max)
        
    Note:
        Approximation valid for small radius (<< Earth radius).
        For radius > 100km, consider more accurate methods.
    """
    # 1 degree of latitude ≈ 111 km
    lat_delta = radius_km / 111.0
    # Longitude delta depends on latitude
    lng_delta = radius_km / (111.0 * cos(radians(lat)))

    return (
        lat - lat_delta,
        lat + lat_delta,
        lng - lng_delta,
        lng + lng_delta
    )


async def check_postgis_available(db: AsyncSession) -> bool:
    """
    Check if PostGIS extension is available.
    
    Returns:
        True if PostGIS functions are available
    """
    try:
        result = await db.execute(text("SELECT PostGIS_Version();"))
        version = result.scalar()
        if version:
            logger.info(f"✅ PostGIS available: {version}")
            return True
    except Exception as e:
        logger.debug(f"PostGIS not available: {e}")
    return False


# ============================================================================
# SPATIAL PREFILTER QUERIES
# ============================================================================

async def find_nearby_drivers_postgis(
    db: AsyncSession,
    lat: float,
    lng: float,
    radius_km: float,
    min_seats: int = 1,
    time_window_start: Optional[datetime] = None,
    time_window_end: Optional[datetime] = None,
) -> List[dict]:
    """
    Find drivers near a point using PostGIS ST_DWithin.
    
    Fast path: Uses spatial index (GIST) for sub-20ms queries.
    
    Args:
        db: Database session
        lat, lng: Search center point
        radius_km: Search radius
        min_seats: Minimum available seats
        time_window_start: Optional start time filter
        time_window_end: Optional end time filter
        
    Returns:
        List of driver records with minimal columns:
        - driver_id, ride_id
        - driver_lat, driver_lng
        - driver_rating
        - seats_available
        - start_time
        - polyline_main
    """
    # Convert km to meters for PostGIS
    radius_m = radius_km * 1000

    # Build query with PostGIS ST_DWithin
    query = select(
        Ride.driver_id,
        Ride.id.label("ride_id"),
        Ride.start_point_lat.label("driver_lat"),
        Ride.start_point_lng.label("driver_lng"),
        Ride.seats_offered,
        Ride.seats_booked,
        Ride.buffer_seats,
        Ride.start_time,
        Ride.base_price,
        Ride.polyline_main,
        User.average_rating.label("driver_rating"),
    ).join(
        User, User.id == Ride.driver_id
    ).where(
        and_(
            Ride.status == "upcoming",  # Only active rides
            func.ST_DWithin(
                func.ST_SetSRID(
                    func.ST_MakePoint(Ride.start_point_lng, Ride.start_point_lat),
                    4326
                ),
                func.ST_SetSRID(
                    func.ST_MakePoint(lng, lat),
                    4326
                ),
                radius_m
            )
        )
    )

    # Apply time window filter
    if time_window_start:
        query = query.where(Ride.start_time >= time_window_start)
    if time_window_end:
        query = query.where(Ride.start_time <= time_window_end)

    result = await db.execute(query)
    rows = result.fetchall()

    # Filter by seats and format
    candidates = []
    for row in rows:
        seats_available = row.seats_offered - row.seats_booked - row.buffer_seats
        if seats_available >= min_seats:
            candidates.append({
                "driver_id": row.driver_id,
                "ride_id": row.ride_id,
                "driver_lat": row.driver_lat,
                "driver_lng": row.driver_lng,
                "driver_rating": float(row.driver_rating) if row.driver_rating else 0.0,
                "seats_available": seats_available,
                "start_time": row.start_time,
                "base_price": float(row.base_price) if row.base_price else 0.0,
                "polyline_main": row.polyline_main,
            })

    logger.info(f"PostGIS prefilter: {len(candidates)} candidates within {radius_km}km")
    return candidates


async def find_nearby_drivers_bbox(
    db: AsyncSession,
    lat: float,
    lng: float,
    radius_km: float,
    min_seats: int = 1,
    time_window_start: Optional[datetime] = None,
    time_window_end: Optional[datetime] = None,
) -> List[dict]:
    """
    Find drivers using bounding box + Haversine filter (fallback).
    
    Performance: < 50ms typical for < 1000 rides in bbox.
    
    Args:
        Same as find_nearby_drivers_postgis
        
    Returns:
        Same format as PostGIS version
    """
    # Calculate bounding box
    lat_min, lat_max, lng_min, lng_max = bounding_box(lat, lng, radius_km)

    # Query with bounding box (uses btree index on lat/lng)
    query = select(
        Ride.driver_id,
        Ride.id.label("ride_id"),
        Ride.start_point_lat.label("driver_lat"),
        Ride.start_point_lng.label("driver_lng"),
        Ride.seats_offered,
        Ride.seats_booked,
        Ride.buffer_seats,
        Ride.start_time,
        Ride.base_price,
        Ride.polyline_main,
        User.average_rating.label("driver_rating"),
    ).join(
        User, User.id == Ride.driver_id
    ).where(
        and_(
            Ride.status == "upcoming",
            Ride.start_point_lat.between(lat_min, lat_max),
            Ride.start_point_lng.between(lng_min, lng_max),
        )
    )

    # Apply time window
    if time_window_start:
        query = query.where(Ride.start_time >= time_window_start)
    if time_window_end:
        query = query.where(Ride.start_time <= time_window_end)

    result = await db.execute(query)
    rows = result.fetchall()

    # Filter by Haversine distance and seats
    candidates = []
    for row in rows:
        # Calculate exact distance
        distance = haversine_distance(lat, lng, row.driver_lat, row.driver_lng)
        if distance > radius_km:
            continue

        seats_available = row.seats_offered - row.seats_booked - row.buffer_seats
        if seats_available < min_seats:
            continue

        candidates.append({
            "driver_id": row.driver_id,
            "ride_id": row.ride_id,
            "driver_lat": row.driver_lat,
            "driver_lng": row.driver_lng,
            "driver_rating": float(row.driver_rating) if row.driver_rating else 0.0,
            "seats_available": seats_available,
            "start_time": row.start_time,
            "base_price": float(row.base_price) if row.base_price else 0.0,
            "polyline_main": row.polyline_main,
            "distance_km": distance,
        })

    logger.info(f"Bounding box prefilter: {len(candidates)} candidates within {radius_km}km")
    return candidates


async def find_nearby_drivers(
    db: AsyncSession,
    lat: float,
    lng: float,
    radius_km: float,
    min_seats: int = 1,
    time_window_start: Optional[datetime] = None,
    time_window_end: Optional[datetime] = None,
    prefer_postgis: bool = True,
) -> List[dict]:
    """
    Find nearby drivers with automatic PostGIS/fallback selection.
    
    Performance target: < 50ms for typical queries
    
    Args:
        db: Database session
        lat, lng: Search center
        radius_km: Search radius (capped at 50km for performance)
        min_seats: Minimum available seats
        time_window_start: Optional time filter
        time_window_end: Optional time filter
        prefer_postgis: Try PostGIS first if available
        
    Returns:
        List of driver candidate dicts
    """
    # Cap radius for performance
    radius_km = min(radius_km, 50.0)

    # Try PostGIS if preferred
    if prefer_postgis:
        try:
            has_postgis = await check_postgis_available(db)
            if has_postgis:
                return await find_nearby_drivers_postgis(
                    db, lat, lng, radius_km, min_seats,
                    time_window_start, time_window_end
                )
        except Exception as e:
            logger.warning(f"PostGIS query failed, falling back to bbox: {e}")

    # Fallback to bounding box
    return await find_nearby_drivers_bbox(
        db, lat, lng, radius_km, min_seats,
        time_window_start, time_window_end
    )


# ============================================================================
# HELPER QUERIES
# ============================================================================

async def get_active_drivers_count(db: AsyncSession) -> int:
    """Get count of drivers with upcoming rides"""
    result = await db.execute(
        select(func.count(func.distinct(Ride.driver_id)))
        .where(Ride.status == "upcoming")
    )
    return result.scalar() or 0


async def get_driver_locations(
    db: AsyncSession,
    driver_ids: List[UUID]
) -> List[Tuple[UUID, float, float]]:
    """
    Get current locations for list of drivers.
    
    Returns:
        List of (driver_id, lat, lng) tuples
    """
    query = select(
        Ride.driver_id,
        Ride.start_point_lat,
        Ride.start_point_lng,
    ).where(
        and_(
            Ride.driver_id.in_(driver_ids),
            Ride.status == "upcoming"
        )
    ).distinct(Ride.driver_id)

    result = await db.execute(query)
    return [
        (row.driver_id, row.start_point_lat, row.start_point_lng)
        for row in result.fetchall()
    ]


async def get_all_active_driver_locations(
    db: AsyncSession,
    limit: int = 1000
) -> List[Tuple[float, float]]:
    """
    Get locations of all active drivers for clustering.
    
    Used by cluster_service for background cluster building.
    
    Args:
        db: Database session
        limit: Max drivers to return (for performance)
        
    Returns:
        List of (lat, lng) tuples
    """
    query = select(
        Ride.start_point_lat,
        Ride.start_point_lng,
    ).where(
        Ride.status == "upcoming"
    ).distinct(Ride.driver_id).limit(limit)

    result = await db.execute(query)
    return [
        (row.start_point_lat, row.start_point_lng)
        for row in result.fetchall()
    ]
