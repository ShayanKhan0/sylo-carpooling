"""
Module: Rides - Service Layer
Purpose: Business logic for ride creation, booking, cancellation, and lifecycle management.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: Handles driver verification, seat management, earnings tracking, and standardized response formatting.
"""

import logging
import math
import json
import uuid
from uuid import UUID
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple
from datetime import date, datetime, time, timedelta, timezone
from sqlalchemy import text, select, and_, or_, cast, String, func, case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.modules.rides import crud
from app.modules.rides.models import RideBooking as RideBookingModel
from app.modules.rides.schemas import (
    RideCreate, RideUpdate, RidePublic, RideWithBookingsPublic,
    RideBookingCreate, RideBookingPublic, RideBookingWithRidePublic,
    RideStatusUpdate, BookingCancellation,
    RideStatistics, PassengerBookingHistory,
    RideRequestCreate, RideRequestPublic,
    RideRouteSelectionUpdate,
)
from app.modules.drivers import crud as drivers_crud
from app.modules.drivers.schema_compat import ensure_driver_vehicle_schema_compat
from app.modules.verification import crud as verification_crud
from app.modules.verification.models import DocumentTypeEnum, VerificationStatusEnum
from app.modules.notifications.schemas import NotificationCreate
from app.modules.notifications.models import NotificationTypeEnum, NotificationPriorityEnum
from app.modules.notifications.service import send_push_notification
from app.core.fare_calculator import calculate_fare, FareEstimate as FareEstimateResult
from app.core.google_maps_client import get_google_maps_client
from app.modules.rides.schema_compat import ACTIVE_BOOKING_STATUSES, ensure_rides_schema_compat
from app.modules.auth.models import User
from app.modules.users.models import UserProfile
from app.models.booking import Booking as LegacyBookingModel
from app.models.recurring_schedule import RecurringSchedule
from app.models.recurring_schedule_subscription import RecurringScheduleSubscription

logger = logging.getLogger(__name__)

DEFAULT_RIDE_DURATION_MINUTES = 45
DEFAULT_REQUEST_DURATION_MINUTES = 45
AVG_URBAN_SPEED_KMH = 40.0
MAX_EXISTING_PASSENGER_DETOUR_RATIO = 0.30
MAX_EXISTING_PASSENGER_DETOUR_BUFFER_KM = 0.80
ROUTE_PLAN_STOP_DWELL_MINUTES = 1
ACTIVE_RIDE_STATUS_SQL = "'open', 'scheduled', 'in_progress', 'ongoing'"
ACTIVE_BOOKING_STATUS_SQL = "'reserved', 'confirmed', 'booked'"
ACTIVE_REQUEST_STATUS_SQL = "'pending', 'accepted'"
ACTIVE_RECURRING_SUBSCRIPTION_STATUS_SQL = "'active'"

WEEKDAY_INDEX = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4,
    "Sat": 5,
    "Sun": 6,
}

RIDE_DURATION_SQL = """
COALESCE(
    NULLIF(estimated_duration_minutes, 0),
    NULLIF(CEIL((COALESCE(route_distance_km, 0)::numeric / :avg_speed_kmh) * 60), 0)::int,
    :default_duration
)
"""

RIDE_END_SQL = f"(departure_time + make_interval(mins => ({RIDE_DURATION_SQL})))"


# ============================================
# HELPER FUNCTIONS
# ============================================

def _format_response(data: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
    """
    Format standardized API response.
    
    Args:
        data: Response payload (None if error)
        error: Error message (None if success)
    
    Returns:
        Dict with {status, data, error} structure
    """
    if error:
        return {
            "status": "error",
            "data": None,
            "error": error
        }
    return {
        "status": "ok",
        "data": data,
        "error": None
    }


def _humanize_status(value: str) -> str:
    if not value:
        return "Unknown"
    return value.replace("_", " ").strip().title()


def _canonical_ride_status(status_value: Any) -> str:
    raw = str(getattr(status_value, "value", status_value) or "").strip().lower()
    aliases = {
        "scheduled": "open",
        "ongoing": "in_progress",
        "in-progress": "in_progress",
        "inprogress": "in_progress",
    }
    return aliases.get(raw, raw or "open")


def _canonical_booking_status(status_value: Any) -> str:
    raw = str(getattr(status_value, "value", status_value) or "").strip().lower()
    aliases = {
        "reserved": "booked",
        "confirmed": "booked",
        "canceled": "cancelled",
    }
    return aliases.get(raw, raw or "booked")


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _driver_display_status(ride_status: str, seats_available: int) -> str:
    if ride_status == "open":
        return "All Seats Booked" if seats_available <= 0 else "Open"
    if ride_status == "in_progress":
        return "Ride Started"
    if ride_status == "completed":
        return "Ride Completed"
    if ride_status == "cancelled":
        return "Ride Cancelled"
    return _humanize_status(ride_status)


def _passenger_display_status(
    *,
    ride_status: str,
    booking_status: str,
    seats_available: int,
    booked_seats: int,
) -> tuple[str, Optional[str]]:
    if booking_status == "cancelled":
        return "Passenger Cancelled", None

    if ride_status == "cancelled":
        return "Driver Cancelled", None

    if ride_status == "in_progress":
        return "Ride Started", None

    if ride_status == "completed" or booking_status == "completed":
        return "Ride Completed", None

    if booking_status == "booked":
        if seats_available <= 0:
            seat_word = "Seat" if booked_seats == 1 else "Seats"
            return f"All Seats Booked, {booked_seats} {seat_word} Reserved", "All Seats Booked"
        return "Booked, Still Open", "Still Open"

    return _humanize_status(booking_status), None


def _apply_ride_display_fields(
    ride_data: Dict[str, Any],
    *,
    role: str = "driver",
) -> Dict[str, Any]:
    canonical_status = _canonical_ride_status(ride_data.get("status"))
    seats_available = _to_int(ride_data.get("available_seats"), default=0)

    ride_data["status"] = canonical_status
    ride_data["display_status"] = _driver_display_status(canonical_status, seats_available)
    ride_data["display_substatus"] = (
        "No seats left" if canonical_status == "open" and seats_available <= 0 else None
    )

    # Driver controls are only valid while a ride is active and before completion.
    ride_data["can_driver_start"] = canonical_status == "open"
    ride_data["can_driver_complete"] = canonical_status == "in_progress"
    ride_data["can_driver_cancel"] = canonical_status == "open"

    return ride_data


def _driver_action_state_from_bookings_payload(
    bookings_data: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Compute booking counters used to gate Start/Complete ride actions."""
    active_booking_count = 0
    non_cancelled_booking_count = 0
    pending_stop_booking_count = 0

    for booking_data in bookings_data:
        status_value = _canonical_booking_status(booking_data.get("status"))
        if status_value == "cancelled":
            continue

        non_cancelled_booking_count += 1
        if status_value in ACTIVE_BOOKING_STATUSES:
            active_booking_count += 1

        pickup_completed = booking_data.get("pickup_completed") is True
        dropoff_completed = booking_data.get("dropoff_completed") is True
        if not (pickup_completed and dropoff_completed):
            pending_stop_booking_count += 1

    return {
        "active_booking_count": active_booking_count,
        "non_cancelled_booking_count": non_cancelled_booking_count,
        "pending_stop_booking_count": pending_stop_booking_count,
    }


def _apply_driver_action_flags(
    ride_data: Dict[str, Any],
    action_state: Dict[str, int],
) -> Dict[str, Any]:
    """Override driver controls using booking-aware guardrails."""
    canonical_status = _canonical_ride_status(ride_data.get("status"))

    if canonical_status == "open":
        ride_data["can_driver_start"] = action_state.get("active_booking_count", 0) > 0

    if canonical_status == "in_progress":
        ride_data["can_driver_complete"] = (
            action_state.get("pending_stop_booking_count", 0) == 0
        )

    return ride_data


def _parse_departure_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return _normalize_to_utc(value)
    if isinstance(value, str):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return _normalize_to_utc(parsed)
    return None


def _resolve_runtime_driver_ride_status(
    ride_data: Dict[str, Any],
    *,
    action_state: Dict[str, int],
    now_utc: datetime,
) -> str:
    """Prevent stale past rides from showing as open in driver My Rides."""
    canonical_status = _canonical_ride_status(ride_data.get("status"))
    if canonical_status != "open":
        return canonical_status

    departure_utc = _parse_departure_utc(ride_data.get("departure_time"))
    if departure_utc is None or departure_utc > now_utc:
        return canonical_status

    non_cancelled_booking_count = int(action_state.get("non_cancelled_booking_count", 0) or 0)
    pending_stop_booking_count = int(action_state.get("pending_stop_booking_count", 0) or 0)

    if non_cancelled_booking_count <= 0:
        return "cancelled"
    if pending_stop_booking_count <= 0:
        return "completed"
    return "in_progress"


async def _load_driver_action_state_for_ride_ids(
    db: AsyncSession,
    ride_ids: List[UUID],
) -> Dict[UUID, Dict[str, int]]:
    """Load booking-derived action guardrail counters for each ride id."""
    if not ride_ids:
        return {}

    status_expr = func.lower(cast(RideBookingModel.status, String))
    active_case = case(
        (status_expr.in_(tuple(ACTIVE_BOOKING_STATUSES)), 1),
        else_=0,
    )
    non_cancelled_case = case((status_expr != "cancelled", 1), else_=0)
    pending_stop_case = case(
        (
            and_(
                status_expr != "cancelled",
                or_(
                    RideBookingModel.actual_pickup_time.is_(None),
                    RideBookingModel.actual_dropoff_time.is_(None),
                ),
            ),
            1,
        ),
        else_=0,
    )

    result = await db.execute(
        select(
            RideBookingModel.ride_id,
            func.coalesce(func.sum(active_case), 0),
            func.coalesce(func.sum(non_cancelled_case), 0),
            func.coalesce(func.sum(pending_stop_case), 0),
        )
        .where(RideBookingModel.ride_id.in_(ride_ids))
        .group_by(RideBookingModel.ride_id)
    )

    state_by_ride: Dict[UUID, Dict[str, int]] = {
        ride_id: {
            "active_booking_count": 0,
            "non_cancelled_booking_count": 0,
            "pending_stop_booking_count": 0,
        }
        for ride_id in ride_ids
    }

    for ride_id, active_count, non_cancelled_count, pending_count in result.all():
        state_by_ride[ride_id] = {
            "active_booking_count": _to_int(active_count, default=0),
            "non_cancelled_booking_count": _to_int(non_cancelled_count, default=0),
            "pending_stop_booking_count": _to_int(pending_count, default=0),
        }

    # Compatibility fallback for datasets that still rely on legacy bookings rows.
    legacy_status_expr = func.lower(cast(LegacyBookingModel.status, String))
    legacy_active_case = case(
        (legacy_status_expr.in_(tuple(ACTIVE_BOOKING_STATUSES)), 1),
        else_=0,
    )
    legacy_result = await db.execute(
        select(
            LegacyBookingModel.ride_id,
            func.coalesce(func.sum(legacy_active_case), 0),
        )
        .where(LegacyBookingModel.ride_id.in_(ride_ids))
        .group_by(LegacyBookingModel.ride_id)
    )

    for ride_id, legacy_active_count in legacy_result.all():
        ride_state = state_by_ride.setdefault(
            ride_id,
            {
                "active_booking_count": 0,
                "non_cancelled_booking_count": 0,
                "pending_stop_booking_count": 0,
            },
        )
        ride_state["active_booking_count"] = max(
            ride_state.get("active_booking_count", 0),
            _to_int(legacy_active_count, default=0),
        )

    return state_by_ride


def _ride_public_payload(
    ride: Any,
    *,
    role: str = "driver",
    with_bookings: bool = False,
) -> Dict[str, Any]:
    model_cls = RideWithBookingsPublic if with_bookings else RidePublic
    ride_data = model_cls.model_validate(ride).model_dump()
    return _apply_ride_display_fields(ride_data, role=role)


async def _attach_recurring_range(
    db: AsyncSession,
    ride_data: Dict[str, Any],
) -> None:
    """Attach recurring date range fields to ride payload when available."""
    recurrence = ride_data.get("recurrence")
    if not isinstance(recurrence, dict):
        return

    schedule_id_raw = recurrence.get("schedule_id")
    if not schedule_id_raw:
        return

    start_raw = recurrence.get("start_date")
    end_raw = recurrence.get("end_date")
    if start_raw:
        ride_data["recurring_start_date"] = str(start_raw)
    if end_raw:
        ride_data["recurring_end_date"] = str(end_raw)
    if start_raw and end_raw:
        return

    try:
        schedule_id = UUID(str(schedule_id_raw))
    except (TypeError, ValueError):
        return

    result = await db.execute(
        select(RecurringSchedule.start_date, RecurringSchedule.end_date).where(
            RecurringSchedule.id == schedule_id
        )
    )
    row = result.first()
    if not row:
        return

    start_date, end_date = row
    if start_date and not ride_data.get("recurring_start_date"):
        ride_data["recurring_start_date"] = start_date.isoformat()
    if end_date and not ride_data.get("recurring_end_date"):
        ride_data["recurring_end_date"] = end_date.isoformat()


async def _build_ride_driver_summary(
    db: AsyncSession,
    ride: Any,
) -> Optional[Dict[str, Any]]:
    """Fetch compact driver details for passenger ride detail views."""
    driver_row_result = await db.execute(
        text(
            """
            SELECT
                u.id AS driver_user_id,
                u.full_name AS driver_name,
                up.profile_photo AS profile_photo,
                d.rating_avg AS rating_avg,
                d.vehicle_id AS fallback_vehicle_id,
                COALESCE(
                    (
                        SELECT COUNT(1)
                        FROM rides r_completed
                        WHERE r_completed.driver_id = u.id
                          AND LOWER(CAST(r_completed.status AS TEXT)) = 'completed'
                    ),
                    0
                ) AS completed_rides
            FROM users u
            LEFT JOIN user_profiles up ON up.user_id = u.id
            LEFT JOIN drivers d ON d.user_id = u.id
            WHERE u.id = :driver_id
            LIMIT 1
            """
        ),
        {"driver_id": getattr(ride, "driver_id", None)},
    )
    driver_row = driver_row_result.mappings().first()
    if not driver_row:
        return None

    effective_vehicle_id = getattr(ride, "vehicle_id", None) or driver_row.get(
        "fallback_vehicle_id"
    )
    car_name: Optional[str] = None
    vehicle_plate: Optional[str] = None

    if effective_vehicle_id:
        vehicle_row_result = await db.execute(
            text(
                """
                SELECT
                    make,
                    model,
                    COALESCE(plate_number, license_plate) AS vehicle_plate
                FROM vehicles
                WHERE id = :vehicle_id
                LIMIT 1
                """
            ),
            {"vehicle_id": effective_vehicle_id},
        )
        vehicle_row = vehicle_row_result.mappings().first()
        if vehicle_row:
            make = str(vehicle_row.get("make") or "").strip()
            model = str(vehicle_row.get("model") or "").strip()
            car_name = " ".join(part for part in (make, model) if part).strip() or None
            vehicle_plate = str(vehicle_row.get("vehicle_plate") or "").strip() or None

    rating_avg: Optional[float] = None
    rating_raw = driver_row.get("rating_avg")
    if rating_raw is not None:
        try:
            rating_avg = round(float(rating_raw), 2)
        except (TypeError, ValueError):
            rating_avg = None

    completed_rides = 0
    try:
        completed_rides = int(driver_row.get("completed_rides") or 0)
    except (TypeError, ValueError):
        completed_rides = 0

    profile_photo = str(driver_row.get("profile_photo") or "").strip() or None
    name = str(driver_row.get("driver_name") or "").strip() or "Driver"

    return {
        "driver_user_id": driver_row.get("driver_user_id"),
        "name": name,
        "profile_photo": profile_photo,
        "rating_avg": rating_avg,
        "completed_rides": completed_rides,
        "car_name": car_name,
        "vehicle_plate": vehicle_plate,
    }


async def _build_booking_passenger_summaries(
    db: AsyncSession,
    passenger_ids: List[UUID],
) -> Dict[str, Dict[str, Optional[str]]]:
    unique_ids = list({pid for pid in passenger_ids if isinstance(pid, UUID)})
    if not unique_ids:
        return {}

    result = await db.execute(
        select(
            User.id.label("user_id"),
            User.full_name.label("full_name"),
            User.phone.label("phone"),
            UserProfile.profile_photo.label("profile_photo"),
        )
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
        .where(User.id.in_(unique_ids))
    )

    summaries: Dict[str, Dict[str, Optional[str]]] = {}
    for row in result.mappings().all():
        user_id = row.get("user_id")
        if not user_id:
            continue

        full_name = str(row.get("full_name") or "").strip()
        phone = str(row.get("phone") or "").strip()
        profile_photo = str(row.get("profile_photo") or "").strip()

        summaries[str(user_id)] = {
            "passenger_name": full_name or None,
            "passenger_phone": phone or None,
            "passenger_profile_photo": profile_photo or None,
        }

    return summaries


def _apply_booking_display_fields(
    booking_data: Dict[str, Any],
    *,
    ride_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    canonical_booking_status = _canonical_booking_status(booking_data.get("status"))
    booking_data["status"] = canonical_booking_status
    booking_data["normalized_status"] = canonical_booking_status

    if ride_payload is None and isinstance(booking_data.get("ride"), dict):
        ride_payload = _apply_ride_display_fields(
            dict(booking_data["ride"]),
            role="driver",
        )
        booking_data["ride"] = ride_payload

    if ride_payload:
        ride_status = _canonical_ride_status(ride_payload.get("status"))
        seats_available = _to_int(ride_payload.get("available_seats"), default=0)
        has_ride_context = True
    else:
        ride_status = "open"
        seats_available = 0
        has_ride_context = False

    booked_seats = _to_int(booking_data.get("booked_seats"), default=1)
    if has_ride_context:
        display_status, display_substatus = _passenger_display_status(
            ride_status=ride_status,
            booking_status=canonical_booking_status,
            seats_available=seats_available,
            booked_seats=booked_seats,
        )
    else:
        if canonical_booking_status == "cancelled":
            display_status, display_substatus = "Passenger Cancelled", None
        elif canonical_booking_status == "completed":
            display_status, display_substatus = "Ride Completed", None
        else:
            display_status, display_substatus = "Booked, Still Open", "Still Open"

    booking_data["display_status"] = display_status
    booking_data["display_substatus"] = display_substatus

    pickup_completed = booking_data.get("actual_pickup_time") is not None
    dropoff_completed = (
        booking_data.get("actual_dropoff_time") is not None
        or canonical_booking_status == "completed"
    )

    if canonical_booking_status == "cancelled":
        booking_stage = "cancelled"
    elif dropoff_completed:
        booking_stage = "dropped_off"
    elif pickup_completed:
        booking_stage = "onboard"
    else:
        booking_stage = "awaiting_pickup"

    if booking_stage == "awaiting_pickup" and ride_status == "in_progress":
        booking_data["display_status"] = "Awaiting Pickup"
        booking_data["display_substatus"] = "Driver En Route"
    elif booking_stage == "onboard" and ride_status == "in_progress":
        booking_data["display_status"] = "Passenger Onboard"
        booking_data["display_substatus"] = "In Transit"

    booking_data["pickup_completed"] = pickup_completed
    booking_data["dropoff_completed"] = dropoff_completed
    booking_data["booking_stage"] = booking_stage

    booking_data["can_passenger_cancel"] = (
        canonical_booking_status == "booked"
        and (ride_status == "open" if has_ride_context else True)
    )
    return booking_data


def _booking_public_payload(
    booking: Any,
    *,
    include_ride: bool = False,
) -> Dict[str, Any]:
    model_cls = RideBookingWithRidePublic if include_ride else RideBookingPublic
    booking_data = model_cls.model_validate(booking).model_dump()
    return _apply_booking_display_fields(booking_data)


async def _load_canonical_ride_bookings(
    db: AsyncSession,
    ride_id: UUID,
) -> List[RideBookingModel]:
    """Load bookings from canonical ride_bookings table ordered newest first."""
    result = await db.execute(
        select(RideBookingModel)
        .where(RideBookingModel.ride_id == ride_id)
        .order_by(RideBookingModel.booking_time.desc())
    )
    return list(result.scalars().all())


def _booking_aggregates_from_payloads(
    bookings_data: List[Dict[str, Any]],
) -> tuple[int, float]:
    """Return (active_booked_seats, non_cancelled_total_earnings)."""
    booked_seats = 0
    total_earnings = 0.0

    for booking_data in bookings_data:
        status_value = _canonical_booking_status(booking_data.get("status"))
        seats_value = max(0, _to_int(booking_data.get("booked_seats"), default=0))

        amount_raw = booking_data.get("total_price")
        try:
            amount_value = float(amount_raw or 0.0)
        except (TypeError, ValueError):
            amount_value = 0.0

        if status_value in ACTIVE_BOOKING_STATUSES:
            booked_seats += seats_value

        if status_value != "cancelled":
            total_earnings += max(0.0, amount_value)

    return booked_seats, round(total_earnings, 2)


def _build_ride_execution_progress(
    bookings_data: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute execution progress summary for pickup/dropoff stop completion."""
    active_bookings = 0
    completed_bookings = 0
    stop_items: List[Dict[str, Any]] = []

    for sequence, booking_data in enumerate(bookings_data):
        status_value = _canonical_booking_status(booking_data.get("status"))
        if status_value == "cancelled":
            continue

        active_bookings += 1
        dropoff_completed = booking_data.get("dropoff_completed") is True
        if status_value == "completed" or dropoff_completed:
            completed_bookings += 1

        booking_id = booking_data.get("id")
        pickup_order = booking_data.get("pickup_stop_order")
        dropoff_order = booking_data.get("dropoff_stop_order")

        if isinstance(pickup_order, int):
            stop_items.append(
                {
                    "order": pickup_order,
                    "event_type": "pickup",
                    "booking_id": booking_id,
                    "completed": booking_data.get("pickup_completed") is True,
                    "sequence": sequence,
                }
            )

        if isinstance(dropoff_order, int):
            stop_items.append(
                {
                    "order": dropoff_order,
                    "event_type": "dropoff",
                    "booking_id": booking_id,
                    "completed": dropoff_completed,
                    "sequence": sequence,
                }
            )

    pending_stops = sorted(
        [item for item in stop_items if not item["completed"]],
        key=lambda item: (item["order"], item["sequence"]),
    )

    completed_stops = sum(1 for item in stop_items if item["completed"])
    total_stops = len(stop_items)
    completion_pct = (
        round((completed_stops / total_stops) * 100, 1) if total_stops > 0 else 0.0
    )

    next_stop = pending_stops[0] if pending_stops else None
    return {
        "active_bookings": active_bookings,
        "completed_bookings": completed_bookings,
        "total_stops": total_stops,
        "completed_stops": completed_stops,
        "completion_pct": completion_pct,
        "next_stop": {
            "order": next_stop["order"],
            "event_type": next_stop["event_type"],
            "booking_id": next_stop["booking_id"],
        }
        if next_stop
        else None,
    }


async def _compute_ride_total_earnings(
    db: AsyncSession,
    ride_id: UUID,
    fallback_total: float = 0.0,
) -> float:
    """Compute earnings from canonical bookings table with a safe fallback."""
    total_result = await db.execute(
        select(func.coalesce(func.sum(RideBookingModel.total_price), 0.0)).where(
            and_(
                RideBookingModel.ride_id == ride_id,
                func.lower(cast(RideBookingModel.status, String)) != "cancelled",
            )
        )
    )

    try:
        canonical_total = float(total_result.scalar_one() or 0.0)
    except Exception:
        canonical_total = 0.0

    if canonical_total > 0:
        return canonical_total

    try:
        return max(0.0, float(fallback_total or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute straight-line distance in kilometers between 2 coordinates."""
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


def _encode_polyline(points: List[tuple[float, float]]) -> Optional[str]:
    """Encode a sequence of (lat, lng) points to Google polyline format."""
    if len(points) < 2:
        return None

    def _encode_value(value: int) -> str:
        value = ~(value << 1) if value < 0 else (value << 1)
        encoded = ""
        while value >= 0x20:
            encoded += chr((0x20 | (value & 0x1F)) + 63)
            value >>= 5
        encoded += chr(value + 63)
        return encoded

    result = []
    last_lat = 0
    last_lng = 0
    for lat, lng in points:
        lat_i = int(round(lat * 1e5))
        lng_i = int(round(lng * 1e5))
        result.append(_encode_value(lat_i - last_lat))
        result.append(_encode_value(lng_i - last_lng))
        last_lat = lat_i
        last_lng = lng_i
    return "".join(result)


def _normalize_to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolve_duration_minutes(
    estimated_duration_minutes: Optional[int],
    route_distance_km: Optional[float],
    *,
    default_minutes: int = DEFAULT_RIDE_DURATION_MINUTES,
) -> int:
    if estimated_duration_minutes and estimated_duration_minutes > 0:
        return max(1, min(720, int(estimated_duration_minutes)))

    if route_distance_km and route_distance_km > 0:
        inferred = int(math.ceil((route_distance_km / AVG_URBAN_SPEED_KMH) * 60))
        if inferred > 0:
            return max(1, min(720, inferred))

    return max(1, min(720, int(default_minutes)))


def _window_end(start_utc: datetime, duration_minutes: int) -> datetime:
    return start_utc + timedelta(minutes=max(1, duration_minutes))


@dataclass
class _RouteBookingInput:
    booking_id: UUID
    passenger_id: UUID
    seats: int
    pickup_lat: float
    pickup_lng: float
    pickup_address: str
    pickup_place_id: Optional[str]
    dropoff_lat: float
    dropoff_lng: float
    dropoff_address: str
    dropoff_place_id: Optional[str]


@dataclass
class _RouteStopEvent:
    booking_id: UUID
    event_type: str  # pickup | dropoff
    lat: float
    lng: float


@dataclass
class _RouteCandidatePlan:
    key: str
    label: str
    is_optimal: bool
    strategy: str
    sequence: List[_RouteStopEvent]
    signature: str
    distance_km: float
    duration_minutes: int
    pickup_order_by_booking: Dict[UUID, int]
    dropoff_order_by_booking: Dict[UUID, int]
    pickup_eta_by_booking: Dict[UUID, datetime]
    dropoff_eta_by_booking: Dict[UUID, datetime]
    segment_km_by_booking: Dict[UUID, float]
    polyline: Optional[str] = None
    summary: Optional[str] = None


def _is_ride_route_mutable(ride: Any) -> bool:
    return _canonical_ride_status(getattr(ride, "status", None)) == "open"


def _resolve_booking_route_payload(ride: Any, booking_data: RideBookingCreate) -> None:
    if booking_data.pickup_lat is None:
        booking_data.pickup_lat = float(getattr(ride, "start_point_lat", 0.0) or 0.0)
    if booking_data.pickup_lng is None:
        booking_data.pickup_lng = float(getattr(ride, "start_point_lng", 0.0) or 0.0)
    if booking_data.dropoff_lat is None:
        booking_data.dropoff_lat = float(getattr(ride, "end_point_lat", 0.0) or 0.0)
    if booking_data.dropoff_lng is None:
        booking_data.dropoff_lng = float(getattr(ride, "end_point_lng", 0.0) or 0.0)

    if not booking_data.pickup_address:
        booking_data.pickup_address = str(
            getattr(ride, "start_point_address", None)
            or getattr(ride, "origin", None)
            or "Pickup"
        ).strip()
    if not booking_data.dropoff_address:
        booking_data.dropoff_address = str(
            getattr(ride, "end_point_address", None)
            or getattr(ride, "destination", None)
            or "Dropoff"
        ).strip()


def _to_route_input_from_model(booking: RideBookingModel) -> Optional[_RouteBookingInput]:
    pickup_lat = getattr(booking, "pickup_lat", None)
    pickup_lng = getattr(booking, "pickup_lng", None)
    dropoff_lat = getattr(booking, "dropoff_lat", None)
    dropoff_lng = getattr(booking, "dropoff_lng", None)

    if None in (pickup_lat, pickup_lng, dropoff_lat, dropoff_lng):
        return None

    try:
        return _RouteBookingInput(
            booking_id=UUID(str(getattr(booking, "id"))),
            passenger_id=UUID(str(getattr(booking, "passenger_id"))),
            seats=max(1, _to_int(getattr(booking, "booked_seats", 1), default=1)),
            pickup_lat=float(pickup_lat),
            pickup_lng=float(pickup_lng),
            pickup_address=str(getattr(booking, "pickup_address", None) or "Pickup").strip(),
            pickup_place_id=getattr(booking, "pickup_place_id", None),
            dropoff_lat=float(dropoff_lat),
            dropoff_lng=float(dropoff_lng),
            dropoff_address=str(getattr(booking, "dropoff_address", None) or "Dropoff").strip(),
            dropoff_place_id=getattr(booking, "dropoff_place_id", None),
        )
    except Exception:
        return None


def _to_route_input_from_create(
    *,
    booking_data: RideBookingCreate,
    passenger_id: UUID,
) -> Optional[_RouteBookingInput]:
    if None in (
        booking_data.pickup_lat,
        booking_data.pickup_lng,
        booking_data.dropoff_lat,
        booking_data.dropoff_lng,
    ):
        return None

    return _RouteBookingInput(
        booking_id=uuid.uuid4(),
        passenger_id=passenger_id,
        seats=max(1, _to_int(booking_data.booked_seats, default=1)),
        pickup_lat=float(booking_data.pickup_lat),
        pickup_lng=float(booking_data.pickup_lng),
        pickup_address=str(booking_data.pickup_address or "Pickup").strip(),
        pickup_place_id=booking_data.pickup_place_id,
        dropoff_lat=float(booking_data.dropoff_lat),
        dropoff_lng=float(booking_data.dropoff_lng),
        dropoff_address=str(booking_data.dropoff_address or "Dropoff").strip(),
        dropoff_place_id=booking_data.dropoff_place_id,
    )


def _route_candidate_score(
    *,
    current_lat: float,
    current_lng: float,
    target_lat: float,
    target_lng: float,
    end_lat: float,
    end_lng: float,
    event_type: str,
    strategy: str,
) -> float:
    leg_km = _haversine_km(current_lat, current_lng, target_lat, target_lng)
    to_end_km = _haversine_km(target_lat, target_lng, end_lat, end_lng)

    if strategy == "dropoff_priority":
        kind_penalty = 0.0 if event_type == "dropoff" else 1.35
        return leg_km + (0.30 * to_end_km) + kind_penalty
    if strategy == "pickup_priority":
        kind_penalty = 0.0 if event_type == "pickup" else 0.70
        return leg_km + (0.10 * to_end_km) + kind_penalty

    kind_penalty = 0.0 if event_type == "dropoff" else 0.22
    return leg_km + (0.18 * to_end_km) + kind_penalty


def _compute_stop_sequence(
    *,
    ride: Any,
    route_inputs: List[_RouteBookingInput],
    strategy: str,
) -> List[_RouteStopEvent]:
    if not route_inputs:
        return []

    end_lat = float(getattr(ride, "end_point_lat"))
    end_lng = float(getattr(ride, "end_point_lng"))
    current_lat = float(getattr(ride, "start_point_lat"))
    current_lng = float(getattr(ride, "start_point_lng"))

    picked_up: set[UUID] = set()
    dropped_off: set[UUID] = set()
    sequence: List[_RouteStopEvent] = []

    while len(dropped_off) < len(route_inputs):
        candidates: List[tuple[float, str, _RouteBookingInput, float, float]] = []

        for route_input in route_inputs:
            bid = route_input.booking_id
            if bid in dropped_off:
                continue

            if bid not in picked_up:
                event_type = "pickup"
                target_lat = route_input.pickup_lat
                target_lng = route_input.pickup_lng
            else:
                event_type = "dropoff"
                target_lat = route_input.dropoff_lat
                target_lng = route_input.dropoff_lng

            score = _route_candidate_score(
                current_lat=current_lat,
                current_lng=current_lng,
                target_lat=target_lat,
                target_lng=target_lng,
                end_lat=end_lat,
                end_lng=end_lng,
                event_type=event_type,
                strategy=strategy,
            )
            candidates.append((score, event_type, route_input, target_lat, target_lng))

        if not candidates:
            break

        # Stable tie-break: lower score, then dropoff before pickup.
        candidates.sort(key=lambda c: (c[0], 0 if c[1] == "dropoff" else 1))
        _, event_type, chosen, target_lat, target_lng = candidates[0]

        sequence.append(
            _RouteStopEvent(
                booking_id=chosen.booking_id,
                event_type=event_type,
                lat=target_lat,
                lng=target_lng,
            )
        )

        if event_type == "pickup":
            picked_up.add(chosen.booking_id)
        else:
            dropped_off.add(chosen.booking_id)

        current_lat = target_lat
        current_lng = target_lng

    return sequence


def _build_candidate_plan(
    *,
    ride: Any,
    route_inputs: List[_RouteBookingInput],
    strategy: str,
    key: str,
    label: str,
    is_optimal: bool,
) -> Optional[_RouteCandidatePlan]:
    sequence = _compute_stop_sequence(ride=ride, route_inputs=route_inputs, strategy=strategy)
    expected_events = len(route_inputs) * 2
    if expected_events == 0:
        return None
    if len(sequence) != expected_events:
        return None

    input_by_booking: Dict[UUID, _RouteBookingInput] = {
        route_input.booking_id: route_input for route_input in route_inputs
    }

    departure = getattr(ride, "departure_time", None)
    departure_utc = (
        _normalize_to_utc(departure)
        if isinstance(departure, datetime)
        else datetime.now(timezone.utc)
    )

    current_lat = float(getattr(ride, "start_point_lat"))
    current_lng = float(getattr(ride, "start_point_lng"))
    current_eta = departure_utc
    total_km = 0.0

    pickup_order_by_booking: Dict[UUID, int] = {}
    dropoff_order_by_booking: Dict[UUID, int] = {}
    pickup_eta_by_booking: Dict[UUID, datetime] = {}
    dropoff_eta_by_booking: Dict[UUID, datetime] = {}
    pickup_km_by_booking: Dict[UUID, float] = {}
    dropoff_km_by_booking: Dict[UUID, float] = {}

    for idx, event in enumerate(sequence, start=1):
        leg_km = _haversine_km(current_lat, current_lng, event.lat, event.lng)
        total_km += leg_km

        travel_minutes = max(0, int(round((leg_km / AVG_URBAN_SPEED_KMH) * 60)))
        current_eta = current_eta + timedelta(minutes=travel_minutes)

        if event.event_type == "pickup":
            pickup_order_by_booking[event.booking_id] = idx
            pickup_eta_by_booking[event.booking_id] = current_eta
            pickup_km_by_booking[event.booking_id] = total_km
        else:
            dropoff_order_by_booking[event.booking_id] = idx
            dropoff_eta_by_booking[event.booking_id] = current_eta
            dropoff_km_by_booking[event.booking_id] = total_km

        current_eta = current_eta + timedelta(minutes=ROUTE_PLAN_STOP_DWELL_MINUTES)
        current_lat = event.lat
        current_lng = event.lng

    end_lat = float(getattr(ride, "end_point_lat"))
    end_lng = float(getattr(ride, "end_point_lng"))
    total_km += _haversine_km(current_lat, current_lng, end_lat, end_lng)

    segment_km_by_booking: Dict[UUID, float] = {}
    for booking_id, pickup_km in pickup_km_by_booking.items():
        drop_km = dropoff_km_by_booking.get(booking_id)
        if drop_km is None:
            continue
        segment_km_by_booking[booking_id] = max(0.0, drop_km - pickup_km)

    duration_minutes = _resolve_duration_minutes(None, total_km)
    signature = ",".join(
        f"{event.event_type}:{event.booking_id}"
        for event in sequence
    )

    # Always keep a deterministic fallback polyline that includes route stops.
    fallback_points: List[tuple[float, float]] = [
        (float(getattr(ride, "start_point_lat")), float(getattr(ride, "start_point_lng")))
    ]
    fallback_points.extend((event.lat, event.lng) for event in sequence)
    fallback_points.append(
        (float(getattr(ride, "end_point_lat")), float(getattr(ride, "end_point_lng")))
    )
    fallback_polyline = _encode_polyline(fallback_points)

    return _RouteCandidatePlan(
        key=key,
        label=label,
        is_optimal=is_optimal,
        strategy=strategy,
        sequence=sequence,
        signature=signature,
        distance_km=round(total_km, 3),
        duration_minutes=duration_minutes,
        pickup_order_by_booking=pickup_order_by_booking,
        dropoff_order_by_booking=dropoff_order_by_booking,
        pickup_eta_by_booking=pickup_eta_by_booking,
        dropoff_eta_by_booking=dropoff_eta_by_booking,
        segment_km_by_booking=segment_km_by_booking,
        polyline=fallback_polyline,
    )


def _hydrate_candidate_from_google_maps(
    *,
    ride: Any,
    candidate: _RouteCandidatePlan,
) -> None:
    try:
        waypoint_pairs = [(event.lat, event.lng) for event in candidate.sequence]
        client = get_google_maps_client()
        directions = client.get_directions(
            origin=(float(getattr(ride, "start_point_lat")), float(getattr(ride, "start_point_lng"))),
            destination=(float(getattr(ride, "end_point_lat")), float(getattr(ride, "end_point_lng"))),
            alternatives=False,
            waypoints=waypoint_pairs,
            optimize_waypoints=False,
        )
        if not directions:
            return

        polyline = directions.get("polyline")
        if isinstance(polyline, str) and polyline.strip():
            candidate.polyline = polyline.strip()

        try:
            candidate.distance_km = float(directions.get("distance_km") or candidate.distance_km)
        except (TypeError, ValueError):
            pass
        try:
            candidate.duration_minutes = int(directions.get("duration_minutes") or candidate.duration_minutes)
        except (TypeError, ValueError):
            pass

        summary = str(directions.get("summary") or "").strip()
        if summary:
            candidate.summary = summary
    except Exception as exc:
        logger.warning("Failed to hydrate route candidate from Google Maps: %s", exc)


def _route_candidate_payload(
    *,
    candidate: _RouteCandidatePlan,
    route_input_by_booking: Dict[UUID, _RouteBookingInput],
) -> Dict[str, Any]:
    sequence_payload: List[Dict[str, Any]] = []
    for idx, event in enumerate(candidate.sequence, start=1):
        route_input = route_input_by_booking.get(event.booking_id)
        if route_input is not None:
            address = (
                route_input.pickup_address
                if event.event_type == "pickup"
                else route_input.dropoff_address
            )
        else:
            address = ""

        sequence_payload.append(
            {
                "order": idx,
                "booking_id": str(event.booking_id),
                "event_type": event.event_type,
                "lat": event.lat,
                "lng": event.lng,
                "address": address,
            }
        )

    return {
        "key": candidate.key,
        "label": candidate.label,
        "is_optimal": candidate.is_optimal,
        "distance_km": round(float(candidate.distance_km or 0.0), 3),
        "duration_minutes": int(max(1, candidate.duration_minutes or 1)),
        "polyline": candidate.polyline,
        "summary": candidate.summary,
        "stop_sequence": sequence_payload,
    }


async def _load_active_canonical_ride_bookings(
    db: AsyncSession,
    ride_id: UUID,
) -> List[RideBookingModel]:
    rows = await _load_canonical_ride_bookings(db, ride_id)
    return [
        row
        for row in rows
        if _canonical_booking_status(getattr(row, "status", None)) in ACTIVE_BOOKING_STATUSES
    ]


def _validate_existing_passenger_detour(
    *,
    ride: Any,
    existing_inputs: List[_RouteBookingInput],
    tentative_input: _RouteBookingInput,
) -> Optional[str]:
    if not existing_inputs:
        return None

    before_plan = _build_candidate_plan(
        ride=ride,
        route_inputs=existing_inputs,
        strategy="optimal",
        key="before",
        label="Before",
        is_optimal=True,
    )
    after_plan = _build_candidate_plan(
        ride=ride,
        route_inputs=[*existing_inputs, tentative_input],
        strategy="optimal",
        key="after",
        label="After",
        is_optimal=True,
    )

    if before_plan is None or after_plan is None:
        return None

    for existing in existing_inputs:
        before_km = before_plan.segment_km_by_booking.get(existing.booking_id)
        after_km = after_plan.segment_km_by_booking.get(existing.booking_id)
        if before_km is None or after_km is None or before_km <= 0:
            continue

        allowed_km = (before_km * (1.0 + MAX_EXISTING_PASSENGER_DETOUR_RATIO)) + MAX_EXISTING_PASSENGER_DETOUR_BUFFER_KM
        if after_km > allowed_km:
            return (
                "This booking would exceed the detour guard for existing passengers "
                f"(max {int(MAX_EXISTING_PASSENGER_DETOUR_RATIO * 100)}% + "
                f"{MAX_EXISTING_PASSENGER_DETOUR_BUFFER_KM:.1f} km buffer)."
            )

    return None


async def _recompute_and_persist_route_plan(
    db: AsyncSession,
    *,
    ride: Any,
    preferred_route_key: Optional[str] = None,
) -> None:
    if not _is_ride_route_mutable(ride):
        # Route freeze rule: only mutable before ride starts.
        return

    ride_id = getattr(ride, "id", None)
    if not isinstance(ride_id, UUID):
        return

    active_rows = await _load_active_canonical_ride_bookings(db, ride_id)
    route_inputs = [
        route_input
        for route_input in (
            _to_route_input_from_model(row)
            for row in active_rows
        )
        if route_input is not None
    ]

    if not route_inputs:
        ride.route_plan_version = int(getattr(ride, "route_plan_version", 0) or 0) + 1
        ride.route_selected_key = None
        ride.route_alternatives = []
        await db.commit()
        return

    candidates: List[_RouteCandidatePlan] = []
    seen_signatures: set[str] = set()

    for key, label, strategy, is_optimal in (
        ("optimal", "Optimal", "optimal", True),
        ("alt_dropoff", "Alternative 1", "dropoff_priority", False),
        ("alt_pickup", "Alternative 2", "pickup_priority", False),
    ):
        candidate = _build_candidate_plan(
            ride=ride,
            route_inputs=route_inputs,
            strategy=strategy,
            key=key,
            label=label,
            is_optimal=is_optimal,
        )
        if candidate is None or candidate.signature in seen_signatures:
            continue

        _hydrate_candidate_from_google_maps(ride=ride, candidate=candidate)
        candidates.append(candidate)
        seen_signatures.add(candidate.signature)

    if not candidates:
        return

    selected_key = (
        (preferred_route_key or "").strip()
        or str(getattr(ride, "route_selected_key", "") or "").strip()
        or "optimal"
    )
    selected = next((c for c in candidates if c.key == selected_key), candidates[0])

    route_input_by_booking: Dict[UUID, _RouteBookingInput] = {
        route_input.booking_id: route_input for route_input in route_inputs
    }
    next_plan_version = int(getattr(ride, "route_plan_version", 0) or 0) + 1

    ride.route_plan_version = next_plan_version
    ride.route_selected_key = selected.key
    ride.route_alternatives = [
        _route_candidate_payload(candidate=c, route_input_by_booking=route_input_by_booking)
        for c in candidates
    ]
    if selected.polyline:
        ride.polyline = selected.polyline
    ride.route_distance_km = round(float(selected.distance_km or 0.0), 3)
    ride.estimated_duration_minutes = int(max(1, selected.duration_minutes or 1))

    active_by_booking_id: Dict[UUID, RideBookingModel] = {
        UUID(str(row.id)): row for row in active_rows
    }
    for booking_id, booking in active_by_booking_id.items():
        booking.pickup_stop_order = selected.pickup_order_by_booking.get(booking_id)
        booking.dropoff_stop_order = selected.dropoff_order_by_booking.get(booking_id)
        booking.planned_pickup_eta = selected.pickup_eta_by_booking.get(booking_id)
        booking.planned_dropoff_eta = selected.dropoff_eta_by_booking.get(booking_id)
        segment_km = selected.segment_km_by_booking.get(booking_id)
        if segment_km is not None:
            # Keep canonical and legacy payload parity for passenger segment details.
            booking.segment_km = round(segment_km, 3)
        booking.route_plan_version = next_plan_version

    await db.commit()


async def _apply_selected_route_key_for_driver(
    db: AsyncSession,
    *,
    ride: Any,
    route_key: str,
) -> bool:
    alternatives = getattr(ride, "route_alternatives", None)
    if not isinstance(alternatives, list) or not alternatives:
        return False

    normalized_key = (route_key or "").strip()
    if not normalized_key:
        return False

    exists = any(str(item.get("key", "")).strip() == normalized_key for item in alternatives if isinstance(item, dict))
    if not exists:
        return False

    await _recompute_and_persist_route_plan(
        db,
        ride=ride,
        preferred_route_key=normalized_key,
    )
    return True


def _ride_route_text(ride: Any) -> str:
    origin = str(
        getattr(ride, "origin", None)
        or getattr(ride, "start_point_address", None)
        or "Origin"
    ).strip()
    destination = str(
        getattr(ride, "destination", None)
        or getattr(ride, "end_point_address", None)
        or "Destination"
    ).strip()
    return f"{origin} -> {destination}"


def _ride_departure_text(ride: Any) -> str:
    departure = getattr(ride, "departure_time", None)
    if not isinstance(departure, datetime):
        return "scheduled time"

    local_departure = departure.astimezone() if departure.tzinfo else departure
    return local_departure.strftime("%d %b %Y %I:%M %p")


def _booking_notification_metadata(
    *,
    ride: Any,
    booking: Any,
    passenger_id: UUID,
    seats_remaining: int,
) -> Dict[str, Any]:
    departure = getattr(ride, "departure_time", None)
    departure_iso = (
        departure.isoformat()
        if isinstance(departure, datetime)
        else None
    )

    return {
        "ride_id": str(getattr(ride, "id", "")),
        "booking_id": str(getattr(booking, "id", "")),
        "booked_seats": _to_int(getattr(booking, "booked_seats", 1), default=1),
        "seats_remaining": max(0, seats_remaining),
        "origin": str(
            getattr(ride, "origin", None)
            or getattr(ride, "start_point_address", None)
            or ""
        ),
        "destination": str(
            getattr(ride, "destination", None)
            or getattr(ride, "end_point_address", None)
            or ""
        ),
        "departure_time": departure_iso,
        "passenger_id": str(passenger_id),
        "driver_id": str(getattr(ride, "driver_id", "")),
    }


async def _send_single_ride_notification(
    db: AsyncSession,
    *,
    receiver_user_id: UUID,
    title: str,
    message: str,
    metadata: Dict[str, Any],
    event_name: str,
) -> None:
    try:
        payload = dict(metadata)
        payload["event"] = event_name

        await send_push_notification(
            db=db,
            background_tasks=None,
            notification_data=NotificationCreate(
                user_id=receiver_user_id,
                title=title,
                message=message,
                type=NotificationTypeEnum.RIDE,
                priority=NotificationPriorityEnum.NORMAL,
                metadata=payload,
            ),
        )
    except Exception as exc:
        logger.exception(
            "Ride booking notification failed: user_id=%s event=%s error=%s",
            receiver_user_id,
            event_name,
            exc,
        )


async def _send_booking_notifications(
    db: AsyncSession,
    *,
    ride: Any,
    booking: Any,
    passenger_id: UUID,
) -> None:
    driver_id = getattr(ride, "driver_id", None)
    if not isinstance(driver_id, UUID):
        logger.warning(
            "Skipping booking notifications: invalid driver_id on ride=%s",
            getattr(ride, "id", None),
        )
        return

    seats_remaining = max(0, _to_int(getattr(ride, "seats_available", 0), default=0))
    booked_seats = _to_int(getattr(booking, "booked_seats", 1), default=1)
    total_price = float(getattr(booking, "total_price", 0) or 0)
    route_text = _ride_route_text(ride)
    departure_text = _ride_departure_text(ride)

    metadata = _booking_notification_metadata(
        ride=ride,
        booking=booking,
        passenger_id=passenger_id,
        seats_remaining=seats_remaining,
    )

    await _send_single_ride_notification(
        db,
        receiver_user_id=driver_id,
        title="New booking received",
        message=(
            f"{booked_seats} seat{'s' if booked_seats > 1 else ''} booked for {route_text}. "
            f"Departure: {departure_text}."
        ),
        metadata=metadata,
        event_name="ride_booking_received",
    )

    await _send_single_ride_notification(
        db,
        receiver_user_id=passenger_id,
        title="Booking confirmed",
        message=(
            f"Your booking is confirmed: {booked_seats} seat{'s' if booked_seats > 1 else ''} "
            f"for {route_text}. Departure: {departure_text}. "
            f"Fare: PKR {total_price:.0f}."
        ),
        metadata=metadata,
        event_name="ride_booking_confirmed",
    )

    if seats_remaining <= 0:
        await _send_single_ride_notification(
            db,
            receiver_user_id=driver_id,
            title="All seats booked",
            message=(
                f"All seats are now booked for your ride {route_text}. "
                f"Departure: {departure_text}."
            ),
            metadata=metadata,
            event_name="ride_fully_booked",
        )

        await _send_single_ride_notification(
            db,
            receiver_user_id=passenger_id,
            title="Ride fully booked",
            message=(
                f"This ride is now fully booked ({route_text}). "
                f"Departure: {departure_text}."
            ),
            metadata=metadata,
            event_name="ride_fully_booked",
        )


async def _load_user_display_name(
    db: AsyncSession,
    user_id: UUID,
) -> str:
    result = await db.execute(
        select(User.full_name)
        .where(User.id == user_id)
        .limit(1)
    )
    full_name = result.scalar_one_or_none()
    text = str(full_name or "").strip()
    return text or "User"


async def _send_dropoff_rating_prompt_notifications(
    db: AsyncSession,
    *,
    booking: Any,
    driver_user_id: UUID,
) -> None:
    booking_id = getattr(booking, "id", None)
    ride_id = getattr(booking, "ride_id", None)
    passenger_id = getattr(booking, "passenger_id", None)

    if not isinstance(booking_id, UUID) or not isinstance(ride_id, UUID):
        logger.warning(
            "Skipping dropoff rating prompts: invalid ride/booking identifiers booking_id=%s ride_id=%s",
            booking_id,
            ride_id,
        )
        return

    if not isinstance(passenger_id, UUID):
        logger.warning(
            "Skipping dropoff rating prompts: invalid passenger_id on booking=%s",
            booking_id,
        )
        return

    driver_name = await _load_user_display_name(db, driver_user_id)
    passenger_name = await _load_user_display_name(db, passenger_id)

    base_metadata = {
        "ride_id": str(ride_id),
        "booking_id": str(booking_id),
    }

    await _send_single_ride_notification(
        db,
        receiver_user_id=passenger_id,
        title="Rate your driver",
        message=f"You were dropped off. Please rate {driver_name}.",
        metadata={
            **base_metadata,
            "rater_id": str(passenger_id),
            "ratee_id": str(driver_user_id),
            "counterpart_name": driver_name,
            "role_context": "passenger_rates_driver",
        },
        event_name="rating_prompt_required",
    )

    await _send_single_ride_notification(
        db,
        receiver_user_id=driver_user_id,
        title="Rate your passenger",
        message=f"Please rate {passenger_name} for this dropoff.",
        metadata={
            **base_metadata,
            "rater_id": str(driver_user_id),
            "ratee_id": str(passenger_id),
            "counterpart_name": passenger_name,
            "role_context": "driver_rates_passenger",
        },
        event_name="rating_prompt_required",
    )


async def _send_booking_cancelled_by_passenger_notifications(
    db: AsyncSession,
    *,
    ride: Any,
    booking: Any,
    passenger_id: UUID,
    reason: Optional[str] = None,
) -> None:
    driver_id = getattr(ride, "driver_id", None)
    if not isinstance(driver_id, UUID):
        logger.warning(
            "Skipping booking cancellation notifications: invalid driver_id on ride=%s",
            getattr(ride, "id", None),
        )
        return

    seats_remaining = max(0, _to_int(getattr(ride, "seats_available", 0), default=0))
    booked_seats = _to_int(getattr(booking, "booked_seats", 1), default=1)
    route_text = _ride_route_text(ride)
    departure_text = _ride_departure_text(ride)
    cleaned_reason = str(reason or "").strip()
    reason_suffix = f" Reason: {cleaned_reason}." if cleaned_reason else ""

    metadata = _booking_notification_metadata(
        ride=ride,
        booking=booking,
        passenger_id=passenger_id,
        seats_remaining=seats_remaining,
    )
    metadata["cancelled_by"] = "passenger"
    if cleaned_reason:
        metadata["cancellation_reason"] = cleaned_reason

    await _send_single_ride_notification(
        db,
        receiver_user_id=driver_id,
        title="Booking cancelled by passenger",
        message=(
            f"{booked_seats} seat{'s' if booked_seats > 1 else ''} booking for {route_text} "
            f"was cancelled by the passenger. Departure: {departure_text}.{reason_suffix}"
        ),
        metadata=metadata,
        event_name="ride_booking_cancelled_by_passenger",
    )

    await _send_single_ride_notification(
        db,
        receiver_user_id=passenger_id,
        title="Booking cancelled",
        message=(
            f"You cancelled your booking for {route_text}. "
            f"Departure: {departure_text}.{reason_suffix}"
        ),
        metadata=metadata,
        event_name="ride_booking_cancelled_by_passenger",
    )


async def _send_ride_cancelled_by_driver_notifications(
    db: AsyncSession,
    *,
    ride: Any,
    cancelled_bookings: List[Any],
) -> None:
    driver_id = getattr(ride, "driver_id", None)
    if not isinstance(driver_id, UUID):
        logger.warning(
            "Skipping ride cancellation notifications: invalid driver_id on ride=%s",
            getattr(ride, "id", None),
        )
        return

    route_text = _ride_route_text(ride)
    departure_text = _ride_departure_text(ride)

    passenger_booking_map: Dict[UUID, Any] = {}
    for booking in cancelled_bookings:
        raw_passenger_id = getattr(booking, "passenger_id", None)
        if isinstance(raw_passenger_id, UUID):
            passenger_booking_map.setdefault(raw_passenger_id, booking)
            continue
        try:
            parsed = UUID(str(raw_passenger_id))
            passenger_booking_map.setdefault(parsed, booking)
        except (TypeError, ValueError):
            continue

    base_metadata: Dict[str, Any] = {
        "ride_id": str(getattr(ride, "id", "")),
        "origin": str(getattr(ride, "origin", None) or getattr(ride, "start_point_address", None) or ""),
        "destination": str(getattr(ride, "destination", None) or getattr(ride, "end_point_address", None) or ""),
        "departure_time": (
            getattr(ride, "departure_time", None).isoformat()
            if isinstance(getattr(ride, "departure_time", None), datetime)
            else None
        ),
        "driver_id": str(driver_id),
        "cancelled_by": "driver",
        "affected_bookings": len(passenger_booking_map),
    }

    await _send_single_ride_notification(
        db,
        receiver_user_id=driver_id,
        title="Ride cancelled",
        message=(
            f"You cancelled this ride ({route_text}). "
            f"Affected bookings: {len(passenger_booking_map)}."
        ),
        metadata=base_metadata,
        event_name="ride_cancelled_by_driver",
    )

    for passenger_id, booking in passenger_booking_map.items():
        booked_seats = _to_int(
            getattr(booking, "booked_seats", getattr(booking, "seats_reserved", 1)),
            default=1,
        )
        passenger_metadata = dict(base_metadata)
        passenger_metadata["passenger_id"] = str(passenger_id)
        passenger_metadata["booking_id"] = str(getattr(booking, "id", ""))
        passenger_metadata["booked_seats"] = booked_seats

        await _send_single_ride_notification(
            db,
            receiver_user_id=passenger_id,
            title="Ride cancelled by driver",
            message=(
                f"Your booking for {route_text} was cancelled by the driver. "
                f"Departure: {departure_text}."
            ),
            metadata=passenger_metadata,
            event_name="ride_cancelled_by_driver",
        )


async def _collect_active_ride_bookings_for_notifications(
    db: AsyncSession,
    *,
    ride: Any,
) -> List[Any]:
    active_bookings: List[Any] = []

    for booking in getattr(ride, "bookings", []) or []:
        booking_status = str(getattr(booking.status, "value", booking.status) or "").lower()
        if booking_status in ACTIVE_BOOKING_STATUSES:
            active_bookings.append(booking)

    ride_id = getattr(ride, "id", None)
    if not ride_id:
        return active_bookings

    try:
        result = await db.execute(
            select(RideBookingModel).where(RideBookingModel.ride_id == ride_id)
        )
        for booking in result.scalars().all():
            booking_status = str(getattr(booking.status, "value", booking.status) or "").lower()
            if booking_status in ACTIVE_BOOKING_STATUSES:
                active_bookings.append(booking)
    except Exception:
        logger.exception(
            "Failed loading ride_bookings for cancellation notifications: ride_id=%s",
            ride_id,
        )

    return active_bookings


def _build_slot_payload(
    *,
    start_utc: datetime,
    end_utc: datetime,
    source: str,
    entity_id: str,
    status_value: str,
) -> Dict[str, Any]:
    return {
        "start_time": start_utc.isoformat(),
        "end_time": end_utc.isoformat(),
        "duration_minutes": max(1, int((end_utc - start_utc).total_seconds() // 60)),
        "source": source,
        "entity_id": entity_id,
        "status": status_value,
    }


def _format_slot_window(start_utc: datetime, end_utc: datetime) -> str:
    return f"{start_utc.strftime('%H:%M')} - {end_utc.strftime('%H:%M')} UTC"


def _clip_window(
    start_utc: datetime,
    end_utc: datetime,
    clip_start_utc: datetime,
    clip_end_utc: datetime,
) -> tuple[datetime, datetime]:
    return max(start_utc, clip_start_utc), min(end_utc, clip_end_utc)


async def _acquire_user_schedule_lock(
    db: AsyncSession,
    user_id: UUID,
    scope: str,
) -> None:
    try:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"{scope}:{user_id}"},
        )
    except Exception:
        logger.warning(
            "Could not acquire advisory lock for user=%s scope=%s",
            user_id,
            scope,
            exc_info=True,
        )


async def _find_driver_overlap(
    db: AsyncSession,
    user_id: UUID,
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> Optional[Dict[str, Any]]:
    query = text(
        f"""
        SELECT
            id,
            departure_time,
            ({RIDE_DURATION_SQL})::int AS duration_minutes,
            LOWER(COALESCE(status::text, '')) AS ride_status
        FROM rides
        WHERE driver_id = :user_id
          AND LOWER(COALESCE(status::text, '')) IN ({ACTIVE_RIDE_STATUS_SQL})
          AND departure_time < :window_end
          AND {RIDE_END_SQL} > :window_start
        ORDER BY departure_time ASC
        LIMIT 1
        """
    )
    result = await db.execute(
        query,
        {
            "user_id": user_id,
            "window_start": window_start_utc,
            "window_end": window_end_utc,
            "avg_speed_kmh": AVG_URBAN_SPEED_KMH,
            "default_duration": DEFAULT_RIDE_DURATION_MINUTES,
        },
    )
    row = result.first()
    if not row:
        return None

    start_utc = _normalize_to_utc(row.departure_time)
    duration_minutes = _resolve_duration_minutes(int(row.duration_minutes or 0), None)
    end_utc = _window_end(start_utc, duration_minutes)
    return {
        "ride_id": str(row.id),
        "start_time": start_utc,
        "end_time": end_utc,
        "status": str(row.ride_status or "open"),
    }


async def _find_passenger_booking_overlap_from_table(
    db: AsyncSession,
    *,
    user_id: UUID,
    window_start_utc: datetime,
    window_end_utc: datetime,
    booking_table: str,
    passenger_col: str,
    status_col: str,
    ride_col: str,
) -> Optional[Dict[str, Any]]:
    query = text(
        f"""
        SELECT
            r.id AS ride_id,
            r.departure_time,
            ({RIDE_DURATION_SQL})::int AS duration_minutes,
            LOWER(COALESCE(r.status::text, '')) AS ride_status
        FROM {booking_table} b
        JOIN rides r ON r.id = b.{ride_col}
        WHERE b.{passenger_col} = :user_id
          AND LOWER(COALESCE(b.{status_col}::text, '')) IN ({ACTIVE_BOOKING_STATUS_SQL})
          AND LOWER(COALESCE(r.status::text, '')) IN ({ACTIVE_RIDE_STATUS_SQL})
          AND r.departure_time < :window_end
          AND {RIDE_END_SQL} > :window_start
        ORDER BY r.departure_time ASC
        LIMIT 1
        """
    )
    result = await db.execute(
        query,
        {
            "user_id": user_id,
            "window_start": window_start_utc,
            "window_end": window_end_utc,
            "avg_speed_kmh": AVG_URBAN_SPEED_KMH,
            "default_duration": DEFAULT_RIDE_DURATION_MINUTES,
        },
    )
    row = result.first()
    if not row:
        return None

    start_utc = _normalize_to_utc(row.departure_time)
    duration_minutes = _resolve_duration_minutes(int(row.duration_minutes or 0), None)
    end_utc = _window_end(start_utc, duration_minutes)
    return {
        "source": "booking",
        "entity_id": str(row.ride_id),
        "start_time": start_utc,
        "end_time": end_utc,
        "status": str(row.ride_status or "open"),
    }


async def _find_passenger_request_overlap(
    db: AsyncSession,
    *,
    user_id: UUID,
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> Optional[Dict[str, Any]]:
    try:
        query = text(
            f"""
            SELECT id, departure_time, LOWER(COALESCE(status::text, '')) AS request_status
            FROM ride_requests
            WHERE passenger_id = :user_id
              AND LOWER(COALESCE(status::text, '')) IN ({ACTIVE_REQUEST_STATUS_SQL})
              AND departure_time < :window_end
              AND departure_time + make_interval(mins => :request_duration) > :window_start
            ORDER BY departure_time ASC
            LIMIT 1
            """
        )
        result = await db.execute(
            query,
            {
                "user_id": user_id,
                "window_start": window_start_utc,
                "window_end": window_end_utc,
                "request_duration": DEFAULT_REQUEST_DURATION_MINUTES,
            },
        )
        row = result.first()
        if not row:
            return None

        start_utc = _normalize_to_utc(row.departure_time)
        end_utc = _window_end(start_utc, DEFAULT_REQUEST_DURATION_MINUTES)
        return {
            "source": "ride_request",
            "entity_id": str(row.id),
            "start_time": start_utc,
            "end_time": end_utc,
            "status": str(row.request_status or "pending"),
        }
    except Exception:
        return None


async def _find_passenger_overlap(
    db: AsyncSession,
    *,
    user_id: UUID,
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> Optional[Dict[str, Any]]:
    overlap = await _find_passenger_booking_overlap_from_table(
        db,
        user_id=user_id,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        booking_table="ride_bookings",
        passenger_col="passenger_id",
        status_col="status",
        ride_col="ride_id",
    )
    if overlap:
        return overlap

    overlap = await _find_passenger_booking_overlap_from_table(
        db,
        user_id=user_id,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        booking_table="bookings",
        passenger_col="passenger_id",
        status_col="status",
        ride_col="ride_id",
    )
    if overlap:
        return overlap

    return await _find_passenger_request_overlap(
        db,
        user_id=user_id,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
    )


async def _collect_driver_slots(
    db: AsyncSession,
    *,
    user_id: UUID,
    day_start_utc: datetime,
    day_end_utc: datetime,
    target_local_date: date,
    client_tz: timezone,
) -> List[Dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    query = text(
        f"""
        SELECT
            id,
            departure_time,
            ({RIDE_DURATION_SQL})::int AS duration_minutes,
            LOWER(COALESCE(status::text, '')) AS ride_status
        FROM rides
        WHERE driver_id = :user_id
          AND LOWER(COALESCE(status::text, '')) IN ({ACTIVE_RIDE_STATUS_SQL})
          AND NOT (
                LOWER(COALESCE(status::text, '')) IN ('open', 'scheduled')
            AND departure_time < :now_utc
          )
          AND departure_time < :day_end
          AND {RIDE_END_SQL} > :day_start
        ORDER BY departure_time ASC
        """
    )
    result = await db.execute(
        query,
        {
            "user_id": user_id,
            "now_utc": now_utc,
            "day_start": day_start_utc,
            "day_end": day_end_utc,
            "avg_speed_kmh": AVG_URBAN_SPEED_KMH,
            "default_duration": DEFAULT_RIDE_DURATION_MINUTES,
        },
    )

    slots: List[Dict[str, Any]] = []
    for row in result.fetchall():
        raw_start = _normalize_to_utc(row.departure_time)
        duration_minutes = _resolve_duration_minutes(int(row.duration_minutes or 0), None)
        raw_end = _window_end(raw_start, duration_minutes)
        start_utc, end_utc = _clip_window(raw_start, raw_end, day_start_utc, day_end_utc)
        slots.append(
            _build_slot_payload(
                start_utc=start_utc,
                end_utc=end_utc,
                source="driver_ride",
                entity_id=str(row.id),
                status_value=str(row.ride_status or "open"),
            )
        )
    slots.extend(
        await _collect_driver_recurring_schedule_slots(
            db,
            user_id=user_id,
            day_start_utc=day_start_utc,
            day_end_utc=day_end_utc,
            target_local_date=target_local_date,
            client_tz=client_tz,
        )
    )

    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for slot in slots:
        key = (
            str(slot.get("source", "")),
            str(slot.get("entity_id", "")),
            str(slot.get("start_time", "")),
            str(slot.get("end_time", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(slot)

    deduped.sort(key=lambda item: str(item.get("start_time", "")))
    return deduped


async def _collect_passenger_booking_slots_from_table(
    db: AsyncSession,
    *,
    user_id: UUID,
    day_start_utc: datetime,
    day_end_utc: datetime,
    booking_table: str,
    passenger_col: str,
    status_col: str,
    ride_col: str,
    source_name: str,
) -> List[Dict[str, Any]]:
    now_utc = datetime.now(timezone.utc)
    query = text(
        f"""
        SELECT
            r.id AS ride_id,
            r.departure_time,
            ({RIDE_DURATION_SQL})::int AS duration_minutes,
            LOWER(COALESCE(r.status::text, '')) AS ride_status
        FROM {booking_table} b
        JOIN rides r ON r.id = b.{ride_col}
        WHERE b.{passenger_col} = :user_id
          AND LOWER(COALESCE(b.{status_col}::text, '')) IN ({ACTIVE_BOOKING_STATUS_SQL})
          AND LOWER(COALESCE(r.status::text, '')) IN ({ACTIVE_RIDE_STATUS_SQL})
          AND NOT (
                LOWER(COALESCE(r.status::text, '')) IN ('open', 'scheduled')
            AND r.departure_time < :now_utc
          )
          AND r.departure_time < :day_end
          AND {RIDE_END_SQL} > :day_start
        ORDER BY r.departure_time ASC
        """
    )
    result = await db.execute(
        query,
        {
            "user_id": user_id,
            "now_utc": now_utc,
            "day_start": day_start_utc,
            "day_end": day_end_utc,
            "avg_speed_kmh": AVG_URBAN_SPEED_KMH,
            "default_duration": DEFAULT_RIDE_DURATION_MINUTES,
        },
    )

    slots: List[Dict[str, Any]] = []
    for row in result.fetchall():
        raw_start = _normalize_to_utc(row.departure_time)
        duration_minutes = _resolve_duration_minutes(int(row.duration_minutes or 0), None)
        raw_end = _window_end(raw_start, duration_minutes)
        start_utc, end_utc = _clip_window(raw_start, raw_end, day_start_utc, day_end_utc)
        slots.append(
            _build_slot_payload(
                start_utc=start_utc,
                end_utc=end_utc,
                source=source_name,
                entity_id=str(row.ride_id),
                status_value=str(row.ride_status or "open"),
            )
        )
    return slots


async def _collect_passenger_request_slots(
    db: AsyncSession,
    *,
    user_id: UUID,
    day_start_utc: datetime,
    day_end_utc: datetime,
) -> List[Dict[str, Any]]:
    try:
        query = text(
            f"""
            SELECT id, departure_time, LOWER(COALESCE(status::text, '')) AS request_status
            FROM ride_requests
            WHERE passenger_id = :user_id
              AND LOWER(COALESCE(status::text, '')) IN ({ACTIVE_REQUEST_STATUS_SQL})
              AND departure_time < :day_end
              AND departure_time + make_interval(mins => :request_duration) > :day_start
            ORDER BY departure_time ASC
            """
        )
        result = await db.execute(
            query,
            {
                "user_id": user_id,
                "day_start": day_start_utc,
                "day_end": day_end_utc,
                "request_duration": DEFAULT_REQUEST_DURATION_MINUTES,
            },
        )

        slots: List[Dict[str, Any]] = []
        for row in result.fetchall():
            raw_start = _normalize_to_utc(row.departure_time)
            raw_end = _window_end(raw_start, DEFAULT_REQUEST_DURATION_MINUTES)
            start_utc, end_utc = _clip_window(raw_start, raw_end, day_start_utc, day_end_utc)
            slots.append(
                _build_slot_payload(
                    start_utc=start_utc,
                    end_utc=end_utc,
                    source="ride_request",
                    entity_id=str(row.id),
                    status_value=str(row.request_status or "pending"),
                )
            )
        return slots
    except Exception:
        return []


async def _collect_passenger_slots(
    db: AsyncSession,
    *,
    user_id: UUID,
    day_start_utc: datetime,
    day_end_utc: datetime,
    target_local_date: date,
    client_tz: timezone,
) -> List[Dict[str, Any]]:
    slots: List[Dict[str, Any]] = []
    slots.extend(
        await _collect_passenger_booking_slots_from_table(
            db,
            user_id=user_id,
            day_start_utc=day_start_utc,
            day_end_utc=day_end_utc,
            booking_table="ride_bookings",
            passenger_col="passenger_id",
            status_col="status",
            ride_col="ride_id",
            source_name="passenger_booking",
        )
    )
    slots.extend(
        await _collect_passenger_booking_slots_from_table(
            db,
            user_id=user_id,
            day_start_utc=day_start_utc,
            day_end_utc=day_end_utc,
            booking_table="bookings",
            passenger_col="passenger_id",
            status_col="status",
            ride_col="ride_id",
            source_name="passenger_booking_legacy",
        )
    )
    slots.extend(
        await _collect_passenger_request_slots(
            db,
            user_id=user_id,
            day_start_utc=day_start_utc,
            day_end_utc=day_end_utc,
        )
    )
    slots.extend(
        await _collect_passenger_recurring_subscription_slots(
            db,
            user_id=user_id,
            day_start_utc=day_start_utc,
            day_end_utc=day_end_utc,
            target_local_date=target_local_date,
            client_tz=client_tz,
        )
    )

    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for slot in slots:
        key = (
            str(slot.get("source", "")),
            str(slot.get("entity_id", "")),
            str(slot.get("start_time", "")),
            str(slot.get("end_time", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(slot)

    deduped.sort(key=lambda item: str(item.get("start_time", "")))
    return deduped


def _normalize_schedule_days(days_raw: Any) -> List[str]:
    normalized: List[str] = []
    for raw in list(days_raw or []):
        short = str(raw or "").strip()[:3].title()
        if short in WEEKDAY_INDEX and short not in normalized:
            normalized.append(short)
    return normalized


def _schedule_matches_target_date(target_date: date, days_of_week: List[str]) -> bool:
    normalized = _normalize_schedule_days(days_of_week)
    if not normalized:
        return False
    allowed_weekdays = {
        WEEKDAY_INDEX[day]
        for day in normalized
        if day in WEEKDAY_INDEX
    }
    return target_date.weekday() in allowed_weekdays


def _local_schedule_datetime_to_utc(
    *,
    target_local_date: date,
    departure_local_time: time,
    client_tz: timezone,
) -> datetime:
    local_dt = datetime.combine(target_local_date, departure_local_time, tzinfo=client_tz)
    return local_dt.astimezone(timezone.utc)


def _extract_schedule_duration_minutes(
    *,
    recurrence_meta: Any,
    start_lat: Optional[float],
    start_lng: Optional[float],
    end_lat: Optional[float],
    end_lng: Optional[float],
) -> int:
    if isinstance(recurrence_meta, dict):
        raw = recurrence_meta.get("estimated_duration_minutes")
        if raw is not None:
            try:
                parsed = int(raw)
                if parsed > 0:
                    return parsed
            except (TypeError, ValueError):
                pass

    if (
        start_lat is not None
        and start_lng is not None
        and end_lat is not None
        and end_lng is not None
    ):
        route_km = _haversine_km(start_lat, start_lng, end_lat, end_lng)
        inferred = int(math.ceil((route_km / AVG_URBAN_SPEED_KMH) * 60))
        if inferred > 0:
            return inferred

    return DEFAULT_RIDE_DURATION_MINUTES


async def _collect_driver_recurring_schedule_slots(
    db: AsyncSession,
    *,
    user_id: UUID,
    day_start_utc: datetime,
    day_end_utc: datetime,
    target_local_date: date,
    client_tz: timezone,
) -> List[Dict[str, Any]]:
    target_date = target_local_date
    query = text(
        f"""
        SELECT
            id,
            departure_time,
            start_date,
            end_date,
            days_of_week,
            recurrence_meta,
            start_lat,
            start_lng,
            end_lat,
            end_lng
        FROM recurring_schedules
        WHERE user_id = :user_id
          AND is_active = TRUE
          AND start_date <= :target_date
          AND end_date >= :target_date
        """
    )
    result = await db.execute(
        query,
        {
            "user_id": user_id,
            "target_date": target_date,
        },
    )

    slots: List[Dict[str, Any]] = []
    for row in result.fetchall():
        if not _schedule_matches_target_date(target_date, row.days_of_week):
            continue

        departure_value = row.departure_time
        if departure_value is None:
            continue
        start_utc = _local_schedule_datetime_to_utc(
            target_local_date=target_date,
            departure_local_time=departure_value,
            client_tz=client_tz,
        )
        duration_minutes = _extract_schedule_duration_minutes(
            recurrence_meta=row.recurrence_meta,
            start_lat=row.start_lat,
            start_lng=row.start_lng,
            end_lat=row.end_lat,
            end_lng=row.end_lng,
        )
        end_utc = _window_end(start_utc, duration_minutes)
        clip_start_utc, clip_end_utc = _clip_window(start_utc, end_utc, day_start_utc, day_end_utc)
        if clip_start_utc >= clip_end_utc:
            continue

        slots.append(
            _build_slot_payload(
                start_utc=clip_start_utc,
                end_utc=clip_end_utc,
                source="driver_recurring_schedule",
                entity_id=str(row.id),
                status_value="active",
            )
        )
    return slots


async def _collect_passenger_recurring_subscription_slots(
    db: AsyncSession,
    *,
    user_id: UUID,
    day_start_utc: datetime,
    day_end_utc: datetime,
    target_local_date: date,
    client_tz: timezone,
) -> List[Dict[str, Any]]:
    target_date = target_local_date
    query = text(
        f"""
        SELECT
            sub.id AS subscription_id,
            sub.status AS subscription_status,
            sch.departure_time,
            sch.start_date AS schedule_start_date,
            sch.end_date AS schedule_end_date,
            sch.days_of_week,
            sch.recurrence_meta,
            sch.start_lat,
            sch.start_lng,
            sch.end_lat,
            sch.end_lng,
            sub.overlap_start_date,
            sub.overlap_end_date,
            sub.departure_window_start,
            sub.departure_window_end
        FROM recurring_schedule_subscriptions sub
        JOIN recurring_schedules sch ON sch.id = sub.schedule_id
        WHERE sub.passenger_id = :user_id
          AND LOWER(COALESCE(sub.status::text, '')) IN ({ACTIVE_RECURRING_SUBSCRIPTION_STATUS_SQL})
          AND sch.is_active = TRUE
          AND sch.start_date <= :target_date
          AND sch.end_date >= :target_date
          AND sub.overlap_start_date <= :target_date
          AND sub.overlap_end_date >= :target_date
        """
    )
    result = await db.execute(
        query,
        {
            "user_id": user_id,
            "target_date": target_date,
        },
    )

    slots: List[Dict[str, Any]] = []
    for row in result.fetchall():
        if not _schedule_matches_target_date(target_date, row.days_of_week):
            continue

        departure_value = row.departure_time
        if departure_value is None:
            continue
        if (
            row.departure_window_start is not None
            and row.departure_window_end is not None
            and not (row.departure_window_start <= departure_value <= row.departure_window_end)
        ):
            continue

        start_utc = _local_schedule_datetime_to_utc(
            target_local_date=target_date,
            departure_local_time=departure_value,
            client_tz=client_tz,
        )
        duration_minutes = _extract_schedule_duration_minutes(
            recurrence_meta=row.recurrence_meta,
            start_lat=row.start_lat,
            start_lng=row.start_lng,
            end_lat=row.end_lat,
            end_lng=row.end_lng,
        )
        end_utc = _window_end(start_utc, duration_minutes)
        clip_start_utc, clip_end_utc = _clip_window(start_utc, end_utc, day_start_utc, day_end_utc)
        if clip_start_utc >= clip_end_utc:
            continue

        slots.append(
            _build_slot_payload(
                start_utc=clip_start_utc,
                end_utc=clip_end_utc,
                source="passenger_recurring_subscription",
                entity_id=str(row.subscription_id),
                status_value=str(row.subscription_status or "active"),
            )
        )
    return slots


def _safe_parse_verification_metadata(metadata_raw: Optional[str]) -> Dict[str, Any]:
    if not metadata_raw:
        return {}

    try:
        parsed = json.loads(metadata_raw)
    except (TypeError, ValueError):
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _is_identity_check_passed(metadata_raw: Optional[str], expected_doc_path: Optional[str]) -> bool:
    metadata = _safe_parse_verification_metadata(metadata_raw)
    identity_meta = metadata.get("identity_data_verification")
    if not isinstance(identity_meta, dict):
        return False

    stored_doc_path = str(identity_meta.get("document_path") or "").strip()
    latest_doc_path = str(expected_doc_path or "").strip()
    if stored_doc_path and latest_doc_path and stored_doc_path != latest_doc_path:
        return False

    status_value = str(identity_meta.get("check_status") or "").strip().lower()
    return status_value in {"passed", "pass", "verified", "approved", "success", "match"}


async def _has_required_driver_verifications(db: AsyncSession, user_id: UUID) -> bool:
    """Return True when required driver docs and identity checks are both verified."""
    try:
        records = await verification_crud.get_user_verifications(db, user_id)
    except Exception:
        return False

    latest_by_doc: Dict[str, Any] = {}
    for record in records:
        # get_user_verifications returns newest-first; keep first seen per doc type.
        latest_by_doc.setdefault(record.doc_type.value, record)

    required_docs = {
        DocumentTypeEnum.CNIC.value,
        DocumentTypeEnum.DRIVING_LICENSE.value,
        DocumentTypeEnum.SELFIE.value,
    }
    identity_required_docs = {
        DocumentTypeEnum.CNIC.value,
        DocumentTypeEnum.DRIVING_LICENSE.value,
    }

    for doc in required_docs:
        verification = latest_by_doc.get(doc)
        if verification is None:
            return False

        if verification.status.value != VerificationStatusEnum.VERIFIED.value:
            return False

        if doc in identity_required_docs and not _is_identity_check_passed(
            verification.meta_data,
            verification.doc_path,
        ):
            return False

    return True


async def _verify_driver_eligibility(db: AsyncSession, user_id: UUID) -> tuple[bool, str, Optional[Any]]:
    """
    Verify if user is eligible to create rides (must be verified active driver).
    
    Args:
        db: Async database session
        user_id: UUID of the user
    
    Returns:
        Tuple of (is_eligible, error_message, driver_profile)
    
    Notes:
        - Checks if driver profile exists
        - Checks if driver is verified
        - Checks if driver status is "active"
        - Checks if driver has at least one active vehicle
    """
    await ensure_driver_vehicle_schema_compat(db)
    driver = await drivers_crud.get_driver_profile(db, user_id)
    
    if not driver:
        return False, "Driver profile not found. Please register as a driver first.", None
    
    kyc_verified = await _has_required_driver_verifications(db, user_id)
    if kyc_verified:
        if not driver.is_verified:
            driver.is_verified = True
            if driver.status in (None, "pending"):
                driver.status = "active"
            await db.commit()
            await db.refresh(driver)
    else:
        if driver.is_verified:
            driver.is_verified = False
            if driver.status in (None, "active"):
                driver.status = "pending"
            await db.commit()
            await db.refresh(driver)
        return False, "Driver account is not verified. Please complete verification process.", None
    
    if driver.status != "active":
        return False, f"Driver account is {driver.status}. Only active drivers can create rides.", None
    
    # Check for active vehicles
    active_vehicles = [
        v for v in driver.vehicles
        if getattr(v, "is_active", True) is not False
        and getattr(v, "registration_verified", True) is not False
    ]
    if not active_vehicles:
        return False, "No active vehicle found. Please add a vehicle first.", None
    
    return True, "", driver


async def _ensure_legacy_driver_row(db: AsyncSession, user_id: UUID, driver_profile: Any) -> None:
    """Best-effort compatibility insert for legacy `drivers` FK targets."""
    license_number = str(getattr(driver_profile, "license_number", None) or "N/A").strip() or "N/A"
    verified = bool(getattr(driver_profile, "is_verified", False))
    verified_status_upper = "VERIFIED" if verified else "PENDING"
    verified_status_lower = "verified" if verified else "pending"
    rating_avg = float(getattr(driver_profile, "rating", 5.0) or 5.0)

    statements = [
        (
            """
            INSERT INTO drivers (user_id, license_number, verified, rating_avg, rating_count, created_at, updated_at)
            VALUES (
                :user_id,
                :license_number,
                CAST(:verified_status AS driver_verification_status),
                :rating_avg,
                :rating_count,
                NOW(),
                NOW()
            )
            ON CONFLICT (user_id) DO NOTHING
            """,
            {
                "user_id": user_id,
                "license_number": license_number,
                "verified_status": verified_status_upper,
                "rating_avg": rating_avg,
                "rating_count": 0,
            },
        ),
        (
            """
            INSERT INTO drivers (user_id, license_number, verified, rating_avg, rating_count, created_at, updated_at)
            VALUES (
                :user_id,
                :license_number,
                CAST(:verified_status AS driver_verification_status),
                :rating_avg,
                :rating_count,
                NOW(),
                NOW()
            )
            ON CONFLICT (user_id) DO NOTHING
            """,
            {
                "user_id": user_id,
                "license_number": license_number,
                "verified_status": verified_status_lower,
                "rating_avg": rating_avg,
                "rating_count": 0,
            },
        ),
        (
            """
            INSERT INTO drivers (user_id, license_number, verified, rating_avg, rating_count, created_at, updated_at)
            VALUES (:user_id, :license_number, :verified, :rating_avg, :rating_count, NOW(), NOW())
            ON CONFLICT (user_id) DO NOTHING
            """,
            {
                "user_id": user_id,
                "license_number": license_number,
                "verified": verified,
                "rating_avg": rating_avg,
                "rating_count": 0,
            },
        ),
        (
            """
            INSERT INTO drivers (user_id, license_number)
            VALUES (:user_id, :license_number)
            ON CONFLICT (user_id) DO NOTHING
            """,
            {"user_id": user_id, "license_number": license_number},
        ),
        (
            """
            INSERT INTO drivers (user_id)
            VALUES (:user_id)
            ON CONFLICT (user_id) DO NOTHING
            """,
            {"user_id": user_id},
        ),
    ]

    for sql, params in statements:
        try:
            async with db.begin_nested():
                await db.execute(text(sql), params)
            return
        except Exception:
            continue

    logger.debug("Legacy drivers upsert skipped for user_id=%s", user_id, exc_info=True)


# ============================================
# RIDE MANAGEMENT SERVICES
# ============================================

async def create_ride_service(
    db: AsyncSession,
    user_id: UUID,
    ride_data: RideCreate
) -> Dict[str, Any]:
    """
    Create a new ride offer (driver only).
    
    Business Logic:
    - Verifies driver is active and verified
    - Ensures vehicle exists and is active
    - Validates available_seats against vehicle capacity
    - Sets initial status to "scheduled"
    
    Args:
        db: Async database session
        user_id: UUID of the user (must be a driver)
        ride_data: RideCreate schema
    
    Returns:
        Standardized response with created ride
    
    Raises:
        HTTPException 403: If user is not eligible to create rides
        HTTPException 400: If vehicle not found or inactive
    """
    try:
        await ensure_rides_schema_compat(db)
        await ensure_driver_vehicle_schema_compat(db)
        # Verify driver eligibility
        is_eligible, error_msg, driver = await _verify_driver_eligibility(db, user_id)
        if not is_eligible:
            logger.warning(f"Driver not eligible: user_id={user_id}, reason={error_msg}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_msg
            )

        await _ensure_legacy_driver_row(db, user_id, driver)
        
        # Verify vehicle exists and belongs to driver
        vehicle = await drivers_crud.get_vehicle_by_id(db, ride_data.vehicle_id)
        owns_vehicle = bool(vehicle) and (
            vehicle.owner_id == user_id or getattr(vehicle, "driver_id", None) == user_id
        )
        if not vehicle or not owns_vehicle:
            logger.warning(f"Vehicle not found or not owned: vehicle_id={ride_data.vehicle_id}, user_id={user_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vehicle not found or you don't own this vehicle"
            )

        if getattr(vehicle, "is_active", True) is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected vehicle is inactive"
            )
        
        # Validate available_seats against vehicle capacity
        if ride_data.available_seats > vehicle.seats_available:
            logger.warning(
                f"Requested seats exceed vehicle capacity: "
                f"requested={ride_data.available_seats}, capacity={vehicle.seats_available}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Available seats cannot exceed vehicle capacity ({vehicle.seats_available})"
            )

        ride_departure_utc = _normalize_to_utc(ride_data.departure_time)
        ride_data.departure_time = ride_departure_utc
        
        # ── Server-side fare calculation (authoritative) ──
        # Driver-submitted price is ignored; backend computes canonical fare.
        distance_km = (
            ride_data.route_distance_km
            if ride_data.route_distance_km and ride_data.route_distance_km > 0
            else _haversine_km(
                ride_data.origin_lat,
                ride_data.origin_lng,
                ride_data.destination_lat,
                ride_data.destination_lng,
            )
        )
        resolved_duration_minutes = _resolve_duration_minutes(
            ride_data.estimated_duration,
            distance_km,
        )
        ride_data.estimated_duration = resolved_duration_minutes
        ride_window_end_utc = _window_end(ride_departure_utc, resolved_duration_minutes)

        await _acquire_user_schedule_lock(db, user_id, "driver-create-ride")
        conflicting_ride = await _find_driver_overlap(
            db,
            user_id=user_id,
            window_start_utc=ride_departure_utc,
            window_end_utc=ride_window_end_utc,
        )
        if conflicting_ride:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This time slot is already occupied by another active ride "
                    f"({_format_slot_window(conflicting_ride['start_time'], conflicting_ride['end_time'])})."
                ),
            )

        fare_est = calculate_fare(
            distance_km=distance_km,
            total_seats=ride_data.available_seats,
            duration_minutes=resolved_duration_minutes,
        )
        ride_data.route_distance_km = distance_km
        ride_data.price_per_seat = fare_est.fare_per_seat
        
        # Create ride
        ride = await crud.create_ride(db, user_id, ride_data)
        
        logger.info(
            "Created ride via service: driver_id=%s, ride_id=%s, fare_per_seat=%.2f",
            user_id,
            ride.id,
            ride_data.price_per_seat,
        )
        
        return _format_response(data=_ride_public_payload(ride, role="driver"))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Error in create_ride_service: user_id=%s vehicle_id=%s",
            user_id,
            getattr(ride_data, "vehicle_id", None),
        )
        return _format_response(error="Failed to create ride")


async def list_available_rides_service(
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
) -> Dict[str, Any]:
    """
    List all available rides with optional filters.
    Supports text-based and geo-proximity search.
    """
    try:
        rides = await crud.list_available_rides(
            db,
            origin=origin,
            destination=destination,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            destination_lat=destination_lat,
            destination_lng=destination_lng,
            radius_km=radius_km,
            min_seats=min_seats,
            driver_total_seats=driver_total_seats,
            max_price=max_price,
            departure_after=departure_after,
            departure_before=departure_before,
            include_recurring=include_recurring,
        )
        
        rides_public = [_ride_public_payload(r, role="passenger") for r in rides]
        
        return _format_response(data=rides_public)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in list_available_rides_service: {str(e)}")
        return _format_response(error="Failed to list available rides")


async def get_ride_details_service(
    db: AsyncSession,
    user_id: UUID,
    ride_id: UUID
) -> Dict[str, Any]:
    """
    Get detailed information about a specific ride including bookings.
    
    Args:
        db: Async database session
        user_id: UUID of requesting user
        ride_id: UUID of the ride
    
    Returns:
        Standardized response with ride details and bookings
    
    Raises:
        HTTPException 404: If ride not found
    """
    try:
        await ensure_rides_schema_compat(db)
        ride = await crud.get_ride_by_id(db, ride_id)
        
        if not ride:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ride not found"
            )
        
        is_driver_owner = getattr(ride, "driver_id", None) == user_id
        ride_role = "driver" if is_driver_owner else "passenger"

        # Build ride core payload first, then attach canonical booking data.
        ride_data = _ride_public_payload(ride, role=ride_role, with_bookings=False)
        await _attach_recurring_range(db, ride_data)

        canonical_bookings = await _load_canonical_ride_bookings(db, ride_id)
        bookings_data: List[Dict[str, Any]] = [
            _apply_booking_display_fields(
                _booking_public_payload(booking, include_ride=False),
                ride_payload=ride_data,
            )
            for booking in canonical_bookings
        ]

        # Backward-compatible fallback for historical rows present only in legacy table.
        if not bookings_data:
            legacy_ride_payload = _ride_public_payload(ride, role=ride_role, with_bookings=True)
            bookings_data = [
                _apply_booking_display_fields(booking_data, ride_payload=ride_data)
                for booking_data in legacy_ride_payload.get("bookings", [])
            ]

        passenger_ids: List[UUID] = []
        for booking_data in bookings_data:
            raw_passenger_id = booking_data.get("passenger_id")
            if isinstance(raw_passenger_id, UUID):
                passenger_ids.append(raw_passenger_id)
                continue

            try:
                passenger_ids.append(UUID(str(raw_passenger_id)))
            except (TypeError, ValueError):
                continue

        passenger_summaries = await _build_booking_passenger_summaries(
            db,
            passenger_ids,
        )

        requester_id_str = str(user_id)
        for booking_data in bookings_data:
            summary = passenger_summaries.get(str(booking_data.get("passenger_id")))
            if summary:
                booking_data.update(summary)

        booked_seats, total_earnings = _booking_aggregates_from_payloads(bookings_data)

        requester_has_booking = any(
            str(booking_data.get("passenger_id")) == requester_id_str
            for booking_data in bookings_data
        )

        visible_bookings = bookings_data
        if not is_driver_owner:
            # Only participants (booked passengers) can view co-rider details.
            if not requester_has_booking:
                visible_bookings = []
            else:
                # Booked passengers can see co-riders, but phone numbers remain private.
                for booking_data in visible_bookings:
                    if str(booking_data.get("passenger_id")) != requester_id_str:
                        booking_data["passenger_phone"] = None

        ride_data["bookings"] = visible_bookings
        ride_data["booked_seats_count"] = booked_seats
        ride_data["total_earnings"] = total_earnings
        ride_data["execution_progress"] = _build_ride_execution_progress(visible_bookings)

        if is_driver_owner:
            action_state = _driver_action_state_from_bookings_payload(bookings_data)
            _apply_driver_action_flags(ride_data, action_state)

        driver_summary = await _build_ride_driver_summary(db, ride)
        if driver_summary is not None:
            ride_data["driver_summary"] = driver_summary
        
        return _format_response(data=ride_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_ride_details_service: {str(e)}")
        return _format_response(error="Failed to retrieve ride details")


async def update_ride_service(
    db: AsyncSession,
    user_id: UUID,
    ride_id: UUID,
    ride_update: RideUpdate
) -> Dict[str, Any]:
    """
    Update ride details (driver only, before ride starts).
    
    Args:
        db: Async database session
        user_id: UUID of the user (must be ride owner)
        ride_id: UUID of the ride
        ride_update: RideUpdate schema
    
    Returns:
        Standardized response with updated ride
    
    Raises:
        HTTPException 403: If user is not the ride owner
        HTTPException 404: If ride not found
        HTTPException 400: If ride has already started
    """
    try:
        # Get ride and verify ownership
        ride = await crud.get_ride_by_id(db, ride_id)
        
        if not ride:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ride not found"
            )
        
        # Verify driver owns this ride
        driver = await drivers_crud.get_driver_profile(db, user_id)
        if not driver or ride.driver_id != driver.user_id:
            logger.warning(f"Unauthorized ride update attempt: user_id={user_id}, ride_id={ride_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this ride"
            )
        
        # Update ride
        updated_ride = await crud.update_ride(db, ride_id, ride_update)
        
        logger.info(f"Updated ride: ride_id={ride_id}, driver_id={driver.user_id}")
        
        return _format_response(data=_ride_public_payload(updated_ride, role="driver"))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_ride_service: {str(e)}")
        return _format_response(error="Failed to update ride")


async def update_ride_status_service(
    db: AsyncSession,
    user_id: UUID,
    ride_id: UUID,
    status_update: RideStatusUpdate
) -> Dict[str, Any]:
    """
    Update ride status (driver only).
    
    Allowed transitions:
    - scheduled → ongoing (driver starts trip)
    - ongoing → completed (driver ends trip)
    - scheduled → cancelled (driver cancels before start)
    
    Args:
        db: Async database session
        user_id: UUID of the user (must be ride owner)
        ride_id: UUID of the ride
        status_update: RideStatusUpdate schema
    
    Returns:
        Standardized response with updated ride
    
    Raises:
        HTTPException 403: If user is not the ride owner
        HTTPException 400: If status transition is invalid
    """
    try:
        # Get ride and verify ownership
        ride = await crud.get_ride_by_id(db, ride_id)
        
        if not ride:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ride not found"
            )
        
        # Verify driver owns this ride
        driver = await drivers_crud.get_driver_profile(db, user_id)
        if not driver or ride.driver_id != driver.user_id:
            logger.warning(f"Unauthorized status update attempt: user_id={user_id}, ride_id={ride_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this ride"
            )
        
        # Validate status transition
        current_status = _canonical_ride_status(ride.status)
        new_status = _canonical_ride_status(status_update.status)
        
        valid_transitions = {
            "open": ["in_progress", "cancelled"],
            "in_progress": ["completed"],
            "completed": [],
            "cancelled": []
        }
        
        if new_status not in valid_transitions.get(current_status, []):
            logger.warning(f"Invalid status transition: {current_status} → {new_status}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot change status from '{current_status}' to '{new_status}'"
            )

        action_state_by_ride = await _load_driver_action_state_for_ride_ids(db, [ride.id])
        action_state = action_state_by_ride.get(
            ride.id,
            {
                "active_booking_count": 0,
                "non_cancelled_booking_count": 0,
                "pending_stop_booking_count": 0,
            },
        )

        if current_status == "open" and new_status == "in_progress":
            if action_state.get("active_booking_count", 0) <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You need at least one passenger to start a ride",
                )

        if current_status == "in_progress" and new_status == "completed":
            if action_state.get("pending_stop_booking_count", 0) > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You need to complete all pickups and dropoffs before completing the ride",
                )
        
        # Update status
        updated_ride = await crud.update_ride_status(db, ride_id, new_status)

        if new_status == "cancelled":
            active_bookings = await _collect_active_ride_bookings_for_notifications(
                db,
                ride=ride,
            )

            try:
                await _send_ride_cancelled_by_driver_notifications(
                    db,
                    ride=ride,
                    cancelled_bookings=active_bookings,
                )
            except Exception as notification_error:
                logger.exception(
                    "Ride cancellation succeeded but notification dispatch failed: ride_id=%s error=%s",
                    ride_id,
                    notification_error,
                )
        
        # If completing ride, update driver's total_rides and total_earnings
        if new_status == "completed":
            ride_earnings_total = await _compute_ride_total_earnings(
                db,
                ride_id=ride_id,
                fallback_total=getattr(ride, "total_earnings", 0.0),
            )
            driver.total_rides += 1
            driver.total_earnings += ride_earnings_total
            await db.commit()
            logger.info(
                "Updated driver stats: driver_id=%s, earnings=%s",
                driver.user_id,
                ride_earnings_total,
            )
        
        logger.info(f"Updated ride status: ride_id={ride_id}, {current_status} → {new_status}")
        
        return _format_response(data=_ride_public_payload(updated_ride, role="driver"))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_ride_status_service: {str(e)}")
        return _format_response(error="Failed to update ride status")


async def update_ride_route_selection_service(
    db: AsyncSession,
    user_id: UUID,
    ride_id: UUID,
    selection: RideRouteSelectionUpdate,
) -> Dict[str, Any]:
    """Allow driver to manually choose one constrained route option while ride is still open."""
    try:
        await ensure_rides_schema_compat(db)

        ride = await crud.get_ride_by_id(db, ride_id)
        if not ride:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ride not found",
            )

        driver = await drivers_crud.get_driver_profile(db, user_id)
        if not driver or ride.driver_id != driver.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this ride route",
            )

        if not _is_ride_route_mutable(ride):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Route is frozen once the ride starts",
            )

        if not isinstance(getattr(ride, "route_alternatives", None), list) or not ride.route_alternatives:
            await _recompute_and_persist_route_plan(db, ride=ride)
            ride = await crud.get_ride_by_id(db, ride_id)

        applied = await _apply_selected_route_key_for_driver(
            db,
            ride=ride,
            route_key=selection.route_key,
        )
        if not applied:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requested route option was not found",
            )

        refreshed = await crud.get_ride_by_id(db, ride_id)
        return _format_response(data=_ride_public_payload(refreshed, role="driver"))

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error in update_ride_route_selection_service: %s", exc)
        return _format_response(error="Failed to update ride route selection")


async def get_driver_rides_service(
    db: AsyncSession,
    user_id: UUID,
    status_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get all rides created by the driver.
    
    Args:
        db: Async database session
        user_id: UUID of the user (driver)
        status_filter: Optional status filter
    
    Returns:
        Standardized response with list of rides
    
    Raises:
        HTTPException 404: If driver profile not found
    """
    try:
        driver = await drivers_crud.get_driver_profile(db, user_id)
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found"
            )
        
        rides = await crud.get_driver_rides(db, driver.user_id, status_filter)
        
        rides_public = [_ride_public_payload(r, role="driver") for r in rides]

        ride_ids = [ride.id for ride in rides if isinstance(getattr(ride, "id", None), UUID)]
        action_state_by_ride = await _load_driver_action_state_for_ride_ids(db, ride_ids)
        now_utc = datetime.now(timezone.utc)

        for ride, ride_data in zip(rides, rides_public):
            ride_id = getattr(ride, "id", None)
            if not isinstance(ride_id, UUID):
                continue

            action_state = action_state_by_ride.get(
                ride_id,
                {
                    "active_booking_count": 0,
                    "non_cancelled_booking_count": 0,
                    "pending_stop_booking_count": 0,
                },
            )
            runtime_status = _resolve_runtime_driver_ride_status(
                ride_data,
                action_state=action_state,
                now_utc=now_utc,
            )
            if runtime_status != ride_data.get("status"):
                ride_data["status"] = runtime_status
                _apply_ride_display_fields(ride_data, role="driver")
            _apply_driver_action_flags(ride_data, action_state)
        
        return _format_response(data=rides_public)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_driver_rides_service: {str(e)}")
        return _format_response(error="Failed to retrieve driver rides")


async def delete_ride_service(
    db: AsyncSession,
    user_id: UUID,
    ride_id: UUID
) -> Dict[str, Any]:
    """
    Delete a ride (only if no active bookings).
    
    Args:
        db: Async database session
        user_id: UUID of the user (must be ride owner)
        ride_id: UUID of the ride
    
    Returns:
        Standardized response with success message
    
    Raises:
        HTTPException 403: If user is not the ride owner
        HTTPException 400: If ride has active bookings
    """
    try:
        driver = await drivers_crud.get_driver_profile(db, user_id)
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found"
            )
        
        await crud.delete_ride(db, ride_id, driver.user_id)
        
        logger.info(f"Deleted ride: ride_id={ride_id}, driver_id={driver.user_id}")
        
        return _format_response(
            data={"message": "Ride deleted successfully", "ride_id": str(ride_id)}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in delete_ride_service: {str(e)}")
        return _format_response(error="Failed to delete ride")


# ============================================
# BOOKING MANAGEMENT SERVICES
# ============================================

async def book_ride_service(
    db: AsyncSession,
    user_id: UUID,
    booking_data: RideBookingCreate
) -> Dict[str, Any]:
    """
    Book a ride as a passenger.
    
    Business Logic:
    - Checks seat availability
    - Prevents double booking
    - Calculates total price
    - Reduces available seats
    - Updates ride earnings
    
    Args:
        db: Async database session
        user_id: UUID of the passenger
        booking_data: RideBookingCreate schema
    
    Returns:
        Standardized response with created booking
    
    Raises:
        HTTPException 400: If insufficient seats or ride not available
    """
    try:
        await ensure_rides_schema_compat(db)

        ride = await crud.get_ride_by_id(db, booking_data.ride_id)
        if not ride:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Ride not found",
            )

        _resolve_booking_route_payload(ride, booking_data)

        ride_start_utc = _normalize_to_utc(ride.departure_time)
        ride_duration_minutes = _resolve_duration_minutes(
            getattr(ride, "estimated_duration_minutes", None),
            getattr(ride, "route_distance_km", None),
        )
        ride_end_utc = _window_end(ride_start_utc, ride_duration_minutes)

        await _acquire_user_schedule_lock(db, user_id, "passenger-book-ride")
        passenger_overlap = await _find_passenger_overlap(
            db,
            user_id=user_id,
            window_start_utc=ride_start_utc,
            window_end_utc=ride_end_utc,
        )
        if passenger_overlap:
            overlap_source = str(passenger_overlap.get("source") or "").lower()
            overlap_entity_id = str(passenger_overlap.get("entity_id") or "").strip()
            if overlap_source == "booking" and overlap_entity_id == str(booking_data.ride_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="You already booked this ride.",
                )

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "You already have an overlapping booked/requested slot "
                    f"({_format_slot_window(passenger_overlap['start_time'], passenger_overlap['end_time'])})."
                ),
            )

        tentative_input = _to_route_input_from_create(
            booking_data=booking_data,
            passenger_id=user_id,
        )
        if tentative_input is not None and _is_ride_route_mutable(ride):
            existing_active = await _load_active_canonical_ride_bookings(db, booking_data.ride_id)
            existing_inputs = [
                route_input
                for route_input in (
                    _to_route_input_from_model(row)
                    for row in existing_active
                )
                if route_input is not None
            ]
            detour_error = _validate_existing_passenger_detour(
                ride=ride,
                existing_inputs=existing_inputs,
                tentative_input=tentative_input,
            )
            if detour_error:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=detour_error,
                )

        booking = await crud.book_ride(db, user_id, booking_data)

        try:
            await _recompute_and_persist_route_plan(db, ride=ride)
            await db.refresh(booking)
        except Exception as route_error:
            logger.exception(
                "Booking succeeded but route-plan recompute failed: ride_id=%s booking_id=%s error=%s",
                getattr(ride, "id", None),
                getattr(booking, "id", None),
                route_error,
            )

        try:
            await _send_booking_notifications(
                db,
                ride=ride,
                booking=booking,
                passenger_id=user_id,
            )
        except Exception as notification_error:
            logger.exception(
                "Booking succeeded but notification dispatch failed: booking_id=%s error=%s",
                getattr(booking, "id", None),
                notification_error,
            )
        
        logger.info(f"Booked ride: passenger_id={user_id}, booking_id={booking.id}")
        
        return _format_response(data=_booking_public_payload(booking, include_ride=False))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in book_ride_service: {str(e)}")
        return _format_response(error="Failed to book ride")


async def get_user_bookings_service(
    db: AsyncSession,
    user_id: UUID,
    status_filter: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get all bookings made by a passenger.
    
    Args:
        db: Async database session
        user_id: UUID of the passenger
        status_filter: Optional status filter
    
    Returns:
        Standardized response with list of bookings
    """
    try:
        await ensure_rides_schema_compat(db)
        bookings = await crud.get_user_bookings(db, user_id, status_filter)
        
        bookings_public = [
            _booking_public_payload(b, include_ride=True)
            for b in bookings
        ]
        
        return _format_response(data=bookings_public)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_user_bookings_service: {str(e)}")
        return _format_response(error="Failed to retrieve bookings")


async def get_my_occupied_slots_service(
    db: AsyncSession,
    user_id: UUID,
    target_date: date,
    mode: str,
    timezone_offset_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    """Return occupied time windows for a selected date window."""
    try:
        await ensure_rides_schema_compat(db)

        normalized_mode = (mode or "driver").strip().lower()
        if normalized_mode not in {"driver", "passenger"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="mode must be either 'driver' or 'passenger'",
            )

        if timezone_offset_minutes is not None:
            if timezone_offset_minutes < -840 or timezone_offset_minutes > 840:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="timezone_offset_minutes must be between -840 and 840",
                )

            client_tz = timezone(timedelta(minutes=timezone_offset_minutes))
            day_start_local = datetime.combine(target_date, time.min, tzinfo=client_tz)
            day_start_utc = day_start_local.astimezone(timezone.utc)
        else:
            client_tz = timezone.utc
            day_start_utc = datetime.combine(target_date, time.min, tzinfo=timezone.utc)

        day_end_utc = day_start_utc + timedelta(days=1)
        target_local_date = target_date

        if normalized_mode == "driver":
            slots = await _collect_driver_slots(
                db,
                user_id=user_id,
                day_start_utc=day_start_utc,
                day_end_utc=day_end_utc,
                target_local_date=target_local_date,
                client_tz=client_tz,
            )
        else:
            slots = await _collect_passenger_slots(
                db,
                user_id=user_id,
                day_start_utc=day_start_utc,
                day_end_utc=day_end_utc,
                target_local_date=target_local_date,
                client_tz=client_tz,
            )

        return _format_response(
            data={
                "date": target_date.isoformat(),
                "mode": normalized_mode,
                "timezone_offset_minutes": timezone_offset_minutes,
                "window_start_utc": day_start_utc.isoformat(),
                "window_end_utc": day_end_utc.isoformat(),
                "slots": slots,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in get_my_occupied_slots_service: %s", str(e))
        return _format_response(error="Failed to load occupied slots")


async def cancel_booking_service(
    db: AsyncSession,
    user_id: UUID,
    booking_id: UUID,
    cancellation: Optional[BookingCancellation] = None
) -> Dict[str, Any]:
    """
    Cancel a booking and restore seats.
    
    Business Logic:
    - Verifies booking ownership
    - Checks if ride has started (cannot cancel ongoing rides)
    - Restores seats to ride
    - Reduces ride earnings
    - Marks payment for refund
    
    Args:
        db: Async database session
        user_id: UUID of the passenger
        booking_id: UUID of the booking
        cancellation: Optional cancellation details
    
    Returns:
        Standardized response with updated booking
    
    Raises:
        HTTPException 404: If booking not found or not owned
        HTTPException 400: If booking already cancelled or ride has started
    """
    try:
        reason = cancellation.reason if cancellation else None
        
        booking = await crud.cancel_booking(db, booking_id, user_id, reason)

        ride_for_notification = await crud.get_ride_by_id(db, booking.ride_id)
        if ride_for_notification is not None:
            try:
                await _recompute_and_persist_route_plan(db, ride=ride_for_notification)
            except Exception as route_error:
                logger.exception(
                    "Booking cancellation succeeded but route-plan recompute failed: booking_id=%s error=%s",
                    booking_id,
                    route_error,
                )

            try:
                await _send_booking_cancelled_by_passenger_notifications(
                    db,
                    ride=ride_for_notification,
                    booking=booking,
                    passenger_id=user_id,
                    reason=reason,
                )
            except Exception as notification_error:
                logger.exception(
                    "Booking cancellation succeeded but notification dispatch failed: booking_id=%s error=%s",
                    booking_id,
                    notification_error,
                )
        
        logger.info(f"Cancelled booking: booking_id={booking_id}, passenger_id={user_id}")
        
        return _format_response(data=_booking_public_payload(booking, include_ride=False))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in cancel_booking_service: {str(e)}")
        return _format_response(error="Failed to cancel booking")


async def mark_booking_pickup_completed_service(
    db: AsyncSession,
    user_id: UUID,
    booking_id: UUID,
) -> Dict[str, Any]:
    """Driver marks passenger pickup as completed for an in-progress ride."""
    try:
        await ensure_rides_schema_compat(db)

        driver = await drivers_crud.get_driver_profile(db, user_id)
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found",
            )

        booking = await crud.mark_booking_pickup_completed(
            db,
            booking_id=booking_id,
            driver_user_id=driver.user_id,
        )

        return _format_response(data=_booking_public_payload(booking, include_ride=False))

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in mark_booking_pickup_completed_service: %s", str(e))
        return _format_response(error="Failed to mark pickup complete")


async def mark_booking_dropoff_completed_service(
    db: AsyncSession,
    user_id: UUID,
    booking_id: UUID,
) -> Dict[str, Any]:
    """Driver marks passenger dropoff as completed for an in-progress ride."""
    try:
        await ensure_rides_schema_compat(db)

        driver = await drivers_crud.get_driver_profile(db, user_id)
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found",
            )

        booking = await crud.mark_booking_dropoff_completed(
            db,
            booking_id=booking_id,
            driver_user_id=driver.user_id,
        )

        try:
            await _send_dropoff_rating_prompt_notifications(
                db,
                booking=booking,
                driver_user_id=driver.user_id,
            )
        except Exception as notification_error:
            logger.exception(
                "Dropoff completion succeeded but rating prompt notifications failed: booking_id=%s error=%s",
                booking_id,
                notification_error,
            )

        return _format_response(data=_booking_public_payload(booking, include_ride=False))

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in mark_booking_dropoff_completed_service: %s", str(e))
        return _format_response(error="Failed to mark dropoff complete")


# ============================================
# STATISTICS SERVICES
# ============================================

async def get_driver_ride_statistics_service(
    db: AsyncSession,
    user_id: UUID
) -> Dict[str, Any]:
    """
    Get comprehensive ride statistics for a driver.
    
    Args:
        db: Async database session
        user_id: UUID of the driver
    
    Returns:
        Standardized response with RideStatistics
    """
    try:
        driver = await drivers_crud.get_driver_profile(db, user_id)
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found"
            )
        
        # Get all driver rides
        all_rides = await crud.get_driver_rides(db, driver.user_id)

        CO2_KG_PER_KM = 0.120
        AVG_SPEED_KMH = 40.0
        draft_like_statuses = {"draft", "pending", "pending_draft"}

        now_utc = datetime.now(timezone.utc)
        ride_statuses = []
        for ride in all_rides:
            status_value = _canonical_ride_status(getattr(ride, "status", None))
            if status_value == "open":
                departure_utc = _parse_departure_utc(getattr(ride, "departure_time", None))
                if departure_utc is not None and departure_utc <= now_utc:
                    # Past open rides are stale from lifecycle perspective.
                    status_value = "cancelled"
            ride_statuses.append(status_value)

        # Calculate statistics
        total_created = len(all_rides)
        total_all_excluding_draft = sum(
            1 for status in ride_statuses if status and status not in draft_like_statuses
        )
        completed = sum(1 for status in ride_statuses if status == "completed")
        cancelled = sum(1 for status in ride_statuses if status == "cancelled")
        scheduled_current = sum(
            1 for status in ride_statuses if status in {"open", "in_progress"}
        )

        # Calculate average occupancy rate without triggering lazy relationship
        # loads (which fail under async contexts with MissingGreenlet).
        completed_rides = [
            ride
            for ride, status in zip(all_rides, ride_statuses)
            if status == "completed"
        ]
        if completed_rides:
            completed_ride_ids = [ride.id for ride in completed_rides]
            seats_by_ride: Dict[UUID, int] = {
                ride_id: 0 for ride_id in completed_ride_ids
            }

            # Legacy bookings table (bookings.seats_reserved)
            legacy_rows = await db.execute(
                select(
                    LegacyBookingModel.ride_id,
                    func.coalesce(func.sum(LegacyBookingModel.seats_reserved), 0),
                )
                .where(LegacyBookingModel.ride_id.in_(completed_ride_ids))
                .where(
                    func.lower(cast(LegacyBookingModel.status, String)).in_(
                        ACTIVE_BOOKING_STATUSES
                    )
                )
                .group_by(LegacyBookingModel.ride_id)
            )
            for ride_id, seat_sum in legacy_rows.all():
                seats_by_ride[ride_id] = max(
                    seats_by_ride.get(ride_id, 0),
                    _to_int(seat_sum, default=0),
                )

            # Modular bookings table (ride_bookings.booked_seats)
            modular_rows = await db.execute(
                select(
                    RideBookingModel.ride_id,
                    func.coalesce(func.sum(RideBookingModel.booked_seats), 0),
                )
                .where(RideBookingModel.ride_id.in_(completed_ride_ids))
                .where(
                    func.lower(cast(RideBookingModel.status, String)).in_(
                        ACTIVE_BOOKING_STATUSES
                    )
                )
                .group_by(RideBookingModel.ride_id)
            )
            for ride_id, seat_sum in modular_rows.all():
                seats_by_ride[ride_id] = max(
                    seats_by_ride.get(ride_id, 0),
                    _to_int(seat_sum, default=0),
                )

            total_capacity = 0
            total_booked = 0
            for ride in completed_rides:
                booked = max(0, seats_by_ride.get(ride.id, 0))
                remaining = max(0, _to_int(getattr(ride, "seats_available", 0), default=0))
                total_capacity += remaining + booked
                total_booked += booked

            avg_occupancy = total_booked / total_capacity if total_capacity > 0 else 0
        else:
            avg_occupancy = 0

        # Driver CO2 savings: completed-route distance only (driver's own route path).
        carbon_saved_kg = 0.0
        for ride in completed_rides:
            distance_km_raw = getattr(ride, "route_distance_km", None)
            try:
                distance_km = float(distance_km_raw) if distance_km_raw is not None else 0.0
            except (TypeError, ValueError):
                distance_km = 0.0

            if distance_km <= 0:
                duration_raw = getattr(ride, "estimated_duration_minutes", None)
                try:
                    duration_minutes = float(duration_raw) if duration_raw is not None else 0.0
                except (TypeError, ValueError):
                    duration_minutes = 0.0
                if duration_minutes > 0:
                    distance_km = (duration_minutes / 60.0) * AVG_SPEED_KMH

            if distance_km > 0:
                carbon_saved_kg += distance_km * CO2_KG_PER_KM
        
        stats = RideStatistics(
            total_rides_created=total_created,
            total_rides_completed=completed,
            total_rides_cancelled=cancelled,
            total_rides_all_excluding_draft=total_all_excluding_draft,
            scheduled_rides_current=scheduled_current,
            total_earnings=driver.total_earnings,
            average_occupancy_rate=round(avg_occupancy, 2),
            carbon_footprint_saved_kg=round(carbon_saved_kg, 2),
        )
        
        return _format_response(data=stats.model_dump())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_driver_ride_statistics_service: {str(e)}")
        return _format_response(error="Failed to retrieve ride statistics")


async def get_passenger_booking_history_service(
    db: AsyncSession,
    user_id: UUID
) -> Dict[str, Any]:
    """
    Get comprehensive booking history for a passenger.
    
    Args:
        db: Async database session
        user_id: UUID of the passenger
    
    Returns:
        Standardized response with PassengerBookingHistory
    """
    try:
        # Get all passenger bookings
        all_bookings = await crud.get_user_bookings(db, user_id)
        
        # Calculate statistics
        total_bookings = len(all_bookings)
        booking_status_rows: List[Tuple[Any, str, str]] = []
        for booking in all_bookings:
            booking_status = _canonical_booking_status(getattr(booking, "status", None))
            ride_status = _canonical_ride_status(getattr(getattr(booking, "ride", None), "status", None))
            booking_status_rows.append((booking, booking_status, ride_status))

        total_spent = sum(
            float(getattr(booking, "total_price", 0.0) or 0.0)
            for booking, booking_status, _ in booking_status_rows
            if booking_status != "cancelled"
        )
        # "Scheduled" includes both planned and currently in-progress rides.
        active = sum(
            1
            for _, booking_status, ride_status in booking_status_rows
            if booking_status not in {"completed", "cancelled"}
            and ride_status not in {"completed", "cancelled"}
        )
        completed = sum(
            1
            for _, booking_status, ride_status in booking_status_rows
            if booking_status != "cancelled"
            and (booking_status == "completed" or ride_status == "completed")
        )
        cancelled = sum(
            1
            for _, booking_status, ride_status in booking_status_rows
            if booking_status == "cancelled" or ride_status == "cancelled"
        )

        # Passenger CO2 savings should use passenger segment path, not full ride route.
        CO2_KG_PER_KM = 0.120
        carbon_saved_kg = 0.0
        for booking, booking_status, ride_status in booking_status_rows:
            if booking_status == "cancelled":
                continue
            if booking_status != "completed" and ride_status != "completed":
                continue

            segment_km_raw = getattr(booking, "segment_km", None)
            try:
                segment_km = float(segment_km_raw) if segment_km_raw is not None else 0.0
            except (TypeError, ValueError):
                segment_km = 0.0

            distance_km = segment_km
            if distance_km <= 0:
                pickup_lat = getattr(booking, "pickup_lat", None)
                pickup_lng = getattr(booking, "pickup_lng", None)
                dropoff_lat = getattr(booking, "dropoff_lat", None)
                dropoff_lng = getattr(booking, "dropoff_lng", None)
                if (
                    pickup_lat is not None
                    and pickup_lng is not None
                    and dropoff_lat is not None
                    and dropoff_lng is not None
                ):
                    try:
                        distance_km = _haversine_km(
                            float(pickup_lat),
                            float(pickup_lng),
                            float(dropoff_lat),
                            float(dropoff_lng),
                        )
                    except (TypeError, ValueError):
                        distance_km = 0.0

            if distance_km > 0:
                carbon_saved_kg += distance_km * CO2_KG_PER_KM
        
        carbon_footprint_saved_kg = round(carbon_saved_kg, 2)
        
        history = PassengerBookingHistory(
            total_bookings=total_bookings,
            total_spent=total_spent,
            active_bookings=active,
            completed_rides=completed,
            cancelled_bookings=cancelled,
            carbon_footprint_saved_kg=carbon_footprint_saved_kg
        )
        
        return _format_response(data=history.model_dump())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_passenger_booking_history_service: {str(e)}")
        return _format_response(error="Failed to retrieve booking history")


# ============================================
# RIDE REQUEST SERVICES (Passenger → Driver)
# ============================================

async def create_ride_request_service(
    db: AsyncSession, user_id: UUID, data: RideRequestCreate
) -> Dict[str, Any]:
    """Passenger creates a ride request."""
    try:
        await ensure_rides_schema_compat(db)

        request_departure_utc = _normalize_to_utc(data.departure_time)
        request_end_utc = _window_end(request_departure_utc, DEFAULT_REQUEST_DURATION_MINUTES)

        await _acquire_user_schedule_lock(db, user_id, "passenger-create-request")
        passenger_overlap = await _find_passenger_overlap(
            db,
            user_id=user_id,
            window_start_utc=request_departure_utc,
            window_end_utc=request_end_utc,
        )
        if passenger_overlap:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "You already have an overlapping booked/requested slot "
                    f"({_format_slot_window(passenger_overlap['start_time'], passenger_overlap['end_time'])})."
                ),
            )

        from app.models.ride_request import RideRequest, RideRequestStatus
        req = RideRequest(
            passenger_id=user_id,
            origin=data.origin,
            origin_lat=data.origin_lat,
            origin_lng=data.origin_lng,
            destination=data.destination,
            destination_lat=data.destination_lat,
            destination_lng=data.destination_lng,
            seats_needed=data.seats_needed,
            max_budget=data.max_budget,
            departure_time=request_departure_utc,
            status=RideRequestStatus.PENDING,
        )
        db.add(req)
        await db.commit()
        await db.refresh(req)
        logger.info(f"Created ride request: id={req.id}, passenger={user_id}")
        return _format_response(
            data=RideRequestPublic.model_validate(req).model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating ride request: {e}")
        return _format_response(error="Failed to create ride request")


async def get_nearby_ride_requests_service(
    db: AsyncSession, lat: float, lng: float, radius_km: float
) -> Dict[str, Any]:
    """Get pending ride requests near the driver's location using Haversine."""
    try:
        from app.models.ride_request import RideRequest, RideRequestStatus
        from sqlalchemy import select
        import math

        from datetime import datetime, timezone, timedelta
        
        stmt = select(RideRequest).where(
            RideRequest.status == RideRequestStatus.PENDING
        )
        result = await db.execute(stmt)
        
        now_dt = datetime.now(timezone.utc)
        # only show requests that haven't 'expired' (departure time is not more than 2 hours in the past)
        all_pending = [
            r for r in result.scalars().all()
            if r.departure_time >= (now_dt - timedelta(hours=2))
        ]

        def _haversine(lat1, lon1, lat2, lon2):
            R = 6371.0
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = (math.sin(dlat / 2) ** 2 +
                 math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
                 math.sin(dlon / 2) ** 2)
            return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        nearby = [
            r for r in all_pending
            if _haversine(lat, lng, r.origin_lat, r.origin_lng) <= radius_km
        ]
        nearby.sort(key=lambda r: r.created_at, reverse=True)

        data = [
            RideRequestPublic.model_validate(r).model_dump() for r in nearby
        ]
        return _format_response(data=data)
    except Exception as e:
        logger.error(f"Error fetching nearby ride requests: {e}")
        return _format_response(error="Failed to fetch nearby requests")


async def get_my_ride_requests_service(
    db: AsyncSession, user_id: UUID
) -> Dict[str, Any]:
    """Get all ride requests created by this passenger."""
    try:
        from app.models.ride_request import RideRequest
        from sqlalchemy import select

        stmt = (
            select(RideRequest)
            .where(RideRequest.passenger_id == user_id)
            .order_by(RideRequest.created_at.desc())
        )
        result = await db.execute(stmt)
        requests = result.scalars().all()

        data = [
            RideRequestPublic.model_validate(r).model_dump() for r in requests
        ]
        return _format_response(data=data)
    except Exception as e:
        logger.error(f"Error fetching my ride requests: {e}")
        return _format_response(error="Failed to fetch ride requests")


async def accept_ride_request_service(
    db: AsyncSession, driver_user_id: UUID, request_id: UUID
) -> Dict[str, Any]:
    """Driver accepts a passenger ride request, generating a Ride and Booking."""
    try:
        from app.models.ride_request import RideRequest, RideRequestStatus
        from app.models.ride import Ride
        from app.models.enums import RideStatus, BookingStatus
        from app.models.booking import Booking
        from sqlalchemy import select
        import uuid
        from datetime import datetime, timezone

        stmt = select(RideRequest).where(RideRequest.id == request_id)
        result = await db.execute(stmt)
        req = result.scalar_one_or_none()

        if not req:
            raise HTTPException(status_code=404, detail="Ride request not found")
        if req.status != RideRequestStatus.PENDING:
            raise HTTPException(status_code=400, detail="Request is no longer pending")

        distance_km = None
        duration_minutes = None
        polyline = None
        try:
            from app.core.google_maps_client import get_google_maps_client
            client = get_google_maps_client()
            route_data = client.get_directions(
                (req.origin_lat, req.origin_lng),
                (req.destination_lat, req.destination_lng),
                alternatives=False
            )
            if route_data:
                distance_km = route_data.get('distance_km')
                duration_minutes = route_data.get('duration_minutes')
                polyline = route_data.get('polyline')
        except Exception as e:
            import logging
            logging.warning(f"Google Maps fail in accept: {e}")
        
        if distance_km is None:
            from app.modules.matching.utils import calculate_distance
            distance_km = calculate_distance(
                req.origin_lat, req.origin_lng,
                req.destination_lat, req.destination_lng
            )

        duration_minutes = _resolve_duration_minutes(duration_minutes, distance_km)
        departure_time_utc = _normalize_to_utc(req.departure_time)

        # Create actual Ride for the driver
        import decimal
        new_ride = Ride(
            driver_id=driver_user_id,
            start_point_lat=req.origin_lat,
            start_point_lng=req.origin_lng,
            end_point_lat=req.destination_lat,
            end_point_lng=req.destination_lng,
            start_point_address=req.origin,
            end_point_address=req.destination,
            departure_time=departure_time_utc,
            seats_available=max(0, 4 - req.seats_needed), # basic formula
            price_per_seat=decimal.Decimal(str(req.max_budget if req.max_budget else 500.0)),
            status=RideStatus.OPEN,
            route_distance_km=distance_km,
            estimated_duration_minutes=duration_minutes,
            polyline=polyline
        )
        db.add(new_ride)
        await db.flush()

        # Create Booking for passenger
        new_booking = Booking(
            ride_id=new_ride.id,
            passenger_id=req.passenger_id,
            seats_reserved=req.seats_needed,
            fare=float((req.max_budget if req.max_budget else 500.0) * req.seats_needed),
            status=BookingStatus.RESERVED,
            booking_time=datetime.now(timezone.utc)
        )
        db.add(new_booking)

        # Mark Request as accepted
        req.status = RideRequestStatus.ACCEPTED
        req.accepted_by_driver_id = driver_user_id
        req.ride_id = new_ride.id

        await db.commit()
        await db.refresh(req)

        data = RideRequestPublic.model_validate(req).model_dump()
        # Ensure we inject the generated ride_id to help the frontend open Chat
        data['ride_id'] = str(new_ride.id) 

        logger.info(f"Driver {driver_user_id} accepted request {request_id} mapped to ride {new_ride.id}")
        return _format_response(data=data)
    except IntegrityError as e:
        await db.rollback()
        detail_text = str(getattr(e, "orig", e)).lower()
        if "ride time overlaps" in detail_text or "trg_enforce_ride_time_overlap" in detail_text:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Driver already has an overlapping active ride for this request time",
            )
        raise HTTPException(status_code=500, detail="Failed to accept ride request")
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error accepting ride request: {e}")
        raise HTTPException(status_code=500, detail="Failed to accept ride request")


async def cancel_ride_request_service(
    db: AsyncSession, user_id: UUID, request_id: UUID
) -> Dict[str, Any]:
    """Passenger cancels their own ride request."""
    try:
        from app.models.ride_request import RideRequest, RideRequestStatus
        from sqlalchemy import select

        stmt = select(RideRequest).where(RideRequest.id == request_id)
        result = await db.execute(stmt)
        req = result.scalar_one_or_none()

        if not req:
            raise HTTPException(status_code=404, detail="Ride request not found")
        if req.passenger_id != user_id:
            raise HTTPException(status_code=403, detail="Not your request")

        req.status = RideRequestStatus.CANCELLED
        await db.commit()
        await db.refresh(req)

        return _format_response(
            data=RideRequestPublic.model_validate(req).model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error cancelling ride request: {e}")
        return _format_response(error="Failed to cancel ride request")


# ============================================
# FARE CALCULATOR SERVICE
# ============================================

async def fare_estimate_service(
    distance_km: float,
    total_seats: int = 4,
    duration_minutes: Optional[float] = None,
    petrol_price: Optional[float] = None,
    fuel_average: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calculate shared fare estimate for a ride.

    Uses the server-side fare calculator with Pakistan-specific defaults:
    - Petrol: 268 PKR/L
    - Fuel avg: 12 km/L
    - Markup: 30%
    - Base fare: 50 PKR
    - Min fare/seat: 80 PKR
    """
    try:
        estimate = calculate_fare(
            distance_km=distance_km,
            total_seats=total_seats,
            duration_minutes=duration_minutes,
            petrol_price=petrol_price,
            fuel_average=fuel_average,
        )
        return _format_response(data=estimate.to_dict())
    except Exception as e:
        logger.error(f"Error calculating fare estimate: {e}")
        return _format_response(error="Failed to calculate fare estimate")
