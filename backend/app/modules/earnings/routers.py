"""
Prompt 11C — Earnings Routers

API endpoints for driver earnings and financial reports.

Author: Smart Carpooling Backend Team
Date: December 20, 2025
"""

import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import require_driver
from app.modules.auth.models import User
from app.modules.earnings import service, schemas

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/monthly",
    response_model=schemas.MonthlyEarningsResponse,
    summary="Get monthly earnings summary",
    description="""
    Get earnings summary for a specific month.
    
    **Driver-only endpoint** - Returns 403 for non-drivers.
    
    Includes:
    - Total rides completed
    - Gross earnings (total fare)
    - Platform commission deducted
    - Net earnings (after commission)
    - Payout status (pending/paid/failed)
    
    Default: Returns current month if year/month not specified.
    """
)
async def get_monthly_earnings(
    year: Optional[int] = Query(None, description="Year (e.g., 2025)", ge=2020, le=2100),
    month: Optional[int] = Query(None, description="Month (1-12)", ge=1, le=12),
    current_user: User = Depends(require_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Get monthly earnings summary for driver.
    
    **Access:** Drivers only (403 for passengers/admins)
    
    **Parameters:**
    - `year`: Year (defaults to current year)
    - `month`: Month 1-12 (defaults to current month)
    
    **Returns:**
    - Monthly earnings breakdown with payout status
    """
    try:
        # Default to current month if not specified
        if year is None or month is None:
            now = datetime.utcnow()
            year = year or now.year
            month = month or now.month
        
        result = await service.get_monthly_earnings(
            db, current_user.id, year, month
        )
        
        logger.info(
            f"[get_monthly_earnings] user_id={current_user.id}, "
            f"year={year}, month={month}"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"[get_monthly_earnings] Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve monthly earnings"
        )


@router.get(
    "/lifetime",
    response_model=schemas.LifetimeEarningsResponse,
    summary="Get lifetime earnings summary",
    description="""
    Get all-time earnings statistics for driver.
    
    **Driver-only endpoint** - Returns 403 for non-drivers.
    
    Includes:
    - Total rides completed
    - Lifetime gross/net earnings
    - Total withdrawals
    - Current wallet balance
    
    Useful for:
    - Driver dashboard overview
    - Financial performance tracking
    - Wallet reconciliation
    """
)
async def get_lifetime_earnings(
    current_user: User = Depends(require_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Get lifetime earnings summary for driver.
    
    **Access:** Drivers only (403 for passengers/admins)
    
    **Returns:**
    - All-time earnings statistics
    - Wallet balance information
    - Total withdrawals
    """
    try:
        result = await service.get_lifetime_earnings(db, current_user.id)
        
        logger.info(f"[get_lifetime_earnings] user_id={current_user.id}")
        
        return result
        
    except Exception as e:
        logger.error(f"[get_lifetime_earnings] Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve lifetime earnings"
        )


@router.get(
    "/chart",
    response_model=schemas.EarningsChartResponse,
    summary="Get daily earnings chart data",
    description="""
    Get daily earnings breakdown for the last 30 days.
    
    **Driver-only endpoint** - Returns 403 for non-drivers.
    
    Returns:
    - Daily earnings for each day
    - Ride count per day
    - Period totals
    
    Useful for:
    - Visualizing earnings trends
    - Performance tracking charts
    - Identifying peak earning days
    """
)
async def get_earnings_chart(
    days: int = Query(30, description="Number of days to include", ge=1, le=90),
    current_user: User = Depends(require_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Get daily earnings chart data.
    
    **Access:** Drivers only (403 for passengers/admins)
    
    **Parameters:**
    - `days`: Number of days to include (1-90, default 30)
    
    **Returns:**
    - Daily breakdown of earnings and rides
    - Period totals for summary
    """
    try:
        result = await service.get_earnings_chart(db, current_user.id, days)
        
        logger.info(
            f"[get_earnings_chart] user_id={current_user.id}, days={days}"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"[get_earnings_chart] Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve earnings chart"
        )


@router.get(
    "/export/csv",
    summary="Export earnings as CSV",
    description="""
    Export detailed ride earnings to CSV file.
    
    **Driver-only endpoint** - Returns 403 for non-drivers.
    
    CSV Columns:
    - Ride ID
    - Date
    - From/To Location
    - Seats Booked
    - Base Fare
    - Commission
    - Net Earning
    - Payout Status
    
    Supports filters:
    - Date range (from_date, to_date)
    - Payout status
    
    Useful for:
    - Tax reporting
    - Financial record keeping
    - Accounting integration
    """,
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "CSV file download"
        }
    }
)
async def export_earnings_csv(
    from_date: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    start_date: Optional[date] = Query(None, include_in_schema=False),
    end_date: Optional[date] = Query(None, include_in_schema=False),
    payout_status: Optional[str] = Query(None, description="Filter by status: pending, paid, failed"),
    current_user: User = Depends(require_driver),
    db: AsyncSession = Depends(get_db)
):
    """
    Export earnings as CSV file.
    
    **Access:** Drivers only (403 for passengers/admins)
    
    **Parameters:**
    - `from_date`: Start date (YYYY-MM-DD)
    - `to_date`: End date (YYYY-MM-DD)
    - `payout_status`: Filter by status (pending/paid/failed)
    
    **Returns:**
    - CSV file with detailed ride earnings
    """
    try:
        # Backward compatibility for older clients.
        from_date = from_date or start_date
        to_date = to_date or end_date

        # Validate filters
        service.validate_date_range(from_date, to_date)
        service.validate_payout_status(payout_status)
        
        # Generate CSV
        csv_content = await service.generate_earnings_csv(
            db, current_user.id, from_date, to_date, payout_status
        )
        
        # Create filename with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"earnings_driver_{current_user.id}_{timestamp}.csv"
        
        logger.info(
            f"[export_earnings_csv] user_id={current_user.id}, "
            f"from_date={from_date}, to_date={to_date}, "
            f"payout_status={payout_status}"
        )
        
        # Return CSV as streaming response
        return StreamingResponse(
            iter([csv_content]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except ValueError as e:
        logger.warning(f"[export_earnings_csv] Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"[export_earnings_csv] Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export earnings CSV"
        )
