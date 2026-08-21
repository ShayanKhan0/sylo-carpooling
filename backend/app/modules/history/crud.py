"""
History CRUD Layer (Prompt 11B)

Async database query functions for ride history.
Aligned with actual DB schema (Ride, Booking, Rating).

Author: Smart Carpooling Backend Team
Date: December 19, 2025
Prompt: 11B - Trip History Module
"""

from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ride import Ride
from app.models.booking import Booking
from app.models.rating import Rating


async def get_user_rides(
    db: AsyncSession,
    user_id: UUID,
    as_driver: bool = False,
    status_filter: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    offset: int = 0,
    limit: int = 20,
) -> Tuple[List[Ride], int]:
    """Get rides for a user with pagination."""
    if as_driver:
        base = select(Ride).where(Ride.driver_id == user_id)
    else:
        ride_ids_q = select(Booking.ride_id).where(Booking.passenger_id == user_id)
        base = select(Ride).where(Ride.id.in_(ride_ids_q))

    if status_filter:
        base = base.where(Ride.status == status_filter)

    if from_date:
        try:
            from_dt = datetime.strptime(from_date, "%Y-%m-%d")
            base = base.where(Ride.created_at >= from_dt)
        except ValueError:
            pass

    if to_date:
        try:
            to_dt = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
            base = base.where(Ride.created_at < to_dt)
        except ValueError:
            pass

    count_res = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_res.scalar() or 0

    data_q = base.order_by(Ride.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(data_q)
    rides = result.scalars().all()

    return rides, total


async def get_ride_with_details(db: AsyncSession, ride_id: UUID) -> Optional[Ride]:
    """Get ride by ID."""
    result = await db.execute(select(Ride).where(Ride.id == ride_id))
    return result.scalar_one_or_none()


async def get_ride_rating(db: AsyncSession, ride_id: UUID, rater_id: UUID) -> Optional[Rating]:
    """Get rating for a ride by a specific user."""
    result = await db.execute(
        select(Rating).where(
            and_(Rating.ride_id == ride_id, Rating.rater_id == rater_id)
        )
    )
    return result.scalar_one_or_none()


async def get_user_average_rating(db: AsyncSession, user_id: UUID) -> Optional[float]:
    """Get average rating for a user."""
    result = await db.execute(
        select(func.avg(Rating.score)).where(Rating.ratee_id == user_id)
    )
    avg = result.scalar()
    return round(float(avg), 2) if avg else None


async def check_ride_access(db: AsyncSession, ride_id: UUID, user_id: UUID) -> bool:
    """Check if user is driver or passenger of the ride."""
    result = await db.execute(select(Ride).where(Ride.id == ride_id))
    ride = result.scalar_one_or_none()
    if not ride:
        return False

    if ride.driver_id == user_id:
        return True

    bk_res = await db.execute(
        select(Booking.id).where(
            and_(Booking.ride_id == ride_id, Booking.passenger_id == user_id)
        )
    )
    return bk_res.scalar_one_or_none() is not None
