"""
Telemetry Service Layer

Business logic orchestration for telemetry processing.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.telemetry import crud
from app.modules.telemetry.schemas import (
    TelemetryBatchRequest,
    TelemetryLatestResponse,
    TelemetryPoint,
    TelemetryReplayResponse,
    AnomalyAlert
)
from app.modules.telemetry.publisher import TelemetryPublisher, get_publisher
from app.modules.telemetry.anomaly import analyze_telemetry_point, enqueue_safety_ai_task
from app.modules.telemetry.replay import build_replay

logger = logging.getLogger(__name__)


class TelemetryService:
    """
    Service layer for telemetry operations.
    
    Orchestrates DB writes, publishing, and anomaly detection.
    """
    
    def __init__(
        self,
        publisher: Optional[TelemetryPublisher] = None,
        **kwargs,
    ):
        """
        Initialize service.
        
        Args:
            publisher: Telemetry publisher instance
        """
        self.publisher = publisher or get_publisher()
    
    async def process_telemetry_point(
        self,
        db: AsyncSession,
        ride_id: UUID,
        point: TelemetryPoint,
        polyline_coords: Optional[List[Tuple[float, float]]] = None,
        pickup_coords: Optional[Tuple[float, float]] = None,
        dropoff_coords: Optional[Tuple[float, float]] = None,
        max_deviation_meters: float = 25.0,
        max_stop_minutes: float = 3.0,
        max_speed_kmh: float = 120.0
    ) -> Dict:
        """
        Process single telemetry point.
        
        Performs:
        1. DB insertion
        2. Publishing
        3. Anomaly detection
        4. Background safety AI task
        
        Args:
            db: Database session
            ride_id: Ride UUID
            point: Telemetry point
            polyline_coords: Expected route for deviation detection
            pickup_coords: Pickup location
            dropoff_coords: Dropoff location
            max_deviation_meters: Lateral deviation threshold
            max_stop_minutes: Stop duration threshold
            max_speed_kmh: Speed limit
            
        Returns:
            Status dict with success, anomalies
        """
        try:
            # 1. Insert to DB
            db_point = await crud.insert_telemetry_point(
                db,
                ride_id=ride_id,
                timestamp=point.timestamp,
                latitude=point.lat,
                longitude=point.lng,
                speed=point.speed,
                bearing=point.bearing,
            )
            
            # 2. Publish telemetry
            point_data = {
                "timestamp": point.timestamp.isoformat(),
                "lat": point.lat,
                "lng": point.lng,
                "speed": point.speed,
                "bearing": point.bearing,
                "accuracy": point.accuracy
            }
            
            await self.publisher.publish_telemetry_point(ride_id, point_data)
            
            # 3. Anomaly detection
            # Get recent points for stop detection (last 5 minutes)
            recent_cutoff = datetime.utcnow() - timedelta(minutes=5)
            recent_points_db = await crud.get_points_in_time_range(
                db, ride_id, recent_cutoff, datetime.utcnow()
            )
            
            recent_points = [
                {
                    "timestamp": p.timestamp,
                    "lat": p.latitude,
                    "lng": p.longitude,
                    "speed": p.speed
                }
                for p in recent_points_db
            ]
            
            anomalies = await analyze_telemetry_point(
                ride_id=ride_id,
                lat=point.lat,
                lng=point.lng,
                speed=point.speed,
                timestamp=point.timestamp,
                polyline_coords=polyline_coords,
                recent_points=recent_points,
                pickup_coords=pickup_coords,
                dropoff_coords=dropoff_coords,
                max_deviation_meters=max_deviation_meters,
                max_stop_minutes=max_stop_minutes,
                max_speed_kmh=max_speed_kmh
            )
            
            # 4. Publish anomaly alerts
            for anomaly in anomalies:
                await self.publisher.publish_anomaly_alert(
                    ride_id,
                    anomaly.dict()
                )
            
            # 5. Enqueue background task if anomalies detected
            if anomalies:
                await enqueue_safety_ai_task(ride_id, anomalies)
            
            logger.debug(f"Processed telemetry point for ride {ride_id}: {len(anomalies)} anomalies")
            
            return {
                "success": True,
                "point_id": str(db_point.id),
                "anomalies": [a.dict() for a in anomalies]
            }
            
        except Exception as e:
            logger.error(f"Failed to process telemetry point: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def process_batch(
        self,
        db: AsyncSession,
        batch_request: TelemetryBatchRequest
    ) -> Dict:
        """
        Process batch telemetry upload.
        
        Args:
            db: Database session
            batch_request: Batch request with ride_id and points
            
        Returns:
            Status dict with success, inserted_count
        """
        try:
            ride_id = batch_request.ride_id
            points = batch_request.points
            
            # 1. Bulk insert to DB
            db_points = await crud.bulk_insert_telemetry_points(
                db,
                ride_id=ride_id,
                points=[
                    {
                        "timestamp": p.timestamp,
                        "lat": p.lat,
                        "lng": p.lng,
                        "speed": p.speed,
                        "bearing": p.bearing,
                        "accuracy": p.accuracy
                    }
                    for p in points
                ]
            )
            
            # 2. Publish each point (async fire-and-forget)
            for point in points:
                point_data = {
                    "timestamp": point.timestamp.isoformat(),
                    "lat": point.lat,
                    "lng": point.lng,
                    "speed": point.speed,
                    "bearing": point.bearing,
                    "accuracy": point.accuracy
                }
                await self.publisher.publish_telemetry_point(ride_id, point_data)
            
            logger.info(f"✅ Processed batch for ride {ride_id}: {db_points} points")
            
            return {
                "success": True,
                "inserted_count": db_points
            }
            
        except Exception as e:
            logger.error(f"Failed to process batch: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_latest_telemetry(
        self,
        db: AsyncSession,
        ride_id: UUID,
        limit: int = 25
    ) -> TelemetryLatestResponse:
        """
        Get latest telemetry points for a ride.
        
        Args:
            db: Database session
            ride_id: Ride UUID
            limit: Maximum points to return
            
        Returns:
            TelemetryLatestResponse
        """
        points = await crud.get_latest_points(db, ride_id, limit)
        
        samples = [
            {
                "timestamp": p.timestamp.isoformat(),
                "lat": p.latitude,
                "lng": p.longitude,
                "speed": p.speed,
                "bearing": p.bearing,
                "accuracy": getattr(p, "accuracy", None),
            }
            for p in points
        ]
        
        return TelemetryLatestResponse(
            ride_id=ride_id,
            points=samples,
            samples=samples,
            count=len(samples)
        )
    
    async def generate_replay(
        self,
        db: AsyncSession,
        ride_id: UUID,
        simplify: bool = True
    ) -> TelemetryReplayResponse:
        """
        Generate complete trip replay.
        
        Args:
            db: Database session
            ride_id: Ride UUID
            simplify: Whether to simplify polyline
            
        Returns:
            TelemetryReplayResponse with encoded route
        """
        # Get all points for ride
        points = await crud.get_all_points_for_ride(db, ride_id)
        
        # Convert to dict format
        point_dicts = [
            {
                "timestamp": p.timestamp,
                "lat": p.latitude,
                "lng": p.longitude,
                "speed": p.speed,
                "bearing": p.bearing,
                "accuracy": getattr(p, "accuracy", None),
            }
            for p in points
        ]
        
        # Build replay
        replay = await build_replay(ride_id, point_dicts, simplify=simplify)
        
        logger.info(f"✅ Generated replay for ride {ride_id}: {replay.sample_count} points")
        
        return replay


# Global service instance
_service_instance: Optional[TelemetryService] = None


def get_service() -> TelemetryService:
    """Get global service instance"""
    global _service_instance
    if _service_instance is None:
        _service_instance = TelemetryService()
    return _service_instance


def set_service(service: TelemetryService):
    """Set global service instance"""
    global _service_instance
    _service_instance = service
