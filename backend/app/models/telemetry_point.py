"""
Purpose: Telemetry point model for GPS tracking during rides.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Stores GPS tracking points during active rides.
       Consider table partitioning by timestamp for large datasets.
       Consider aggregating into polylines for long-term storage.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Float, Index
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ride import Ride


class TelemetryPoint(Base):
    """
    Telemetry point model for GPS tracking during rides.
    
    Attributes:
        id: Unique identifier (UUID)
        ride_id: Foreign key to ride
        timestamp: GPS point timestamp
        latitude: GPS latitude
        longitude: GPS longitude
        speed: Vehicle speed (km/h)
        bearing: Direction of travel (0-360 degrees)
    
    Relationships:
        ride: Associated ride
    
    Notes:
        - Consider partitioning this table by timestamp for performance
        - Consider aggregating old points into polylines for storage efficiency
        - High write volume during active rides
    """
    
    __tablename__ = "telemetry_points"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    
    # Ride Reference
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rides.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        index=True,
        comment="GPS point timestamp - consider partitioning by this column"
    )
    
    # Location Data
    latitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="GPS latitude - consider PostGIS POINT type for spatial queries"
    )
    
    longitude: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="GPS longitude - consider PostGIS POINT type for spatial queries"
    )
    
    # Speed and Direction
    speed: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Vehicle speed in km/h"
    )
    
    bearing: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Direction of travel (0-360 degrees)"
    )
    
    # Relationships
    ride: Mapped["Ride"] = relationship(
        "Ride",
        back_populates="telemetry_points"
    )
    
    # Indexes
    # TODO: Consider table partitioning by timestamp (monthly or weekly)
    # CREATE TABLE telemetry_points_2025_01 PARTITION OF telemetry_points FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
    __table_args__ = (
        Index("idx_telemetry_ride_id", "ride_id"),
        Index("idx_telemetry_timestamp", "timestamp"),
        # Composite index for ride timeline queries
        Index("idx_telemetry_ride_timestamp", "ride_id", "timestamp"),
        # Spatial index for location-based queries (if not using PostGIS)
        Index("idx_telemetry_location", "latitude", "longitude"),
    )
    
    def __repr__(self) -> str:
        return f"<TelemetryPoint(id={self.id}, ride_id={self.ride_id}, timestamp={self.timestamp})>"
