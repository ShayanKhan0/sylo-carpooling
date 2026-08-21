"""
Pydantic schemas for Safety AI Module.

Schemas for telemetry data, incident reports, and safety analysis.

Author: Smart Carpooling Development Team
Created: 2025-11-08
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel, Field, validator, ConfigDict

from .models import IncidentTypeEnum, SeverityEnum


# ============================================================================
# TELEMETRY SCHEMAS
# ============================================================================

class TelemetryInput(BaseModel):
    """
    Input schema for telemetry data ingestion.
    
    Sent from mobile app during active rides.
    """
    ride_id: UUID = Field(..., description="Active ride ID")
    speed: float = Field(..., ge=0, le=300, description="Current speed in km/h")
    acceleration: Optional[float] = Field(None, ge=-15, le=15, description="Acceleration in m/s²")
    gps_lat: Decimal = Field(..., ge=-90, le=90, description="Latitude")
    gps_lng: Decimal = Field(..., ge=-180, le=180, description="Longitude")
    gps_accuracy: Optional[float] = Field(None, ge=0, description="GPS accuracy in meters")
    bearing: Optional[float] = Field(None, ge=0, le=360, description="Heading direction in degrees")
    altitude: Optional[float] = Field(None, description="Altitude in meters")
    device_id: Optional[str] = Field(None, max_length=100, description="Device identifier")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ride_id": "123e4567-e89b-12d3-a456-426614174000",
                "speed": 65.5,
                "acceleration": -2.3,
                "gps_lat": 31.5204,
                "gps_lng": 74.3587,
                "gps_accuracy": 10.5,
                "bearing": 45.0,
                "altitude": 215.0,
                "device_id": "device-abc123"
            }
        }
    )


class TelemetryBatchInput(BaseModel):
    """
    Batch input schema for multiple telemetry data points.
    
    Allows efficient bulk ingestion.
    """
    ride_id: UUID
    telemetry_data: List[TelemetryInput] = Field(..., min_length=1, max_length=100)
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ride_id": "123e4567-e89b-12d3-a456-426614174000",
                "telemetry_data": [
                    {
                        "ride_id": "123...",
                        "speed": 60.0,
                        "gps_lat": 31.5204,
                        "gps_lng": 74.3587
                    }
                ]
            }
        }
    )


class TelemetryResponse(BaseModel):
    """
    Response schema for telemetry data.
    """
    id: UUID
    ride_id: UUID
    driver_id: Optional[UUID]
    speed: float
    acceleration: Optional[float]
    gps_lat: Decimal
    gps_lng: Decimal
    timestamp: datetime
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "789...",
                "ride_id": "123...",
                "driver_id": "456...",
                "speed": 65.5,
                "acceleration": -2.3,
                "gps_lat": 31.5204,
                "gps_lng": 74.3587,
                "timestamp": "2025-11-08T10:00:00Z"
            }
        }
    )


# ============================================================================
# INCIDENT SCHEMAS
# ============================================================================

class IncidentResponse(BaseModel):
    """
    Response schema for incident report.
    """
    id: UUID
    ride_id: UUID
    driver_id: Optional[UUID]
    type: IncidentTypeEnum
    severity: SeverityEnum
    ai_score: float
    ai_confidence: Optional[float]
    description: str
    location_lat: Optional[Decimal]
    location_lng: Optional[Decimal]
    speed_at_incident: Optional[float]
    detected_at: datetime
    reviewed: bool
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "789...",
                "ride_id": "123...",
                "driver_id": "456...",
                "type": "overspeed",
                "severity": "high",
                "ai_score": 0.92,
                "ai_confidence": 0.95,
                "description": "Overspeed detected: 135.0 km/h",
                "location_lat": 31.5204,
                "location_lng": 74.3587,
                "speed_at_incident": 135.0,
                "detected_at": "2025-11-08T10:15:00Z",
                "reviewed": False
            }
        }
    )


class IncidentListResponse(BaseModel):
    """
    Response schema for list of incidents.
    """
    total: int
    incidents: List[IncidentResponse]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 2,
                "incidents": [
                    {
                        "id": "789...",
                        "type": "overspeed",
                        "severity": "high"
                    }
                ]
            }
        }
    )


# ============================================================================
# SAFETY ANALYSIS SCHEMAS
# ============================================================================

class SafetySummaryResponse(BaseModel):
    """
    Response schema for driver safety summary.
    """
    driver_id: UUID
    safety_score: float = Field(..., ge=0, le=100, description="Overall safety score (0-100)")
    total_rides: int
    total_incidents: int
    incident_breakdown: Dict[str, int] = Field(..., description="Count by incident type")
    severity_breakdown: Dict[str, int] = Field(..., description="Count by severity")
    recent_incidents: List[IncidentResponse] = Field(..., description="Last 5 incidents")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "driver_id": "456...",
                "safety_score": 85.5,
                "total_rides": 150,
                "total_incidents": 8,
                "incident_breakdown": {
                    "overspeed": 3,
                    "harsh_brake": 4,
                    "harsh_acceleration": 1
                },
                "severity_breakdown": {
                    "low": 2,
                    "medium": 5,
                    "high": 1
                },
                "recent_incidents": []
            }
        }
    )


class SOSRequest(BaseModel):
    """
    Request schema for SOS emergency signal.
    """
    ride_id: Optional[UUID] = Field(None, description="Active ride ID (optional if not in a ride)")
    gps_lat: Optional[Decimal] = Field(None, ge=-90, le=90)
    gps_lng: Optional[Decimal] = Field(None, ge=-180, le=180)
    message: Optional[str] = Field(None, max_length=500, description="Optional emergency message")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ride_id": "123...",
                "gps_lat": 31.5204,
                "gps_lng": 74.3587,
                "message": "Emergency assistance needed"
            }
        }
    )


class SOSResponse(BaseModel):
    """
    Response schema for SOS emergency signal.
    """
    sos_received: bool = Field(..., description="Whether SOS was received")
    incident_id: Optional[UUID] = Field(None, description="Incident record ID if created")
    admin_notified: bool = Field(False)
    message: str = Field(..., description="Status message")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sos_received": True,
                "incident_id": "456e7890-e89b-12d3-a456-426614174000",
                "admin_notified": True,
                "message": "SOS signal received. Emergency contacts notified."
            }
        }
    )


class AIAnalysisRequest(BaseModel):
    """
    Request schema for manual AI analysis trigger.
    """
    ride_id: UUID
    force_reanalyze: Optional[bool] = Field(False, description="Force reanalysis of ride data")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ride_id": "123...",
                "force_reanalyze": False
            }
        }
    )


class AIAnalysisResponse(BaseModel):
    """
    Response schema for AI analysis results.
    """
    ride_id: UUID
    analyzed: bool
    incidents_detected: int
    anomaly_score: float = Field(..., ge=0, le=1, description="Overall anomaly score")
    incidents: List[IncidentResponse]
    summary: str
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ride_id": "123...",
                "analyzed": True,
                "incidents_detected": 2,
                "anomaly_score": 0.73,
                "incidents": [],
                "summary": "2 incidents detected: 1 overspeed, 1 harsh brake"
            }
        }
    )


# ============================================================================
# OPERATION RESPONSE SCHEMA
# ============================================================================

class OperationResponse(BaseModel):
    """
    Generic operation response.
    """
    message: str
    incident_id: Optional[UUID] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Telemetry data ingested successfully",
                "incident_id": None
            }
        }
    )


# ============================================================================
# PROMPT 8 - SAFETY AI MICROSERVICE SCHEMAS
# ============================================================================

class AnomalyResultResponse(BaseModel):
    """
    Response schema for anomaly detection result.
    """
    anomaly_type: str = Field(..., description="Type of anomaly (off_route, unexpected_stop, overspeed, etc.)")
    confidence: float = Field(..., ge=0, le=1, description="Detection confidence (0-1)")
    severity: str = Field(..., description="Severity level (low, medium, high)")
    details: Dict[str, Any] = Field(..., description="Additional details about the anomaly")
    detected_at: datetime = Field(..., description="Detection timestamp")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "anomaly_type": "off_route",
                "confidence": 0.87,
                "severity": "medium",
                "details": {
                    "distance_m": 85.3,
                    "threshold_m": 60,
                    "description": "Vehicle 85.3m off expected route"
                },
                "detected_at": "2025-11-08T10:15:30Z"
            }
        }
    )


class EscalationAlertResponse(BaseModel):
    """
    Response schema for escalation alert.
    """
    ride_id: UUID
    anomaly: AnomalyResultResponse
    stage: str = Field(..., description="Escalation stage (stage1_popup, stage2_emergency_contacts, stage3_admin_alert)")
    status: str = Field(..., description="Alert status (pending, acknowledged, resolved, escalated)")
    created_at: datetime
    updated_at: datetime
    actions_taken: List[str] = Field(..., description="List of actions taken")
    timeout_at: Optional[datetime] = Field(None, description="Timeout timestamp for current stage")
    user_response: Optional[str] = Field(None, description="User response (ok, not_ok, emergency)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ride_id": "123e4567-e89b-12d3-a456-426614174000",
                "anomaly": {
                    "anomaly_type": "overspeed",
                    "confidence": 0.95,
                    "severity": "high",
                    "details": {"speed_kmh": 145.0},
                    "detected_at": "2025-11-08T10:15:30Z"
                },
                "stage": "stage1_popup",
                "status": "pending",
                "created_at": "2025-11-08T10:15:30Z",
                "updated_at": "2025-11-08T10:15:30Z",
                "actions_taken": ["Sent in-app popup at 2025-11-08T10:15:30Z"],
                "timeout_at": "2025-11-08T10:16:30Z",
                "user_response": None
            }
        }
    )


class SafetyRuleResponse(BaseModel):
    """
    Response schema for safety rules configuration.
    """
    rules: Dict[str, Any] = Field(..., description="Current safety rules")
    last_loaded: datetime = Field(..., description="Last time rules were loaded/reloaded")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rules": {
                    "off_route_threshold_m": 60,
                    "stop_minutes": 3,
                    "overspeed_kmh": 120,
                    "ml_sensitivity": 0.7
                },
                "last_loaded": "2025-11-08T09:00:00Z"
            }
        }
    )


class RuleReloadRequest(BaseModel):
    """
    Request schema for rule engine hot-reload.
    """
    force: bool = Field(False, description="Force reload even if file hasn't changed")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "force": True
            }
        }
    )


class PolylineComputationResponse(BaseModel):
    """
    Response schema for polyline computation.
    """
    status: str = Field(..., description="Computation status (success, error)")
    main_polyline: Optional[str] = Field(None, description="Main route polyline (encoded)")
    alternates_count: int = Field(..., description="Number of alternate routes computed")
    message: Optional[str] = Field(None, description="Status message or error description")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "success",
                "main_polyline": "abc123xyz...",
                "alternates_count": 3,
                "message": "Polylines computed successfully"
            }
        }
    )


class RideAnomaliesResponse(BaseModel):
    """
    Response schema for ride anomaly history.
    """
    ride_id: UUID
    total_anomalies: int
    anomalies: List[AnomalyResultResponse]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ride_id": "123e4567-e89b-12d3-a456-426614174000",
                "total_anomalies": 2,
                "anomalies": [
                    {
                        "anomaly_type": "overspeed",
                        "confidence": 0.92,
                        "severity": "high",
                        "details": {},
                        "detected_at": "2025-11-08T10:15:30Z"
                    }
                ]
            }
        }
    )


class ResolveAlertRequest(BaseModel):
    """
    Request schema for manually resolving an alert.
    """
    resolved_by: str = Field(..., description="Admin username or ID who resolved the alert")
    notes: Optional[str] = Field(None, max_length=1000, description="Resolution notes")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "resolved_by": "admin@example.com",
                "notes": "False alarm - driver stopped for gas"
            }
        }
    )


class UserResponseRequest(BaseModel):
    """
    Request schema for user response to safety alert popup.
    """
    response: str = Field(..., description="User response (ok, not_ok, emergency)")
    
    @validator('response')
    def validate_response(cls, v):
        allowed = ['ok', 'not_ok', 'emergency']
        if v not in allowed:
            raise ValueError(f"Response must be one of: {allowed}")
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "response": "ok"
            }
        }
    )
