"""
Module: Rides - CRUD Operations
Purpose: Async database operations for ride creation, booking, and management.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: All operations use async SQLAlchemy with comprehensive error handling and seat management logic.
       Column names aligned with actual PostgreSQL 'rides' table schema.
       Supports geo-proximity search via Haversine formula.
"""

import math
import logging
from uuid import UUID
from typing import Optional, List, Tuple
from datetime import datetime, timezone
from sqlalchemy import select, and_, or_, func, literal_column, case, cast, Float, String, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.models.ride import Ride
from app.models.booking import Booking
from app.models.enums import RideStatus
from app.modules.rides.models import RideBooking, BookingStatusEnum
from app.modules.rides.schemas import RideCreate, RideUpdate, RideBookingCreate
from app.modules.rides.schema_compat import ACTIVE_BOOKING_STATUSES

logger = logging.getLogger(__name__)

# Earth radius in kilometers (for Haversine formula)
EARTH_RADIUS_KM = 6371.0
ACTIVE_RIDE_FILTER_STATUSES = ("open", "scheduled", "in_progress", "ongoing")
ACTIVE_BOOKING_FILTER_STATUSES = ("booked", "reserved", "confirmed")
ROUTE_PICKUP_DEVIATION_KM = 1.0
LEGACY_MAIN_PROXIMITY_KM = 5.0
LEGACY_ROUTE_DEVIATION_KM = 1.0
DYNAMIC_MAIN_PERCENT = 0.20
DYNAMIC_CORRIDOR_PERCENT = 0.05
DYNAMIC_MAIN_MIN_KM = 0.2
DYNAMIC_MAIN_MAX_KM = 5.0
DYNAMIC_CORRIDOR_MIN_KM = 0.2
DYNAMIC_CORRIDOR_MAX_KM = 3.0


def _normalized_status_values(status_filter: str) -> tuple[str, ...]:
    """Return compatible status values for mixed legacy/canonical enums."""
    raw = (status_filter or "").strip().lower()
    if not raw:
        return tuple()

    if raw == "active":
        return ("open", "scheduled", "in_progress", "ongoing")

    if raw == "scheduled":
        return ("open", "scheduled")

    if raw == "history":
        return ("completed", "cancelled")

    alias_to_canonical = {
        "scheduled": "open",
        "ongoing": "in_progress",
        "inprogress": "in_progress",
        "in-progress": "in_progress",
    }
    canonical = alias_to_canonical.get(raw, raw)

    values = {canonical}
    if canonical == "open":
        values.add("scheduled")
    elif canonical == "in_progress":
        values.add("ongoing")

    return tuple(values)


def _normalized_booking_status_values(status_filter: str) -> tuple[str, ...]:
    """Return compatible booking status values for mixed legacy/current states."""
    raw = (status_filter or "").strip().lower()
    if not raw:
        return tuple()

    if raw in {"active", "booked", "reserved", "confirmed"}:
        return ("booked", "reserved", "confirmed")

    if raw == "scheduled":
        return ("booked", "reserved", "confirmed")

    if raw in {"cancelled", "canceled"}:
        return ("cancelled",)

    if raw == "history":
        return ("completed", "cancelled")

    if raw == "completed":
        return ("completed",)

    return (raw,)


# ============================================
# RIDE CRUD OPERATIONS
# ============================================

async def create_ride(
    db: AsyncSession,
    driver_id: UUID,
    ride_data: RideCreate
) -> Ride:
    """
    Create a new ride offer by a driver.
    Maps schema fields to actual DB column names.
    """
    try:
        new_ride = Ride(
            driver_id=driver_id,
            vehicle_id=ride_data.vehicle_id,
            # Map coordinates to DB columns
            start_point_lat=ride_data.origin_lat,
            start_point_lng=ride_data.origin_lng,
            start_point_address=ride_data.origin,
            end_point_lat=ride_data.destination_lat,
            end_point_lng=ride_data.destination_lng,
            end_point_address=ride_data.destination,
            # Schedule & pricing (column names match DB)
            departure_time=ride_data.departure_time,
            seats_available=ride_data.available_seats,
            price_per_seat=ride_data.price_per_seat,
            # Route metadata
            estimated_duration_minutes=ride_data.estimated_duration,
            route_distance_km=ride_data.route_distance_km,
            polyline=ride_data.polyline,
            # Status: 'open' matches DB default
            status=RideStatus.OPEN,
        )
        
        db.add(new_ride)
        await db.commit()
        await db.refresh(new_ride)
        
        logger.info(f"Created ride: driver_id={driver_id}, ride_id={new_ride.id}, origin={ride_data.origin}")
        return new_ride
        
    except IntegrityError as e:
        await db.rollback()
        detail_text = str(getattr(e, "orig", e)).lower()
        if "trg_enforce_ride_time_overlap" in detail_text or "ride time overlaps" in detail_text:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This ride time overlaps with an existing active ride for the driver",
            )
        logger.error(f"Integrity error creating ride for driver_id={driver_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ride could not be created due to a conflicting database constraint",
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating ride for driver_id={driver_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ride"
        )


async def get_ride_by_id(db: AsyncSession, ride_id: UUID) -> Optional[Ride]:
    """
    Retrieve ride by ID with bookings loaded.
    
    Args:
        db: Async database session
        ride_id: UUID of the ride
    
    Returns:
        Ride instance with bookings, or None if not found
    
    Notes:
        - Uses selectinload for efficient booking fetching
    """
    try:
        result = await db.execute(
            select(Ride)
            .options(selectinload(Ride.bookings))
            .where(Ride.id == ride_id)
        )
        return result.scalar_one_or_none()
        
    except Exception as e:
        logger.error(f"Error fetching ride by ride_id={ride_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve ride"
        )


async def list_available_rides(
    db: AsyncSession,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    origin_lat: Optional[float] = None,
    origin_lng: Optional[float] = None,
    destination_lat: Optional[float] = None,
    destination_lng: Optional[float] = None,
    radius_km: float = 5.0,
    min_seats: Optional[int] = None,
    driver_total_seats: Optional[int] = None,
    max_price: Optional[float] = None,
    departure_after: Optional[datetime] = None,
    departure_before: Optional[datetime] = None,
    include_recurring: bool = False,
) -> List[Ride]:
    """
    List all available rides with optional filters.
    Supports both text-based and geo-proximity search.
    
    Geo-proximity uses the Haversine formula implemented in Python
    (since PostGIS is not available). Rides within `radius_km` of
    the specified origin/destination coordinates are returned.
    """
    try:
        # Reconstruct original offered seats for exact total-seats filtering.
        # Primary path uses ride_bookings; legacy path uses bookings.
        active_booked_seats_expr = (
            select(func.coalesce(func.sum(RideBooking.booked_seats), 0))
            .where(
                and_(
                    RideBooking.ride_id == Ride.id,
                    func.lower(cast(RideBooking.status, String)).in_(
                        tuple(ACTIVE_BOOKING_STATUSES)
                    ),
                )
            )
            .correlate(Ride)
            .scalar_subquery()
        )
        legacy_active_booked_seats_expr = (
            select(func.coalesce(func.sum(Booking.seats_reserved), 0))
            .where(
                and_(
                    Booking.ride_id == Ride.id,
                    func.lower(cast(Booking.status, String)).in_(
                        tuple(ACTIVE_BOOKING_STATUSES)
                    ),
                )
            )
            .correlate(Ride)
            .scalar_subquery()
        )
        effective_booked_seats_expr = func.greatest(
            active_booked_seats_expr,
            legacy_active_booked_seats_expr,
        )
        total_seats_expr = (Ride.seats_available + effective_booked_seats_expr)

        query = select(Ride, total_seats_expr.label("total_seats")).where(
            and_(
                Ride.status == RideStatus.OPEN,
                Ride.seats_available > 0
            )
        )

        # Keep scheduled search isolated to one-off rides unless explicitly requested.
        if not include_recurring:
            query = query.where(
                or_(
                    Ride.recurrence.is_(None),
                    cast(Ride.recurrence, String).in_(("{}", "null")),
                )
            )
        
        # Text-based filters (fallback when no coordinates)
        if origin and not origin_lat:
            query = query.where(Ride.start_point_address.ilike(f"%{origin}%"))
        
        if destination and not destination_lat:
            query = query.where(Ride.end_point_address.ilike(f"%{destination}%"))
        
        if min_seats:
            query = query.where(Ride.seats_available >= min_seats)

        if driver_total_seats:
            query = query.where(total_seats_expr == driver_total_seats)
        
        if max_price:
            query = query.where(Ride.price_per_seat <= max_price)
        
        if departure_after:
            query = query.where(Ride.departure_time >= departure_after)
        else:
            # Default: only show future rides
            query = query.where(Ride.departure_time > datetime.now())

        if departure_before:
            query = query.where(Ride.departure_time <= departure_before)
        
        # Order by departure time
        query = query.order_by(Ride.departure_time.asc())
        
        result = await db.execute(query)
        rows = result.all()
        rides: List[Ride] = []
        for row in rows:
            ride = row[0]
            computed_total_seats = int(row[1] or ride.seats_available)
            setattr(ride, "total_seats", computed_total_seats)
            rides.append(ride)
        
        # Geo-proximity filtering with approved logic:
        # ((pickup_to_start <= mainThreshold) AND (destination_to_end <= mainThreshold))
        #   OR
        # ((pickup_to_route <= corridorThreshold) AND (destination_to_end <= mainThreshold))
        #
        # Thresholds are dynamic from the driver's selected route distance:
        # mainThreshold = clamp(20% of D, 0.2km, 5km)
        # corridorThreshold = clamp(5% of D, 0.2km, 3km)
        # If D cannot be computed, fallback to legacy fixed values (5km, 1km).
        has_origin_geo = origin_lat is not None and origin_lng is not None
        has_destination_geo = destination_lat is not None and destination_lng is not None
        if has_origin_geo and has_destination_geo:
            matched_with_score: List[Tuple[Ride, float]] = []
            for ride in rides:
                effective_polyline = _effective_ride_polyline(ride)
                route_distance_km = _polyline_length_km(effective_polyline)
                if route_distance_km is None:
                    start_lat = getattr(ride, "start_point_lat", None)
                    start_lng = getattr(ride, "start_point_lng", None)
                    end_lat = getattr(ride, "end_point_lat", None)
                    end_lng = getattr(ride, "end_point_lng", None)
                    if (
                        start_lat is not None
                        and start_lng is not None
                        and end_lat is not None
                        and end_lng is not None
                    ):
                        route_distance_km = _haversine_distance(
                            start_lat,
                            start_lng,
                            end_lat,
                            end_lng,
                        )
                main_threshold_km, corridor_threshold_km = _derive_dynamic_thresholds(
                    route_distance_km
                )

                pickup_to_start_km = _haversine_distance(
                    origin_lat, origin_lng, ride.start_point_lat, ride.start_point_lng
                )
                destination_to_end_km = _haversine_distance(
                    destination_lat, destination_lng, ride.end_point_lat, ride.end_point_lng
                )
                pickup_to_route_km = _point_to_polyline_distance_km(
                    origin_lat, origin_lng, effective_polyline
                )

                branch_a = (
                    pickup_to_start_km <= main_threshold_km
                    and destination_to_end_km <= main_threshold_km
                )
                branch_b = (
                    pickup_to_route_km is not None and
                    pickup_to_route_km <= corridor_threshold_km and
                    destination_to_end_km <= main_threshold_km
                )

                if branch_a or branch_b:
                    pickup_score = min(
                        pickup_to_start_km,
                        pickup_to_route_km if pickup_to_route_km is not None else float("inf"),
                    )
                    score = destination_to_end_km + pickup_score
                    matched_with_score.append((ride, score))

            matched_with_score.sort(key=lambda item: item[1])
            rides = [ride for ride, _ in matched_with_score]
        elif has_origin_geo:
            rides = [
                r for r in rides
                if _haversine_distance(origin_lat, origin_lng, r.start_point_lat, r.start_point_lng) <= radius_km
            ]
        elif has_destination_geo:
            rides = [
                r for r in rides
                if _haversine_distance(destination_lat, destination_lng, r.end_point_lat, r.end_point_lng) <= radius_km
            ]
        
        logger.debug(f"Found {len(rides)} available rides")
        return rides
        
    except Exception as e:
        logger.error(f"Error listing available rides: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list available rides"
        )


def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance between two lat/lng points in kilometers using Haversine formula."""
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _derive_dynamic_thresholds(route_distance_km: Optional[float]) -> Tuple[float, float]:
    """Return (main_threshold_km, corridor_threshold_km)."""
    if route_distance_km is None or route_distance_km <= 0:
        return LEGACY_MAIN_PROXIMITY_KM, LEGACY_ROUTE_DEVIATION_KM
    main_threshold = _clamp(
        route_distance_km * DYNAMIC_MAIN_PERCENT,
        DYNAMIC_MAIN_MIN_KM,
        DYNAMIC_MAIN_MAX_KM,
    )
    corridor_threshold = _clamp(
        route_distance_km * DYNAMIC_CORRIDOR_PERCENT,
        DYNAMIC_CORRIDOR_MIN_KM,
        DYNAMIC_CORRIDOR_MAX_KM,
    )
    return main_threshold, corridor_threshold


def _decode_polyline(encoded: Optional[str]) -> List[Tuple[float, float]]:
    """Decode Google encoded polyline into (lat, lng) pairs."""
    if not encoded:
        return []
    points: List[Tuple[float, float]] = []
    index = 0
    lat = 0
    lng = 0
    length = len(encoded)

    while index < length:
        shift = 0
        result = 0
        while True:
            if index >= length:
                return points
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        shift = 0
        result = 0
        while True:
            if index >= length:
                return points
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng
        points.append((lat / 1e5, lng / 1e5))
    return points


def _polyline_length_km(encoded_polyline: Optional[str]) -> Optional[float]:
    """Total route distance from encoded polyline in km."""
    points = _decode_polyline(encoded_polyline)
    if len(points) < 2:
        return None
    total = 0.0
    for idx in range(len(points) - 1):
        start = points[idx]
        end = points[idx + 1]
        total += _haversine_distance(start[0], start[1], end[0], end[1])
    return total if total > 0 else None


def _project_local_xy_km(lat_ref: float, lng_ref: float, lat: float, lng: float) -> Tuple[float, float]:
    """Project lat/lng to local tangent plane in kilometers."""
    lat_ref_rad = math.radians(lat_ref)
    x = (lng - lng_ref) * 111.320 * math.cos(lat_ref_rad)
    y = (lat - lat_ref) * 110.574
    return x, y


def _point_to_segment_distance_km(
    p: Tuple[float, float],
    a: Tuple[float, float],
    b: Tuple[float, float],
) -> float:
    """Compute point-to-segment distance using local planar projection in km."""
    lat_ref = (p[0] + a[0] + b[0]) / 3.0
    lng_ref = (p[1] + a[1] + b[1]) / 3.0
    px, py = _project_local_xy_km(lat_ref, lng_ref, p[0], p[1])
    ax, ay = _project_local_xy_km(lat_ref, lng_ref, a[0], a[1])
    bx, by = _project_local_xy_km(lat_ref, lng_ref, b[0], b[1])

    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= 1e-12:
        return math.hypot(px - ax, py - ay)

    t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    cx = ax + t * dx
    cy = ay + t * dy
    return math.hypot(px - cx, py - cy)


def _point_to_polyline_distance_km(
    lat: Optional[float],
    lng: Optional[float],
    encoded_polyline: Optional[str],
) -> Optional[float]:
    """Minimum distance from point to route polyline in km."""
    if lat is None or lng is None:
        return None
    points = _decode_polyline(encoded_polyline)
    if len(points) < 2:
        return None

    p = (lat, lng)
    best = float("inf")
    for idx in range(len(points) - 1):
        dist = _point_to_segment_distance_km(p, points[idx], points[idx + 1])
        if dist < best:
            best = dist
    if math.isinf(best):
        return None
    return best


def _effective_ride_polyline(ride: Ride) -> Optional[str]:
    """Resolve selected driver route polyline for route-deviation matching."""
    alternatives = getattr(ride, "route_alternatives", None)
    selected_key = str(getattr(ride, "route_selected_key", "") or "").strip()
    if selected_key and isinstance(alternatives, list):
        for option in alternatives:
            if not isinstance(option, dict):
                continue
            option_key = str(option.get("key") or "").strip()
            if option_key != selected_key:
                continue
            poly = option.get("polyline")
            if isinstance(poly, str) and poly.strip():
                return poly.strip()

    # Fallback to persisted selected polyline on ride row.
    primary = getattr(ride, "polyline", None)
    if isinstance(primary, str) and primary.strip():
        return primary.strip()

    # Do not use non-selected alternatives.
    return None


async def get_driver_rides(
    db: AsyncSession,
    driver_id: UUID,
    status_filter: Optional[str] = None
) -> List[Ride]:
    """
    Retrieve all rides created by a specific driver.
    
    Args:
        db: Async database session
        driver_id: UUID of the driver
        status_filter: Optional status filter (supports open/scheduled and in_progress/ongoing)
    
    Returns:
        List of Ride instances ordered by departure_time DESC
    """
    try:
        query = select(Ride).where(Ride.driver_id == driver_id)
        
        if status_filter:
            status_values = _normalized_status_values(status_filter)
            if status_values:
                # Cast enum to text so filter works across schema variants.
                query = query.where(func.lower(cast(Ride.status, String)).in_(status_values))
        
        query = query.order_by(Ride.departure_time.desc())
        
        result = await db.execute(query)
        rides = result.scalars().all()
        
        logger.debug(f"Retrieved {len(rides)} rides for driver_id={driver_id}")
        return list(rides)
        
    except Exception as e:
        logger.error(f"Error fetching driver rides for driver_id={driver_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve driver rides"
        )


async def update_ride(
    db: AsyncSession,
    ride_id: UUID,
    ride_update: RideUpdate
) -> Ride:
    """
    Update ride details (before ride starts).
    
    Args:
        db: Async database session
        ride_id: UUID of the ride
        ride_update: RideUpdate schema with updated fields
    
    Returns:
        Updated Ride instance
    
    Raises:
        HTTPException 404: If ride not found
        HTTPException 400: If ride has already started
        HTTPException 500: On database errors
    
    Notes:
        - Cannot update ride if status is "ongoing" or "completed"
        - Only updates fields that are explicitly set
    """
    try:
        ride = await get_ride_by_id(db, ride_id)
        
        if not ride:
            logger.warning(f"Ride not found: ride_id={ride_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ride not found"
            )
        
        # Cannot update ongoing or completed rides
        if ride.status in [RideStatus.IN_PROGRESS, RideStatus.COMPLETED]:
            logger.warning(f"Cannot update ride with status={ride.status}: ride_id={ride_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot update ride with status '{ride.status}'"
            )
        
        # Update only provided fields
        update_data = ride_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(ride, field, value)
        
        await db.commit()
        await db.refresh(ride)
        
        logger.info(f"Updated ride: ride_id={ride_id}")
        return ride
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating ride_id={ride_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ride"
        )


async def update_ride_status(
    db: AsyncSession,
    ride_id: UUID,
    new_status: str
) -> Ride:
    """
    Update ride status (scheduled → ongoing → completed/cancelled).
    
    Args:
        db: Async database session
        ride_id: UUID of the ride
        new_status: New status value
    
    Returns:
        Updated Ride instance
    
    Raises:
        HTTPException 404: If ride not found
        HTTPException 500: On database errors
    
    Notes:
        - Used by driver to start/complete ride
        - Used by system for auto-cancellation
        - When status becomes "completed", all bookings are marked "completed"
    """
    try:
        ride = await get_ride_by_id(db, ride_id)
        
        if not ride:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ride not found"
            )
        
        old_status = ride.status
        new_status_value = str(getattr(new_status, "value", new_status) or "").lower()
        ride.status = new_status_value
        
        # If completing ride, mark all bookings as completed
        if new_status_value == RideStatus.COMPLETED.value:
            for booking in ride.bookings:
                booking_status = str(getattr(booking.status, "value", booking.status) or "").lower()
                if booking_status in ACTIVE_BOOKING_STATUSES:
                    booking.status = BookingStatusEnum.COMPLETED.value

            # Keep the canonical ride_bookings table in sync as well.
            await db.execute(
                update(RideBooking)
                .where(
                    and_(
                        RideBooking.ride_id == ride.id,
                        func.lower(cast(RideBooking.status, String)).in_(
                            tuple(ACTIVE_BOOKING_STATUSES)
                        ),
                    )
                )
                .values(status=BookingStatusEnum.COMPLETED.value)
            )
        
        await db.commit()
        await db.refresh(ride)
        
        logger.info(f"Updated ride status: ride_id={ride_id}, {old_status} -> {new_status}")
        return ride
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating ride status for ride_id={ride_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ride status"
        )


async def delete_ride(db: AsyncSession, ride_id: UUID, driver_id: UUID) -> bool:
    """
    Delete a ride (only if no bookings exist).
    
    Args:
        db: Async database session
        ride_id: UUID of the ride
        driver_id: UUID of the driver (for ownership verification)
    
    Returns:
        True if deleted successfully
    
    Raises:
        HTTPException 404: If ride not found or not owned by driver
        HTTPException 400: If ride has bookings
        HTTPException 500: On database errors
    
    Notes:
        - Cannot delete ride with existing bookings
        - Ownership is verified before deletion
    """
    try:
        ride = await get_ride_by_id(db, ride_id)
        
        if not ride or ride.driver_id != driver_id:
            logger.warning(f"Ride not found or unauthorized: ride_id={ride_id}, driver_id={driver_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ride not found or you don't own this ride"
            )
        
        # Check canonical active bookings first.
        active_canonical_count_result = await db.execute(
            select(func.count(RideBooking.id)).where(
                and_(
                    RideBooking.ride_id == ride.id,
                    func.lower(cast(RideBooking.status, String)).in_(
                        tuple(ACTIVE_BOOKING_STATUSES)
                    ),
                )
            )
        )
        active_canonical_count = int(active_canonical_count_result.scalar_one() or 0)
        if active_canonical_count > 0:
            logger.warning(
                "Cannot delete ride with active canonical bookings: ride_id=%s active=%s",
                ride_id,
                active_canonical_count,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete ride with active bookings. Please cancel all bookings first.",
            )

        # Legacy fallback guard.
        if ride.bookings and len(ride.bookings) > 0:
            active_legacy_bookings = [
                b
                for b in ride.bookings
                if str(getattr(b.status, "value", b.status) or "").lower()
                in ACTIVE_BOOKING_STATUSES
            ]
            if active_legacy_bookings:
                logger.warning(
                    "Cannot delete ride with active legacy bookings: ride_id=%s active=%s",
                    ride_id,
                    len(active_legacy_bookings),
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete ride with active bookings. Please cancel all bookings first.",
                )
        
        await db.delete(ride)
        await db.commit()
        
        logger.info(f"Deleted ride: ride_id={ride_id}, driver_id={driver_id}")
        return True
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting ride_id={ride_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete ride"
        )


# ============================================
# RIDE BOOKING CRUD OPERATIONS
# ============================================

async def book_ride(
    db: AsyncSession,
    passenger_id: UUID,
    booking_data: RideBookingCreate
) -> RideBooking:
    """
    Create a new booking for a ride.
    
    Args:
        db: Async database session
        passenger_id: UUID of the passenger booking the ride
        booking_data: RideBookingCreate schema with booking details
    
    Returns:
        Created RideBooking instance
    
    Raises:
        HTTPException 404: If ride not found
        HTTPException 400: If insufficient seats or ride not available
        HTTPException 500: On database errors
    
    Notes:
        - Checks seat availability before booking
        - Reduces ride.seats_available by booked_seats
        - Calculates total_price = booked_seats × price_per_seat
        - Prevents double booking by same passenger
    """
    try:
        # Get ride with lock to prevent race conditions
        locked_ride_result = await db.execute(
            select(Ride)
            .where(Ride.id == booking_data.ride_id)
            .with_for_update()
            .options(selectinload(Ride.bookings))
        )
        ride = locked_ride_result.scalar_one_or_none()
        
        if not ride:
            logger.warning(f"Ride not found: ride_id={booking_data.ride_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ride not found"
            )
        
        # Verify ride is available for booking
        if ride.status != RideStatus.OPEN:
            logger.warning(f"Ride not available (status={ride.status}): ride_id={ride.id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ride is not available for booking (status: {ride.status})"
            )
        
        # Check seat availability
        if ride.seats_available < booking_data.booked_seats:
            logger.warning(
                f"Insufficient seats: ride_id={ride.id}, "
                f"available={ride.seats_available}, requested={booking_data.booked_seats}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Only {ride.seats_available} seats available"
            )
        
        # Check for existing active booking by same passenger
        existing_booking_result = await db.execute(
            select(RideBooking).where(
                and_(
                    RideBooking.ride_id == booking_data.ride_id,
                    RideBooking.passenger_id == passenger_id,
                    func.lower(cast(RideBooking.status, String)).in_(
                        tuple(ACTIVE_BOOKING_STATUSES)
                    ),
                )
            )
        )
        existing_booking = existing_booking_result.scalar_one_or_none()
        
        if existing_booking:
            logger.warning(f"Passenger already has booking: passenger_id={passenger_id}, ride_id={ride.id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You already have an active booking for this ride"
            )
        
        # Calculate total price
        total_price = booking_data.booked_seats * ride.price_per_seat
        
        # Create booking
        new_booking = RideBooking(
            ride_id=ride.id,
            passenger_id=passenger_id,
            booked_seats=booking_data.booked_seats,
            total_price=total_price,
            status=BookingStatusEnum.BOOKED,
            pickup_lat=booking_data.pickup_lat,
            pickup_lng=booking_data.pickup_lng,
            pickup_address=booking_data.pickup_address,
            pickup_place_id=booking_data.pickup_place_id,
            dropoff_lat=booking_data.dropoff_lat,
            dropoff_lng=booking_data.dropoff_lng,
            dropoff_address=booking_data.dropoff_address,
            dropoff_place_id=booking_data.dropoff_place_id,
        )
        
        # Update ride available seats
        ride.seats_available -= booking_data.booked_seats
        
        db.add(new_booking)
        await db.commit()
        await db.refresh(new_booking)
        
        logger.info(
            f"Created booking: passenger_id={passenger_id}, ride_id={ride.id}, "
            f"seats={booking_data.booked_seats}, price={total_price}"
        )
        return new_booking
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating booking: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create booking"
        )


async def get_booking_by_id(db: AsyncSession, booking_id: UUID) -> Optional[RideBooking]:
    """
    Retrieve booking by ID with ride details loaded.
    
    Args:
        db: Async database session
        booking_id: UUID of the booking
    
    Returns:
        RideBooking instance with ride details, or None if not found
    """
    try:
        result = await db.execute(
            select(RideBooking)
            .options(selectinload(RideBooking.ride))
            .where(RideBooking.id == booking_id)
        )
        return result.scalar_one_or_none()
        
    except Exception as e:
        logger.error(f"Error fetching booking by booking_id={booking_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve booking"
        )


async def _get_driver_owned_booking_for_update(
    db: AsyncSession,
    booking_id: UUID,
    driver_user_id: UUID,
) -> RideBooking:
    """Load booking with ride ownership check and row lock for driver-side execution updates."""
    result = await db.execute(
        select(RideBooking)
        .join(Ride, RideBooking.ride_id == Ride.id)
        .options(selectinload(RideBooking.ride))
        .where(
            and_(
                RideBooking.id == booking_id,
                Ride.driver_id == driver_user_id,
            )
        )
        .with_for_update()
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found or you don't have permission to update it",
        )
    return booking


async def mark_booking_pickup_completed(
    db: AsyncSession,
    booking_id: UUID,
    driver_user_id: UUID,
) -> RideBooking:
    """Mark pickup completed for a booking during an in-progress ride."""
    try:
        booking = await _get_driver_owned_booking_for_update(db, booking_id, driver_user_id)

        booking_status = str(getattr(booking.status, "value", booking.status) or "").lower()
        ride_status_value = getattr(getattr(booking, "ride", None), "status", "")
        ride_status = str(getattr(ride_status_value, "value", ride_status_value) or "").lower()

        if booking_status == BookingStatusEnum.CANCELLED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot complete pickup for a cancelled booking",
            )

        if booking_status == BookingStatusEnum.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking is already completed",
            )

        if ride_status not in {RideStatus.IN_PROGRESS.value, "ongoing"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pickup can only be marked once ride is in progress",
            )

        if booking.actual_pickup_time is None:
            booking.actual_pickup_time = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(booking)
        return booking

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Error marking pickup complete for booking_id=%s: %s", booking_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark pickup complete",
        )


async def mark_booking_dropoff_completed(
    db: AsyncSession,
    booking_id: UUID,
    driver_user_id: UUID,
) -> RideBooking:
    """Mark dropoff completed for a booking during an in-progress ride."""
    try:
        booking = await _get_driver_owned_booking_for_update(db, booking_id, driver_user_id)

        booking_status = str(getattr(booking.status, "value", booking.status) or "").lower()
        ride_status_value = getattr(getattr(booking, "ride", None), "status", "")
        ride_status = str(getattr(ride_status_value, "value", ride_status_value) or "").lower()

        if booking_status == BookingStatusEnum.CANCELLED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot complete dropoff for a cancelled booking",
            )

        if booking_status == BookingStatusEnum.COMPLETED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking is already completed",
            )

        if ride_status not in {RideStatus.IN_PROGRESS.value, "ongoing"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dropoff can only be marked once ride is in progress",
            )

        now_utc = datetime.now(timezone.utc)
        if booking.actual_pickup_time is None:
            booking.actual_pickup_time = now_utc
        if booking.actual_dropoff_time is None:
            booking.actual_dropoff_time = now_utc

        booking.status = BookingStatusEnum.COMPLETED.value

        await db.commit()
        await db.refresh(booking)
        return booking

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error("Error marking dropoff complete for booking_id=%s: %s", booking_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark dropoff complete",
        )


async def get_user_bookings(
    db: AsyncSession,
    passenger_id: UUID,
    status_filter: Optional[str] = None
) -> List[RideBooking]:
    """
    Retrieve all bookings made by a passenger.
    
    Args:
        db: Async database session
        passenger_id: UUID of the passenger
        status_filter: Optional status filter (booked/cancelled/completed)
    
    Returns:
        List of RideBooking instances with ride details, ordered by booking_time DESC
    """
    try:
        booking_status_expr = func.lower(cast(RideBooking.status, String))
        ride_status_expr = func.lower(cast(Ride.status, String))
        normalized_filter = (status_filter or "").strip().lower()

        query = (
            select(RideBooking)
            .options(selectinload(RideBooking.ride))
            .outerjoin(Ride, RideBooking.ride_id == Ride.id)
            .where(RideBooking.passenger_id == passenger_id)
        )

        if normalized_filter:
            if normalized_filter == "active":
                # User-defined semantics:
                # active = (active booking + active ride) OR booking completed
                query = query.where(
                    or_(
                        and_(
                            booking_status_expr.in_(ACTIVE_BOOKING_FILTER_STATUSES),
                            ride_status_expr.in_(ACTIVE_RIDE_FILTER_STATUSES),
                        ),
                        booking_status_expr == "completed",
                    )
                )
            elif normalized_filter == "scheduled":
                # Home scheduled rides:
                # active booking + active ride that has not started/completed/cancelled.
                query = query.where(
                    and_(
                        booking_status_expr.in_(ACTIVE_BOOKING_FILTER_STATUSES),
                        ride_status_expr.in_(("open", "scheduled")),
                    )
                )
            elif normalized_filter == "history":
                # Home rides history:
                # booking completed/cancelled OR ride completed/cancelled.
                query = query.where(
                    or_(
                        booking_status_expr.in_(("completed", "cancelled")),
                        ride_status_expr.in_(("completed", "cancelled")),
                    )
                )
            elif normalized_filter == "completed":
                # completed = booking completed OR ride completed
                query = query.where(
                    or_(
                        booking_status_expr == "completed",
                        ride_status_expr == "completed",
                    )
                )
            elif normalized_filter in {"cancelled", "canceled"}:
                # cancelled = booking cancelled OR ride cancelled
                query = query.where(
                    or_(
                        booking_status_expr == "cancelled",
                        ride_status_expr == "cancelled",
                    )
                )
            else:
                status_values = _normalized_booking_status_values(normalized_filter)
                if status_values:
                    query = query.where(booking_status_expr.in_(status_values))
        
        query = query.order_by(RideBooking.booking_time.desc())
        
        result = await db.execute(query)
        bookings = result.scalars().all()
        
        logger.debug(f"Retrieved {len(bookings)} bookings for passenger_id={passenger_id}")
        return list(bookings)
        
    except Exception as e:
        logger.error(f"Error fetching bookings for passenger_id={passenger_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve bookings"
        )


async def cancel_booking(
    db: AsyncSession,
    booking_id: UUID,
    passenger_id: UUID,
    reason: Optional[str] = None
) -> RideBooking:
    """
    Cancel a booking and restore seats to ride.
    
    Args:
        db: Async database session
        booking_id: UUID of the booking
        passenger_id: UUID of the passenger (for ownership verification)
        reason: Optional cancellation reason
    
    Returns:
        Updated RideBooking instance
    
    Raises:
        HTTPException 404: If booking not found or not owned by passenger
        HTTPException 400: If booking already cancelled or ride has started
        HTTPException 500: On database errors
    
    Notes:
        - Restores booked_seats back to ride.seats_available
        - Reduces ride.total_earnings
        - Cannot cancel after ride status is "ongoing"
        - Sets cancellation_time to current time
    """
    try:
        booking = await get_booking_by_id(db, booking_id)
        
        if not booking or booking.passenger_id != passenger_id:
            logger.warning(f"Booking not found or unauthorized: booking_id={booking_id}, passenger_id={passenger_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found or you don't own this booking"
            )
        
        # Check if already cancelled
        if booking.status == BookingStatusEnum.CANCELLED:
            logger.warning(f"Booking already cancelled: booking_id={booking_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking is already cancelled"
            )
        
        # Check if ride has started
        if booking.ride.status in [RideStatus.IN_PROGRESS, RideStatus.COMPLETED]:
            logger.warning(f"Cannot cancel booking for {booking.ride.status} ride: booking_id={booking_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel booking for {booking.ride.status} ride"
            )
        
        # Restore seats to ride
        booking.ride.seats_available += booking.booked_seats
        
        # Update booking status
        booking.status = BookingStatusEnum.CANCELLED
        booking.cancellation_time = datetime.now()
        booking.cancellation_reason = reason
        
        await db.commit()
        await db.refresh(booking)
        
        logger.info(
            f"Cancelled booking: booking_id={booking_id}, passenger_id={passenger_id}, "
            f"restored_seats={booking.booked_seats}"
        )
        return booking
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error cancelling booking_id={booking_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel booking"
        )
