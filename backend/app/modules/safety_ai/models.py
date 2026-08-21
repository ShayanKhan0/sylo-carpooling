"""
Database models for Safety AI Module.

Models:
- TelemetryData: Real-time vehicle telemetry data from rides
- IncidentReport: AI-detected safety incidents and anomalies

Author: Smart Carpooling Development Team
Created: 2025-11-08
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, String, Integer, Float, Numeric, DateTime, ForeignKey, Text, Enum as SQLEnum, Index, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class IncidentTypeEnum(str, enum.Enum):
    """
    Types of safety incidents detected by AI.
    
    Types:
    - OVERSPEED: Excessive speed detected
    - HARSH_BRAKE: Sudden braking detected
    - HARSH_ACCELERATION: Rapid acceleration detected
    - ROUTE_DEVIATION: Significant deviation from planned route
    - SOS: Emergency SOS signal triggered
    - ERRATIC_DRIVING: Erratic/unsafe driving patterns
    - GEOFENCE_VIOLATION: Left designated safe zone
    """
    OVERSPEED = "overspeed"
    HARSH_BRAKE = "harsh_brake"
    HARSH_ACCELERATION = "harsh_acceleration"
    ROUTE_DEVIATION = "route_deviation"
    SOS = "sos"
    ERRATIC_DRIVING = "erratic_driving"
    GEOFENCE_VIOLATION = "geofence_violation"


class SeverityEnum(str, enum.Enum):
    """
    Incident severity levels.
    
    Levels:
    - LOW: Minor issue, informational
    - MEDIUM: Moderate concern, monitor
    - HIGH: Serious issue, requires attention
    - CRITICAL: Immediate action required
    """
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TelemetryData(Base):
    """
    Real-time vehicle telemetry data.
    
    Business Rules:
    - Ingested every 5-30 seconds during active rides
    - Stored for AI analysis and anomaly detection
    - Used to calculate driver safety scores
    - Batch processing for performance
    - Retention: 90 days (then archive/delete)
    
    Data Sources:
    - Mobile app GPS
    - Vehicle sensors (if integrated)
    - OBD-II devices (future)
    - Smartphone accelerometer
    
    Performance:
    - High-volume table (millions of records)
    - Indexed by ride_id and timestamp
    - Partition by date recommended
    - Async bulk inserts for efficiency
    """
    __tablename__ = "telemetry_data"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Ride and driver references
    ride_id = Column(UUID(as_uuid=True), ForeignKey("rides.id", ondelete="CASCADE"), nullable=False, index=True)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Speed data
    speed = Column(Float, nullable=False)  # km/h
    speed_limit = Column(Float, nullable=True)  # km/h (if available)
    
    # Acceleration data
    acceleration = Column(Float, nullable=True)  # m/s² (positive = accelerating, negative = braking)
    
    # GPS location
    gps_lat = Column(Numeric(10, 7), nullable=False)  # Latitude (-90 to 90)
    gps_lng = Column(Numeric(10, 7), nullable=False)  # Longitude (-180 to 180)
    gps_accuracy = Column(Float, nullable=True)  # meters
    
    # Bearing and direction
    bearing = Column(Float, nullable=True)  # degrees (0-360)
    
    # Additional sensor data
    altitude = Column(Float, nullable=True)  # meters
    
    # Timestamp
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Device metadata
    device_id = Column(String(100), nullable=True)
    meta_data = Column(Text, nullable=True)  # JSON: battery level, network, etc.
    
    # Relationships
    ride = relationship("Ride", back_populates="telemetry")
    driver = relationship("User")
    
    # Constraints and indexes
    __table_args__ = (
        Index('idx_telemetry_ride_id', 'ride_id'),
        Index('idx_telemetry_driver_id', 'driver_id'),
        Index('idx_telemetry_timestamp', 'timestamp'),
        Index('idx_telemetry_ride_timestamp', 'ride_id', 'timestamp'),
    )

    def __repr__(self):
        return f"<TelemetryData(ride_id={self.ride_id}, speed={self.speed}, timestamp={self.timestamp})>"


class IncidentReport(Base):
    """
    AI-detected safety incidents.
    
    Business Rules:
    - Created automatically when AI detects anomalies
    - Severity determines notification urgency
    - Critical incidents trigger immediate alerts
    - Affects driver safety score
    - Admin review capability
    - Used for driver training and coaching
    
    Detection Algorithm:
    1. Analyze telemetry stream in real-time
    2. Calculate anomaly score using AI
    3. Compare against thresholds
    4. Create incident if threshold exceeded
    5. Notify relevant parties (driver, rider, admin)
    
    Incident Workflow:
    1. AI detects anomaly (score > 0.85)
    2. Create incident report
    3. Determine severity
    4. Send notifications based on severity
    5. Log for driver history
    6. Update safety score
    """
    __tablename__ = "incident_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Ride and driver references
    ride_id = Column(UUID(as_uuid=True), ForeignKey("rides.id", ondelete="CASCADE"), nullable=False, index=True)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Incident details
    type = Column(SQLEnum(IncidentTypeEnum), nullable=False, index=True)
    severity = Column(SQLEnum(SeverityEnum), nullable=False, index=True)
    
    # AI analysis
    ai_score = Column(Float, nullable=False)  # Anomaly score (0.0 - 1.0)
    ai_confidence = Column(Float, nullable=True)  # AI confidence in detection
    
    # Location
    location_lat = Column(Numeric(10, 7), nullable=True)
    location_lng = Column(Numeric(10, 7), nullable=True)
    location_description = Column(String(255), nullable=True)  # Human-readable location
    
    # Incident description
    description = Column(Text, nullable=False)
    ai_remarks = Column(Text, nullable=True)
    
    # Telemetry snapshot
    speed_at_incident = Column(Float, nullable=True)
    acceleration_at_incident = Column(Float, nullable=True)
    
    # Timestamps
    detected_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    
    # Review and resolution
    reviewed = Column(Boolean, nullable=False, default=False)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    admin_remarks = Column(Text, nullable=True)
    
    # Metadata
    meta_data = Column(Text, nullable=True)  # JSON: telemetry snapshot, context, etc.
    
    # Relationships
    ride = relationship("Ride", back_populates="incidents")
    driver = relationship("User", foreign_keys=[driver_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    
    # Constraints and indexes
    __table_args__ = (
        Index('idx_incident_ride_id', 'ride_id'),
        Index('idx_incident_driver_id', 'driver_id'),
        Index('idx_incident_type', 'type'),
        Index('idx_incident_severity', 'severity'),
        Index('idx_incident_detected_at', 'detected_at'),
        Index('idx_incident_reviewed', 'reviewed'),
    )

    def __repr__(self):
        return f"<IncidentReport(ride_id={self.ride_id}, type={self.type}, severity={self.severity})>"

