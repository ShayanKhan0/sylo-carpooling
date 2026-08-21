from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user, require_driver
from app.modules.auth.models import User
from app.modules.auth.models import UserRole

from . import service
from .schemas import (
    TripStartResponse,
    TripCompleteResponse,
    TripSettleResponse,
    TripSummaryResponse,
)


router = APIRouter(prefix="/api/v2/trips", tags=["Trips (Workflow)"])


def _telemetry_ws_template(ride_id: UUID) -> str:
    # Telemetry router is included with prefix "/api/v2" in app/main.py.
    # WebSocket endpoint path inside telemetry router: "/ws/trip/{ride_id}".
    return f"/api/v2/ws/trip/{ride_id}?token=<JWT_ACCESS_TOKEN>"


@router.post(
    "/{ride_id}/start",
    response_model=TripStartResponse,
    status_code=status.HTTP_200_OK,
    summary="Start a live trip (driver)",
)
async def start_trip(
    ride_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_driver),
):
    ride = await service.start_trip(db=db, current_user_id=current_user.id, ride_id=ride_id)

    return TripStartResponse(
        ride_id=ride.id,
        status=str(ride.status),
        telemetry_ws_url_template=_telemetry_ws_template(ride.id),
        started_at=ride.updated_at,
    )


@router.post(
    "/{ride_id}/complete",
    response_model=TripCompleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete trip + (optionally) settle payments (driver)",
)
async def complete_trip(
    ride_id: UUID,
    settle: bool = Query(True, description="If true, attempt wallet settlement for all bookings"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_driver),
):
    ride, settlement_items = await service.complete_trip(
        db=db,
        current_user_id=current_user.id,
        ride_id=ride_id,
        settle=settle,
    )

    settled_count = sum(1 for x in settlement_items if x.settled)
    failed_count = sum(1 for x in settlement_items if not x.settled)

    return TripCompleteResponse(
        ride_id=ride.id,
        status=str(ride.status),
        completed_at=ride.updated_at,
        settlement_attempted=settle,
        settled_count=settled_count,
        failed_count=failed_count,
        settlement=settlement_items,
        next_rating_endpoint="/api/v1/ratings",
    )


@router.post(
    "/{ride_id}/settle",
    response_model=TripSettleResponse,
    status_code=status.HTTP_200_OK,
    summary="Settle payments for a completed trip (driver)",
)
async def settle_trip(
    ride_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_driver),
):
    ride = await service._get_ride_or_404(db, ride_id)

    if ride.driver_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the ride driver can settle payments",
        )

    settlement_items = await service.settle_trip_payments(db=db, ride=ride)
    settled_count = sum(1 for x in settlement_items if x.settled)
    failed_count = sum(1 for x in settlement_items if not x.settled)

    return TripSettleResponse(
        ride_id=ride.id,
        settled_count=settled_count,
        failed_count=failed_count,
        settlement=settlement_items,
    )


@router.get(
    "/{ride_id}/summary",
    response_model=TripSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Trip summary (driver/passenger/admin)",
)
async def trip_summary(
    ride_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Authorization: driver, admin, or passenger with a booking.
    summary = await service.get_trip_summary(db=db, ride_id=ride_id)
    ride = summary["ride"]

    is_driver = ride.driver_id == current_user.id
    is_admin = getattr(current_user, "role", None) == UserRole.ADMIN

    if not is_driver and not is_admin:
        # Check passenger booking
        from sqlalchemy import select
        from app.models.booking import Booking

        result = await db.execute(
            select(Booking.id).where(
                Booking.ride_id == ride_id,
                Booking.passenger_id == current_user.id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this trip",
            )

    return TripSummaryResponse(
        ride_id=ride.id,
        ride_status=str(ride.status),
        driver_id=ride.driver_id,
        bookings_total=summary["bookings_total"],
        bookings_active=summary["bookings_active"],
        telemetry_points_total=summary["telemetry_points_total"],
        safety_telemetry_total=summary["safety_telemetry_total"],
        incidents_total=summary["incidents_total"],
        incidents_critical=summary["incidents_critical"],
    )
