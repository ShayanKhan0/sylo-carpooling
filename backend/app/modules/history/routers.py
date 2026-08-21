"""
History API Router (Prompt 11B - Trip History Module)

Endpoints for viewing ride history and exporting to CSV.
Earnings routes removed — they live in the standalone earnings module.

Endpoints:
- GET /api/v1/history/rides - List rides with filters
- GET /api/v1/history/rides/{ride_id} - Detailed ride view
- GET /api/v1/history/export/csv - CSV export

Author: Smart Carpooling Backend Team
Date: December 19, 2025
Prompt: 11B - Trip History Module
"""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.history.service import HistoryService
from app.modules.history import schemas
from app.modules.history.utils import generate_ride_history_csv
from app.core.exceptions import NotFoundException, ForbiddenException

router = APIRouter(tags=["History"])


@router.get(
    "/history/rides",
    response_model=schemas.RideHistoryResponse,
    summary="Get ride history",
)
async def get_ride_history(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    role: Optional[str] = Query(None, description="View as 'passenger' or 'driver'"),
    status: Optional[str] = Query(None, description="Filter by status"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get ride history for current user."""
    as_driver = (role == "driver") if role else False
    service = HistoryService(db)
    return await service.get_ride_history(
        user_id=current_user.id,
        as_driver=as_driver,
        page=page,
        page_size=limit,
        status_filter=status,
        from_date=from_date,
        to_date=to_date,
    )


@router.get(
    "/history/rides/{ride_id}",
    response_model=schemas.RideDetailedResponse,
    summary="Get detailed ride history",
)
async def get_ride_details(
    ride_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed ride information."""
    try:
        service = HistoryService(db)
        return await service.get_ride_details(ride_id=ride_id, user_id=current_user.id)
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get(
    "/history/export/csv",
    summary="Export ride history to CSV",
)
async def export_ride_history_csv_endpoint(
    role: Optional[str] = Query(None, description="Export as 'passenger' or 'driver'"),
    status: Optional[str] = Query(None, description="Filter by status"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export ride history to CSV."""
    as_driver = (role == "driver") if role else False
    service = HistoryService(db)

    history_data = await service.get_ride_history(
        user_id=current_user.id,
        as_driver=as_driver,
        page=1,
        page_size=10000,
        status_filter=status,
        from_date=from_date,
        to_date=to_date,
    )

    csv_content = generate_ride_history_csv(history_data["rides"])
    role_str = role or ("driver" if as_driver else "passenger")
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=ride_history_{role_str}_{current_user.id}.csv"
        },
    )
