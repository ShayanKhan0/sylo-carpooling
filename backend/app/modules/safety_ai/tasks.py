"""
Background Tasks for Safety AI

Async tasks (replacing Celery) for:
- Polyline computation (Google Directions API)
- Telemetry anomaly analysis
- Escalation timeout monitoring

These functions run via FastAPI BackgroundTasks or asyncio.create_task().
"""

import logging
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.ride import Ride
from app.modules.safety_ai.polyline_engine import get_polyline_engine
from app.modules.safety_ai.detector import get_anomaly_detector
from app.modules.safety_ai.escalation import get_escalation_manager

logger = logging.getLogger(__name__)


async def compute_ride_polylines_task(ride_id: str) -> Dict:
    """
    Compute main and alternate polylines for a ride using Google Directions API.

    Args:
        ride_id: Ride UUID as string

    Returns:
        Dict with status and polyline data
    """
    try:
        ride_uuid = UUID(ride_id)
        polyline_engine = get_polyline_engine()

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Ride).where(Ride.id == ride_uuid)
            )
            ride = result.scalar_one_or_none()

            if not ride:
                logger.error(f"Ride {ride_id} not found")
                return {"status": "error", "message": "Ride not found"}

            pickup_lat = ride.pickup_lat
            pickup_lng = ride.pickup_lng
            dropoff_lat = ride.dropoff_lat
            dropoff_lng = ride.dropoff_lng

            if not all([pickup_lat, pickup_lng, dropoff_lat, dropoff_lng]):
                logger.error(f"Ride {ride_id} missing coordinates")
                return {"status": "error", "message": "Missing coordinates"}

            result = await polyline_engine.compute_and_store_polylines(
                ride_id=ride_uuid,
                pickup_lat=pickup_lat,
                pickup_lng=pickup_lng,
                dropoff_lat=dropoff_lat,
                dropoff_lng=dropoff_lng,
                db=db
            )

            logger.info(f"Polylines computed for ride {ride_id}: {result['alternates_count']} alternates")
            return result

    except Exception as e:
        logger.error(f"Failed to compute polylines for ride {ride_id}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def analyze_telemetry_task(ride_id: str, point_dict: Dict) -> Dict:
    """
    Analyze telemetry point for anomalies and trigger escalation if needed.

    Args:
        ride_id: Ride UUID as string
        point_dict: Telemetry point data

    Returns:
        Dict with analysis results
    """
    try:
        ride_uuid = UUID(ride_id)
        detector = get_anomaly_detector()
        escalation_mgr = get_escalation_manager()

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Ride).where(Ride.id == ride_uuid)
            )
            ride = result.scalar_one_or_none()

            if not ride:
                logger.error(f"Ride {ride_id} not found")
                return {"status": "error", "message": "Ride not found"}

            polyline_coords = None
            if ride.polyline_main:
                from app.modules.telemetry.anomaly import decode_polyline
                polyline_coords = decode_polyline(ride.polyline_main)

            from app.modules.telemetry.crud import get_recent_points
            recent_points = await get_recent_points(db, ride_uuid, limit=20)

            recent_dicts = [
                {
                    "lat": p.lat,
                    "lng": p.lng,
                    "speed": p.speed,
                    "bearing": p.bearing,
                    "timestamp": p.timestamp
                }
                for p in recent_points
            ]

            anomalies = detector.analyze_point(
                ride_id=ride_uuid,
                point=point_dict,
                polyline_coords=polyline_coords,
                recent_points=recent_dicts,
                pickup_coords=(ride.pickup_lat, ride.pickup_lng),
                dropoff_coords=(ride.dropoff_lat, ride.dropoff_lng)
            )

            escalation_results = []
            for anomaly in anomalies:
                alert = await escalation_mgr.handle_anomaly(
                    ride_id=ride_uuid,
                    anomaly=anomaly,
                    db=db,
                    rider_id=ride.rider_id,
                    driver_id=ride.driver_id
                )
                escalation_results.append(alert.to_dict())

            return {
                "status": "success",
                "anomalies_detected": len(anomalies),
                "anomalies": [a.to_dict() for a in anomalies],
                "escalations": escalation_results
            }

    except Exception as e:
        logger.error(f"Failed to analyze telemetry for ride {ride_id}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def check_escalation_timeouts_task() -> Dict:
    """
    Periodic task to check for escalation timeouts and auto-escalate.

    Should be scheduled to run every 30 seconds via background scheduler.

    Returns:
        Dict with check results
    """
    try:
        escalation_mgr = get_escalation_manager()

        async with AsyncSessionLocal() as db:
            await escalation_mgr.check_timeouts(db)

        active_count = len(escalation_mgr.active_alerts)
        logger.info(f"Escalation timeout check complete. Active alerts: {active_count}")

        return {
            "status": "success",
            "active_alerts": active_count
        }

    except Exception as e:
        logger.error(f"Failed to check escalation timeouts: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def train_ml_detector_task(training_data_path: Optional[str] = None) -> Dict:
    """
    Train ML detector with new data.

    Args:
        training_data_path: Optional path to training CSV file

    Returns:
        Dict with training results
    """
    try:
        detector = get_anomaly_detector()

        if not detector.ml_detector:
            return {"status": "error", "message": "ML not enabled"}

        if training_data_path:
            import pandas as pd
            training_df = pd.read_csv(training_data_path)
            training_data = training_df.to_dict('records')
        else:
            from app.modules.safety_ai.ml_adapter import generate_training_data
            training_data = generate_training_data(2000)

        detector.ml_detector.fit(training_data)

        logger.info(f"ML detector trained with {len(training_data)} samples")

        return {
            "status": "success",
            "samples": len(training_data),
            "model_type": type(detector.ml_detector).__name__
        }

    except Exception as e:
        logger.error(f"Failed to train ML detector: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
