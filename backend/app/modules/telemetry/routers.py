"""
Telemetry API Routers

REST endpoints and WebSocket for telemetry streaming.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.modules.auth.deps import get_current_user, require_admin, require_driver
from app.modules.auth.models import User
from app.modules.telemetry.schemas import (
    TelemetryBatchRequest,
    TelemetryLatestResponse,
    TelemetryReplayResponse
)
from app.modules.telemetry.service import TelemetryService, get_service
from app.modules.telemetry.websocket_handler import handle_telemetry_stream

logger = logging.getLogger(__name__)

router = APIRouter()


async def _is_location_sharing_enabled(db: AsyncSession, user_id: UUID) -> bool:
    """Return True when the user's location sharing preference allows telemetry upload."""
    try:
        result = await db.execute(
            text(
                """
                SELECT COALESCE(share_location_enabled, TRUE) AS share_location_enabled
                FROM user_profiles
                WHERE user_id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
        row = result.first()
        return bool(row[0]) if row else True
    except Exception:
        # Fail open for legacy schemas to avoid blocking active rides.
        return True


@router.websocket("/ws/trip/{ride_id}")
async def websocket_telemetry_endpoint(
    websocket: WebSocket,
    ride_id: UUID,
    token: Optional[str] = Query(None, description="JWT authentication token"),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings)
):
    """
    WebSocket endpoint for real-time telemetry streaming.
    
    **Authentication**: JWT token via query parameter `?token=xxx`
    
    **Message Format** (Client -> Server):
    ```json
    {
        "timestamp": "2025-01-10T12:00:00",
        "lat": 40.7128,
        "lng": -74.0060,
        "speed": 45.5,
        "bearing": 180.0,
        "accuracy": 5.0
    }
    ```
    
    **Response Format** (Server -> Client):
    ```json
    {
        "type": "ack",
        "point_id": "uuid",
        "timestamp": "2025-01-10T12:00:00"
    }
    ```
    
    **Ping/Pong**: Server sends `{"type": "ping"}` every 30 seconds.
                   Client should respond with `{"type": "pong"}`.
    
    Args:
        websocket: WebSocket connection
        ride_id: Ride UUID to stream telemetry for
        token: JWT token for authentication
        db: Database session
        settings: App settings
    """
    await handle_telemetry_stream(
        websocket=websocket,
        ride_id=ride_id,
        db=db,
        token=token,
        secret_key=settings.JWT_SECRET,
        ping_interval=30
    )


@router.post(
    "/telemetry/batch",
    status_code=status.HTTP_201_CREATED,
    summary="Batch Upload Telemetry Points"
)
async def batch_upload_telemetry(
    batch_request: TelemetryBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_driver),
    service: TelemetryService = Depends(get_service)
):
    """
    Batch upload telemetry points for a ride.
    
    **Permissions**: Driver role required. Must be the driver of the ride.
    
    **Constraints**:
    - Maximum 500 points per batch
    - Points must be chronologically ordered
    - Speed must be <= 300 km/h
    
    **Process**:
    1. Bulk insert to database
    2. Publish each point to Redis channel `telemetry:ride:{ride_id}`
    3. Trigger anomaly detection (async)
    
    Args:
        batch_request: Batch request with ride_id and points array
        db: Database session
        current_user: Authenticated user (must be driver)
        service: Telemetry service instance
        
    Returns:
        Success status and inserted count
    """
    # Verify current_user is the driver of the ride
    from sqlalchemy import select
    from app.modules.rides.models import Ride
    ride_check = await db.execute(select(Ride).where(Ride.id == batch_request.ride_id))
    ride_obj = ride_check.scalar_one_or_none()
    if ride_obj and str(ride_obj.driver_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Only the ride driver can upload telemetry")

    if not await _is_location_sharing_enabled(db, current_user.id):
        logger.info(
            "Telemetry upload skipped due to disabled location sharing for user %s ride %s",
            current_user.id,
            batch_request.ride_id,
        )
        return {
            "success": True,
            "ride_id": str(batch_request.ride_id),
            "inserted_count": 0,
            "message": "Location sharing is disabled for this account. Telemetry upload skipped."
        }
    
    logger.info(f"Batch upload request from user {current_user.id} for ride {batch_request.ride_id}: {len(batch_request.points)} points")
    
    result = await service.process_batch(db, batch_request)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Failed to process batch")
        )
    
    return {
        "success": True,
        "ride_id": str(batch_request.ride_id),
        "inserted_count": result["inserted_count"],
        "message": f"Successfully inserted {result['inserted_count']} telemetry points"
    }


@router.get(
    "/telemetry/{ride_id}/latest",
    response_model=TelemetryLatestResponse,
    summary="Get Latest Telemetry Points"
)
async def get_latest_telemetry(
    ride_id: UUID,
    limit: int = Query(25, ge=1, le=100, description="Maximum points to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: TelemetryService = Depends(get_service)
):
    """
    Get the latest telemetry points for a ride.
    
    **Permissions**: Authenticated user (passenger, driver, or admin)
    
    **Default**: Returns last 25 points, ordered by timestamp descending
    
    Args:
        ride_id: Ride UUID
        limit: Maximum points to return (1-100)
        db: Database session
        current_user: Authenticated user
        service: Telemetry service instance
        
    Returns:
        TelemetryLatestResponse with samples array
    """
    # Verify user has access to this ride (is passenger, driver, or admin)
    from sqlalchemy import select
    from app.modules.rides.models import Ride, RideBooking
    from app.models.enums import UserRole
    if current_user.role != UserRole.ADMIN:
        ride_check = await db.execute(select(Ride).where(Ride.id == ride_id))
        ride_obj = ride_check.scalar_one_or_none()
        if ride_obj and str(ride_obj.driver_id) != str(current_user.id):
            booking_check = await db.execute(
                select(RideBooking).where(RideBooking.ride_id == ride_id, RideBooking.passenger_id == current_user.id)
            )
            if not booking_check.scalar_one_or_none():
                raise HTTPException(status_code=403, detail="You can only view telemetry for your own rides")
    
    response = await service.get_latest_telemetry(db, ride_id, limit)
    
    logger.info(f"User {current_user.id} retrieved {response.count} latest points for ride {ride_id}")
    
    return response


@router.get(
    "/telemetry/replay/{ride_id}",
    response_model=TelemetryReplayResponse,
    summary="Generate Trip Replay (Admin Only)"
)
async def get_trip_replay(
    ride_id: UUID,
    simplify: bool = Query(True, description="Simplify polyline for reduced data"),
    db: AsyncSession = Depends(get_db),
    admin_user: User = Depends(require_admin),
    service: TelemetryService = Depends(get_service)
):
    """
    Generate complete trip replay with encoded polyline and statistics.
    
    **Permissions**: Admin role required
    
    **Output**:
    - Encoded polyline (Google Maps format)
    - All timestamped telemetry samples
    - Duration, distance, speed statistics
    - Start/end timestamps
    
    **Performance**: <300ms for trips with 1000+ points
    
    Args:
        ride_id: Ride UUID
        simplify: Whether to simplify polyline (reduces size)
        db: Database session
        admin_user: Authenticated admin user
        service: Telemetry service instance
        
    Returns:
        TelemetryReplayResponse with full trip data
    """
    logger.info(f"Admin {admin_user.id} requesting replay for ride {ride_id}")
    
    replay = await service.generate_replay(db, ride_id, simplify=simplify)
    
    if replay.sample_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No telemetry data found for ride {ride_id}"
        )
    
    logger.info(f"✅ Generated replay for ride {ride_id}: {replay.sample_count} points, {replay.distance_km} km")
    
    return replay


@router.get(
    "/telemetry/{ride_id}/stats",
    summary="Get Telemetry Statistics"
)
async def get_telemetry_stats(
    ride_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get basic statistics about telemetry data for a ride.
    
    **Permissions**: Authenticated user
    
    Args:
        ride_id: Ride UUID
        db: Database session
        current_user: Authenticated user
        
    Returns:
        Statistics dict with total_points count
    """
    from app.modules.telemetry import crud
    
    total_points = await crud.get_telemetry_count(db, ride_id)
    
    return {
        "ride_id": str(ride_id),
        "total_points": total_points,
        "has_data": total_points > 0
    }
