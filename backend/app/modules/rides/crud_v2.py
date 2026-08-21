"""
Module: Rides & Scheduling - CRUD Operations (Prompt 5)
Purpose: Database operations with atomic seat booking and geo-radius search
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: December 8, 2025
Notes: Implements SELECT FOR UPDATE for atomic booking and Haversine formula for geo-search
"""

import math
from datetime import datetime, date, time
from typing import Any, Dict, List, Optional
from uuid import UUID
from decimal import Decimal

from sqlalchemy import select, update, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.ride import Ride, RideStatus
from app.models.booking import Booking, BookingStatus
from app.models.recurring_schedule import RecurringSchedule
from app.models.recurring_schedule_subscription import RecurringScheduleSubscription
from app.modules.auth.models import User
from app.core.exceptions import NotFoundError, ConflictError, ValidationError


ACTIVE_RECURRING_BOOKING_STATUSES = ("reserved", "booked", "confirmed")
ACTIVE_RECURRING_RIDE_STATUSES = ("open", "scheduled", "in_progress", "ongoing")


# ============================================
# HAVERSINE DISTANCE CALCULATION
# ============================================

def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate distance between two points using Haversine formula.
    
    Args:
        lat1: Latitude of first point
        lng1: Longitude of first point
        lat2: Latitude of second point
        lng2: Longitude of second point
    
    Returns:
        Distance in kilometers
    
    Example:
        >>> distance = haversine_distance(31.4697, 74.2728, 31.5204, 74.3587)
        >>> print(f"{distance:.2f} km")
    """
    # Earth's radius in kilometers
    R = 6371.0
    
    # Convert degrees to radians
    lat1_rad = math.radians(lat1)
    lng1_rad = math.radians(lng1)
    lat2_rad = math.radians(lat2)
    lng2_rad = math.radians(lng2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlng = lng2_rad - lng1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    distance = R * c
    return distance


# ============================================
# RIDE CRUD OPERATIONS
# ============================================

async def create_ride(
    db: AsyncSession,
    driver_id: UUID,
    start_point_lat: float,
    start_point_lng: float,
    start_point_address: str,
    end_point_lat: float,
    end_point_lng: float,
    end_point_address: str,
    start_time: datetime,
    seats_offered: int,
    base_price: Decimal,
    polyline_main: Optional[str] = None,
    polyline_alternates: Optional[dict] = None,
    buffer_seats: int = 0,
    recurrence: Optional[dict] = None
) -> Ride:
    """
    Create a new ride.
    
    Args:
        db: Database session
        driver_id: Driver's user ID
        start_point_*: Starting point details
        end_point_*: Destination details
        start_time: Departure time
        seats_offered: Total seats
        base_price: Price per seat
        polyline_main: Encoded route polyline
        polyline_alternates: Alternative routes
        buffer_seats: Seats kept aside
        recurrence: Recurrence pattern
    
    Returns:
        Created ride object
    """
    available_seats = max(0, int(seats_offered) - int(buffer_seats))

    ride = Ride(
        driver_id=driver_id,
        start_point_lat=start_point_lat,
        start_point_lng=start_point_lng,
        start_point_address=start_point_address,
        end_point_lat=end_point_lat,
        end_point_lng=end_point_lng,
        end_point_address=end_point_address,
        departure_time=start_time,
        polyline=polyline_main,
        route_alternatives=polyline_alternates,
        seats_available=available_seats,
        price_per_seat=base_price,
        status=RideStatus.OPEN,
        recurrence=recurrence
    )
    
    db.add(ride)
    await db.commit()
    await db.refresh(ride)
    return ride


async def get_ride_by_id(db: AsyncSession, ride_id: UUID) -> Optional[Ride]:
    """Get ride by ID."""
    result = await db.execute(
        select(Ride).where(Ride.id == ride_id)
    )
    return result.scalars().first()


async def update_ride(
    db: AsyncSession,
    ride_id: UUID,
    **updates
) -> Ride:
    """
    Update ride details.
    
    Args:
        db: Database session
        ride_id: Ride ID
        **updates: Fields to update
    
    Returns:
        Updated ride object
    """
    ride = await get_ride_by_id(db, ride_id)
    if not ride:
        raise NotFoundError(f"Ride {ride_id} not found")
    
    for key, value in updates.items():
        if hasattr(ride, key) and value is not None:
            setattr(ride, key, value)
    
    await db.commit()
    await db.refresh(ride)
    return ride


async def get_driver_upcoming_rides(
    db: AsyncSession,
    driver_id: UUID,
    limit: int = 50
) -> List[Ride]:
    """
    Get driver's upcoming rides.
    
    Args:
        db: Database session
        driver_id: Driver's user ID
        limit: Maximum number of rides to return
    
    Returns:
        List of upcoming rides
    """
    result = await db.execute(
        select(Ride)
        .where(
            and_(
                Ride.driver_id == driver_id,
                Ride.start_time >= datetime.now(),
                Ride.status == RideStatus.OPEN
            )
        )
        .order_by(Ride.start_time)
        .limit(limit)
    )
    return result.scalars().all()


async def search_rides_geo_radius(
    db: AsyncSession,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    radius_km: float = 5.0,
    target_date: Optional[date] = None,
    min_seats: int = 1,
    max_price: Optional[Decimal] = None
) -> List[Ride]:
    """
    Search rides within geo-radius of origin and destination (Prompt 5 core feature).
    
    Uses Haversine formula to filter rides within radius of both origin and destination.
    
    Args:
        db: Database session
        origin_lat: Search origin latitude
        origin_lng: Search origin longitude
        dest_lat: Search destination latitude
        dest_lng: Search destination longitude
        radius_km: Search radius in kilometers
        target_date: Specific date to search (defaults to today)
        min_seats: Minimum available seats
        max_price: Maximum price per seat
    
    Returns:
        List of matching rides
    
    Example:
        >>> rides = await search_rides_geo_radius(
        ...     db, 31.4697, 74.2728, 31.5204, 74.3587, radius_km=5.0, min_seats=2
        ... )
    """
    if target_date is None:
        target_date = date.today()
    
    # Query all rides for the target date with open status
    query = select(Ride).where(
        and_(
            func.date(Ride.start_time) == target_date,
            Ride.status == RideStatus.OPEN,
            (Ride.seats_offered - Ride.seats_booked - Ride.buffer_seats) >= min_seats
        )
    )
    
    if max_price:
        query = query.where(Ride.base_price <= max_price)
    
    result = await db.execute(query)
    all_rides = result.scalars().all()
    
    # Filter by geo-radius using Haversine formula
    matching_rides = []
    for ride in all_rides:
        # Calculate distance from search origin to ride start point
        origin_distance = haversine_distance(
            origin_lat, origin_lng,
            ride.start_point_lat, ride.start_point_lng
        )
        
        # Calculate distance from search destination to ride end point
        dest_distance = haversine_distance(
            dest_lat, dest_lng,
            ride.end_point_lat, ride.end_point_lng
        )
        
        # Include ride if both origin and destination are within radius
        if origin_distance <= radius_km and dest_distance <= radius_km:
            matching_rides.append(ride)
    
    return matching_rides


# ============================================
# ATOMIC BOOKING OPERATIONS (PROMPT 5 CORE)
# ============================================

async def book_seat_atomic(
    db: AsyncSession,
    ride_id: UUID,
    passenger_id: UUID,
    seats_reserved: int
) -> Booking:
    """
    Atomically book seats on a ride (Prompt 5 core feature).
    
    Uses SELECT FOR UPDATE to prevent race conditions. Ensures:
    1. Ride has enough available seats
    2. Seats are updated atomically
    3. Booking is created transactionally
    
    Args:
        db: Database session
        ride_id: Ride to book
        passenger_id: Passenger user ID
        seats_reserved: Number of seats to reserve
    
    Returns:
        Created booking object
    
    Raises:
        NotFoundError: If ride doesn't exist
        ConflictError: If not enough seats available
        ValidationError: If passenger already has booking
    
    Example:
        >>> booking = await book_seat_atomic(db, ride_id, passenger_id, 2)
    """
    # Lock the ride row for update (prevents concurrent modifications)
    result = await db.execute(
        select(Ride)
        .where(Ride.id == ride_id)
        .with_for_update()  # ATOMIC LOCK
    )
    ride = result.scalars().first()
    
    if not ride:
        raise NotFoundError(f"Ride {ride_id} not found")
    
    # Check if ride is bookable
    if ride.status != RideStatus.OPEN:
        raise ConflictError(f"Ride is not available for booking (status: {ride.status})")
    
    # Calculate available seats (excluding buffer seats)
    available_seats = ride.seats_offered - ride.seats_booked - ride.buffer_seats
    
    if available_seats < seats_reserved:
        raise ConflictError(
            f"Not enough seats available. Requested: {seats_reserved}, Available: {available_seats}"
        )
    
    # Check if passenger already has a booking for this ride
    existing_booking = await db.execute(
        select(Booking).where(
            and_(
                Booking.ride_id == ride_id,
                Booking.passenger_id == passenger_id,
                Booking.status != BookingStatus.CANCELLED
            )
        )
    )
    if existing_booking.scalars().first():
        raise ValidationError("You already have a booking for this ride")
    
    # Update ride seats (atomic within transaction)
    ride.seats_booked += seats_reserved
    
    # Calculate fare
    fare = Decimal(ride.base_price) * seats_reserved
    
    # Create booking
    booking = Booking(
        ride_id=ride_id,
        passenger_id=passenger_id,
        seats_reserved=seats_reserved,
        fare=fare,
        status=BookingStatus.RESERVED,
        version=0  # Initial version for optimistic concurrency
    )
    
    db.add(booking)
    
    # Commit transaction (both updates happen atomically)
    await db.commit()
    await db.refresh(booking)
    await db.refresh(ride)
    
    return booking


async def cancel_booking(
    db: AsyncSession,
    booking_id: UUID,
    user_id: UUID
) -> Booking:
    """
    Cancel a booking and release seats atomically.
    
    Args:
        db: Database session
        booking_id: Booking to cancel
        user_id: User requesting cancellation (passenger or driver)
    
    Returns:
        Updated booking object
    """
    # Lock booking and ride for update
    result = await db.execute(
        select(Booking)
        .where(Booking.id == booking_id)
        .with_for_update()
    )
    booking = result.scalars().first()
    
    if not booking:
        raise NotFoundError(f"Booking {booking_id} not found")
    
    if booking.status == BookingStatus.CANCELLED:
        raise ConflictError("Booking is already cancelled")
    
    # Lock the ride
    ride_result = await db.execute(
        select(Ride)
        .where(Ride.id == booking.ride_id)
        .with_for_update()
    )
    ride = ride_result.scalars().first()
    
    # Release seats atomically
    ride.seats_booked -= booking.seats_reserved
    booking.status = BookingStatus.CANCELLED
    booking.version += 1
    
    await db.commit()
    await db.refresh(booking)
    
    return booking


# ============================================
# RECURRING SCHEDULE CRUD
# ============================================

async def save_recurring_schedule(
    db: AsyncSession,
    user_id: UUID,
    days_of_week: List[str],
    time: time,
    start_point_lat: float,
    start_point_lng: float,
    start_point_address: str,
    end_point_lat: float,
    end_point_lng: float,
    end_point_address: str,
    seats_offered: int,
    base_price: Decimal,
    start_date: date,
    end_date: date,
    polyline_main: Optional[str] = None,
    buffer_seats: int = 0,
    recurrence_meta: Optional[dict] = None
) -> RecurringSchedule:
    """
    Create recurring schedule (Prompt 5 feature).
    
    Args:
        db: Database session
        user_id: User creating schedule
        days_of_week: List of days ["Mon", "Tue", ...]
        time: Time of day
        start_point_*: Origin details
        end_point_*: Destination details
        seats_offered: Seats per ride
        base_price: Price per seat
        start_date: Schedule start
        end_date: Schedule end
        polyline_main: Route polyline
        buffer_seats: Buffer seats
        recurrence_meta: Additional metadata
    
    Returns:
        Created schedule object
    """
    schedule = RecurringSchedule(
        user_id=user_id,
        days_of_week=days_of_week,
        time=time,
        start_point_lat=start_point_lat,
        start_point_lng=start_point_lng,
        start_point_address=start_point_address,
        end_point_lat=end_point_lat,
        end_point_lng=end_point_lng,
        end_point_address=end_point_address,
        polyline_main=polyline_main,
        seats_offered=seats_offered,
        base_price=base_price,
        buffer_seats=buffer_seats,
        start_date=start_date,
        end_date=end_date,
        recurrence_meta=recurrence_meta,
        is_active=True
    )
    
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return schedule


async def list_user_schedules(
    db: AsyncSession,
    user_id: UUID,
    active_only: bool = True
) -> List[RecurringSchedule]:
    """
    List user's recurring schedules.
    
    Args:
        db: Database session
        user_id: User ID
        active_only: Return only active schedules
    
    Returns:
        List of schedules
    """
    query = select(RecurringSchedule).where(
        RecurringSchedule.user_id == user_id
    )
    
    if active_only:
        query = query.where(RecurringSchedule.is_active == True)
    
    result = await db.execute(query.order_by(RecurringSchedule.created_at.desc()))
    return result.scalars().all()


async def list_recurring_schedules_for_discovery(
    db: AsyncSession,
    passenger_from_date: date,
    passenger_until_date: date,
    min_seats: int = 1,
    driver_total_seats: Optional[int] = None,
    max_price: Optional[Decimal] = None,
    exclude_user_id: Optional[UUID] = None,
) -> List[tuple[RecurringSchedule, Optional[str]]]:
    """
    Fetch recurring schedules that overlap passenger date range.

    The caller applies geo-distance and time-window filtering.
    """
    seats_available_expr = RecurringSchedule.seats_offered - RecurringSchedule.buffer_seats

    query = (
        select(RecurringSchedule, User.full_name)
        .join(User, User.id == RecurringSchedule.user_id)
        .where(
            and_(
                RecurringSchedule.is_active == True,
                RecurringSchedule.start_date <= passenger_until_date,
                RecurringSchedule.end_date >= passenger_from_date,
                seats_available_expr >= min_seats,
            )
        )
        .order_by(RecurringSchedule.start_date.asc(), RecurringSchedule.time.asc())
    )

    if max_price is not None:
        query = query.where(RecurringSchedule.base_price <= max_price)

    if driver_total_seats is not None:
        query = query.where(RecurringSchedule.seats_offered == driver_total_seats)

    if exclude_user_id is not None:
        query = query.where(RecurringSchedule.user_id != exclude_user_id)

    result = await db.execute(query)
    return [(row[0], row[1]) for row in result.all()]


async def get_schedule_by_id_for_user(
    db: AsyncSession,
    schedule_id: UUID,
    user_id: UUID,
) -> RecurringSchedule:
    """Get a recurring schedule by id, scoped to owner."""
    result = await db.execute(
        select(RecurringSchedule).where(
            and_(
                RecurringSchedule.id == schedule_id,
                RecurringSchedule.user_id == user_id,
            )
        )
    )
    schedule = result.scalars().first()
    if not schedule:
        raise NotFoundError(f"Schedule {schedule_id} not found")
    return schedule


async def get_schedule_by_id(
    db: AsyncSession,
    schedule_id: UUID,
) -> Optional[RecurringSchedule]:
    """Get recurring schedule by id without ownership scoping."""
    result = await db.execute(
        select(RecurringSchedule).where(RecurringSchedule.id == schedule_id)
    )
    return result.scalars().first()


async def update_schedule(
    db: AsyncSession,
    schedule_id: UUID,
    user_id: UUID,
    **updates
) -> RecurringSchedule:
    """Update recurring schedule with ownership check."""
    schedule = await get_schedule_by_id_for_user(db, schedule_id, user_id)

    for key, value in updates.items():
        if hasattr(schedule, key) and value is not None:
            setattr(schedule, key, value)

    await db.commit()
    await db.refresh(schedule)
    return schedule


async def deactivate_schedule(
    db: AsyncSession,
    schedule_id: UUID,
    user_id: UUID,
) -> RecurringSchedule:
    """Deactivate schedule (soft delete) with ownership check."""
    schedule = await get_schedule_by_id_for_user(db, schedule_id, user_id)
    schedule.is_active = False
    await db.commit()
    await db.refresh(schedule)
    return schedule


async def purge_future_open_rides_for_schedule(
    db: AsyncSession,
    schedule_id: UUID,
) -> int:
    """
    Delete previously materialized future rides linked to this schedule.

    Removes only future rides that are still open, so completed/in-progress
    history remains untouched.
    """
    column_result = await db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'rides'
              AND column_name IN ('departure_time', 'start_time')
            """
        )
    )
    time_columns = {row.column_name for row in column_result}
    time_column = "departure_time" if "departure_time" in time_columns else "start_time"

    if time_column not in {"departure_time", "start_time"}:
        return 0

    stmt = text(
        f"""
        DELETE FROM rides
        WHERE recurrence IS NOT NULL
          AND recurrence->>'schedule_id' = :schedule_id
          AND {time_column} >= NOW()
          AND LOWER(status::text) IN ('open', 'scheduled')
        """
    )
    result = await db.execute(stmt, {"schedule_id": str(schedule_id)})
    await db.commit()
    return int(result.rowcount or 0)


async def get_active_schedules_for_date(
    db: AsyncSession,
    target_date: date
) -> List[RecurringSchedule]:
    """
    Get all active schedules that should run on target date.
    
    Args:
        db: Database session
        target_date: Date to check
    
    Returns:
        List of schedules matching the date
    """
    day_name = target_date.strftime("%a")

    result = await db.execute(
        select(RecurringSchedule)
        .where(
            and_(
                RecurringSchedule.is_active == True,
                RecurringSchedule.start_date <= target_date,
                RecurringSchedule.end_date >= target_date,
                text("days_of_week::jsonb ? :day_name"),
            )
        )
        .params(day_name=day_name)
    )
    return result.scalars().all()


async def _resolve_rides_time_column(db: AsyncSession) -> str:
    """Resolve canonical rides departure-time column name across schema variants."""
    column_result = await db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'rides'
              AND column_name IN ('departure_time', 'start_time')
            """
        )
    )
    time_columns = {row.column_name for row in column_result}
    if "departure_time" in time_columns:
        return "departure_time"
    if "start_time" in time_columns:
        return "start_time"
    return "departure_time"


async def get_materialized_ride_for_schedule_date(
    db: AsyncSession,
    schedule_id: UUID,
    target_date: date,
) -> Optional[Ride]:
    """Find an already-materialized ride instance for schedule on a date."""
    time_column = await _resolve_rides_time_column(db)
    result = await db.execute(
        text(
            f"""
            SELECT id
            FROM rides
            WHERE recurrence IS NOT NULL
              AND recurrence->>'schedule_id' = :schedule_id
              AND DATE({time_column}) = :target_date
            ORDER BY {time_column} ASC
            LIMIT 1
            """
        ),
        {
            "schedule_id": str(schedule_id),
            "target_date": target_date,
        },
    )
    ride_id = result.scalar_one_or_none()
    if not ride_id:
        return None
    return await get_ride_by_id(db, ride_id)


async def list_materialized_schedule_rides_for_range(
    db: AsyncSession,
    schedule_id: UUID,
    range_start: date,
    range_end: date,
) -> List[Ride]:
    """List materialized rides for a schedule inside a date range."""
    time_column = await _resolve_rides_time_column(db)
    result = await db.execute(
        text(
            f"""
            SELECT id
            FROM rides
            WHERE recurrence IS NOT NULL
              AND recurrence->>'schedule_id' = :schedule_id
              AND DATE({time_column}) BETWEEN :range_start AND :range_end
            ORDER BY {time_column} ASC
            """
        ),
        {
            "schedule_id": str(schedule_id),
            "range_start": range_start,
            "range_end": range_end,
        },
    )
    ride_ids = [row.id for row in result]
    if not ride_ids:
        return []

    rides_result = await db.execute(select(Ride).where(Ride.id.in_(ride_ids)))
    ride_by_id = {ride.id: ride for ride in rides_result.scalars().all()}
    return [ride_by_id[rid] for rid in ride_ids if rid in ride_by_id]


async def find_next_active_ride_for_schedule(
    db: AsyncSession,
    schedule_id: UUID,
    now_utc: datetime,
) -> Optional[Dict[str, Any]]:
    """Resolve nearest active/upcoming ride for a schedule."""
    time_column = await _resolve_rides_time_column(db)
    result = await db.execute(
        text(
            f"""
            SELECT
                id AS ride_id,
                {time_column} AS departure_time,
                LOWER(COALESCE(status::text, '')) AS ride_status
            FROM rides
            WHERE recurrence IS NOT NULL
              AND recurrence->>'schedule_id' = :schedule_id
              AND (
                    LOWER(COALESCE(status::text, '')) IN ('in_progress', 'ongoing')
                    OR (
                        LOWER(COALESCE(status::text, '')) IN ('open', 'scheduled')
                        AND {time_column} >= :now_utc
                    )
                  )
            ORDER BY
                CASE
                    WHEN LOWER(COALESCE(status::text, '')) IN ('in_progress', 'ongoing') THEN 0
                    ELSE 1
                END,
                {time_column} ASC
            LIMIT 1
            """
        ),
        {
            "schedule_id": str(schedule_id),
            "now_utc": now_utc,
        },
    )
    row = result.mappings().first()
    if not row:
        return None
    return {
        "ride_id": row.get("ride_id"),
        "departure_time": row.get("departure_time"),
        "ride_status": row.get("ride_status"),
    }


async def create_recurring_subscription(
    db: AsyncSession,
    *,
    schedule_id: UUID,
    passenger_id: UUID,
    overlap_start_date: date,
    overlap_end_date: date,
    departure_window_start: time,
    departure_window_end: time,
    seats_reserved: int,
    pickup_lat: Optional[float],
    pickup_lng: Optional[float],
    pickup_address: Optional[str],
    pickup_place_id: Optional[str],
    dropoff_lat: Optional[float],
    dropoff_lng: Optional[float],
    dropoff_address: Optional[str],
    dropoff_place_id: Optional[str],
) -> RecurringScheduleSubscription:
    """Create passenger recurring subscription entry."""
    subscription = RecurringScheduleSubscription(
        schedule_id=schedule_id,
        passenger_id=passenger_id,
        overlap_start_date=overlap_start_date,
        overlap_end_date=overlap_end_date,
        departure_window_start=departure_window_start,
        departure_window_end=departure_window_end,
        seats_reserved=seats_reserved,
        pickup_lat=pickup_lat,
        pickup_lng=pickup_lng,
        pickup_address=pickup_address,
        pickup_place_id=pickup_place_id,
        dropoff_lat=dropoff_lat,
        dropoff_lng=dropoff_lng,
        dropoff_address=dropoff_address,
        dropoff_place_id=dropoff_place_id,
        status="active",
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)
    return subscription


async def get_active_subscription_for_schedule_passenger(
    db: AsyncSession,
    schedule_id: UUID,
    passenger_id: UUID,
) -> Optional[RecurringScheduleSubscription]:
    """Get active subscription for schedule/passenger pair if present."""
    result = await db.execute(
        select(RecurringScheduleSubscription)
        .where(
            and_(
                RecurringScheduleSubscription.schedule_id == schedule_id,
                RecurringScheduleSubscription.passenger_id == passenger_id,
                RecurringScheduleSubscription.status == "active",
            )
        )
        .order_by(RecurringScheduleSubscription.created_at.desc())
    )
    return result.scalars().first()


async def get_subscription_for_passenger(
    db: AsyncSession,
    subscription_id: UUID,
    passenger_id: UUID,
) -> Optional[RecurringScheduleSubscription]:
    """Load subscription by id scoped to passenger owner."""
    result = await db.execute(
        select(RecurringScheduleSubscription).where(
            and_(
                RecurringScheduleSubscription.id == subscription_id,
                RecurringScheduleSubscription.passenger_id == passenger_id,
            )
        )
    )
    return result.scalars().first()


async def delete_subscription(
    db: AsyncSession,
    subscription_id: UUID,
) -> None:
    """Hard-delete subscription row (used for rollback on failed create)."""
    result = await db.execute(
        select(RecurringScheduleSubscription).where(
            RecurringScheduleSubscription.id == subscription_id
        )
    )
    subscription = result.scalars().first()
    if not subscription:
        return
    await db.delete(subscription)
    await db.commit()


async def list_passenger_subscriptions_with_schedules(
    db: AsyncSession,
    passenger_id: UUID,
    *,
    active_only: bool = True,
) -> List[tuple[RecurringScheduleSubscription, RecurringSchedule, Optional[str]]]:
    """List passenger subscriptions joined with schedule and driver display name."""
    query = (
        select(RecurringScheduleSubscription, RecurringSchedule, User.full_name)
        .join(
            RecurringSchedule,
            RecurringSchedule.id == RecurringScheduleSubscription.schedule_id,
        )
        .join(User, User.id == RecurringSchedule.user_id)
        .where(RecurringScheduleSubscription.passenger_id == passenger_id)
        .order_by(RecurringScheduleSubscription.created_at.desc())
    )

    if active_only:
        today = date.today()
        query = query.where(
            and_(
                RecurringScheduleSubscription.status == "active",
                RecurringSchedule.is_active == True,
                RecurringScheduleSubscription.overlap_end_date >= today,
            )
        )

    result = await db.execute(query)
    return [(row[0], row[1], row[2]) for row in result.all()]


async def list_active_subscriptions_for_schedule_date(
    db: AsyncSession,
    schedule_id: UUID,
    target_date: date,
    ride_time: time,
) -> List[RecurringScheduleSubscription]:
    """Find subscriptions that should be auto-booked for a schedule date/time."""
    result = await db.execute(
        select(RecurringScheduleSubscription).where(
            and_(
                RecurringScheduleSubscription.schedule_id == schedule_id,
                RecurringScheduleSubscription.status == "active",
                RecurringScheduleSubscription.overlap_start_date <= target_date,
                RecurringScheduleSubscription.overlap_end_date >= target_date,
                RecurringScheduleSubscription.departure_window_start <= ride_time,
                RecurringScheduleSubscription.departure_window_end >= ride_time,
            )
        )
    )
    return list(result.scalars().all())


async def list_active_subscriptions_for_schedule(
    db: AsyncSession,
    schedule_id: UUID,
) -> List[RecurringScheduleSubscription]:
    """List active subscriptions for a schedule."""
    result = await db.execute(
        select(RecurringScheduleSubscription).where(
            and_(
                RecurringScheduleSubscription.schedule_id == schedule_id,
                RecurringScheduleSubscription.status == "active",
            )
        )
    )
    return list(result.scalars().all())


async def mark_subscription_cancelled(
    db: AsyncSession,
    subscription_id: UUID,
    reason: Optional[str],
) -> Optional[RecurringScheduleSubscription]:
    """Mark one subscription as cancelled."""
    result = await db.execute(
        select(RecurringScheduleSubscription).where(
            RecurringScheduleSubscription.id == subscription_id
        )
    )
    subscription = result.scalars().first()
    if not subscription:
        return None

    subscription.status = "cancelled"
    subscription.cancellation_reason = reason
    subscription.cancelled_at = datetime.utcnow()
    await db.commit()
    await db.refresh(subscription)
    return subscription


async def mark_schedule_subscriptions_cancelled(
    db: AsyncSession,
    schedule_id: UUID,
    reason: Optional[str],
) -> int:
    """Cancel all active passenger subscriptions for a schedule."""
    result = await db.execute(
        select(RecurringScheduleSubscription).where(
            and_(
                RecurringScheduleSubscription.schedule_id == schedule_id,
                RecurringScheduleSubscription.status == "active",
            )
        )
    )
    subscriptions = list(result.scalars().all())
    if not subscriptions:
        return 0

    cancelled_at = datetime.utcnow()
    for subscription in subscriptions:
        subscription.status = "cancelled"
        subscription.cancellation_reason = reason
        subscription.cancelled_at = cancelled_at

    await db.commit()
    return len(subscriptions)


async def set_booking_subscription(
    db: AsyncSession,
    booking_id: UUID,
    subscription_id: UUID,
) -> None:
    """Link a canonical ride booking row to recurring subscription id."""
    await db.execute(
        text(
            """
            UPDATE ride_bookings
            SET recurring_subscription_id = :subscription_id
            WHERE id = :booking_id
            """
        ),
        {
            "subscription_id": str(subscription_id),
            "booking_id": str(booking_id),
        },
    )
    await db.commit()


async def get_active_subscription_booking_for_ride(
    db: AsyncSession,
    subscription_id: UUID,
    ride_id: UUID,
) -> Optional[UUID]:
    """Get active booking id for (subscription, ride) pair if one already exists."""
    result = await db.execute(
        text(
            """
            SELECT id
            FROM ride_bookings
            WHERE recurring_subscription_id = :subscription_id
              AND ride_id = :ride_id
              AND LOWER(COALESCE(status, '')) IN ('reserved', 'booked', 'confirmed')
            LIMIT 1
            """
        ),
        {
            "subscription_id": str(subscription_id),
            "ride_id": str(ride_id),
        },
    )
    return result.scalar_one_or_none()


async def get_active_passenger_booking_for_ride(
    db: AsyncSession,
    passenger_id: UUID,
    ride_id: UUID,
) -> Optional[UUID]:
    """Get active booking id for a passenger on a ride."""
    result = await db.execute(
        text(
            """
            SELECT id
            FROM ride_bookings
            WHERE passenger_id = :passenger_id
              AND ride_id = :ride_id
              AND LOWER(COALESCE(status, '')) IN ('reserved', 'booked', 'confirmed')
            LIMIT 1
            """
        ),
        {
            "passenger_id": str(passenger_id),
            "ride_id": str(ride_id),
        },
    )
    return result.scalar_one_or_none()


async def list_future_booking_ids_for_subscription(
    db: AsyncSession,
    subscription_id: UUID,
    now_utc: datetime,
) -> List[UUID]:
    """List future open/scheduled booking ids attached to a recurring subscription."""
    time_column = await _resolve_rides_time_column(db)
    result = await db.execute(
        text(
            f"""
            SELECT rb.id
            FROM ride_bookings rb
            JOIN rides r ON r.id = rb.ride_id
            WHERE rb.recurring_subscription_id = :subscription_id
              AND LOWER(COALESCE(rb.status, '')) IN ('reserved', 'booked', 'confirmed')
              AND LOWER(COALESCE(r.status::text, '')) IN ('open', 'scheduled')
              AND r.{time_column} >= :now_utc
            ORDER BY r.{time_column} ASC
            """
        ),
        {
            "subscription_id": str(subscription_id),
            "now_utc": now_utc,
        },
    )
    return [row.id for row in result]


async def count_subscription_bookings(
    db: AsyncSession,
    subscription_id: UUID,
) -> int:
    """Count bookings linked to a recurring subscription."""
    result = await db.execute(
        text(
            """
            SELECT COUNT(1) AS total
            FROM ride_bookings
            WHERE recurring_subscription_id = :subscription_id
            """
        ),
        {"subscription_id": str(subscription_id)},
    )
    return int(result.scalar_one() or 0)


async def find_next_active_ride_for_subscription(
    db: AsyncSession,
    subscription_id: UUID,
    now_utc: datetime,
) -> Optional[Dict[str, Any]]:
    """Resolve nearest active/upcoming ride for passenger recurring subscription."""
    time_column = await _resolve_rides_time_column(db)
    result = await db.execute(
        text(
            f"""
            SELECT
                r.id AS ride_id,
                r.{time_column} AS departure_time,
                LOWER(COALESCE(r.status::text, '')) AS ride_status
            FROM ride_bookings rb
            JOIN rides r ON r.id = rb.ride_id
            WHERE rb.recurring_subscription_id = :subscription_id
              AND LOWER(COALESCE(rb.status, '')) IN ('reserved', 'booked', 'confirmed')
              AND (
                    LOWER(COALESCE(r.status::text, '')) IN ('in_progress', 'ongoing')
                    OR (
                        LOWER(COALESCE(r.status::text, '')) IN ('open', 'scheduled')
                        AND r.{time_column} >= :now_utc
                    )
                  )
            ORDER BY
                CASE
                    WHEN LOWER(COALESCE(r.status::text, '')) IN ('in_progress', 'ongoing') THEN 0
                    ELSE 1
                END,
                r.{time_column} ASC
            LIMIT 1
            """
        ),
        {
            "subscription_id": str(subscription_id),
            "now_utc": now_utc,
        },
    )
    row = result.mappings().first()
    if not row:
        return None
    return {
        "ride_id": row.get("ride_id"),
        "departure_time": row.get("departure_time"),
        "ride_status": row.get("ride_status"),
    }
