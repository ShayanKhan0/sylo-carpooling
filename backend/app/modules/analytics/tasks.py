"""
Prompt 11D-1 — Analytics Tasks

Daily aggregation job (manual/cron compatible).

Author: Smart Carpooling Backend Team
Date: January 23, 2026
"""

from datetime import date

from app.db.session import AsyncSessionLocal
from app.modules.analytics import crud


async def aggregate_day(target_date: date) -> None:
    """
    Aggregate metrics for a single day.

    Idempotent: updates existing row if present, otherwise inserts.
    Uses a DB transaction (managed by session context).
    """
    async with AsyncSessionLocal() as db:
        (
            rides_count,
            completed_rides,
            cancelled_rides,
            gross_revenue,
            commission_revenue,
            active_drivers,
            verification_failures
        ) = await crud.compute_daily_metrics(db, target_date)

        await crud.upsert_daily_aggregate(
            db=db,
            target_date=target_date,
            rides_count=rides_count,
            completed_rides=completed_rides,
            cancelled_rides=cancelled_rides,
            gross_revenue=gross_revenue,
            commission_revenue=commission_revenue,
            active_drivers=active_drivers,
            verification_failures=verification_failures
        )

        await db.commit()
