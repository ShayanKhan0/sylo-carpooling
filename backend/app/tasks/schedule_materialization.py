"""
Module: Recurring Schedule Materialization (Prompt 5)
Purpose: Async helper to convert recurring schedules into actual rides without Celery.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: December 8, 2025
Notes: Runs daily to materialize scheduled rides for the next 7 days
"""

import asyncio
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.modules.rides import service_v2


async def materialize_recurring_schedules_task():
    """
    Celery task to materialize recurring schedules into actual rides.
    
    Runs daily (recommended: 00:00 UTC) to create rides for the next 7 days.
    
    Schedule in celeryconfig.py:
        beat_schedule = {
            'materialize-schedules-daily': {
                'task': 'materialize_recurring_schedules',
                'schedule': crontab(hour=0, minute=0),  # Daily at midnight
            },
        }
    
    Returns:
        Summary of materialization results
    """
    # Run async function in event loop
    return await _materialize_schedules_async()


async def _materialize_schedules_async():
    """
    Async implementation of schedule materialization.
    
    Materializes schedules for next 7 days to ensure advance availability.
    """
    # Create async engine and session
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True
    )
    
    async_session_maker = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    results = {
        "total_days_processed": 0,
        "total_rides_created": 0,
        "days_detail": []
    }
    
    try:
        async with async_session_maker() as session:
            # Materialize for next 7 days
            for days_ahead in range(7):
                target_date = date.today() + timedelta(days=days_ahead)
                
                # Materialize schedules for this date
                result = await service_v2.materialize_scheduled_rides_service(
                    db=session,
                    target_date=target_date
                )
                
                results["total_days_processed"] += 1
                results["total_rides_created"] += result["rides_created"]
                results["days_detail"].append(result)
        
        print(f"[SCHEDULE MATERIALIZATION] Success!")
        print(f"  Days processed: {results['total_days_processed']}")
        print(f"  Total rides created: {results['total_rides_created']}")
        
    except Exception as e:
        print(f"[SCHEDULE MATERIALIZATION] Error: {str(e)}")
        results["error"] = str(e)
    
    finally:
        await engine.dispose()
    
    return results


async def materialize_specific_date_task(target_date_str: str):
    """
    Materialize schedules for a specific date (manual trigger).
    
    Args:
        target_date_str: Date string in format "YYYY-MM-DD"
    
    Returns:
        Materialization result for the date
    """
    target_date = date.fromisoformat(target_date_str)
    return await _materialize_specific_date_async(target_date)


async def _materialize_specific_date_async(target_date: date):
    """
    Async implementation for specific date materialization.
    
    Args:
        target_date: Date to materialize
    
    Returns:
        Materialization result
    """
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True
    )
    
    async_session_maker = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    try:
        async with async_session_maker() as session:
            result = await service_v2.materialize_scheduled_rides_service(
                db=session,
                target_date=target_date
            )
        
        print(f"[SCHEDULE MATERIALIZATION] Date: {target_date}")
        print(f"  Rides created: {result['rides_created']}")
        print(f"  Errors: {len(result['errors'])}")
        
        return result
        
    except Exception as e:
        print(f"[SCHEDULE MATERIALIZATION] Error: {str(e)}")
        return {"error": str(e)}
    
    finally:
        await engine.dispose()


# ============================================
# BACKGROUND SCHEDULER CONFIGURATION
# ============================================

"""
The materialization task is registered in app/core/background.py
and runs daily at midnight UTC via the asyncio-based scheduler.

To trigger manually via admin API:

@router.post("/admin/materialize-schedules/{target_date}")
async def trigger_materialization(
    target_date: date,
    current_user: User = Depends(require_admin)
):
    from app.tasks.schedule_materialization import materialize_specific_date_task
    result = await materialize_specific_date_task(str(target_date))
    return {
        "target_date": str(target_date),
        "status": "completed",
        "result": result
    }
"""
