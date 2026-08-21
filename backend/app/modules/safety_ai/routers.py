"""
Safety AI Router

This module provides REST API endpoints for telemetry ingestion, AI-powered safety analysis,
incident management, and emergency SOS handling.

Author: Smart Carpooling Backend Team
"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.schemas import UserPublic
from app.modules.safety_ai.schemas import (
    TelemetryInput,
    TelemetryBatchInput,
    TelemetryResponse,
    IncidentListResponse,
    AIAnalysisRequest,
    AIAnalysisResponse,
    SOSRequest,
    SOSResponse,
    SafetySummaryResponse
)
from app.modules.safety_ai import service

router = APIRouter(prefix="/safety", tags=["Safety AI"])


@router.post(
    "/telemetry",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest Telemetry Data",
    description="""
    Ingest real-time telemetry data from a ride (speed, acceleration, GPS, etc.).
    The system will automatically run AI analysis and create incidents if anomalies detected.
    
    **Use Cases:**
    - Mobile app sends telemetry data every 5-10 seconds during a ride
    - IoT devices in vehicles stream telemetry data
    - Driver monitoring systems report vehicle metrics
    
    **AI Analysis:**
    - Overspeed detection (speed > 120 km/h)
    - Harsh braking/acceleration detection
    - Route deviation detection
    - Overall safety score calculation
    
    **Response includes:**
    - Telemetry record ID
    - AI analysis results
    - Whether an incident was created
    - Incident ID if created
    """
)
async def ingest_telemetry(
    telemetry: TelemetryInput,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Ingest telemetry data and run AI safety analysis.
    
    Creates telemetry record, runs AI analysis, and creates incidents if anomalies detected.
    Requires JWT authentication.
    """
    return await service.ingest_telemetry_service(db, telemetry)


@router.post(
    "/telemetry/batch",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Batch Ingest Telemetry Data",
    description="""
    Batch ingest multiple telemetry records for improved performance.
    
    **Use Cases:**
    - Mobile app sends buffered telemetry data when connectivity is restored
    - Offline mode: accumulate data and sync when online
    - High-frequency sensors sending data in batches
    
    **Performance:**
    - More efficient than individual inserts
    - Reduces database round-trips
    - Suitable for bulk data ingestion
    
    **Note:** Batch inserts do NOT trigger AI analysis on each record.
    Use the single telemetry endpoint for real-time analysis.
    """
)
async def batch_ingest_telemetry(
    batch: TelemetryBatchInput,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Batch ingest multiple telemetry records.
    
    Inserts multiple telemetry records in a single transaction for performance.
    Requires JWT authentication.
    """
    return await service.batch_ingest_telemetry_service(db, batch.telemetry_data)


@router.get(
    "/incident/{ride_id}",
    response_model=dict,
    summary="Get Ride Incidents",
    description="""
    Retrieve all safety incidents detected for a specific ride.
    
    **Use Cases:**
    - Rider/driver reviews safety incidents after ride completion
    - Admin investigates safety issues reported during a ride
    - Safety dashboard displays ride-specific incidents
    
    **Response includes:**
    - List of all incidents (overspeed, harsh braking, SOS, etc.)
    - Incident details (type, severity, AI score, GPS location)
    - Resolution status
    - Metadata with additional context
    
    **Incident Types:**
    - OVERSPEED: Speed exceeded safe limits
    - HARSH_BRAKE: Sudden deceleration detected
    - HARSH_ACCELERATION: Sudden acceleration detected
    - ROUTE_DEVIATION: Driver deviated from expected route
    - SOS: Emergency signal activated
    - SUSPICIOUS_ACTIVITY: AI detected anomalous behavior
    """
)
async def get_ride_incidents(
    ride_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all incidents for a specific ride.
    
    Returns list of incidents with details. Requires JWT authentication.
    """
    return await service.get_incident_history_service(db, ride_id)


@router.post(
    "/ai/analyze",
    response_model=AIAnalysisResponse,
    summary="Analyze Ride Safety (Manual)",
    description="""
    Manually trigger comprehensive AI safety analysis for a ride.
    
    **Use Cases:**
    - Admin manually reviews ride safety after rider complaint
    - Periodic batch analysis of completed rides
    - Re-analyze ride with updated AI models
    
    **Analysis includes:**
    - Overall safety score (0-1)
    - Incident detection and classification
    - Severity assessment
    - Telemetry statistics (max speed, avg speed, harsh brakes)
    - Recent incident summary
    
    **Severity Levels:**
    - LOW: Minor issues, no immediate danger
    - MEDIUM: Concerning behavior, requires monitoring
    - HIGH: Serious safety concerns, may require intervention
    - CRITICAL: Immediate danger, emergency response needed
    """
)
async def analyze_ride_safety(
    request: AIAnalysisRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually trigger AI safety analysis for a ride.
    
    Analyzes telemetry data and returns comprehensive safety assessment.
    Requires JWT authentication.
    """
    return await service.analyze_ride_service(db, request.ride_id)


@router.post(
    "/sos",
    response_model=SOSResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Emergency SOS Signal",
    description="""
    Handle emergency SOS signal from rider or driver.
    
    **Use Cases:**
    - Rider feels unsafe and activates emergency button
    - Driver encounters emergency situation (accident, medical issue, etc.)
    - Automatic SOS trigger from vehicle crash detection
    
    **Emergency Types:**
    - accident: Vehicle collision or crash
    - medical: Medical emergency (driver or passenger)
    - threat: Safety threat (harassment, violence, etc.)
    - breakdown: Vehicle breakdown in unsafe location
    - other: Other emergency situations
    
    **Automatic Actions:**
    - Creates CRITICAL severity incident
    - Sends push notifications to rider, driver, and admin
    - May dispatch emergency services (configurable)
    - Records GPS location for emergency response
    - Logs incident with full details
    
    **IMPORTANT:** This is a critical safety feature. All SOS signals are treated
    with highest priority and trigger immediate response protocols.
    """
)
async def handle_sos(
    sos_request: SOSRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Handle emergency SOS signal.
    
    Creates critical incident, sends notifications, and may dispatch emergency services.
    Requires JWT authentication.
    """
    return await service.handle_sos_service(db, sos_request, current_user)


@router.get("/sos/eligibility", response_model=dict)
async def sos_eligibility(
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.get_sos_eligibility_service(db, current_user)


@router.get(
    "/driver/{driver_id}/safety",
    response_model=SafetySummaryResponse,
    summary="Get Driver Safety Summary",
    description="""
    Get comprehensive safety summary for a driver over a specified period.
    
    **Use Cases:**
    - Driver views their own safety score and performance
    - Admin reviews driver safety record for verification
    - Rider checks driver's safety rating before accepting ride
    - Safety analytics dashboard displays driver metrics
    
    **Response includes:**
    - Overall safety score (0-100)
    - Total incidents count
    - Critical incidents count
    - Incident breakdown by type
    - Detailed safety report with recommendations
    
    **Safety Score Calculation:**
    - Based on 30-day rolling average of incident AI scores
    - Higher score = safer driver
    - Score < 50: Poor safety record
    - Score 50-75: Average safety record
    - Score 75-90: Good safety record
    - Score > 90: Excellent safety record
    """
)
async def get_driver_safety_summary(
    driver_id: UUID,
    days: int = 30,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive safety summary for a driver.
    
    Returns safety score, incident counts, and detailed report.
    Requires JWT authentication.
    """
    return await service.get_driver_safety_service(db, driver_id, days)


# ============================================================================
# PROMPT 8 - SAFETY AI MICROSERVICE ENDPOINTS
# ============================================================================

from app.modules.safety_ai.schemas import (
    SafetyRuleResponse,
    RuleReloadRequest,
    PolylineComputationResponse,
    RideAnomaliesResponse,
    EscalationAlertResponse,
    ResolveAlertRequest,
    UserResponseRequest,
    AnomalyResultResponse
)
from app.modules.auth.deps import require_admin


@router.get(
    "/ai/rules",
    response_model=SafetyRuleResponse,
    summary="[Admin] Get Current Safety Rules",
    description="""
    Get current safety AI rules configuration.
    
    **Admin Only** - Requires admin role.
    
    Returns all safety thresholds including:
    - Off-route detection threshold (meters)
    - Unexpected stop duration (minutes)
    - Overspeed thresholds (km/h)
    - ML sensitivity (0-1)
    - False positive suppression settings
    - Escalation timeouts
    """
)
async def get_safety_rules(
    current_user: UserPublic = Depends(require_admin)
):
    """
    Get current safety rules configuration.
    
    Requires admin authentication.
    """
    from app.modules.safety_ai.rule_engine import get_rule_engine
    from datetime import datetime
    
    rule_engine = get_rule_engine()
    rules = rule_engine.rules.copy()
    
    return SafetyRuleResponse(
        rules=rules,
        last_loaded=datetime.utcnow()
    )


@router.post(
    "/ai/rules/reload",
    response_model=dict,
    summary="[Admin] Hot Reload Safety Rules",
    description="""
    Hot reload safety rules from YAML file without restarting the service.
    
    **Admin Only** - Requires admin role.
    
    Useful for:
    - Adjusting detection thresholds in production
    - Testing different rule configurations
    - Emergency rule changes without downtime
    """
)
async def reload_safety_rules(
    request: RuleReloadRequest,
    current_user: UserPublic = Depends(require_admin)
):
    """
    Hot reload safety rules from YAML file.
    
    Requires admin authentication.
    """
    from app.modules.safety_ai.rule_engine import get_rule_engine
    import logging
    
    logger = logging.getLogger(__name__)
    rule_engine = get_rule_engine()
    
    try:
        rule_engine.reload_rules()
        logger.info(f"Safety rules reloaded by admin: {current_user.email}")
        
        return {
            "status": "success",
            "message": "Safety rules reloaded successfully",
            "rules_count": len(rule_engine.rules)
        }
    except Exception as e:
        logger.error(f"Failed to reload rules: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reload rules: {str(e)}"
        )


@router.get(
    "/ai/ride/{ride_id}/anomalies",
    response_model=RideAnomaliesResponse,
    summary="[Admin] Get Ride Anomaly History",
    description="""
    Get all detected anomalies for a specific ride.
    
    **Admin Only** - Requires admin role.
    
    Returns anomaly history including:
    - Anomaly type (off_route, unexpected_stop, overspeed, etc.)
    - Detection confidence (0-1)
    - Severity level (low, medium, high)
    - Detailed context for each anomaly
    """
)
async def get_ride_anomalies(
    ride_id: UUID,
    current_user: UserPublic = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get anomaly history for a ride.
    
    Requires admin authentication.
    """
    # TODO: Implement anomaly history storage and retrieval
    # For now, return empty list
    return RideAnomaliesResponse(
        ride_id=ride_id,
        total_anomalies=0,
        anomalies=[]
    )


@router.get(
    "/ai/ride/{ride_id}/escalation_status",
    response_model=dict,
    summary="[Admin] Get Escalation Alert Status",
    description="""
    Get current escalation alert status for a ride.
    
    **Admin Only** - Requires admin role.
    
    Returns:
    - Alert existence and current stage
    - Status (pending, acknowledged, resolved, escalated)
    - Actions taken at each escalation stage
    - User responses (if any)
    """
)
async def get_escalation_status(
    ride_id: UUID,
    current_user: UserPublic = Depends(require_admin)
):
    """
    Get escalation alert status for a ride.
    
    Requires admin authentication.
    """
    from app.modules.safety_ai.service import get_safety_ai_service
    
    safety_service = get_safety_ai_service()
    alert = safety_service.get_alert(ride_id)
    
    if alert:
        return {
            "status": "active",
            "alert": alert
        }
    else:
        return {
            "status": "none",
            "message": "No active alert for this ride"
        }


@router.post(
    "/ai/ride/{ride_id}/resolve_alert",
    response_model=dict,
    summary="[Admin] Manually Resolve Safety Alert",
    description="""
    Manually resolve an active safety alert.
    
    **Admin Only** - Requires admin role.
    
    Use when:
    - False positive confirmed after investigation
    - Issue resolved through external intervention
    - Admin determines no further action needed
    """
)
async def resolve_alert(
    ride_id: UUID,
    request: ResolveAlertRequest,
    current_user: UserPublic = Depends(require_admin)
):
    """
    Manually resolve a safety alert.
    
    Requires admin authentication.
    """
    from app.modules.safety_ai.service import get_safety_ai_service
    import logging
    
    logger = logging.getLogger(__name__)
    safety_service = get_safety_ai_service()
    
    resolved = await safety_service.resolve_alert(
        ride_id=ride_id,
        resolved_by=request.resolved_by,
        notes=request.notes
    )
    
    if resolved:
        logger.info(f"Alert for ride {ride_id} resolved by {request.resolved_by}")
        return {
            "status": "success",
            "message": "Alert resolved successfully"
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active alert found for this ride"
        )


@router.post(
    "/ai/ride/{ride_id}/user_response",
    response_model=dict,
    summary="User Response to Safety Alert Popup",
    description="""
    Submit user response to safety alert in-app popup.
    
    **User Endpoint** - Rider or driver can respond.
    
    Response options:
    - 'ok': User confirms they are safe, alert resolved
    - 'not_ok': User indicates problem, escalate to Stage 2
    - 'emergency': User needs immediate help, escalate to Stage 2
    """
)
async def submit_user_response(
    ride_id: UUID,
    request: UserResponseRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Submit user response to safety alert popup.
    
    Requires authentication.
    """
    from app.modules.safety_ai.service import get_safety_ai_service
    import logging
    
    logger = logging.getLogger(__name__)
    safety_service = get_safety_ai_service()
    
    resolved = await safety_service.handle_user_response(
        ride_id=ride_id,
        response=request.response,
        db=db
    )
    
    if resolved:
        logger.info(f"Alert for ride {ride_id} resolved by user response: {request.response}")
        return {
            "status": "resolved",
            "message": "Thank you for confirming your safety"
        }
    else:
        logger.warning(f"Alert for ride {ride_id} escalated due to user response: {request.response}")
        return {
            "status": "escalated",
            "message": "Emergency contacts have been notified. Help is on the way."
        }


@router.get(
    "/ai/active_alerts",
    response_model=dict,
    summary="[Admin] Get All Active Alerts",
    description="""
    Get all currently active safety alerts across all rides.
    
    **Admin Only** - Requires admin role.
    
    Useful for:
    - Safety dashboard monitoring
    - Real-time alert tracking
    - Emergency response coordination
    """
)
async def get_active_alerts(
    current_user: UserPublic = Depends(require_admin)
):
    """
    Get all active safety alerts.
    
    Requires admin authentication.
    """
    from app.modules.safety_ai.service import get_safety_ai_service
    
    safety_service = get_safety_ai_service()
    alerts = safety_service.get_active_alerts()
    
    return {
        "status": "success",
        "total_alerts": len(alerts),
        "alerts": alerts
    }
