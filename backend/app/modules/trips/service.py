from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import List
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.enums import RideStatus
from app.models.ride import Ride
from app.models.telemetry_point import TelemetryPoint
from app.modules.safety_ai.models import IncidentReport, SeverityEnum, TelemetryData
from app.modules.payments import service as payments_service
from app.modules.payments.models import Transaction, TransactionStatusEnum, TransactionTypeEnum

from .schemas import SettlementItem


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_ride_or_404(db: AsyncSession, ride_id: UUID) -> Ride:
    result = await db.execute(select(Ride).where(Ride.id == ride_id))
    ride = result.scalar_one_or_none()
    if not ride:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")
    return ride


async def start_trip(db: AsyncSession, current_user_id: UUID, ride_id: UUID) -> Ride:
    result = await db.execute(
        select(Ride)
        .where(Ride.id == ride_id)
        .with_for_update()
    )
    ride = result.scalar_one_or_none()
    if not ride:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")

    if ride.driver_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the ride driver can start the trip")

    if ride.status == RideStatus.IN_PROGRESS:
        return ride

    if ride.status != RideStatus.OPEN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot start trip in status '{ride.status}'",
        )

    ride.status = RideStatus.IN_PROGRESS
    await db.commit()
    await db.refresh(ride)
    return ride


async def complete_trip(
    db: AsyncSession,
    current_user_id: UUID,
    ride_id: UUID,
    settle: bool = True,
) -> tuple[Ride, List[SettlementItem]]:
    result = await db.execute(
        select(Ride)
        .where(Ride.id == ride_id)
        .with_for_update()
    )
    ride = result.scalar_one_or_none()
    if not ride:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ride not found")

    if ride.driver_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the ride driver can complete the trip")

    if ride.status not in (RideStatus.IN_PROGRESS, RideStatus.OPEN, RideStatus.COMPLETED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot complete trip in status '{ride.status}'",
        )

    # Mark ride completed
    ride.status = RideStatus.COMPLETED

    # Mark active bookings completed (reserved -> completed)
    bookings_result = await db.execute(
        select(Booking)
        .where(Booking.ride_id == ride_id)
        .with_for_update()
    )
    bookings = bookings_result.scalars().all()
    for booking in bookings:
        if booking.status == BookingStatus.RESERVED:
            booking.status = BookingStatus.COMPLETED
            booking.version += 1

    await db.commit()
    await db.refresh(ride)

    settlement_items: List[SettlementItem] = []
    if settle:
        settlement_items = await settle_trip_payments(db=db, ride=ride)

    return ride, settlement_items


async def _booking_already_paid(
    db: AsyncSession,
    passenger_id: UUID,
    ride_id: UUID,
    fare: Decimal,
) -> bool:
    # The payments module logs fare deductions as negative amounts.
    result = await db.execute(
        select(Transaction.id)
        .where(
            Transaction.user_id == passenger_id,
            Transaction.ride_id == ride_id,
            Transaction.type == TransactionTypeEnum.DEDUCT,
            Transaction.status == TransactionStatusEnum.COMPLETED,
            Transaction.amount == -fare,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def settle_trip_payments(db: AsyncSession, ride: Ride) -> List[SettlementItem]:
    # Fetch current bookings (completed or reserved are payable; cancelled ignored).
    bookings_result = await db.execute(
        select(Booking).where(
            Booking.ride_id == ride.id,
            Booking.status.in_([BookingStatus.RESERVED, BookingStatus.COMPLETED])
        )
    )
    bookings = bookings_result.scalars().all()

    items: List[SettlementItem] = []
    for booking in bookings:
        fare = Decimal(booking.fare)
        if fare <= 0:
            items.append(
                SettlementItem(
                    booking_id=booking.id,
                    passenger_id=booking.passenger_id,
                    fare=fare,
                    settled=True,
                )
            )
            continue

        try:
            if await _booking_already_paid(db, booking.passenger_id, ride.id, fare):
                items.append(
                    SettlementItem(
                        booking_id=booking.id,
                        passenger_id=booking.passenger_id,
                        fare=fare,
                        settled=True,
                    )
                )
                continue

            await payments_service.process_ride_payment_service(
                db=db,
                passenger_id=booking.passenger_id,
                driver_id=ride.driver_id,
                ride_id=ride.id,
                fare_amount=fare,
            )

            items.append(
                SettlementItem(
                    booking_id=booking.id,
                    passenger_id=booking.passenger_id,
                    fare=fare,
                    settled=True,
                )
            )
        except Exception as e:
            items.append(
                SettlementItem(
                    booking_id=booking.id,
                    passenger_id=booking.passenger_id,
                    fare=fare,
                    settled=False,
                    error=str(e),
                )
            )

    return items


async def get_trip_summary(db: AsyncSession, ride_id: UUID) -> dict:
    ride = await _get_ride_or_404(db, ride_id)

    bookings_total = await db.scalar(
        select(func.count(Booking.id)).where(Booking.ride_id == ride_id)
    )
    bookings_active = await db.scalar(
        select(func.count(Booking.id)).where(
            Booking.ride_id == ride_id,
            Booking.status != BookingStatus.CANCELLED,
        )
    )

    telemetry_points_total = await db.scalar(
        select(func.count(TelemetryPoint.id)).where(TelemetryPoint.ride_id == ride_id)
    )

    safety_telemetry_total = await db.scalar(
        select(func.count(TelemetryData.id)).where(TelemetryData.ride_id == ride_id)
    )

    incidents_total = await db.scalar(
        select(func.count(IncidentReport.id)).where(IncidentReport.ride_id == ride_id)
    )

    incidents_critical = await db.scalar(
        select(func.count(IncidentReport.id)).where(
            IncidentReport.ride_id == ride_id,
            IncidentReport.severity == SeverityEnum.CRITICAL,
        )
    )

    return {
        "ride": ride,
        "bookings_total": int(bookings_total or 0),
        "bookings_active": int(bookings_active or 0),
        "telemetry_points_total": int(telemetry_points_total or 0),
        "safety_telemetry_total": int(safety_telemetry_total or 0),
        "incidents_total": int(incidents_total or 0),
        "incidents_critical": int(incidents_critical or 0),
    }
