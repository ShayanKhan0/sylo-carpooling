import logging
import csv
import io
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, cast, String

from app.modules.earnings import crud, schemas
from app.models.booking import Booking
from app.models.enums import BookingStatus
from app.modules.rides.models import RideBooking

logger = logging.getLogger(__name__)

CANONICAL_CANCELLED_STATUSES = {"cancelled", "canceled"}


def _normalize_status(raw: object) -> str:
    if raw is None:
        return ""
    if hasattr(raw, "value"):
        return str(getattr(raw, "value") or "").strip().lower()
    return str(raw).strip().lower()


async def get_monthly_earnings(
    db: AsyncSession,
    driver_id: UUID,
    year: int,
    month: int
) -> schemas.MonthlyEarningsResponse:
    """
    Calculate monthly earnings summary for driver.
    
    Args:
        db: Database session
        driver_id: Driver's user ID
        year: Year (e.g., 2025)
        month: Month (1-12)
    
    Returns:
        MonthlyEarningsResponse with all earnings data
    """
    try:
        # Get rides and earnings from CRUD
        total_rides, gross_earnings, commission_deducted = await crud.get_monthly_rides_earnings(
            db, driver_id, year, month
        )
        
        # Calculate net earnings
        net_earnings = gross_earnings - commission_deducted
        
        # Determine payout status
        payout_status = await crud.check_payout_status(db, driver_id, year, month)
        
        logger.info(
            f"[get_monthly_earnings] driver_id={driver_id}, "
            f"year={year}, month={month}, rides={total_rides}, "
            f"gross={gross_earnings}, net={net_earnings}"
        )
        
        return schemas.MonthlyEarningsResponse(
            year=year,
            month=month,
            total_rides=total_rides,
            gross_earnings=gross_earnings,
            commission_deducted=commission_deducted,
            net_earnings=net_earnings,
            payout_status=payout_status
        )
        
    except Exception as e:
        logger.error(f"[get_monthly_earnings] Error: {e}", exc_info=True)
        raise


async def get_lifetime_earnings(
    db: AsyncSession,
    driver_id: UUID
) -> schemas.LifetimeEarningsResponse:
    """
    Calculate lifetime earnings summary for driver.
    
    Args:
        db: Database session
        driver_id: Driver's user ID
    
    Returns:
        LifetimeEarningsResponse with all-time statistics
    """
    try:
        # Get lifetime rides and earnings
        total_rides, lifetime_gross, lifetime_commission = await crud.get_lifetime_rides_earnings(
            db, driver_id
        )
        
        # Calculate lifetime net
        lifetime_net = lifetime_gross - lifetime_commission
        
        # Get wallet information
        current_wallet_balance = await crud.get_wallet_balance(db, driver_id)
        total_withdrawn = await crud.get_total_withdrawals(db, driver_id)
        
        logger.info(
            f"[get_lifetime_earnings] driver_id={driver_id}, "
            f"rides={total_rides}, gross={lifetime_gross}, "
            f"net={lifetime_net}, withdrawn={total_withdrawn}, "
            f"balance={current_wallet_balance}"
        )
        
        return schemas.LifetimeEarningsResponse(
            total_rides=total_rides,
            lifetime_gross=lifetime_gross,
            lifetime_commission=lifetime_commission,
            lifetime_net=lifetime_net,
            total_withdrawn=total_withdrawn,
            current_wallet_balance=current_wallet_balance
        )
        
    except Exception as e:
        logger.error(f"[get_lifetime_earnings] Error: {e}", exc_info=True)
        raise


async def get_earnings_chart(
    db: AsyncSession,
    driver_id: UUID,
    days: int = 30
) -> schemas.EarningsChartResponse:
    """
    Get daily earnings chart data for the last N days.
    
    Args:
        db: Database session
        driver_id: Driver's user ID
        days: Number of days to include (default 30)
    
    Returns:
        EarningsChartResponse with daily breakdown
    """
    try:
        # Get daily data from CRUD
        daily_data_raw = await crud.get_daily_earnings_chart(db, driver_id, days)
        
        # Calculate period dates
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days - 1)
        
        # Convert to schema objects
        daily_data = [
            schemas.DailyEarningsData(
                date=ride_date,
                rides=rides,
                earnings=earnings_amount
            )
            for ride_date, rides, earnings_amount in daily_data_raw
        ]
        
        # Calculate totals
        total_earnings = sum(d.earnings for d in daily_data)
        total_rides = sum(d.rides for d in daily_data)
        
        logger.info(
            f"[get_earnings_chart] driver_id={driver_id}, "
            f"days={days}, total_earnings={total_earnings}, "
            f"total_rides={total_rides}"
        )
        
        return schemas.EarningsChartResponse(
            period_start=start_date,
            period_end=end_date,
            daily_data=daily_data,
            total_earnings=total_earnings,
            total_rides=total_rides
        )
        
    except Exception as e:
        logger.error(f"[get_earnings_chart] Error: {e}", exc_info=True)
        raise


async def generate_earnings_csv(
    db: AsyncSession,
    driver_id: UUID,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    payout_status: Optional[str] = None
) -> str:
    """
    Generate CSV export of ride earnings.
    
    Args:
        db: Database session
        driver_id: Driver's user ID
        from_date: Optional start date filter
        to_date: Optional end date filter
        payout_status: Optional payout status filter
    
    Returns:
        CSV content as string
    """
    try:
        # Get ride details from CRUD
        rides = await crud.get_ride_earnings_details(
            db, driver_id, from_date, to_date, payout_status
        )

        ride_ids = [ride.id for ride in rides if getattr(ride, "id", None) is not None]
        canonical_totals: dict[UUID, tuple[int, Decimal]] = {}
        legacy_totals: dict[UUID, tuple[int, Decimal]] = {}

        if ride_ids:
            canonical_query = (
                select(
                    RideBooking.ride_id.label("ride_id"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    ~func.lower(cast(RideBooking.status, String)).in_(
                                        tuple(CANONICAL_CANCELLED_STATUSES)
                                    ),
                                    func.coalesce(RideBooking.booked_seats, 0),
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("seats_booked"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    ~func.lower(cast(RideBooking.status, String)).in_(
                                        tuple(CANONICAL_CANCELLED_STATUSES)
                                    ),
                                    func.coalesce(RideBooking.total_price, 0),
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("gross_earnings"),
                )
                .where(RideBooking.ride_id.in_(ride_ids))
                .group_by(RideBooking.ride_id)
            )
            canonical_rows = (await db.execute(canonical_query)).all()
            for row in canonical_rows:
                canonical_totals[row.ride_id] = (
                    int(row.seats_booked or 0),
                    Decimal(str(row.gross_earnings or 0)),
                )

            legacy_query = (
                select(
                    Booking.ride_id.label("ride_id"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    Booking.status != BookingStatus.CANCELLED,
                                    func.coalesce(Booking.seats_reserved, 0),
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("seats_booked"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    Booking.status != BookingStatus.CANCELLED,
                                    func.coalesce(
                                        func.nullif(Booking.fare, 0),
                                        func.nullif(
                                            func.coalesce(Booking.individual_fare, 0)
                                            * func.coalesce(Booking.seats_reserved, 0),
                                            0,
                                        ),
                                        0,
                                    ),
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("gross_earnings"),
                )
                .where(Booking.ride_id.in_(ride_ids))
                .group_by(Booking.ride_id)
            )
            legacy_rows = (await db.execute(legacy_query)).all()
            for row in legacy_rows:
                legacy_totals[row.ride_id] = (
                    int(row.seats_booked or 0),
                    Decimal(str(row.gross_earnings or 0)),
                )
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "Ride ID",
            "Date",
            "From Location",
            "To Location",
            "Seats Booked",
            "Earnings (PKR)",
            "Payout Status",
        ])

        payout_status_by_month: dict[tuple[int, int], str] = {}
        
        # Write data rows
        for ride in rides:
            # Prefer canonical ride_bookings totals; fallback to legacy bookings totals.
            seats_booked = 0
            gross_earnings = Decimal("0.00")
            if ride.id in canonical_totals:
                seats_booked, gross_earnings = canonical_totals[ride.id]
            elif ride.id in legacy_totals:
                seats_booked, gross_earnings = legacy_totals[ride.id]
            else:
                # Defensive fallback for unexpected ORM states.
                for booking in getattr(ride, "bookings", []) or []:
                    if _normalize_status(getattr(booking, "status", None)) in CANONICAL_CANCELLED_STATUSES:
                        continue
                    seats_reserved = int(getattr(booking, "seats_reserved", 0) or 0)
                    seats_booked += seats_reserved
                    fare_amount = Decimal(str(getattr(booking, "fare", 0) or 0))
                    if fare_amount > 0:
                        gross_earnings += fare_amount

            period_key = (ride.departure_time.year, ride.departure_time.month)
            if period_key not in payout_status_by_month:
                payout_status_by_month[period_key] = await crud.check_payout_status(
                    db, driver_id, period_key[0], period_key[1]
                )

            ride_payout_status = payout_status_by_month[period_key]
            if payout_status and ride_payout_status != payout_status:
                continue
            
            writer.writerow([
                str(ride.id),
                ride.departure_time.strftime("%Y-%m-%d %H:%M:%S"),
                ride.start_point_address or "",
                ride.end_point_address or "",
                seats_booked,
                f"{gross_earnings:.2f}",
                ride_payout_status,
            ])
        
        csv_content = output.getvalue()
        output.close()
        
        logger.info(
            f"[generate_earnings_csv] driver_id={driver_id}, "
            f"from_date={from_date}, to_date={to_date}, "
            f"rides={len(rides)}"
        )
        
        return csv_content
        
    except Exception as e:
        logger.error(f"[generate_earnings_csv] Error: {e}", exc_info=True)
        raise


def validate_date_range(from_date: Optional[date], to_date: Optional[date]) -> None:
    """
    Validate date range parameters.
    
    Args:
        from_date: Start date
        to_date: End date
    
    Raises:
        ValueError: If date range is invalid
    """
    if from_date and to_date:
        if from_date > to_date:
            raise ValueError("from_date cannot be after to_date")
        
        # Prevent excessive date ranges (e.g., more than 1 year)
        if (to_date - from_date).days > 365:
            raise ValueError("Date range cannot exceed 365 days")


def validate_payout_status(payout_status: Optional[str]) -> None:
    """
    Validate payout status parameter.
    
    Args:
        payout_status: Payout status value
    
    Raises:
        ValueError: If payout status is invalid
    """
    valid_statuses = ["pending", "paid", "failed"]
    
    if payout_status and payout_status not in valid_statuses:
        raise ValueError(
            f"Invalid payout_status: {payout_status}. "
            f"Must be one of: {', '.join(valid_statuses)}"
        )
