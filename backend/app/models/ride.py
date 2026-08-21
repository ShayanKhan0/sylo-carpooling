"""
Purpose: Ride model for driver-created trips.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Represents trips offered by drivers.
       Includes route information (polylines), pricing, and seat availability.
       Spatial indexing available if PostGIS is enabled.
       Column names match the actual PostgreSQL 'rides' table schema.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, Float, ForeignKey, DECIMAL, Index, Text, JSON, Enum as SQLEnum, inspect
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm.attributes import NO_VALUE
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import RideStatus
from app.models.driver import Driver  # noqa: F401
from app.models.booking import Booking  # noqa: F401
from app.models.telemetry_point import TelemetryPoint  # noqa: F401
from app.models.rating import Rating  # noqa: F401

if TYPE_CHECKING:
    from app.models.driver import Driver
    from app.models.booking import Booking
    from app.models.telemetry_point import TelemetryPoint
    from app.models.rating import Rating
    from app.modules.safety_ai.models import TelemetryData, IncidentReport


class Ride(Base):
    """
    Ride model representing driver-created trips.
    
    Matches the actual PostgreSQL 'rides' table columns exactly.
    Additional convenience properties map between API-friendly names
    and the actual DB column names.
    """
    
    __tablename__ = "rides"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    
    # Driver Reference
    driver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("drivers.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Vehicle Reference (nullable in DB)
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Start Point (actual DB columns)
    start_point_lat: Mapped[float] = mapped_column(
        nullable=False,
        comment="Starting point latitude"
    )
    
    start_point_lng: Mapped[float] = mapped_column(
        nullable=False,
        comment="Starting point longitude"
    )
    
    # End Point (actual DB columns)
    end_point_lat: Mapped[float] = mapped_column(
        nullable=False,
        comment="Destination latitude"
    )
    
    end_point_lng: Mapped[float] = mapped_column(
        nullable=False,
        comment="Destination longitude"
    )
    
    # Schedule Information (actual DB column name)
    departure_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        index=True
    )
    
    # Seat Management (actual DB column name)
    seats_available: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    
    # Pricing (actual DB column name)
    price_per_seat: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 2),
        nullable=False
    )
    
    # Status (ride_status enum, default 'open')
    status: Mapped[RideStatus] = mapped_column(
        SQLEnum(RideStatus, name="ride_status", create_type=False),
        nullable=False,
        default=RideStatus.OPEN,
        index=True
    )
    
    # Route polyline (actual DB column name: 'polyline', text)
    polyline: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Google Maps encoded polyline for the selected route"
    )
    
    # Recurrence pattern (actual DB column: jsonb)
    recurrence: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Recurring schedule: {pattern: 'daily', days: [1,2,3,4,5], time: '08:00'}"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now()
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # ── New columns (will be added via Alembic migration) ──
    # Human-readable addresses for display
    start_point_address: Mapped[str | None] = mapped_column(
        Text, nullable=True, server_default=None,
        comment="Human-readable start address"
    )
    
    end_point_address: Mapped[str | None] = mapped_column(
        Text, nullable=True, server_default=None,
        comment="Human-readable destination address"
    )
    
    # Route metadata
    estimated_duration_minutes: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default=None,
        comment="Estimated trip duration in minutes"
    )
    
    route_distance_km: Mapped[float | None] = mapped_column(
        Float, nullable=True, server_default=None,
        comment="Route distance in kilometers"
    )

    route_plan_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
        comment="Incremented whenever stop order/polyline plan changes",
    )

    route_selected_key: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        server_default=None,
        comment="Selected route option key (optimal/alternative)",
    )

    route_alternatives: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        server_default=None,
        comment="Precomputed constrained route alternatives for active ride",
    )
    
    # ── Convenience properties for API compatibility ──
    @property
    def origin(self) -> str:
        """API-friendly alias: start address or lat/lng fallback."""
        return self.start_point_address or f"{self.start_point_lat},{self.start_point_lng}"
    
    @property
    def destination(self) -> str:
        """API-friendly alias: end address or lat/lng fallback."""
        return self.end_point_address or f"{self.end_point_lat},{self.end_point_lng}"
    
    @property
    def available_seats(self) -> int:
        """API-friendly alias for seats_available."""
        return self.seats_available
    
    @property
    def estimated_duration(self) -> int | None:
        """API-friendly alias for estimated_duration_minutes."""
        return self.estimated_duration_minutes
    
    @property
    def total_earnings(self) -> float:
        """Computed total earnings from active bookings without implicit async DB I/O."""
        try:
            bookings_attr = inspect(self).attrs.bookings
            loaded_bookings = bookings_attr.loaded_value
        except Exception:
            return 0.0

        if loaded_bookings is NO_VALUE or not loaded_bookings:
            return 0.0

        total = 0.0
        for booking in loaded_bookings:
            status_value = str(getattr(booking, "status", "")).lower()
            if "cancel" in status_value:
                continue

            amount = getattr(booking, "total_price", None)
            if amount is None:
                amount = getattr(booking, "fare", None)
            if amount is None:
                amount = getattr(booking, "individual_fare", None)

            try:
                total += float(amount or 0.0)
            except (TypeError, ValueError):
                continue

        return total
    
    # Relationships
    driver: Mapped["Driver"] = relationship(
        "Driver",
        back_populates="rides"
    )
    
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        back_populates="ride",
        cascade="all, delete-orphan"
    )
    
    telemetry_points: Mapped[list["TelemetryPoint"]] = relationship(
        "TelemetryPoint",
        back_populates="ride",
        cascade="all, delete-orphan"
    )

    telemetry: Mapped[list["TelemetryData"]] = relationship(
        "TelemetryData",
        back_populates="ride",
        cascade="all, delete-orphan"
    )
    
    ratings: Mapped[list["Rating"]] = relationship(
        "Rating",
        back_populates="ride",
        cascade="all, delete-orphan"
    )

    incidents: Mapped[list["IncidentReport"]] = relationship(
        "IncidentReport",
        back_populates="ride",
        cascade="all, delete-orphan"
    )

    
    # Indexes matching actual DB
    __table_args__ = (
        Index("idx_rides_driver_id", "driver_id"),
        Index("idx_rides_departure_time", "departure_time"),
        Index("idx_rides_status", "status"),
        Index("idx_rides_driver_status", "driver_id", "status"),
        Index("idx_rides_status_departure", "status", "departure_time"),
        Index("idx_rides_start_point", "start_point_lat", "start_point_lng"),
        Index("idx_rides_end_point", "end_point_lat", "end_point_lng"),
    )
    
    def __repr__(self) -> str:
        return f"<Ride(id={self.id}, driver_id={self.driver_id}, status={self.status}, seats={self.seats_available})>"
