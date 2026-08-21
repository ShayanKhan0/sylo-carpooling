"""
Safety AI Service Layer

This module provides business logic for telemetry ingestion, AI-powered safety analysis,
incident management, and emergency SOS handling.

Author: Smart Carpooling Backend Team
"""

from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import HTTPException, status

from app.modules.safety_ai import crud
from app.modules.safety_ai.schemas import (
    TelemetryInput,
    TelemetryResponse,
    IncidentResponse,
    AIAnalysisResponse,
    SOSRequest,
    SOSResponse,
    SafetySummaryResponse
)
from app.modules.safety_ai.models import IncidentTypeEnum, SeverityEnum
from app.modules.safety_ai.ai_engine import (
    analyze_telemetry,
    calculate_safety_score,
    analyze_sos_signal,
    generate_safety_report
)
from app.modules.rides.crud import get_ride_by_id

import logging

logger = logging.getLogger(__name__)


def _role_text(role: Any) -> str:
    if role is None:
        return "unknown"
    if hasattr(role, "value"):
        return str(role.value).strip().lower()
    return str(role).strip().lower()


async def _infer_active_ride_id_for_user(db: AsyncSession, current_user: Any) -> Optional[UUID]:
    role = _role_text(getattr(current_user, "role", None))
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        return None

    if role == "driver":
        row = (
            await db.execute(
                text(
                    """
                    SELECT id
                    FROM rides
                    WHERE driver_id = :user_id
                      AND LOWER(CAST(status AS TEXT)) = 'in_progress'
                    ORDER BY departure_time DESC
                    LIMIT 1
                    """
                ),
                {"user_id": user_id},
            )
        ).mappings().first()
        return row["id"] if row else None

    # Passenger/default branch: only treat as active when ride is in_progress.
    row = (
        await db.execute(
            text(
                """
                SELECT r.id
                FROM ride_bookings rb
                JOIN rides r ON r.id = rb.ride_id
                WHERE rb.passenger_id = :user_id
                  AND LOWER(CAST(r.status AS TEXT)) = 'in_progress'
                  AND LOWER(CAST(rb.status AS TEXT)) NOT IN ('cancelled', 'completed')
                ORDER BY r.departure_time DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().first()
    return row["id"] if row else None


async def _is_passenger_active_on_ride(
    db: AsyncSession,
    *,
    passenger_id: UUID,
    ride_id: UUID,
) -> bool:
    row = (
        await db.execute(
            text(
                """
                SELECT rb.id
                FROM ride_bookings rb
                JOIN rides r ON r.id = rb.ride_id
                WHERE rb.passenger_id = :passenger_id
                  AND rb.ride_id = :ride_id
                  AND LOWER(CAST(r.status AS TEXT)) = 'in_progress'
                  AND LOWER(CAST(rb.status AS TEXT)) NOT IN ('cancelled', 'completed')
                LIMIT 1
                """
            ),
            {"passenger_id": passenger_id, "ride_id": ride_id},
        )
    ).mappings().first()
    return row is not None


async def _can_user_send_sos_for_ride(
    db: AsyncSession,
    *,
    current_user: Any,
    ride_id: UUID,
) -> bool:
    role = _role_text(getattr(current_user, "role", None))
    user_id = getattr(current_user, "id", None)
    if user_id is None:
        return False

    ride = await get_ride_by_id(db, ride_id)
    if not ride:
        return False

    ride_status = _role_text(getattr(ride, "status", None))
    if ride_status != "in_progress":
        return False

    if role == "driver":
        return getattr(ride, "driver_id", None) == user_id

    return await _is_passenger_active_on_ride(
        db,
        passenger_id=user_id,
        ride_id=ride_id,
    )


async def get_sos_eligibility_service(
    db: AsyncSession,
    current_user: Any,
) -> Dict[str, Any]:
    linked_ride_id = await _infer_active_ride_id_for_user(db, current_user)
    can_send = linked_ride_id is not None
    return {
        "status": "ok",
        "data": {
            "can_send": can_send,
            "ride_id": linked_ride_id,
            "reason": None
            if can_send
            else "You can send SOS only after the ride starts.",
        },
        "error": None,
    }


async def ingest_telemetry_service(
    db: AsyncSession,
    telemetry_data: TelemetryInput
) -> Dict[str, Any]:
    """
    Ingest telemetry data, run AI analysis, and create incidents if anomalies detected.
    
    Args:
        db: Database session
        telemetry_data: Telemetry input data
    
    Returns:
        Response with telemetry record and analysis results
    
    Raises:
        HTTPException: If ride not found
    """
    # Verify ride exists
    ride = await get_ride_by_id(db, telemetry_data.ride_id)
    if not ride:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ride {telemetry_data.ride_id} not found"
        )
    
    # Create telemetry record
    telemetry = await crud.create_telemetry(
        db=db,
        ride_id=telemetry_data.ride_id,
        driver_id=telemetry_data.driver_id,
        speed=telemetry_data.speed,
        acceleration=telemetry_data.acceleration,
        gps_lat=telemetry_data.gps_lat,
        gps_lng=telemetry_data.gps_lng,
        harsh_brake_detected=telemetry_data.harsh_brake_detected,
        device_info=telemetry_data.device_info
    )
    
    # Run AI analysis
    telemetry_dict = {
        "speed": telemetry_data.speed,
        "acceleration": telemetry_data.acceleration,
        "gps_lat": telemetry_data.gps_lat,
        "gps_lng": telemetry_data.gps_lng,
        "harsh_brake_detected": telemetry_data.harsh_brake_detected
    }
    
    analysis = analyze_telemetry(telemetry_dict, ride)
    
    # Create incident if anomaly detected
    incident_created = False
    incident_id = None
    
    if analysis["incident"]:
        incident_type = IncidentTypeEnum(analysis["type"])
        
        # Determine severity based on AI score
        if analysis["score"] >= 0.9:
            severity = SeverityEnum.CRITICAL
        elif analysis["score"] >= 0.75:
            severity = SeverityEnum.HIGH
        elif analysis["score"] >= 0.5:
            severity = SeverityEnum.MEDIUM
        else:
            severity = SeverityEnum.LOW
        
        incident = await crud.create_incident(
            db=db,
            ride_id=telemetry_data.ride_id,
            driver_id=telemetry_data.driver_id,
            incident_type=incident_type,
            severity=severity,
            ai_score=analysis["score"],
            description=analysis["details"].get("reason", "Anomaly detected"),
            gps_lat=telemetry_data.gps_lat,
            gps_lng=telemetry_data.gps_lng,
            metadata=analysis["details"]
        )
        
        incident_created = True
        incident_id = incident.id
        
        logger.warning(f"Incident created: {incident_type.value} for ride {telemetry_data.ride_id}")
        
        # TODO: Send push notification to rider and admin
        # await send_safety_notification(incident)
    
    return {
        "status": "ok",
        "data": {
            "telemetry_id": telemetry.id,
            "analysis": analysis,
            "incident_created": incident_created,
            "incident_id": str(incident_id) if incident_id else None
        },
        "error": None
    }


async def batch_ingest_telemetry_service(
    db: AsyncSession,
    telemetry_list: List[TelemetryInput]
) -> Dict[str, Any]:
    """
    Batch ingest multiple telemetry records for performance.
    
    Args:
        db: Database session
        telemetry_list: List of telemetry input data
    
    Returns:
        Response with count of records inserted
    """
    if not telemetry_list:
        return {
            "status": "ok",
            "data": {"records_inserted": 0},
            "error": None
        }
    
    # Convert to dict format for batch insert
    telemetry_dicts = [
        {
            "ride_id": t.ride_id,
            "driver_id": t.driver_id,
            "speed": t.speed,
            "acceleration": t.acceleration,
            "gps_lat": t.gps_lat,
            "gps_lng": t.gps_lng,
            "harsh_brake_detected": t.harsh_brake_detected,
            "device_info": t.device_info
        }
        for t in telemetry_list
    ]
    
    count = await crud.batch_insert_telemetry(db, telemetry_dicts)
    
    logger.info(f"Batch ingested {count} telemetry records")
    
    return {
        "status": "ok",
        "data": {"records_inserted": count},
        "error": None
    }


async def analyze_ride_service(
    db: AsyncSession,
    ride_id: UUID
) -> AIAnalysisResponse:
    """
    Manually trigger AI analysis for a ride's telemetry data.
    
    Args:
        db: Database session
        ride_id: Ride UUID
    
    Returns:
        AI analysis response
    
    Raises:
        HTTPException: If ride not found
    """
    # Verify ride exists
    ride = await get_ride_by_id(db, ride_id)
    if not ride:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ride {ride_id} not found"
        )
    
    # Get telemetry data
    telemetry_records = await crud.get_ride_telemetry(db, ride_id, limit=100)
    
    if not telemetry_records:
        return AIAnalysisResponse(
            incident=False,
            score=0.0,
            type=None,
            severity=None,
            details={"message": "No telemetry data available"}
        )
    
    # Get telemetry stats
    stats = await crud.get_telemetry_stats(db, ride_id)
    
    # Get incidents
    incidents = await crud.get_ride_incidents(db, ride_id)
    
    # Calculate overall safety score
    incident_count = len(incidents)
    avg_ai_score = sum(i.ai_score for i in incidents) / incident_count if incident_count > 0 else 0.0
    
    # Determine if ride has critical issues
    has_critical = any(i.severity == SeverityEnum.CRITICAL for i in incidents)
    
    return AIAnalysisResponse(
        incident=incident_count > 0,
        score=avg_ai_score,
        type=incidents[0].incident_type if incidents else None,
        severity=incidents[0].severity if incidents else None,
        details={
            "total_incidents": incident_count,
            "has_critical": has_critical,
            "telemetry_stats": stats,
            "recent_incidents": [
                {
                    "type": i.incident_type.value,
                    "severity": i.severity.value,
                    "score": i.ai_score
                }
                for i in incidents[:5]
            ]
        }
    )


async def handle_sos_service(
    db: AsyncSession,
    sos_request: SOSRequest,
    current_user: Any,
) -> SOSResponse:
    """
    Handle emergency SOS signal from rider or driver.
    """
    incident_id = None
    linked_ride_id = sos_request.ride_id or await _infer_active_ride_id_for_user(
        db,
        current_user,
    )
    if not linked_ride_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can send SOS only after the ride starts.",
        )

    allowed = await _can_user_send_sos_for_ride(
        db,
        current_user=current_user,
        ride_id=linked_ride_id,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can send SOS only after the ride starts.",
        )

    ride = await get_ride_by_id(db, linked_ride_id)
    if not ride:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ride not found for SOS request.",
        )

    incident = await crud.create_incident(
        db=db,
        ride_id=linked_ride_id,
        driver_id=ride.driver_id,
        incident_type=IncidentTypeEnum.SOS,
        severity=SeverityEnum.CRITICAL,
        ai_score=1.0,
        description=f"SOS: {sos_request.message or 'Emergency SOS'}",
        gps_lat=sos_request.gps_lat,
        gps_lng=sos_request.gps_lng,
        metadata={
            "timestamp": datetime.utcnow().isoformat(),
            "triggered_by_user_id": str(getattr(current_user, "id", "")),
            "triggered_by_role": _role_text(getattr(current_user, "role", None)),
        },
    )
    incident_id = incident.id

    logger.critical(
        f"SOS received: ride_id={sos_request.ride_id}, "
        f"lat={sos_request.gps_lat}, lng={sos_request.gps_lng}, "
        f"message={sos_request.message}"
    )

    return SOSResponse(
        sos_received=True,
        incident_id=incident_id,
        admin_notified=True,
        message="SOS signal received. Safety team has been alerted."
    )


async def get_incident_history_service(
    db: AsyncSession,
    ride_id: UUID
) -> Dict[str, Any]:
    """
    Get incident history for a ride.
    
    Args:
        db: Database session
        ride_id: Ride UUID
    
    Returns:
        Response with list of incidents
    """
    incidents = await crud.get_ride_incidents(db, ride_id)
    
    incident_responses = [
        IncidentResponse(
            id=i.id,
            ride_id=i.ride_id,
            driver_id=i.driver_id,
            incident_type=i.incident_type,
            severity=i.severity,
            ai_score=i.ai_score,
            description=i.description,
            gps_lat=i.gps_lat,
            gps_lng=i.gps_lng,
            detected_at=i.detected_at,
            resolved=i.resolved,
            metadata=i.metadata
        )
        for i in incidents
    ]
    
    return {
        "status": "ok",
        "data": {
            "incidents": incident_responses,
            "total": len(incident_responses)
        },
        "error": None
    }


async def get_driver_safety_service(
    db: AsyncSession,
    driver_id: UUID,
    days: int = 30
) -> SafetySummaryResponse:
    """
    Get comprehensive safety summary for a driver.
    
    Args:
        db: Database session
        driver_id: Driver UUID
        days: Number of days to analyze (default 30)
    
    Returns:
        Safety summary response
    """
    # Generate comprehensive safety report
    report = await generate_safety_report(driver_id, db)
    
    # Get incident stats
    stats = await crud.get_incident_stats(db, driver_id, days)
    
    # Calculate safety score
    safety_score = await calculate_safety_score(driver_id, db)
    
    return SafetySummaryResponse(
        driver_id=driver_id,
        safety_score=safety_score,
        total_incidents=stats["total_incidents"],
        critical_incidents=stats["by_severity"].get("CRITICAL", 0),
        incident_breakdown=stats["by_type"],
        period_days=days,
        report=report
    )


async def send_safety_notification(incident: Any) -> None:
    """
    Send push notification for safety incident (placeholder for FCM integration).
    
    Args:
        incident: IncidentReport instance
    
    Note:
        This is a placeholder. Implement with Firebase Cloud Messaging (FCM) or
        other push notification service.
    """
    # TODO: Implement FCM push notification
    logger.info(f"[NOTIFICATION PLACEHOLDER] Safety alert for incident {incident.id}")
    pass


# ============================================================================
# PROMPT 8 - SAFETY AI MICROSERVICE
# ============================================================================

class SafetyAIService:
    """
    Safety AI Microservice Orchestration Layer (Prompt 8).
    
    Integrates:
    - Polyline computation via Google Directions
    - Hybrid anomaly detection (deterministic + ML)
    - 3-stage escalation workflow
    - Real-time telemetry streaming via Redis
    """
    
    def __init__(self):
        """Initialize Safety AI service"""
        from app.modules.safety_ai.polyline_engine import get_polyline_engine
        from app.modules.safety_ai.detector import get_anomaly_detector
        from app.modules.safety_ai.escalation import get_escalation_manager
        
        self.polyline_engine = get_polyline_engine()
        self.detector = get_anomaly_detector()
        self.escalation_mgr = get_escalation_manager()
        
        logger.info("✅ SafetyAIService initialized")
    
    async def process_telemetry_point(
        self,
        ride_id: UUID,
        point: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Main entry point for telemetry processing.
        
        Args:
            ride_id: Ride UUID
            point: Telemetry point data
            db: Database session
            
        Returns:
            Processing result with anomalies and escalations
        """
        from app.models.ride import Ride
        from sqlalchemy import select
        from app.modules.telemetry.anomaly import decode_polyline
        from app.modules.telemetry.crud import get_recent_points
        
        # Fetch ride details
        result = await db.execute(select(Ride).where(Ride.id == ride_id))
        ride = result.scalar_one_or_none()
        
        if not ride:
            logger.error(f"Ride {ride_id} not found")
            return {"status": "error", "message": "Ride not found"}
        
        # Decode polyline
        polyline_coords = None
        if ride.polyline_main:
            polyline_coords = decode_polyline(ride.polyline_main)
        
        # Fetch recent telemetry
        recent_points = await get_recent_points(db, ride_id, limit=20)
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
        
        # Run anomaly detection
        anomalies = self.detector.analyze_point(
            ride_id=ride_id,
            point=point,
            polyline_coords=polyline_coords,
            recent_points=recent_dicts,
            pickup_coords=(ride.pickup_lat, ride.pickup_lng),
            dropoff_coords=(ride.dropoff_lat, ride.dropoff_lng)
        )
        
        # Handle escalations
        escalation_results = []
        for anomaly in anomalies:
            alert = await self.escalation_mgr.handle_anomaly(
                ride_id=ride_id,
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
    
    async def run_anomaly_detection(
        self,
        ride_id: UUID,
        point: Dict[str, Any],
        polyline_coords: Optional[List[tuple]] = None,
        recent_points: Optional[List[Dict]] = None
    ) -> List[Any]:
        """
        Run anomaly detection on a single telemetry point.
        
        Args:
            ride_id: Ride UUID
            point: Telemetry point
            polyline_coords: Expected route coordinates
            recent_points: Recent historical points
            
        Returns:
            List of detected anomalies
        """
        return self.detector.analyze_point(
            ride_id=ride_id,
            point=point,
            polyline_coords=polyline_coords,
            recent_points=recent_points
        )
    
    async def handle_escalation(
        self,
        ride_id: UUID,
        anomaly: Any,
        db: AsyncSession,
        rider_id: Optional[UUID] = None,
        driver_id: Optional[UUID] = None
    ) -> Any:
        """
        Handle escalation workflow for detected anomaly.
        
        Args:
            ride_id: Ride UUID
            anomaly: Detected anomaly
            db: Database session
            rider_id: Rider user ID
            driver_id: Driver user ID
            
        Returns:
            EscalationAlert instance
        """
        return await self.escalation_mgr.handle_anomaly(
            ride_id, anomaly, db, rider_id, driver_id
        )
    
    async def compute_ride_polylines(
        self,
        ride_id: UUID,
        pickup_lat: float,
        pickup_lng: float,
        dropoff_lat: float,
        dropoff_lng: float,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        Compute and store main + alternate polylines for a ride.
        
        Args:
            ride_id: Ride UUID
            pickup_lat, pickup_lng: Pickup coordinates
            dropoff_lat, dropoff_lng: Dropoff coordinates
            db: Database session
            
        Returns:
            Computation result with polylines
        """
        return await self.polyline_engine.compute_and_store_polylines(
            ride_id, pickup_lat, pickup_lng, dropoff_lat, dropoff_lng, db
        )
    
    async def handle_user_response(
        self,
        ride_id: UUID,
        response: str,
        db: AsyncSession
    ) -> bool:
        """
        Handle user response to safety alert popup.
        
        Args:
            ride_id: Ride UUID
            response: User response (ok, not_ok, emergency)
            db: Database session
            
        Returns:
            True if alert resolved, False if escalated
        """
        return await self.escalation_mgr.handle_user_response(ride_id, response, db)
    
    async def resolve_alert(
        self,
        ride_id: UUID,
        resolved_by: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Manually resolve an active alert.
        
        Args:
            ride_id: Ride UUID
            resolved_by: Admin who resolved
            notes: Resolution notes
            
        Returns:
            True if successful
        """
        return await self.escalation_mgr.resolve_alert(ride_id, resolved_by, notes)
    
    def get_active_alerts(self) -> List[Dict]:
        """Get all active escalation alerts"""
        return self.escalation_mgr.get_active_alerts()
    
    def get_alert(self, ride_id: UUID) -> Optional[Dict]:
        """Get specific alert"""
        return self.escalation_mgr.get_alert(ride_id)


# Global SafetyAIService instance
_safety_ai_service_instance: Optional[SafetyAIService] = None


def get_safety_ai_service() -> SafetyAIService:
    """Get global SafetyAIService instance (singleton)"""
    global _safety_ai_service_instance
    
    if _safety_ai_service_instance is None:
        _safety_ai_service_instance = SafetyAIService()
    
    return _safety_ai_service_instance
