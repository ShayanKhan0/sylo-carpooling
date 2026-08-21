"""
Prompt 11C — Earnings CRUD Layer

Database query functions for driver earnings data.
Optimized aggregation queries with no N+1 issues.

Author: Smart Carpooling Backend Team
Date: December 20, 2025
"""

import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Tuple, Optional
from uuid import UUID

from sqlalchemy import func, and_, extract, case, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.future import select

from app.models.ride import Ride
from app.models.booking import Booking
from app.models.wallet import Wallet
from app.models.enums import RideStatus, BookingStatus
from app.modules.rides.models import RideBooking
from app.modules.payments.models import (
    Transaction as PaymentTransaction,
    TransactionTypeEnum,
    TransactionStatusEnum,
)

logger = logging.getLogger(__name__)


# Commission rate configuration (aligned with payment module)
COMMISSION_RATE = Decimal("0.03")  # 3% platform commission on ride fares
CANONICAL_CANCELLED_BOOKING_STATUSES = ("cancelled", "canceled")


def _non_cancelled_booking_earnings_expr():
    """SQL expression for booking earnings with legacy-safe fallbacks.

    Priority for each non-cancelled booking:
    1) booking.fare
    2) booking.individual_fare * booking.seats_reserved
    3) ride.price_per_seat * booking.seats_reserved
    """
    return case(
        (
            Booking.status != BookingStatus.CANCELLED,
            func.coalesce(
                func.nullif(Booking.fare, 0),
                func.nullif(
                    func.coalesce(Booking.individual_fare, 0)
                    * func.coalesce(Booking.seats_reserved, 0),
                    0,
                ),
                func.coalesce(Ride.price_per_seat, 0)
                * func.coalesce(Booking.seats_reserved, 0),
                0,
            ),
        ),
        else_=0,
    )


def _non_cancelled_ride_booking_earnings_expr():
    """SQL expression for canonical ride_bookings earnings."""
    return case(
        (
            ~func.lower(cast(RideBooking.status, String)).in_(
                CANONICAL_CANCELLED_BOOKING_STATUSES
            ),
            func.coalesce(
                func.nullif(RideBooking.total_price, 0),
                func.coalesce(Ride.price_per_seat, 0)
                * func.coalesce(RideBooking.booked_seats, 0),
                0,
            ),
        ),
        else_=0,
    )


def _legacy_ride_earnings_subquery():
    """Correlated per-ride earnings from legacy bookings table."""
    return (
        select(func.coalesce(func.sum(_non_cancelled_booking_earnings_expr()), 0))
        .where(Booking.ride_id == Ride.id)
        .correlate(Ride)
        .scalar_subquery()
    )


def _canonical_ride_earnings_subquery():
    """Correlated per-ride earnings from canonical ride_bookings table."""
    return (
        select(func.coalesce(func.sum(_non_cancelled_ride_booking_earnings_expr()), 0))
        .where(RideBooking.ride_id == Ride.id)
        .correlate(Ride)
        .scalar_subquery()
    )


def _effective_ride_earnings_expr():
    """Per-ride earnings using canonical totals with legacy compatibility."""
    return func.greatest(
        func.coalesce(_canonical_ride_earnings_subquery(), 0),
        func.coalesce(_legacy_ride_earnings_subquery(), 0),
    )


async def get_monthly_rides_earnings(
    db: AsyncSession,
    driver_id: UUID,
    year: int,
    month: int
) -> Tuple[int, Decimal, Decimal]:
    """
    Get total rides and earnings for a specific month.
    
    Args:
        db: Database session
        driver_id: Driver's user ID
        year: Year (e.g., 2025)
        month: Month (1-12)
    
    Returns:
        Tuple[total_rides, gross_earnings, commission_deducted]
    """
    try:
        gross_earnings_expr = func.coalesce(func.sum(_effective_ride_earnings_expr()), 0)

        # Query completed rides in the specified month
        query = (
            select(
                func.count(func.distinct(Ride.id)).label("total_rides"),
                gross_earnings_expr.label("gross_earnings"),
            )
            .where(
                and_(
                    Ride.driver_id == driver_id,
                    Ride.status == RideStatus.COMPLETED,
                    extract('year', Ride.departure_time) == year,
                    extract('month', Ride.departure_time) == month
                )
            )
        )
        
        result = await db.execute(query)
        row = result.first()
        
        if not row:
            return 0, Decimal("0.00"), Decimal("0.00")
        
        total_rides = row.total_rides or 0
        gross_earnings = Decimal(str(row.gross_earnings or 0))
        commission_deducted = gross_earnings * COMMISSION_RATE
        
        logger.debug(
            f"[get_monthly_rides_earnings] driver_id={driver_id}, "
            f"year={year}, month={month}, rides={total_rides}, "
            f"gross={gross_earnings}, commission={commission_deducted}"
        )
        
        return total_rides, gross_earnings, commission_deducted
        
    except Exception as e:
        logger.error(f"[get_monthly_rides_earnings] Error: {e}", exc_info=True)
        raise


async def get_lifetime_rides_earnings(
    db: AsyncSession,
    driver_id: UUID
) -> Tuple[int, Decimal, Decimal]:
    """
    Get lifetime total rides and earnings.
    
    Args:
        db: Database session
        driver_id: Driver's user ID
    
    Returns:
        Tuple[total_rides, gross_earnings, commission_deducted]
    """
    try:
        gross_earnings_expr = func.coalesce(func.sum(_effective_ride_earnings_expr()), 0)

        # Query all completed rides
        query = (
            select(
                func.count(func.distinct(Ride.id)).label("total_rides"),
                gross_earnings_expr.label("gross_earnings"),
            )
            .where(
                and_(
                    Ride.driver_id == driver_id,
                    Ride.status == RideStatus.COMPLETED
                )
            )
        )
        
        result = await db.execute(query)
        row = result.first()
        
        if not row:
            return 0, Decimal("0.00"), Decimal("0.00")
        
        total_rides = row.total_rides or 0
        gross_earnings = Decimal(str(row.gross_earnings or 0))
        commission_deducted = gross_earnings * COMMISSION_RATE
        
        logger.debug(
            f"[get_lifetime_rides_earnings] driver_id={driver_id}, "
            f"rides={total_rides}, gross={gross_earnings}, commission={commission_deducted}"
        )
        
        return total_rides, gross_earnings, commission_deducted
        
    except Exception as e:
        logger.error(f"[get_lifetime_rides_earnings] Error: {e}", exc_info=True)
        raise


async def get_wallet_balance(
    db: AsyncSession,
    user_id: UUID
) -> Decimal:
    """
    Get current wallet balance for user.
    
    Args:
        db: Database session
        user_id: User's ID
    
    Returns:
        Current wallet balance
    """
    try:
        query = select(Wallet.balance).where(Wallet.user_id == user_id)
        result = await db.execute(query)
        balance = result.scalar()
        
        return Decimal(str(balance or 0))
        
    except Exception as e:
        logger.error(f"[get_wallet_balance] Error: {e}", exc_info=True)
        raise


async def get_total_withdrawals(
    db: AsyncSession,
    user_id: UUID
) -> Decimal:
    """
    Get total amount withdrawn by user.
    
    Sums all completed payout transactions from wallet.
    
    Args:
        db: Database session
        user_id: User's ID
    
    Returns:
        Total withdrawn amount
    """
    try:
        # Sum completed payout transactions from the payments ledger.
        # This includes Prop Money payouts as well.
        query = (
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (PaymentTransaction.amount < 0, PaymentTransaction.amount),
                            else_=0,
                        )
                    ),
                    0,
                )
            )
            .where(
                and_(
                    PaymentTransaction.user_id == user_id,
                    PaymentTransaction.type == TransactionTypeEnum.PAYOUT,
                    PaymentTransaction.status == TransactionStatusEnum.COMPLETED,
                )
            )
        )
        
        result = await db.execute(query)
        total = result.scalar()
        
        # Payout amounts are negative, so take absolute value
        total_withdrawn = abs(Decimal(str(total or 0)))
        
        logger.debug(
            f"[get_total_withdrawals] user_id={user_id}, "
            f"total_withdrawn={total_withdrawn}"
        )
        
        return total_withdrawn
        
    except Exception as e:
        logger.error(f"[get_total_withdrawals] Error: {e}", exc_info=True)
        raise


async def get_daily_earnings_chart(
    db: AsyncSession,
    driver_id: UUID,
    days: int = 30
) -> List[Tuple[date, int, Decimal]]:
    """
    Get daily earnings for the last N days.
    
    Returns earnings grouped by day for chart visualization.
    
    Args:
        db: Database session
        driver_id: Driver's user ID
        days: Number of days to include (default 30)
    
    Returns:
        List of tuples: (date, ride_count, net_earnings)
    """
    try:
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days - 1)

        gross_earnings_expr = func.coalesce(func.sum(_effective_ride_earnings_expr()), 0)
        
        # Query rides grouped by date
        query = (
            select(
                func.date(Ride.departure_time).label("ride_date"),
                func.count(func.distinct(Ride.id)).label("rides"),
                gross_earnings_expr.label("gross_earnings"),
            )
            .where(
                and_(
                    Ride.driver_id == driver_id,
                    Ride.status == RideStatus.COMPLETED,
                    func.date(Ride.departure_time) >= start_date,
                    func.date(Ride.departure_time) <= end_date
                )
            )
            .group_by(func.date(Ride.departure_time))
            .order_by(func.date(Ride.departure_time))
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        # Convert to list with net earnings (after commission)
        daily_data = []
        for row in rows:
            ride_date = row.ride_date
            rides = row.rides or 0
            gross = Decimal(str(row.gross_earnings or 0))
            gross_earnings = gross
            
            daily_data.append((ride_date, rides, gross_earnings))
        
        logger.debug(
            f"[get_daily_earnings_chart] driver_id={driver_id}, "
            f"days={days}, data_points={len(daily_data)}"
        )
        
        return daily_data
        
    except Exception as e:
        logger.error(f"[get_daily_earnings_chart] Error: {e}", exc_info=True)
        raise


async def get_ride_earnings_details(
    db: AsyncSession,
    driver_id: UUID,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    payout_status: Optional[str] = None
) -> List[Ride]:
    """
    Get detailed ride earnings for CSV export.
    
    Includes all ride details with eager loading to prevent N+1 queries.
    
    Args:
        db: Database session
        driver_id: Driver's user ID
        from_date: Optional start date filter
        to_date: Optional end date filter
        payout_status: Optional payout status filter
    
    Returns:
        List of Ride objects with bookings loaded
    """
    try:
        # Base query with eager loading
        query = (
            select(Ride)
            .options(joinedload(Ride.bookings))
            .where(
                and_(
                    Ride.driver_id == driver_id,
                    Ride.status == RideStatus.COMPLETED
                )
            )
        )
        
        # Apply date filters
        if from_date:
            query = query.where(func.date(Ride.departure_time) >= from_date)
        
        if to_date:
            query = query.where(func.date(Ride.departure_time) <= to_date)
        
        # Note: payout_status filtering would require wallet transaction correlation
        # For now, we'll handle this in the service layer
        
        query = query.order_by(Ride.departure_time.desc())
        
        result = await db.execute(query)
        rides = result.unique().scalars().all()
        
        logger.debug(
            f"[get_ride_earnings_details] driver_id={driver_id}, "
            f"from_date={from_date}, to_date={to_date}, rides={len(rides)}"
        )
        
        return list(rides)
        
    except Exception as e:
        logger.error(f"[get_ride_earnings_details] Error: {e}", exc_info=True)
        raise


async def check_payout_status(
    db: AsyncSession,
    user_id: UUID,
    year: int,
    month: int
) -> str:
    """
    Determine payout status for a given month.
    
    Logic:
    - Check wallet transactions for payouts in the month
    - If all payouts completed -> "paid"
    - If any failed -> "failed"
    - Otherwise -> "pending"
    
    Args:
        db: Database session
        user_id: User's ID
        year: Year
        month: Month
    
    Returns:
        Payout status: "pending", "paid", or "failed"
    """
    try:
        # Check payout transactions in this month from the payments ledger.
        query = (
            select(PaymentTransaction.status)
            .where(
                and_(
                    PaymentTransaction.user_id == user_id,
                    PaymentTransaction.type == TransactionTypeEnum.PAYOUT,
                    extract('year', PaymentTransaction.created_at) == year,
                    extract('month', PaymentTransaction.created_at) == month,
                )
            )
        )
        
        result = await db.execute(query)
        statuses = [row[0] for row in result.all()]
        
        if not statuses:
            return "pending"
        
        # Check for failed transactions
        if TransactionStatusEnum.FAILED in statuses:
            return "failed"
        
        # Check if all are completed
        if all(status == TransactionStatusEnum.COMPLETED for status in statuses):
            return "paid"
        
        return "pending"
        
    except Exception as e:
        logger.error(f"[check_payout_status] Error: {e}", exc_info=True)
        return "pending"
