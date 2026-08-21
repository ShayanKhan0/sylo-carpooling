"""
Prompt 11D-2 — Analytics API Router

Admin-only, read-only analytics endpoints backed by daily_aggregates.
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.security.admin_auth import require_admin
from app.modules.analytics import schemas, service

router = APIRouter(prefix="/analytics", tags=["Analytics (Prompt 11D)"])


@router.get(
	"/overview",
	response_model=schemas.OverviewResponse,
	summary="Get admin analytics overview",
	description="""
	KPI summary derived **only** from daily_aggregates:
	- **today**: rides_count, gross_revenue, commission_revenue, active_drivers
	- **last_7_days**: total_rides, total_revenue, total_commission
	- **lifetime**: total_rides, total_revenue, total_commission
	"""
)
async def get_overview(
	admin=Depends(require_admin),
	db: AsyncSession = Depends(get_db)
):
	return await service.get_overview(db)


@router.get(
	"/rides/day",
	response_model=List[schemas.DailyRideCount],
	summary="Get daily ride counts",
	description="""
	Returns daily ride counts from daily_aggregates.
	Ordered by date ascending.
	"""
)
async def get_rides_by_day(
	admin=Depends(require_admin),
	db: AsyncSession = Depends(get_db)
):
	return await service.get_rides_by_day(db)


@router.get(
	"/revenue/day",
	response_model=List[schemas.DailyRevenue],
	summary="Get daily revenue",
	description="""
	Returns daily gross and commission revenue from daily_aggregates.
	Ordered by date ascending.
	"""
)
async def get_revenue_by_day(
	admin=Depends(require_admin),
	db: AsyncSession = Depends(get_db)
):
	return await service.get_revenue_by_day(db)


@router.get(
	"/verification_failures",
	response_model=List[schemas.DailyVerificationFailures],
	summary="Get daily verification failures",
	description="""
	Returns daily verification failure counts from daily_aggregates.
	"""
)
async def get_verification_failures(
	admin=Depends(require_admin),
	db: AsyncSession = Depends(get_db)
):
	return await service.get_verification_failures(db)


@router.get(
	"/active_drivers_by_region",
	response_model=List[schemas.ActiveDriversByRegion],
	summary="Get active drivers by region",
	description="""
	Groups drivers by region/city derived from last known coordinates.
	Sorted by driver count (desc).
	"""
)
async def get_active_drivers_by_region(
	admin=Depends(require_admin),
	db: AsyncSession = Depends(get_db)
):
	return await service.get_active_drivers_by_region(db)
