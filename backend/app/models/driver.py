"""
Purpose: Driver model for driver-specific information.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: One-to-one relationship with User model.
       License number should be encrypted at application level (TODO: integrate KMS).
       Spatial indexing available if PostGIS is enabled.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, Float, Integer, Index, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import DriverVerificationStatus

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.models.vehicle import Vehicle
    from app.models.ride import Ride


class Driver(Base):
    """
    Driver model representing driver-specific information.
    
    Attributes:
        user_id: Foreign key to users table (one-to-one, primary key)
        license_number: Driver's license number (encrypted)
        vehicle_id: Foreign key to current vehicle (optional)
        verified: Driver verification status
        rating_avg: Average driver rating
        rating_count: Total number of ratings
        location_last_lat: Last known latitude
        location_last_lng: Last known longitude
        created_at: Record creation timestamp
        updated_at: Last update timestamp
    
    Relationships:
        user: Associated user account
        vehicle: Currently assigned vehicle
        rides: Rides created by this driver
    """
    
    __tablename__ = "drivers"
    
    # Primary Key (one-to-one with User)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True
    )
    
    # === VERIFICATION FUNCTIONALITY START ===
    # TODO: Encrypt license_number at application level using KMS or field-level encryption
    # This field stores sensitive driver license information
    license_number: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Encrypted license number - integrate with KMS for encryption/decryption"
    )
    
    # Vehicle Assignment
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    
    # Verification Status
    verified: Mapped[DriverVerificationStatus] = mapped_column(
        SQLEnum(
            DriverVerificationStatus,
            name="driver_verification_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=DriverVerificationStatus.PENDING,
        index=True
    )
    # === VERIFICATION FUNCTIONALITY END ===
    
    # Rating Information
    rating_avg: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        index=True
    )
    
    rating_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0
    )
    
    # Last Known Location
    # TODO: Consider PostGIS POINT type for better spatial queries
    # For now using standard float columns with composite index
    location_last_lat: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Last known latitude - consider PostGIS POINT type for spatial indexing"
    )
    
    location_last_lng: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Last known longitude - consider PostGIS POINT type for spatial indexing"
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
    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="driver"
    )
    
    vehicle: Mapped["Vehicle | None"] = relationship("Vehicle")
    
    rides: Mapped[list["Ride"]] = relationship(
        "Ride",
        back_populates="driver",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    # TODO: If PostGIS is available, use spatial index: CREATE INDEX idx_drivers_location ON drivers USING GIST (location_point);
    __table_args__ = (
        Index("idx_drivers_user_id", "user_id"),
        Index("idx_drivers_vehicle_id", "vehicle_id"),
        Index("idx_drivers_verified", "verified"),
        Index("idx_drivers_rating_avg", "rating_avg"),
        # Composite index for location-based queries (if not using PostGIS)
        Index("idx_drivers_location", "location_last_lat", "location_last_lng"),
    )
    
    def __repr__(self) -> str:
        return f"<Driver(user_id={self.user_id}, verified={self.verified}, rating={self.rating_avg})>"
