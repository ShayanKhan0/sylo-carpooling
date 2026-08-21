"""
Prompt 11D-2 — Analytics Service Layer

Read-only admin analytics backed by daily_aggregates.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import List

from sqlalchemy import select, func, case, literal, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics import crud, schemas
from app.models.driver import Driver


async def get_rides_by_day(db: AsyncSession) -> List[schemas.DailyRideCount]:
	aggregates = await crud.get_all_daily_aggregates(db)
	return [
		schemas.DailyRideCount(date=a.date, rides_count=a.rides_count)
		for a in aggregates
	]


async def get_revenue_by_day(db: AsyncSession) -> List[schemas.DailyRevenue]:
	aggregates = await crud.get_all_daily_aggregates(db)
	return [
		schemas.DailyRevenue(
			date=a.date,
			gross_revenue=a.gross_revenue,
			commission_revenue=a.commission_revenue
		)
		for a in aggregates
	]


async def get_verification_failures(db: AsyncSession) -> List[schemas.DailyVerificationFailures]:
	aggregates = await crud.get_all_daily_aggregates(db)
	return [
		schemas.DailyVerificationFailures(
			date=a.date,
			verification_failures=a.verification_failures
		)
		for a in aggregates
	]


async def get_active_drivers_by_region(db: AsyncSession) -> List[schemas.ActiveDriversByRegion]:
	"""
	Group drivers by derived region using last known coordinates.

	Note: Region label is derived by rounding lat/lng to 2 decimals to avoid heavy joins.
	"""
	region_label = case(
		(
			and_(
				Driver.location_last_lat.isnot(None),
				Driver.location_last_lng.isnot(None)
			),
			func.concat(
				literal("lat="),
				func.round(Driver.location_last_lat, 2),
				literal(",lng="),
				func.round(Driver.location_last_lng, 2)
			)
		),
		else_=literal("Unknown")
	)

	result = await db.execute(
		select(
			region_label.label("region"),
			func.count(Driver.user_id).label("driver_count")
		)
		.group_by(region_label)
		.order_by(func.count(Driver.user_id).desc())
	)

	return [
		schemas.ActiveDriversByRegion(
			region=row.region,
			driver_count=int(row.driver_count or 0)
		)
		for row in result.all()
	]


def _sum_decimal(values) -> Decimal:
	total = Decimal("0.00")
	for value in values:
		total += value or Decimal("0.00")
	return total


async def get_overview(db: AsyncSession) -> schemas.OverviewResponse:
	today = date.today()
	today_row = await crud.get_daily_aggregate(db, today)

	today_summary = schemas.OverviewToday(
		rides_count=int(today_row.rides_count) if today_row else 0,
		gross_revenue=today_row.gross_revenue if today_row else Decimal("0.00"),
		commission_revenue=today_row.commission_revenue if today_row else Decimal("0.00"),
		active_drivers=int(today_row.active_drivers) if today_row else 0
	)

	last_7_rows = await crud.get_daily_aggregates_range(
		db,
		today - timedelta(days=6),
		today
	)
	last_7_summary = schemas.OverviewLast7Days(
		total_rides=sum(int(r.rides_count) for r in last_7_rows),
		total_revenue=_sum_decimal(r.gross_revenue for r in last_7_rows),
		total_commission=_sum_decimal(r.commission_revenue for r in last_7_rows)
	)

	(
		lifetime_rides,
		_completed_rides,
		_cancelled_rides,
		lifetime_revenue,
		lifetime_commission,
		_active_drivers,
		_verification_failures
	) = await crud.get_lifetime_totals(db)

	lifetime_summary = schemas.OverviewLifetime(
		total_rides=lifetime_rides,
		total_revenue=lifetime_revenue,
		total_commission=lifetime_commission
	)

	return schemas.OverviewResponse(
		today=today_summary,
		last_7_days=last_7_summary,
		lifetime=lifetime_summary
	)
