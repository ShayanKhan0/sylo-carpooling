"""
Telemetry Schemas

Pydantic models for telemetry data validation.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, validator


class TelemetryPoint(BaseModel):
    """Single telemetry data point from device"""
    
    timestamp: datetime = Field(..., description="UTC timestamp of measurement")
    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lng: float = Field(..., ge=-180, le=180, description="Longitude")
    speed: float = Field(..., ge=0, description="Speed in km/h")
    bearing: Optional[float] = Field(None, ge=0, lt=360, description="Bearing in degrees")
    accuracy: Optional[float] = Field(None, ge=0, description="GPS accuracy in meters")
    
    @validator('speed')
    def validate_speed(cls, v):
        if v > 300:  # Reasonable max speed in km/h
            raise ValueError('Speed exceeds reasonable maximum (300 km/h)')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2025-12-08T10:30:00Z",
                "lat": 31.4697,
                "lng": 74.2728,
                "speed": 45.5,
                "bearing": 270.0,
                "accuracy": 5.0
            }
        }


class TelemetryBatchRequest(BaseModel):
    """Batch upload of telemetry points"""
    
    ride_id: UUID = Field(..., description="Ride UUID")
    points: List[TelemetryPoint] = Field(..., min_length=1, max_length=500)
    
    @validator('points')
    def validate_points_ordering(cls, v):
        """Ensure points are in chronological order"""
        if len(v) > 1:
            for i in range(1, len(v)):
                if v[i].timestamp < v[i-1].timestamp:
                    raise ValueError('Telemetry points must be in chronological order')
        return v


class TelemetryLatestResponse(BaseModel):
    """Latest telemetry points for a ride"""
    
    ride_id: UUID
    points: List[dict]
    samples: List[dict] = Field(default_factory=list)
    count: int


class TelemetryReplayResponse(BaseModel):
    """Complete trip replay data"""
    
    ride_id: UUID
    polyline: str = Field(..., description="Encoded polyline of entire route")
    samples: List[dict] = Field(..., description="All telemetry samples with timestamps")
    start_time: datetime
    end_time: datetime
    duration_sec: float
    total_distance_km: float
    avg_speed_kmh: float
    max_speed_kmh: float
    sample_count: int


class AnomalyAlert(BaseModel):
    """Anomaly detection alert"""
    
    ride_id: UUID
    timestamp: datetime
    anomaly_type: str = Field(..., description="lateral_deviation | unexpected_stop | overspeed")
    severity: str = Field(..., description="low | medium | high")
    details: dict
    location: dict = Field(..., description="lat/lng of anomaly")
