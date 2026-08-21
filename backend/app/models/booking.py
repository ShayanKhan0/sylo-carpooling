"""
Purpose: Booking model for passenger ride reservations.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Represents passenger bookings for rides.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Float, DECIMAL, Index, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import BookingStatus

if TYPE_CHECKING:
    from app.models.ride import Ride
    from app.modules.auth.models import User


class Booking(Base):
    """
    Booking model representing passenger ride reservations.
    
    Attributes:
        id: Unique identifier (UUID)
        ride_id: Foreign key to ride
        passenger_id: Foreign key to passenger user
        seats_reserved: Number of seats reserved
        fare: Total fare for this booking
        status: Booking status (reserved, cancelled, completed)
        created_at: Booking creation timestamp
        updated_at: Last update timestamp
    
    Relationships:
        ride: Associated ride
        passenger: Passenger who made this booking
    """
    
    __tablename__ = "bookings"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    
    # References
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rides.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    passenger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Booking Details
    seats_reserved: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    
    fare: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 2),
        nullable=False
    )
    
    # ── Dynamic Fare & Route Membership (Module 2 / 3 / 4) ───────────────────
    individual_fare: Mapped[Decimal | None] = mapped_column(
        DECIMAL(10, 2),
        nullable=True,
        comment="Per-passenger dynamic fare from proportional distance engine (PKR)",
    )

    estimated_pickup_time: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Pre-computed ETA for when driver reaches this passenger's pickup",
    )

    segment_km: Mapped[float | None] = mapped_column(
        Float(),
        nullable=True,
        comment="Route km this passenger travels (pickup → dropoff along driver route)",
    )

    pickup_pct: Mapped[float | None] = mapped_column(
        Float(),
        nullable=True,
        comment="Fraction along route where pickup falls (0.0 – 1.0)",
    )

    dropoff_pct: Mapped[float | None] = mapped_column(
        Float(),
        nullable=True,
        comment="Fraction along route where dropoff falls (0.0 – 1.0)",
    )

    pickup_route_km: Mapped[float | None] = mapped_column(
        Float(),
        nullable=True,
        comment="Km along route to pickup point",
    )

    dropoff_route_km: Mapped[float | None] = mapped_column(
        Float(),
        nullable=True,
        comment="Km along route to dropoff point",
    )

    rate_per_km_used: Mapped[float | None] = mapped_column(
        Float(),
        nullable=True,
        comment="PKR/km rate snapshot used at booking creation time",
    )

    # Optimistic Concurrency Control
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Version field for optimistic locking"
    )
    
    # Status
    status: Mapped[BookingStatus] = mapped_column(
        SQLEnum(BookingStatus, name="booking_status"),
        nullable=False,
        default=BookingStatus.RESERVED,
        index=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        index=True
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    ride: Mapped["Ride"] = relationship(
        "Ride",
        back_populates="bookings"
    )
    
    passenger: Mapped["User"] = relationship(
        "User",
        back_populates="bookings",
        foreign_keys=[passenger_id]
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_bookings_ride_id", "ride_id"),
        Index("idx_bookings_passenger_id", "passenger_id"),
        Index("idx_bookings_status", "status"),
        Index("idx_bookings_created_at", "created_at"),
        # Composite indexes for common queries
        Index("idx_bookings_ride_status", "ride_id", "status"),
        Index("idx_bookings_passenger_status", "passenger_id", "status"),
    )
    
    def __repr__(self) -> str:
        return f"<Booking(id={self.id}, ride_id={self.ride_id}, passenger_id={self.passenger_id}, status={self.status})>"
