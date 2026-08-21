"""
Prompt 11D — Analytics CRUD Layer

Database queries for daily aggregates and admin analytics.

Author: Smart Carpooling Backend Team
Date: January 23, 2026
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Tuple

from sqlalchemy import func, and_, select, distinct, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ride import Ride
from app.models.booking import Booking
from app.models.wallet_transaction import WalletTransaction
from app.models.verification import Verification
from app.models.enums import RideStatus, BookingStatus, VerificationStatus, TransactionType, TransactionStatus
from app.modules.analytics.models import DailyAggregate


COMMISSION_RATE = Decimal("0.03")


async def get_daily_aggregate(
    db: AsyncSession,
    target_date: date
) -> DailyAggregate | None:
    result = await db.execute(
        select(DailyAggregate).where(DailyAggregate.date == target_date)
    )
    return result.scalar_one_or_none()


async def upsert_daily_aggregate(
    db: AsyncSession,
    target_date: date,
    rides_count: int,
    completed_rides: int,
    cancelled_rides: int,
    gross_revenue: Decimal,
    commission_revenue: Decimal,
    active_drivers: int,
    verification_failures: int
) -> DailyAggregate:
    existing = await get_daily_aggregate(db, target_date)

    if existing:
        existing.rides_count = rides_count
        existing.completed_rides = completed_rides
        existing.cancelled_rides = cancelled_rides
        existing.gross_revenue = gross_revenue
        existing.commission_revenue = commission_revenue
        existing.active_drivers = active_drivers
        existing.verification_failures = verification_failures
        await db.flush()
        return existing

    aggregate = DailyAggregate(
        date=target_date,
        rides_count=rides_count,
        completed_rides=completed_rides,
        cancelled_rides=cancelled_rides,
        gross_revenue=gross_revenue,
        commission_revenue=commission_revenue,
        active_drivers=active_drivers,
        verification_failures=verification_failures
    )
    db.add(aggregate)
    await db.flush()
    return aggregate


async def get_daily_aggregates_range(
    db: AsyncSession,
    start_date: date,
    end_date: date
) -> List[DailyAggregate]:
    result = await db.execute(
        select(DailyAggregate)
        .where(
            and_(
                DailyAggregate.date >= start_date,
                DailyAggregate.date <= end_date
            )
        )
        .order_by(DailyAggregate.date.asc())
    )
    return list(result.scalars().all())


async def get_last_n_days_aggregates(
    db: AsyncSession,
    days: int
) -> List[DailyAggregate]:
    end_date = date.today()
    start_date = end_date - timedelta(days=days - 1)
    return await get_daily_aggregates_range(db, start_date, end_date)


async def get_all_daily_aggregates(db: AsyncSession) -> List[DailyAggregate]:
    result = await db.execute(
        select(DailyAggregate).order_by(DailyAggregate.date.asc())
    )
    return list(result.scalars().all())


async def get_lifetime_totals(db: AsyncSession) -> Tuple[int, int, int, Decimal, Decimal, int, int]:
    result = await db.execute(
        select(
            func.coalesce(func.sum(DailyAggregate.rides_count), 0),
            func.coalesce(func.sum(DailyAggregate.completed_rides), 0),
            func.coalesce(func.sum(DailyAggregate.cancelled_rides), 0),
            func.coalesce(func.sum(DailyAggregate.gross_revenue), 0),
            func.coalesce(func.sum(DailyAggregate.commission_revenue), 0),
            func.coalesce(func.sum(DailyAggregate.active_drivers), 0),
            func.coalesce(func.sum(DailyAggregate.verification_failures), 0)
        )
    )
    row = result.first()
    if not row:
        return 0, 0, 0, Decimal("0.00"), Decimal("0.00"), 0, 0

    return (
        int(row[0] or 0),
        int(row[1] or 0),
        int(row[2] or 0),
        Decimal(str(row[3] or 0)),
        Decimal(str(row[4] or 0)),
        int(row[5] or 0),
        int(row[6] or 0),
    )


async def compute_daily_metrics(
    db: AsyncSession,
    target_date: date
) -> Tuple[int, int, int, Decimal, Decimal, int, int]:
    start_dt = datetime.combine(target_date, datetime.min.time())
    end_dt = datetime.combine(target_date, datetime.max.time())

    rides_result = await db.execute(
        select(
            func.count(Ride.id),
            func.coalesce(func.sum(case((Ride.status == RideStatus.COMPLETED, 1), else_=0)), 0),
            func.coalesce(func.sum(case((Ride.status == RideStatus.CANCELLED, 1), else_=0)), 0)
        ).where(
            and_(
                Ride.start_time >= start_dt,
                Ride.start_time <= end_dt
            )
        )
    )
    rides_row = rides_result.first()
    rides_count = int(rides_row[0] or 0)
    completed_rides = int(rides_row[1] or 0)
    cancelled_rides = int(rides_row[2] or 0)

    revenue_result = await db.execute(
        select(func.coalesce(func.sum(Booking.fare), 0))
        .select_from(Booking)
        .join(Ride, Ride.id == Booking.ride_id)
        .where(
            and_(
                Ride.start_time >= start_dt,
                Ride.start_time <= end_dt,
                Ride.status == RideStatus.COMPLETED,
                Booking.status == BookingStatus.COMPLETED
            )
        )
    )
    gross_revenue = Decimal(str(revenue_result.scalar() or 0))
    commission_revenue = gross_revenue * COMMISSION_RATE

    active_drivers_result = await db.execute(
        select(func.count(distinct(Ride.driver_id)))
        .where(
            and_(
                Ride.start_time >= start_dt,
                Ride.start_time <= end_dt,
                Ride.status == RideStatus.COMPLETED
            )
        )
    )
    active_drivers = int(active_drivers_result.scalar() or 0)

    wallet_result = await db.execute(
        select(func.coalesce(func.sum(func.abs(WalletTransaction.amount)), 0))
        .where(
            and_(
                WalletTransaction.created_at >= start_dt,
                WalletTransaction.created_at <= end_dt,
                WalletTransaction.type == TransactionType.RIDE,
                WalletTransaction.status == TransactionStatus.COMPLETED
            )
        )
    )
    wallet_gross = Decimal(str(wallet_result.scalar() or 0))

    if gross_revenue == Decimal("0") and wallet_gross > 0:
        gross_revenue = wallet_gross
        commission_revenue = gross_revenue * COMMISSION_RATE

    verification_result = await db.execute(
        select(func.count(Verification.id))
        .where(
            and_(
                Verification.created_at >= start_dt,
                Verification.created_at <= end_dt,
                Verification.status == VerificationStatus.REJECTED
            )
        )
    )
    verification_failures = int(verification_result.scalar() or 0)

    return (
        rides_count,
        completed_rides,
        cancelled_rides,
        gross_revenue,
        commission_revenue,
        active_drivers,
        verification_failures
    )
