"""
Module: Rides & Scheduling - Service Layer (Prompt 5)
Purpose: Business logic orchestration for atomic booking, geo-search, and schedules
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: December 8, 2025
Notes: Implements 10 core functions including notification stubs
"""

from datetime import datetime, date, time, timedelta, timezone
import math
from typing import List, Optional, Dict, Any
from uuid import UUID
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text, select, and_, func, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.modules.rides import crud_v2
from app.modules.rides import service as rides_service
from app.modules.rides import crud as rides_crud
from app.modules.rides.schemas_v2 import (
    RideCreateV2,
    RideUpdateV2,
    RideSearchRequest,
    BookingRequest,
    ScheduleCreate,
    ScheduleUpdate,
    RecurringScheduleDiscoverRequest,
    RecurringScheduleDiscoverPublic,
    RecurringScheduleBookSeriesRequest,
    RecurringScheduleBookSeriesResponse,
    RecurringDriverHomePublic,
    RecurringPassengerHomePublic,
    RecurringRideResolutionPublic,
    GeoPoint,
    NotificationPayload
)
from app.modules.rides.schemas import RideBookingCreate
from app.core.fare_calculator import calculate_fare
from app.core.exceptions import NotFoundError, ConflictError, ValidationError, ForbiddenError
from app.models.ride import Ride
from app.models.booking import Booking
from app.models.recurring_schedule import RecurringSchedule
from app.models.recurring_schedule_subscription import RecurringScheduleSubscription
from app.modules.rides.schema_compat import ensure_rides_schema_compat


DEFAULT_SCHEDULE_DURATION_MINUTES = 45
AVG_URBAN_SPEED_KMH = 40.0
ROUTE_PICKUP_DEVIATION_KM = 1.0
LEGACY_MAIN_PROXIMITY_KM = 5.0
LEGACY_ROUTE_DEVIATION_KM = 1.0
DYNAMIC_MAIN_PERCENT = 0.20
DYNAMIC_CORRIDOR_PERCENT = 0.05
DYNAMIC_MAIN_MIN_KM = 0.2
DYNAMIC_MAIN_MAX_KM = 5.0
DYNAMIC_CORRIDOR_MIN_KM = 0.2
DYNAMIC_CORRIDOR_MAX_KM = 3.0
WEEKDAY_INDEX = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4,
    "Sat": 5,
    "Sun": 6,
}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _dynamic_discovery_thresholds(route_distance_km: Optional[float]) -> tuple[float, float]:
    """Return (main_threshold_km, corridor_threshold_km) for recurring discovery."""
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


def _extract_duration_from_meta(meta: Optional[Dict[str, Any]]) -> Optional[int]:
    if not isinstance(meta, dict):
        return None
    value = meta.get("estimated_duration_minutes")
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _resolve_schedule_duration_minutes(
    *,
    route_distance_km: Optional[float],
    recurrence_meta: Optional[Dict[str, Any]],
) -> int:
    meta_duration = _extract_duration_from_meta(recurrence_meta)
    if meta_duration is not None:
        return max(1, min(720, meta_duration))

    if route_distance_km and route_distance_km > 0:
        inferred = int(math.ceil((route_distance_km / AVG_URBAN_SPEED_KMH) * 60))
        if inferred > 0:
            return max(1, min(720, inferred))

    return DEFAULT_SCHEDULE_DURATION_MINUTES


def _normalize_schedule_days(days: List[str]) -> List[str]:
    normalized = []
    for day in days:
        short = (day or "").strip()[:3].title()
        if short in WEEKDAY_INDEX and short not in normalized:
            normalized.append(short)
    return normalized


def _expand_weekly_segments(days: List[str], start_minute: int, duration_minutes: int) -> List[tuple[int, int, int]]:
    segments: List[tuple[int, int, int]] = []
    end_minute = start_minute + duration_minutes
    for day in days:
        day_idx = WEEKDAY_INDEX.get(day)
        if day_idx is None:
            continue
        if end_minute <= 1440:
            segments.append((day_idx, start_minute, end_minute))
            continue

        segments.append((day_idx, start_minute, 1440))
        next_day_idx = (day_idx + 1) % 7
        segments.append((next_day_idx, 0, end_minute - 1440))
    return segments


def _range_contains_weekday(start_date: date, end_date: date, weekday_idx: int) -> bool:
    days_until_target = (weekday_idx - start_date.weekday()) % 7
    first_target_date = start_date + timedelta(days=days_until_target)
    return first_target_date <= end_date


def _find_schedule_overlap_day(
    *,
    days_a: List[str],
    start_time_a: time,
    duration_a: int,
    start_date_a: date,
    end_date_a: date,
    days_b: List[str],
    start_time_b: time,
    duration_b: int,
    start_date_b: date,
    end_date_b: date,
) -> Optional[str]:
    overlap_start = max(start_date_a, start_date_b)
    overlap_end = min(end_date_a, end_date_b)
    if overlap_start > overlap_end:
        return None

    start_minute_a = (start_time_a.hour * 60) + start_time_a.minute
    start_minute_b = (start_time_b.hour * 60) + start_time_b.minute
    segments_a = _expand_weekly_segments(days_a, start_minute_a, duration_a)
    segments_b = _expand_weekly_segments(days_b, start_minute_b, duration_b)

    reverse_day_lookup = {v: k for k, v in WEEKDAY_INDEX.items()}
    for day_a, seg_a_start, seg_a_end in segments_a:
        for day_b, seg_b_start, seg_b_end in segments_b:
            if day_a != day_b:
                continue
            if seg_a_start >= seg_b_end or seg_a_end <= seg_b_start:
                continue
            if not _range_contains_weekday(overlap_start, overlap_end, day_a):
                continue
            return reverse_day_lookup.get(day_a, "Unknown")

    return None


def _count_matching_dates_in_overlap(
    days_of_week: List[str],
    overlap_start: date,
    overlap_end: date,
) -> tuple[Optional[date], int]:
    """Count schedule days in overlap range and return first matching date."""
    if overlap_start > overlap_end:
        return None, 0

    normalized_days = _normalize_schedule_days(days_of_week)
    allowed_weekdays = {
        WEEKDAY_INDEX[day]
        for day in normalized_days
        if day in WEEKDAY_INDEX
    }
    if not allowed_weekdays:
        return None, 0

    first_matching_date: Optional[date] = None
    matching_count = 0
    cursor = overlap_start
    one_day = timedelta(days=1)

    while cursor <= overlap_end:
        if cursor.weekday() in allowed_weekdays:
            matching_count += 1
            if first_matching_date is None:
                first_matching_date = cursor
        cursor += one_day

    return first_matching_date, matching_count


def _matching_dates_in_overlap(
    days_of_week: List[str],
    overlap_start: date,
    overlap_end: date,
) -> List[date]:
    """Return concrete matching dates for schedule days inside overlap range."""
    if overlap_start > overlap_end:
        return []

    normalized_days = _normalize_schedule_days(days_of_week)
    if not normalized_days:
        normalized_days = list(WEEKDAY_INDEX.keys())

    allowed_weekdays = {
        WEEKDAY_INDEX[day]
        for day in normalized_days
        if day in WEEKDAY_INDEX
    }
    if not allowed_weekdays:
        return []

    dates: List[date] = []
    cursor = overlap_start
    one_day = timedelta(days=1)
    while cursor <= overlap_end:
        if cursor.weekday() in allowed_weekdays:
            dates.append(cursor)
        cursor += one_day
    return dates


def _combine_schedule_datetime(target_date: date, ride_time: time) -> datetime:
    """Build timezone-aware UTC datetime for a schedule day and time."""
    return datetime.combine(target_date, ride_time).replace(tzinfo=timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_departure_time(dt_value: Optional[datetime]) -> Optional[datetime]:
    if dt_value is None:
        return None
    if dt_value.tzinfo is None:
        return dt_value.replace(tzinfo=timezone.utc)
    return dt_value.astimezone(timezone.utc)


def _extract_booking_id_from_response(response: Dict[str, Any]) -> UUID:
    """Parse booking UUID from v1 booking service standardized response."""
    if response.get("status") != "ok":
        error = str(response.get("error") or "Booking failed")
        raise ValidationError(error)

    data = response.get("data")
    if not isinstance(data, dict):
        raise ValidationError("Booking response payload was malformed")

    booking_id_raw = data.get("id")
    if not booking_id_raw:
        raise ValidationError("Booking id missing in booking response")

    try:
        return UUID(str(booking_id_raw))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Booking id was invalid") from exc


async def _materialize_or_get_schedule_ride_for_date(
    db: AsyncSession,
    schedule: RecurringSchedule,
    target_date: date,
) -> tuple[Ride, bool]:
    """Idempotently materialize one ride instance for schedule/date."""
    existing = await crud_v2.get_materialized_ride_for_schedule_date(
        db,
        schedule.id,
        target_date,
    )
    if existing:
        return existing, False

    start_datetime = _combine_schedule_datetime(target_date, schedule.time)

    try:
        ride = await crud_v2.create_ride(
            db=db,
            driver_id=schedule.user_id,
            start_point_lat=schedule.start_point_lat,
            start_point_lng=schedule.start_point_lng,
            start_point_address=schedule.start_point_address,
            end_point_lat=schedule.end_point_lat,
            end_point_lng=schedule.end_point_lng,
            end_point_address=schedule.end_point_address,
            start_time=start_datetime,
            seats_offered=int(schedule.seats_offered),
            base_price=schedule.base_price,
            polyline_main=schedule.polyline_main,
            buffer_seats=int(schedule.buffer_seats),
            recurrence={
                "schedule_id": str(schedule.id),
                "start_date": schedule.start_date.isoformat(),
                "end_date": schedule.end_date.isoformat(),
            },
        )
        return ride, True
    except IntegrityError:
        await db.rollback()
        existing_after = await crud_v2.get_materialized_ride_for_schedule_date(
            db,
            schedule.id,
            target_date,
        )
        if existing_after:
            return existing_after, False
        raise


async def _ensure_driver_schedule_next_ride(
    db: AsyncSession,
    schedule: RecurringSchedule,
) -> Optional[Dict[str, Any]]:
    """Resolve nearest active/upcoming ride for driver schedule and materialize if needed."""
    now_utc = _utc_now()
    next_ride = await crud_v2.find_next_active_ride_for_schedule(db, schedule.id, now_utc)
    if next_ride:
        return next_ride

    if not schedule.is_active:
        return None

    overlap_start = max(schedule.start_date, now_utc.date())
    overlap_end = schedule.end_date
    if overlap_start > overlap_end:
        return None

    candidate_dates = _matching_dates_in_overlap(
        list(schedule.days_of_week or []),
        overlap_start,
        overlap_end,
    )

    for candidate_date in candidate_dates:
        candidate_dt = _combine_schedule_datetime(candidate_date, schedule.time)
        if candidate_dt < now_utc:
            continue
        try:
            await _materialize_or_get_schedule_ride_for_date(db, schedule, candidate_date)
        except Exception:
            continue

        next_ride = await crud_v2.find_next_active_ride_for_schedule(
            db,
            schedule.id,
            now_utc,
        )
        if next_ride:
            return next_ride

    return None


def _is_time_inside_window(
    ride_time: time,
    window_start: time,
    window_end: time,
) -> bool:
    return window_start <= ride_time <= window_end


async def _acquire_schedule_lock(db: AsyncSession, user_id: UUID, scope: str) -> None:
    try:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"{scope}:{user_id}"},
        )
    except Exception:
        # Advisory locks are PostgreSQL-specific. Skip silently for compatibility.
        return


def _window_for_schedule_datetime(target_date: date, ride_time: time, duration_minutes: int) -> tuple[datetime, datetime]:
    start_utc = _combine_schedule_datetime(target_date, ride_time)
    end_utc = start_utc + timedelta(minutes=max(1, int(duration_minutes)))
    return start_utc, end_utc


def _time_overlap(start_a: time, duration_a: int, start_b: time, duration_b: int) -> bool:
    a_start = start_a.hour * 60 + start_a.minute
    a_end = a_start + max(1, int(duration_a))
    b_start = start_b.hour * 60 + start_b.minute
    b_end = b_start + max(1, int(duration_b))
    return a_start < b_end and b_start < a_end


def _is_schedule_active_on_date(schedule: RecurringSchedule, target_date: date) -> bool:
    if not schedule.is_active:
        return False
    if target_date < schedule.start_date or target_date > schedule.end_date:
        return False
    normalized_days = _normalize_schedule_days(list(schedule.days_of_week or []))
    if not normalized_days:
        return False
    allowed = {
        WEEKDAY_INDEX[d]
        for d in normalized_days
        if d in WEEKDAY_INDEX
    }
    return target_date.weekday() in allowed


async def _has_passenger_active_subscription_overlap(
    db: AsyncSession,
    *,
    user_id: UUID,
    target_date: date,
    ride_time: time,
    duration_minutes: int,
    exclude_schedule_id: Optional[UUID] = None,
) -> bool:
    query = (
        select(RecurringSchedule)
        .join(
            RecurringScheduleSubscription,
            RecurringScheduleSubscription.schedule_id == RecurringSchedule.id,
        )
        .where(
            and_(
                RecurringScheduleSubscription.passenger_id == user_id,
                func.lower(func.coalesce(cast(RecurringScheduleSubscription.status, String), "")) == "active",
                RecurringSchedule.is_active.is_(True),
                RecurringScheduleSubscription.overlap_start_date <= target_date,
                RecurringScheduleSubscription.overlap_end_date >= target_date,
                RecurringSchedule.start_date <= target_date,
                RecurringSchedule.end_date >= target_date,
            )
        )
    )
    if exclude_schedule_id is not None:
        query = query.where(RecurringSchedule.id != exclude_schedule_id)

    rows = await db.execute(query)
    for schedule in rows.scalars().all():
        if not _is_schedule_active_on_date(schedule, target_date):
            continue
        schedule_duration = _resolve_schedule_duration_minutes(
            route_distance_km=crud_v2.haversine_distance(
                schedule.start_point_lat,
                schedule.start_point_lng,
                schedule.end_point_lat,
                schedule.end_point_lng,
            ),
            recurrence_meta=schedule.recurrence_meta,
        )
        if _time_overlap(schedule.time, schedule_duration, ride_time, duration_minutes):
            return True
    return False


async def _driver_has_ride_overlap_for_schedule_date(
    db: AsyncSession,
    *,
    user_id: UUID,
    target_date: date,
    ride_time: time,
    duration_minutes: int,
) -> Optional[Dict[str, Any]]:
    start_utc, end_utc = _window_for_schedule_datetime(target_date, ride_time, duration_minutes)
    return await rides_service._find_driver_overlap(
        db,
        user_id=user_id,
        window_start_utc=start_utc,
        window_end_utc=end_utc,
    )


async def _passenger_has_common_slot_overlap_for_schedule_date(
    db: AsyncSession,
    *,
    user_id: UUID,
    schedule_id: UUID,
    target_date: date,
    ride_time: time,
    duration_minutes: int,
) -> bool:
    start_utc, end_utc = _window_for_schedule_datetime(target_date, ride_time, duration_minutes)
    overlap = await rides_service._find_passenger_overlap(
        db,
        user_id=user_id,
        window_start_utc=start_utc,
        window_end_utc=end_utc,
    )
    if overlap:
        return True

    return await _has_passenger_active_subscription_overlap(
        db,
        user_id=user_id,
        target_date=target_date,
        ride_time=ride_time,
        duration_minutes=duration_minutes,
        exclude_schedule_id=schedule_id,
    )


# ============================================
# 1. CREATE RIDE
# ============================================

async def create_ride_service(
    db: AsyncSession,
    driver_id: UUID,
    data: RideCreateV2
) -> Ride:
    """
    Create a new ride (Service Function #1).
    
    Args:
        db: Database session
        driver_id: Driver's user ID
        data: Ride creation data
    
    Returns:
        Created ride object
    """
    # Validate driver exists and has active profile
    # (In production, check driver verification status)
    
    distance_km = crud_v2.haversine_distance(
        data.start_point.lat,
        data.start_point.lng,
        data.end_point.lat,
        data.end_point.lng,
    )
    fare = calculate_fare(distance_km=distance_km, total_seats=data.seats_offered)

    ride = await crud_v2.create_ride(
        db=db,
        driver_id=driver_id,
        start_point_lat=data.start_point.lat,
        start_point_lng=data.start_point.lng,
        start_point_address=data.start_point.address or "",
        end_point_lat=data.end_point.lat,
        end_point_lng=data.end_point.lng,
        end_point_address=data.end_point.address or "",
        start_time=data.start_time,
        seats_offered=data.seats_offered,
        base_price=Decimal(str(fare.fare_per_seat)),
        polyline_main=data.polyline_main,
        polyline_alternates=data.polyline_alternates,
        buffer_seats=data.buffer_seats,
        recurrence=data.recurrence
    )
    
    return ride


# ============================================
# 2. UPDATE RIDE
# ============================================

async def update_ride_service(
    db: AsyncSession,
    ride_id: UUID,
    driver_id: UUID,
    data: RideUpdateV2
) -> Ride:
    """
    Update ride details (Service Function #2).
    
    Validates:
    - Ride exists
    - User is the driver
    - Ride is not already completed/cancelled
    
    Args:
        db: Database session
        ride_id: Ride ID
        driver_id: Driver's user ID (for permission check)
        data: Update data
    
    Returns:
        Updated ride object
    """
    ride = await crud_v2.get_ride_by_id(db, ride_id)
    if not ride:
        raise NotFoundError(f"Ride {ride_id} not found")
    
    # Permission check
    if ride.driver_id != driver_id:
        raise ForbiddenError("You can only update your own rides")
    
    # Status check
    if ride.status in ["COMPLETED", "CANCELLED"]:
        raise ConflictError(f"Cannot update ride with status {ride.status}")
    
    # Build updates dict
    updates = {}
    if data.start_time is not None:
        updates["start_time"] = data.start_time
    if data.seats_offered is not None:
        updates["seats_offered"] = data.seats_offered
    if data.buffer_seats is not None:
        updates["buffer_seats"] = data.buffer_seats
    if data.base_price is not None:
        updates["base_price"] = data.base_price
    if data.status is not None:
        updates["status"] = data.status
    
    updated_ride = await crud_v2.update_ride(db, ride_id, **updates)
    
    # Notify passengers if ride was updated
    await send_booking_notification(
        ride_id=ride_id,
        notification_type="RIDE_UPDATED",
        message=f"Ride has been updated by the driver",
        data={"ride_id": str(ride_id)}
    )
    
    return updated_ride


# ============================================
# 3. GET DRIVER UPCOMING RIDES
# ============================================

async def get_driver_upcoming_rides_service(
    db: AsyncSession,
    driver_id: UUID,
    limit: int = 50
) -> List[Ride]:
    """
    Get driver's upcoming rides (Service Function #3).
    
    Args:
        db: Database session
        driver_id: Driver's user ID
        limit: Maximum number of rides
    
    Returns:
        List of upcoming rides
    """
    rides = await crud_v2.get_driver_upcoming_rides(db, driver_id, limit)
    return rides


# ============================================
# 4. SEARCH RIDES (GEO-RADIUS)
# ============================================

async def search_rides_service(
    db: AsyncSession,
    search_request: RideSearchRequest
) -> List[Ride]:
    """
    Search rides within geo-radius (Service Function #4 - Prompt 5 core).
    
    Uses Haversine formula to find rides near origin and destination.
    
    Args:
        db: Database session
        search_request: Search parameters
    
    Returns:
        List of matching rides
    """
    rides = await crud_v2.search_rides_geo_radius(
        db=db,
        origin_lat=search_request.origin.lat,
        origin_lng=search_request.origin.lng,
        dest_lat=search_request.destination.lat,
        dest_lng=search_request.destination.lng,
        radius_km=search_request.radius_km,
        target_date=search_request.date,
        min_seats=search_request.min_seats,
        max_price=search_request.max_price
    )
    
    return rides


# ============================================
# 5. BOOK SEAT ATOMICALLY
# ============================================

async def book_seat_service(
    db: AsyncSession,
    passenger_id: UUID,
    booking_request: BookingRequest
) -> Booking:
    """
    Book seats atomically (Service Function #5 - Prompt 5 CORE).
    
    Prevents race conditions using SELECT FOR UPDATE.
    
    Args:
        db: Database session
        passenger_id: Passenger's user ID
        booking_request: Booking details
    
    Returns:
        Created booking object
    """
    # Validate passenger exists and is verified
    # (In production, check passenger verification status)
    
    booking = await crud_v2.book_seat_atomic(
        db=db,
        ride_id=booking_request.ride_id,
        passenger_id=passenger_id,
        seats_reserved=booking_request.seats_reserved
    )
    
    # Send notification to driver and passenger
    await send_booking_notification(
        ride_id=booking_request.ride_id,
        booking_id=booking.id,
        notification_type="BOOKING_CONFIRMED",
        message=f"Booking confirmed for {booking_request.seats_reserved} seat(s)",
        data={
            "booking_id": str(booking.id),
            "passenger_id": str(passenger_id),
            "seats": booking_request.seats_reserved,
            "fare": float(booking.fare)
        }
    )
    
    return booking


# ============================================
# 6. CANCEL BOOKING
# ============================================

async def cancel_booking_service(
    db: AsyncSession,
    booking_id: UUID,
    user_id: UUID,
    reason: Optional[str] = None
) -> Booking:
    """
    Cancel booking and release seats (Service Function #6).
    
    Args:
        db: Database session
        booking_id: Booking to cancel
        user_id: User requesting cancellation
        reason: Cancellation reason
    
    Returns:
        Updated booking object
    """
    booking = await crud_v2.cancel_booking(db, booking_id, user_id)
    
    # Send notification
    await send_booking_notification(
        ride_id=booking.ride_id,
        booking_id=booking_id,
        notification_type="BOOKING_CANCELLED",
        message=f"Booking has been cancelled. Reason: {reason or 'Not provided'}",
        data={
            "booking_id": str(booking_id),
            "reason": reason
        }
    )
    
    return booking


# ============================================
# 7. CREATE RECURRING SCHEDULE
# ============================================

async def create_recurring_schedule_service(
    db: AsyncSession,
    user_id: UUID,
    data: ScheduleCreate
) -> RecurringSchedule:
    """
    Create recurring ride schedule (Service Function #7 - Prompt 5 feature).
    
    Args:
        db: Database session
        user_id: User creating schedule (driver)
        data: Schedule details
    
    Returns:
        Created schedule object
    """
    await ensure_rides_schema_compat(db)

    normalized_days = _normalize_schedule_days(data.days_of_week)
    distance_km = crud_v2.haversine_distance(
        data.start_point.lat,
        data.start_point.lng,
        data.end_point.lat,
        data.end_point.lng,
    )
    duration_minutes = _resolve_schedule_duration_minutes(
        route_distance_km=distance_km,
        recurrence_meta=data.recurrence_meta,
    )
    recurrence_meta = dict(data.recurrence_meta or {})
    recurrence_meta["estimated_duration_minutes"] = duration_minutes

    await _acquire_schedule_lock(db, user_id, "recurring-schedule-create")
    await rides_service._acquire_user_schedule_lock(db, user_id, "driver-create-ride")
    existing_schedules = await crud_v2.list_user_schedules(db, user_id, active_only=True)
    for existing in existing_schedules:
        existing_days = _normalize_schedule_days(list(existing.days_of_week or []))
        existing_distance_km = crud_v2.haversine_distance(
            existing.start_point_lat,
            existing.start_point_lng,
            existing.end_point_lat,
            existing.end_point_lng,
        )
        existing_duration = _resolve_schedule_duration_minutes(
            route_distance_km=existing_distance_km,
            recurrence_meta=existing.recurrence_meta,
        )
        overlap_day = _find_schedule_overlap_day(
            days_a=existing_days,
            start_time_a=existing.time,
            duration_a=existing_duration,
            start_date_a=existing.start_date,
            end_date_a=existing.end_date,
            days_b=normalized_days,
            start_time_b=data.ride_time,
            duration_b=duration_minutes,
            start_date_b=data.start_date,
            end_date_b=data.end_date,
        )
        if overlap_day:
            raise ValidationError(
                "Recurring schedule overlaps with an existing active schedule "
                f"on {overlap_day}"
            )

    now_utc = _utc_now()
    candidate_dates = _matching_dates_in_overlap(
        normalized_days,
        data.start_date,
        data.end_date,
    )
    for candidate_date in candidate_dates:
        candidate_dt = _combine_schedule_datetime(candidate_date, data.ride_time)
        if candidate_dt < now_utc:
            continue
        conflicting_ride = await _driver_has_ride_overlap_for_schedule_date(
            db,
            user_id=user_id,
            target_date=candidate_date,
            ride_time=data.ride_time,
            duration_minutes=duration_minutes,
        )
        if conflicting_ride:
            raise ValidationError(
                "Recurring schedule overlaps with an existing active ride slot "
                f"({rides_service._format_slot_window(conflicting_ride['start_time'], conflicting_ride['end_time'])})."
            )

    fare = calculate_fare(distance_km=distance_km, total_seats=data.seats_offered)

    schedule = await crud_v2.save_recurring_schedule(
        db=db,
        user_id=user_id,
        days_of_week=normalized_days,
        time=data.ride_time,
        start_point_lat=data.start_point.lat,
        start_point_lng=data.start_point.lng,
        start_point_address=data.start_point.address or "",
        end_point_lat=data.end_point.lat,
        end_point_lng=data.end_point.lng,
        end_point_address=data.end_point.address or "",
        seats_offered=data.seats_offered,
        base_price=Decimal(str(fare.fare_per_seat)),
        start_date=data.start_date,
        end_date=data.end_date,
        polyline_main=data.polyline_main,
        buffer_seats=data.buffer_seats,
        recurrence_meta=recurrence_meta,
    )
    
    return schedule


# ============================================
# 8. LIST USER SCHEDULES
# ============================================

async def list_user_schedules_service(
    db: AsyncSession,
    user_id: UUID,
    active_only: bool = True
) -> List[RecurringSchedule]:
    """
    List user's recurring schedules (Service Function #8).
    
    Args:
        db: Database session
        user_id: User ID
        active_only: Return only active schedules
    
    Returns:
        List of schedules
    """
    await ensure_rides_schema_compat(db)

    schedules = await crud_v2.list_user_schedules(db, user_id, active_only)
    return schedules


async def discover_recurring_schedules_service(
    db: AsyncSession,
    user_id: UUID,
    search_request: RecurringScheduleDiscoverRequest,
) -> List[RecurringScheduleDiscoverPublic]:
    """
    Discover recurring schedules for passengers.

    Passenger date range is treated as "every day" between from/until dates.
    Driver schedule days are matched against that overlap range.
    """
    await ensure_rides_schema_compat(db)

    candidates = await crud_v2.list_recurring_schedules_for_discovery(
        db=db,
        passenger_from_date=search_request.passenger_from_date,
        passenger_until_date=search_request.passenger_until_date,
        min_seats=search_request.min_seats,
        driver_total_seats=search_request.driver_total_seats,
        max_price=search_request.max_price,
        exclude_user_id=user_id,
    )

    results: List[RecurringScheduleDiscoverPublic] = []
    now_utc = _utc_now()

    for schedule, driver_name in candidates:
        route_distance_km = rides_crud._polyline_length_km(  # pylint: disable=protected-access
            getattr(schedule, "polyline_main", None)
        )
        if route_distance_km is None:
            start_lat = getattr(schedule, "start_point_lat", None)
            start_lng = getattr(schedule, "start_point_lng", None)
            end_lat = getattr(schedule, "end_point_lat", None)
            end_lng = getattr(schedule, "end_point_lng", None)
            if (
                start_lat is not None
                and start_lng is not None
                and end_lat is not None
                and end_lng is not None
            ):
                route_distance_km = crud_v2.haversine_distance(
                    start_lat,
                    start_lng,
                    end_lat,
                    end_lng,
                )
        main_threshold_km, corridor_threshold_km = _dynamic_discovery_thresholds(
            route_distance_km
        )

        origin_distance = crud_v2.haversine_distance(
            search_request.origin.lat,
            search_request.origin.lng,
            schedule.start_point_lat,
            schedule.start_point_lng,
        )

        destination_distance = crud_v2.haversine_distance(
            search_request.destination.lat,
            search_request.destination.lng,
            schedule.end_point_lat,
            schedule.end_point_lng,
        )
        if destination_distance > main_threshold_km:
            continue

        pickup_route_distance = rides_crud._point_to_polyline_distance_km(
            search_request.origin.lat,
            search_request.origin.lng,
            getattr(schedule, "polyline_main", None),
        )

        pickup_matches = (
            origin_distance <= main_threshold_km or
            (
                pickup_route_distance is not None and
                pickup_route_distance <= corridor_threshold_km
            )
        )
        if not pickup_matches:
            continue

        if not (
            search_request.departure_window_start
            <= schedule.time
            <= search_request.departure_window_end
        ):
            continue

        overlap_start = max(schedule.start_date, search_request.passenger_from_date)
        overlap_end = min(schedule.end_date, search_request.passenger_until_date)
        first_matching_date, matching_days_count = _count_matching_dates_in_overlap(
            list(schedule.days_of_week or []),
            overlap_start,
            overlap_end,
        )

        if not first_matching_date or matching_days_count <= 0:
            continue

        schedule_distance_km = crud_v2.haversine_distance(
            schedule.start_point_lat,
            schedule.start_point_lng,
            schedule.end_point_lat,
            schedule.end_point_lng,
        )
        schedule_duration = _resolve_schedule_duration_minutes(
            route_distance_km=schedule_distance_km,
            recurrence_meta=schedule.recurrence_meta,
        )
        candidate_dates = _matching_dates_in_overlap(
            list(schedule.days_of_week or []),
            overlap_start,
            overlap_end,
        )
        bookable_dates = [
            d for d in candidate_dates if _combine_schedule_datetime(d, schedule.time) >= now_utc
        ]
        if not bookable_dates:
            continue

        has_common_slot_conflict = False
        for candidate_date in bookable_dates:
            if await _passenger_has_common_slot_overlap_for_schedule_date(
                db,
                user_id=user_id,
                schedule_id=schedule.id,
                target_date=candidate_date,
                ride_time=schedule.time,
                duration_minutes=schedule_duration,
            ):
                has_common_slot_conflict = True
                break
        if has_common_slot_conflict:
            # Hidden by design: unavailable schedules are not returned in search.
            continue

        first_matching_date = bookable_dates[0]
        matching_days_count = len(bookable_dates)

        template_available_seats = max(
            0,
            int(schedule.seats_offered) - int(schedule.buffer_seats),
        )

        results.append(
            RecurringScheduleDiscoverPublic(
                schedule_id=schedule.id,
                driver_id=schedule.user_id,
                driver_name=driver_name,
                days_of_week=list(schedule.days_of_week or []),
                ride_time=schedule.time,
                start_point=GeoPoint(
                    lat=schedule.start_point_lat,
                    lng=schedule.start_point_lng,
                    address=schedule.start_point_address,
                ),
                end_point=GeoPoint(
                    lat=schedule.end_point_lat,
                    lng=schedule.end_point_lng,
                    address=schedule.end_point_address,
                ),
                seats_offered=int(schedule.seats_offered),
                buffer_seats=int(schedule.buffer_seats),
                template_available_seats=template_available_seats,
                base_price=schedule.base_price,
                schedule_start_date=schedule.start_date,
                schedule_end_date=schedule.end_date,
                overlap_start_date=overlap_start,
                overlap_end_date=overlap_end,
                first_matching_date=first_matching_date,
                matching_days_count=matching_days_count,
                distance_from_origin_km=round(
                    min(
                        origin_distance,
                        pickup_route_distance
                        if pickup_route_distance is not None
                        else float("inf"),
                    ),
                    3,
                ),
                distance_to_destination_km=round(destination_distance, 3),
            )
        )

    results.sort(
        key=lambda item: (
            item.first_matching_date,
            item.ride_time,
            item.distance_from_origin_km,
        )
    )
    return results


def _build_recurring_booking_payload(
    *,
    ride_id: UUID,
    seats_reserved: int,
    pickup_lat: Optional[float],
    pickup_lng: Optional[float],
    pickup_address: Optional[str],
    pickup_place_id: Optional[str],
    dropoff_lat: Optional[float],
    dropoff_lng: Optional[float],
    dropoff_address: Optional[str],
    dropoff_place_id: Optional[str],
) -> RideBookingCreate:
    return RideBookingCreate(
        ride_id=ride_id,
        booked_seats=seats_reserved,
        pickup_lat=pickup_lat,
        pickup_lng=pickup_lng,
        pickup_address=pickup_address,
        pickup_place_id=pickup_place_id,
        dropoff_lat=dropoff_lat,
        dropoff_lng=dropoff_lng,
        dropoff_address=dropoff_address,
        dropoff_place_id=dropoff_place_id,
    )


async def _ensure_subscription_booking_for_ride(
    db: AsyncSession,
    *,
    subscription: RecurringScheduleSubscription,
    ride: Ride,
) -> UUID:
    """Ensure passenger has booking for ride linked to subscription."""
    existing_subscription_booking = await crud_v2.get_active_subscription_booking_for_ride(
        db,
        subscription.id,
        ride.id,
    )
    if existing_subscription_booking:
        return existing_subscription_booking

    payload = _build_recurring_booking_payload(
        ride_id=ride.id,
        seats_reserved=max(1, int(subscription.seats_reserved)),
        pickup_lat=subscription.pickup_lat,
        pickup_lng=subscription.pickup_lng,
        pickup_address=subscription.pickup_address,
        pickup_place_id=subscription.pickup_place_id,
        dropoff_lat=subscription.dropoff_lat,
        dropoff_lng=subscription.dropoff_lng,
        dropoff_address=subscription.dropoff_address,
        dropoff_place_id=subscription.dropoff_place_id,
    )

    try:
        booking_response = await rides_service.book_ride_service(
            db,
            subscription.passenger_id,
            payload,
        )
        booking_id = _extract_booking_id_from_response(booking_response)
        await crud_v2.set_booking_subscription(db, booking_id, subscription.id)
        return booking_id
    except HTTPException as exc:
        detail_text = str(getattr(exc, "detail", "") or "").lower()
        already_booked = (
            "already have an active booking for this ride" in detail_text
            or "already booked this ride" in detail_text
            or "you already booked this ride" in detail_text
        )
        if not already_booked:
            raise

        existing_passenger_booking = await crud_v2.get_active_passenger_booking_for_ride(
            db,
            subscription.passenger_id,
            ride.id,
        )
        if existing_passenger_booking is None:
            raise

        await crud_v2.set_booking_subscription(
            db,
            existing_passenger_booking,
            subscription.id,
        )
        return existing_passenger_booking


async def _rollback_recurring_series_create(
    db: AsyncSession,
    *,
    passenger_id: UUID,
    subscription_id: UUID,
    booking_ids: List[UUID],
) -> None:
    """Best-effort rollback for partially-created recurring series booking."""
    for booking_id in reversed(booking_ids):
        try:
            await rides_crud.cancel_booking(
                db,
                booking_id,
                passenger_id,
                "Recurring series booking rollback",
            )
        except Exception:
            continue

    try:
        await crud_v2.delete_subscription(db, subscription_id)
    except Exception:
        pass


async def _ensure_passenger_subscription_next_ride(
    db: AsyncSession,
    *,
    subscription: RecurringScheduleSubscription,
    schedule: RecurringSchedule,
) -> Optional[Dict[str, Any]]:
    """Resolve next ride for passenger subscription, materializing/booking if required."""
    now_utc = _utc_now()
    next_ride = await crud_v2.find_next_active_ride_for_subscription(
        db,
        subscription.id,
        now_utc,
    )
    if next_ride:
        return next_ride

    if subscription.status != "active" or not schedule.is_active:
        return None

    if not _is_time_inside_window(
        schedule.time,
        subscription.departure_window_start,
        subscription.departure_window_end,
    ):
        return None

    overlap_start = max(
        schedule.start_date,
        subscription.overlap_start_date,
        now_utc.date(),
    )
    overlap_end = min(schedule.end_date, subscription.overlap_end_date)
    if overlap_start > overlap_end:
        return None

    candidate_dates = _matching_dates_in_overlap(
        list(schedule.days_of_week or []),
        overlap_start,
        overlap_end,
    )
    for candidate_date in candidate_dates:
        candidate_dt = _combine_schedule_datetime(candidate_date, schedule.time)
        if candidate_dt < now_utc:
            continue

        try:
            ride, _ = await _materialize_or_get_schedule_ride_for_date(
                db,
                schedule,
                candidate_date,
            )
            await _ensure_subscription_booking_for_ride(
                db,
                subscription=subscription,
                ride=ride,
            )
        except Exception:
            continue

        next_ride = await crud_v2.find_next_active_ride_for_subscription(
            db,
            subscription.id,
            now_utc,
        )
        if next_ride:
            return next_ride

    return None


async def book_recurring_schedule_series_service(
    db: AsyncSession,
    user_id: UUID,
    schedule_id: UUID,
    request: RecurringScheduleBookSeriesRequest,
) -> RecurringScheduleBookSeriesResponse:
    """Book passenger on all matching recurring instances (all-or-nothing)."""
    await ensure_rides_schema_compat(db)

    schedule = await crud_v2.get_schedule_by_id(db, schedule_id)
    if not schedule:
        raise NotFoundError(f"Schedule {schedule_id} not found")

    if not schedule.is_active:
        raise ValidationError("Selected recurring schedule is no longer active")

    if schedule.user_id == user_id:
        raise ForbiddenError("You cannot subscribe to your own recurring schedule")

    if not _is_time_inside_window(
        schedule.time,
        request.departure_window_start,
        request.departure_window_end,
    ):
        raise ValidationError("Schedule departure time is outside your selected window")

    overlap_start = max(schedule.start_date, request.passenger_from_date)
    overlap_end = min(schedule.end_date, request.passenger_until_date)
    if overlap_start > overlap_end:
        raise ValidationError("No overlapping date range exists for this recurring schedule")

    existing_subscription = await crud_v2.get_active_subscription_for_schedule_passenger(
        db,
        schedule.id,
        user_id,
    )
    if existing_subscription is not None:
        raise ConflictError("You already have an active recurring booking for this schedule")

    matching_dates = _matching_dates_in_overlap(
        list(schedule.days_of_week or []),
        overlap_start,
        overlap_end,
    )
    now_utc = _utc_now()
    bookable_dates = [
        d for d in matching_dates if _combine_schedule_datetime(d, schedule.time) >= now_utc
    ]
    if not bookable_dates:
        raise ValidationError("No upcoming matching recurring rides are available to book")

    schedule_distance_km = crud_v2.haversine_distance(
        schedule.start_point_lat,
        schedule.start_point_lng,
        schedule.end_point_lat,
        schedule.end_point_lng,
    )
    schedule_duration = _resolve_schedule_duration_minutes(
        route_distance_km=schedule_distance_km,
        recurrence_meta=schedule.recurrence_meta,
    )

    await rides_service._acquire_user_schedule_lock(db, user_id, "passenger-book-ride")
    for candidate_date in bookable_dates:
        if await _passenger_has_common_slot_overlap_for_schedule_date(
            db,
            user_id=user_id,
            schedule_id=schedule.id,
            target_date=candidate_date,
            ride_time=schedule.time,
            duration_minutes=schedule_duration,
        ):
            raise ValidationError(
                "You already have an overlapping booked slot during recurring schedule time."
            )

    subscription = await crud_v2.create_recurring_subscription(
        db,
        schedule_id=schedule.id,
        passenger_id=user_id,
        overlap_start_date=overlap_start,
        overlap_end_date=overlap_end,
        departure_window_start=request.departure_window_start,
        departure_window_end=request.departure_window_end,
        seats_reserved=request.seats_reserved,
        pickup_lat=request.pickup_point.lat,
        pickup_lng=request.pickup_point.lng,
        pickup_address=request.pickup_point.address,
        pickup_place_id=None,
        dropoff_lat=request.dropoff_point.lat,
        dropoff_lng=request.dropoff_point.lng,
        dropoff_address=request.dropoff_point.address,
        dropoff_place_id=None,
    )

    created_booking_ids: List[UUID] = []

    try:
        for candidate_date in bookable_dates:
            ride, _ = await _materialize_or_get_schedule_ride_for_date(
                db,
                schedule,
                candidate_date,
            )
            booking_id = await _ensure_subscription_booking_for_ride(
                db,
                subscription=subscription,
                ride=ride,
            )
            if booking_id not in created_booking_ids:
                created_booking_ids.append(booking_id)

    except HTTPException as exc:
        await _rollback_recurring_series_create(
            db,
            passenger_id=user_id,
            subscription_id=subscription.id,
            booking_ids=created_booking_ids,
        )
        detail_text = str(getattr(exc, "detail", "") or "Recurring series booking failed")
        if exc.status_code == 409:
            raise ConflictError(detail_text)
        if exc.status_code in {400, 422}:
            raise ValidationError(detail_text)
        raise ValidationError(detail_text)
    except Exception as exc:
        await _rollback_recurring_series_create(
            db,
            passenger_id=user_id,
            subscription_id=subscription.id,
            booking_ids=created_booking_ids,
        )
        raise ValidationError(f"Recurring series booking failed: {str(exc)}") from exc

    next_ride = await _ensure_passenger_subscription_next_ride(
        db,
        subscription=subscription,
        schedule=schedule,
    )

    return RecurringScheduleBookSeriesResponse(
        subscription_id=subscription.id,
        schedule_id=schedule.id,
        overlap_start_date=overlap_start,
        overlap_end_date=overlap_end,
        matching_days_count=len(bookable_dates),
        bookings_created=len(created_booking_ids),
        next_ride_id=(next_ride or {}).get("ride_id"),
        next_departure_time=_coerce_departure_time((next_ride or {}).get("departure_time")),
    )


async def list_driver_recurring_home_service(
    db: AsyncSession,
    user_id: UUID,
) -> List[RecurringDriverHomePublic]:
    """Home recurring section for driver-created recurring schedules."""
    await ensure_rides_schema_compat(db)

    schedules = await crud_v2.list_user_schedules(db, user_id, active_only=True)
    today = _utc_now().date()

    items: List[RecurringDriverHomePublic] = []
    for schedule in schedules:
        if schedule.end_date < today:
            continue

        next_ride = await _ensure_driver_schedule_next_ride(db, schedule)
        items.append(
            RecurringDriverHomePublic(
                schedule_id=schedule.id,
                start_point=GeoPoint(
                    lat=schedule.start_point_lat,
                    lng=schedule.start_point_lng,
                    address=schedule.start_point_address,
                ),
                end_point=GeoPoint(
                    lat=schedule.end_point_lat,
                    lng=schedule.end_point_lng,
                    address=schedule.end_point_address,
                ),
                ride_time=schedule.time,
                start_date=schedule.start_date,
                end_date=schedule.end_date,
                seats_offered=int(schedule.seats_offered),
                base_price=schedule.base_price,
                next_ride_id=(next_ride or {}).get("ride_id"),
                next_departure_time=_coerce_departure_time((next_ride or {}).get("departure_time")),
                next_ride_status=(next_ride or {}).get("ride_status"),
            )
        )

    items.sort(
        key=lambda item: (
            item.next_departure_time or datetime.max.replace(tzinfo=timezone.utc),
            item.ride_time,
        )
    )
    return items


async def list_passenger_recurring_home_service(
    db: AsyncSession,
    user_id: UUID,
) -> List[RecurringPassengerHomePublic]:
    """Home recurring section for passenger recurring subscriptions."""
    await ensure_rides_schema_compat(db)

    rows = await crud_v2.list_passenger_subscriptions_with_schedules(
        db,
        user_id,
        active_only=True,
    )

    items: List[RecurringPassengerHomePublic] = []
    for subscription, schedule, driver_name in rows:
        next_ride = await _ensure_passenger_subscription_next_ride(
            db,
            subscription=subscription,
            schedule=schedule,
        )
        booked_instances = await crud_v2.count_subscription_bookings(
            db,
            subscription.id,
        )

        items.append(
            RecurringPassengerHomePublic(
                subscription_id=subscription.id,
                schedule_id=schedule.id,
                driver_id=schedule.user_id,
                driver_name=driver_name,
                pickup_address=subscription.pickup_address,
                dropoff_address=subscription.dropoff_address,
                seats_reserved=max(1, int(subscription.seats_reserved)),
                base_price=schedule.base_price,
                overlap_start_date=subscription.overlap_start_date,
                overlap_end_date=subscription.overlap_end_date,
                status=subscription.status,
                booked_instances_count=booked_instances,
                next_ride_id=(next_ride or {}).get("ride_id"),
                next_departure_time=_coerce_departure_time((next_ride or {}).get("departure_time")),
                next_ride_status=(next_ride or {}).get("ride_status"),
            )
        )

    items.sort(
        key=lambda item: (
            item.next_departure_time or datetime.max.replace(tzinfo=timezone.utc),
            item.overlap_end_date,
        )
    )
    return items


async def resolve_driver_schedule_next_ride_service(
    db: AsyncSession,
    user_id: UUID,
    schedule_id: UUID,
) -> RecurringRideResolutionPublic:
    """Resolve nearest active/upcoming ride for driver recurring schedule card tap."""
    await ensure_rides_schema_compat(db)
    schedule = await crud_v2.get_schedule_by_id_for_user(db, schedule_id, user_id)
    next_ride = await _ensure_driver_schedule_next_ride(db, schedule)
    return RecurringRideResolutionPublic(
        ride_id=(next_ride or {}).get("ride_id"),
        departure_time=_coerce_departure_time((next_ride or {}).get("departure_time")),
        ride_status=(next_ride or {}).get("ride_status"),
    )


async def resolve_passenger_subscription_next_ride_service(
    db: AsyncSession,
    user_id: UUID,
    subscription_id: UUID,
) -> RecurringRideResolutionPublic:
    """Resolve nearest active/upcoming ride for passenger recurring subscription tap."""
    await ensure_rides_schema_compat(db)

    subscription = await crud_v2.get_subscription_for_passenger(
        db,
        subscription_id,
        user_id,
    )
    if subscription is None:
        raise NotFoundError(f"Subscription {subscription_id} not found")

    schedule = await crud_v2.get_schedule_by_id(db, subscription.schedule_id)
    if schedule is None:
        return RecurringRideResolutionPublic()

    next_ride = await _ensure_passenger_subscription_next_ride(
        db,
        subscription=subscription,
        schedule=schedule,
    )
    return RecurringRideResolutionPublic(
        ride_id=(next_ride or {}).get("ride_id"),
        departure_time=_coerce_departure_time((next_ride or {}).get("departure_time")),
        ride_status=(next_ride or {}).get("ride_status"),
    )


async def cancel_passenger_recurring_subscription_service(
    db: AsyncSession,
    user_id: UUID,
    subscription_id: UUID,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Cancel passenger recurring subscription and cancel all future instances."""
    await ensure_rides_schema_compat(db)

    subscription = await crud_v2.get_subscription_for_passenger(
        db,
        subscription_id,
        user_id,
    )
    if subscription is None:
        raise NotFoundError(f"Subscription {subscription_id} not found")

    if subscription.status != "active":
        raise ValidationError("Recurring subscription is already cancelled")

    now_utc = _utc_now()
    booking_ids = await crud_v2.list_future_booking_ids_for_subscription(
        db,
        subscription.id,
        now_utc,
    )

    cancelled_count = 0
    for booking_id in booking_ids:
        try:
            await rides_crud.cancel_booking(
                db,
                booking_id,
                user_id,
                reason or "Cancelled full recurring series",
            )
            cancelled_count += 1
        except Exception:
            continue

    await crud_v2.mark_subscription_cancelled(
        db,
        subscription.id,
        reason or "Cancelled full recurring series",
    )

    return {
        "subscription_id": subscription.id,
        "status": "cancelled",
        "cancelled_future_bookings": cancelled_count,
    }


# ============================================
# 8b. UPDATE USER SCHEDULE
# ============================================

async def update_user_schedule_service(
    db: AsyncSession,
    user_id: UUID,
    schedule_id: UUID,
    data: ScheduleUpdate,
    purge_future_rides: bool = True,
) -> RecurringSchedule:
    """Update an owned recurring schedule and optionally purge future generated rides."""
    await ensure_rides_schema_compat(db)

    schedule = await crud_v2.get_schedule_by_id_for_user(db, schedule_id, user_id)

    updates: Dict[str, Any] = {}
    if data.days_of_week is not None:
        updates["days_of_week"] = _normalize_schedule_days(data.days_of_week)
    if data.ride_time is not None:
        updates["time"] = data.ride_time
    if data.start_point is not None:
        updates["start_point_lat"] = data.start_point.lat
        updates["start_point_lng"] = data.start_point.lng
        updates["start_point_address"] = data.start_point.address or ""
    if data.end_point is not None:
        updates["end_point_lat"] = data.end_point.lat
        updates["end_point_lng"] = data.end_point.lng
        updates["end_point_address"] = data.end_point.address or ""
    if data.polyline_main is not None:
        updates["polyline_main"] = data.polyline_main
    if data.seats_offered is not None:
        updates["seats_offered"] = data.seats_offered
    if data.buffer_seats is not None:
        updates["buffer_seats"] = data.buffer_seats
    if data.base_price is not None:
        updates["base_price"] = data.base_price
    if data.start_date is not None:
        updates["start_date"] = data.start_date
    if data.end_date is not None:
        updates["end_date"] = data.end_date
    if data.is_active is not None:
        updates["is_active"] = data.is_active

    effective_start_date = updates.get("start_date", schedule.start_date)
    effective_end_date = updates.get("end_date", schedule.end_date)
    if effective_end_date <= effective_start_date:
        raise ValidationError("End date must be after start date")

    effective_seats = updates.get("seats_offered", schedule.seats_offered)
    effective_buffer = updates.get("buffer_seats", schedule.buffer_seats)
    if effective_buffer >= effective_seats:
        raise ValidationError("Buffer seats must be less than seats offered")

    effective_start_lat = updates.get("start_point_lat", schedule.start_point_lat)
    effective_start_lng = updates.get("start_point_lng", schedule.start_point_lng)
    effective_end_lat = updates.get("end_point_lat", schedule.end_point_lat)
    effective_end_lng = updates.get("end_point_lng", schedule.end_point_lng)
    effective_days = _normalize_schedule_days(
        list(updates.get("days_of_week", schedule.days_of_week) or [])
    )
    effective_time = updates.get("time", schedule.time)
    effective_is_active = updates.get("is_active", schedule.is_active)

    effective_distance_km = crud_v2.haversine_distance(
        effective_start_lat,
        effective_start_lng,
        effective_end_lat,
        effective_end_lng,
    )
    effective_recurrence_meta: Dict[str, Any] = dict(schedule.recurrence_meta or {})
    effective_duration_minutes = _resolve_schedule_duration_minutes(
        route_distance_km=effective_distance_km,
        recurrence_meta=effective_recurrence_meta,
    )
    effective_recurrence_meta["estimated_duration_minutes"] = effective_duration_minutes
    updates["recurrence_meta"] = effective_recurrence_meta

    if effective_is_active:
        await _acquire_schedule_lock(db, user_id, "recurring-schedule-update")
        existing_schedules = await crud_v2.list_user_schedules(db, user_id, active_only=True)
        for existing in existing_schedules:
            if existing.id == schedule_id:
                continue
            existing_days = _normalize_schedule_days(list(existing.days_of_week or []))
            existing_distance_km = crud_v2.haversine_distance(
                existing.start_point_lat,
                existing.start_point_lng,
                existing.end_point_lat,
                existing.end_point_lng,
            )
            existing_duration = _resolve_schedule_duration_minutes(
                route_distance_km=existing_distance_km,
                recurrence_meta=existing.recurrence_meta,
            )
            overlap_day = _find_schedule_overlap_day(
                days_a=existing_days,
                start_time_a=existing.time,
                duration_a=existing_duration,
                start_date_a=existing.start_date,
                end_date_a=existing.end_date,
                days_b=effective_days,
                start_time_b=effective_time,
                duration_b=effective_duration_minutes,
                start_date_b=effective_start_date,
                end_date_b=effective_end_date,
            )
            if overlap_day:
                raise ValidationError(
                    "Recurring schedule overlaps with another active schedule "
                    f"on {overlap_day}"
                )

    should_recalculate_fare = (
        data.base_price is None
        and any(
            key in updates
            for key in (
                "start_point_lat",
                "start_point_lng",
                "end_point_lat",
                "end_point_lng",
                "seats_offered",
            )
        )
    )

    if should_recalculate_fare:
        fare = calculate_fare(distance_km=effective_distance_km, total_seats=effective_seats)
        updates["base_price"] = Decimal(str(fare.fare_per_seat))

    updated_schedule = await crud_v2.update_schedule(
        db=db,
        schedule_id=schedule_id,
        user_id=user_id,
        **updates,
    )

    if purge_future_rides:
        await crud_v2.purge_future_open_rides_for_schedule(db, schedule_id)

    return updated_schedule


# ============================================
# 8c. DEACTIVATE USER SCHEDULE
# ============================================

async def deactivate_user_schedule_service(
    db: AsyncSession,
    user_id: UUID,
    schedule_id: UUID,
    purge_future_rides: bool = True,
) -> RecurringSchedule:
    """Deactivate an owned recurring schedule and optionally purge future generated rides."""
    await ensure_rides_schema_compat(db)

    schedule = await crud_v2.deactivate_schedule(db, schedule_id, user_id)

    await crud_v2.mark_schedule_subscriptions_cancelled(
        db,
        schedule_id,
        "Driver cancelled recurring schedule",
    )

    if purge_future_rides:
        await crud_v2.purge_future_open_rides_for_schedule(db, schedule_id)

    return schedule


# ============================================
# 9. MATERIALIZE SCHEDULED RIDES
# ============================================

async def _auto_book_subscriptions_for_materialized_schedule_ride(
    db: AsyncSession,
    *,
    schedule: RecurringSchedule,
    ride: Ride,
    target_date: date,
) -> tuple[int, List[Dict[str, str]]]:
    """Auto-book all active subscriptions matching this schedule/date/time."""
    subscriptions = await crud_v2.list_active_subscriptions_for_schedule_date(
        db,
        schedule.id,
        target_date,
        schedule.time,
    )

    booked_count = 0
    errors: List[Dict[str, str]] = []

    for subscription in subscriptions:
        try:
            await _ensure_subscription_booking_for_ride(
                db,
                subscription=subscription,
                ride=ride,
            )
            booked_count += 1
        except HTTPException as exc:
            errors.append(
                {
                    "schedule_id": str(schedule.id),
                    "subscription_id": str(subscription.id),
                    "error": str(getattr(exc, "detail", "Auto-book failed")),
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "schedule_id": str(schedule.id),
                    "subscription_id": str(subscription.id),
                    "error": str(exc),
                }
            )

    return booked_count, errors

async def materialize_scheduled_rides_service(
    db: AsyncSession,
    target_date: date
) -> Dict[str, Any]:
    """
    Materialize scheduled rides for a date (Service Function #9 - for Celery task).
    
    Converts recurring schedules into actual ride entries for the target date.
    
    Args:
        db: Database session
        target_date: Date to materialize rides for
    
    Returns:
        Summary of materialized rides
    """
    await ensure_rides_schema_compat(db)

    schedules = await crud_v2.get_active_schedules_for_date(db, target_date)

    materialized_count = 0
    auto_booked_count = 0
    errors: List[Dict[str, str]] = []

    for schedule in schedules:
        try:
            ride, created = await _materialize_or_get_schedule_ride_for_date(
                db,
                schedule,
                target_date,
            )

            if created:
                materialized_count += 1

            booked_count, booking_errors = (
                await _auto_book_subscriptions_for_materialized_schedule_ride(
                    db,
                    schedule=schedule,
                    ride=ride,
                    target_date=target_date,
                )
            )
            auto_booked_count += booked_count
            errors.extend(booking_errors)

        except Exception as e:
            errors.append(
                {
                    "schedule_id": str(schedule.id),
                    "error": str(e),
                }
            )

    return {
        "target_date": str(target_date),
        "schedules_processed": len(schedules),
        "rides_created": materialized_count,
        "auto_bookings_created": auto_booked_count,
        "errors": errors,
    }


# ============================================
# 10. SEND BOOKING NOTIFICATIONS (STUB)
# ============================================

async def send_booking_notification(
    ride_id: UUID,
    notification_type: str,
    message: str,
    booking_id: Optional[UUID] = None,
    data: Optional[Dict[str, Any]] = None
) -> Dict[str, bool]:
    """
    Send booking notification via WebSocket and FCM (Service Function #10 - STUB).
    
    Prompt 5 requirement: Stub implementation for notification system.
    In production, this would integrate with:
    - WebSocket server for real-time notifications
    - Firebase Cloud Messaging (FCM) for push notifications
    
    Args:
        ride_id: Ride ID
        notification_type: Type of notification
        message: Notification message
        booking_id: Booking ID (optional)
        data: Additional data payload
    
    Returns:
        Delivery status: {"websocket": bool, "fcm": bool}
    """
    # STUB: Log notification instead of sending
    print(f"[NOTIFICATION STUB] {notification_type}")
    print(f"  Ride ID: {ride_id}")
    if booking_id:
        print(f"  Booking ID: {booking_id}")
    print(f"  Message: {message}")
    if data:
        print(f"  Data: {data}")
    
    # TODO: Implement actual WebSocket broadcasting
    # websocket_success = await broadcast_to_websocket(ride_id, message, data)
    
    # TODO: Implement FCM push notification
    # fcm_success = await send_fcm_notification(user_ids, message, data)
    
    return {
        "websocket": True,  # Stub: Always success
        "fcm": True  # Stub: Always success
    }


# ============================================
# UTILITY FUNCTIONS
# ============================================

async def validate_ride_driver_permissions(
    db: AsyncSession,
    ride_id: UUID,
    driver_id: UUID
) -> Ride:
    """
    Validate that user is the driver of the ride.
    
    Args:
        db: Database session
        ride_id: Ride ID
        driver_id: Driver ID to check
    
    Returns:
        Ride object if valid
    
    Raises:
        NotFoundError: If ride doesn't exist
        ForbiddenError: If user is not the driver
    """
    ride = await crud_v2.get_ride_by_id(db, ride_id)
    if not ride:
        raise NotFoundError(f"Ride {ride_id} not found")
    
    if ride.driver_id != driver_id:
        raise ForbiddenError("You are not the driver of this ride")
    
    return ride


async def validate_passenger_booking_rules(
    db: AsyncSession,
    passenger_id: UUID,
    ride_id: UUID
) -> bool:
    """
    Validate passenger can book this ride.
    
    Rules:
    - Passenger cannot book their own ride
    - Passenger cannot have multiple active bookings for same ride
    - Passenger must have verified profile (TODO: implement)
    
    Args:
        db: Database session
        passenger_id: Passenger ID
        ride_id: Ride ID
    
    Returns:
        True if valid
    
    Raises:
        ValidationError: If validation fails
    """
    ride = await crud_v2.get_ride_by_id(db, ride_id)
    if not ride:
        raise NotFoundError(f"Ride {ride_id} not found")
    
    # Cannot book your own ride
    if ride.driver_id == passenger_id:
        raise ValidationError("You cannot book your own ride")
    
    # Check for existing booking (handled in crud_v2.book_seat_atomic)
    
    return True


async def calculate_distance_between_points(
    point1: GeoPoint,
    point2: GeoPoint
) -> float:
    """
    Calculate distance between two geographic points.
    
    Args:
        point1: First point
        point2: Second point
    
    Returns:
        Distance in kilometers
    """
    return crud_v2.haversine_distance(
        point1.lat, point1.lng,
        point2.lat, point2.lng
    )
