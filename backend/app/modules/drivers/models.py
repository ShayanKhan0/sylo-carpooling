"""
Module: Drivers - Database Models
Purpose: Manage driver registration, vehicle information, verification, and earnings tracking.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: This module enables scalable management of driver data and integrates later with ride and payment modules.

Tables:
- driver_profiles: Core driver information, verification status, and performance metrics
- vehicles: Vehicle registration details linked to driver profiles
"""

import uuid
import enum
from datetime import datetime, date
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Date,
    ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, foreign

from app.db.base import Base

# Import Vehicle removed to break circular dependency
# from app.models.vehicle import Vehicle  # noqa: F401


class DriverStatusEnum(str, enum.Enum):
    """
    Enum for driver account status.
    
    Values:
    - PENDING: Initial state, awaiting verification
    - ACTIVE: Verified and can accept rides
    - SUSPENDED: Temporarily banned due to policy violations
    - INACTIVE: Driver chose to pause services
    """
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


class DriverProfile(Base):
    """
    Driver profile table storing driver-specific information.
    
    Fields:
    - id: Primary key (UUID)
    - user_id: Foreign key to users table (CASCADE delete)
    - is_verified: Overall verification status (True if all docs verified)
    - license_number: Driver's license number (required)
    - license_expiry: License expiration date (optional)
    - cnic_number: CNIC number for Pakistan (format: 12345-1234567-1)
    - cnic_verified: Whether CNIC has been verified by admin/AI
    - address: Driver's residential address
    - rating: Average rating from passengers (1.0 - 5.0)
    - total_rides: Total number of completed rides
    - total_earnings: Cumulative earnings in PKR
    - joined_at: Timestamp when driver registered
    - updated_at: Timestamp of last profile update
    - status: Current driver status (pending/active/suspended/inactive)
    
    Relationships:
    - user: One-to-one with User model
    - vehicles: One-to-many with Vehicle model
    """
    __tablename__ = "driver_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        unique=True,
        nullable=False,
        index=True
    )
    
    # Verification fields
    is_verified = Column(Boolean, default=False, nullable=False)
    license_number = Column(String(50), nullable=False)
    license_expiry = Column(Date, nullable=True)
    cnic_number = Column(String(20), nullable=False)
    cnic_verified = Column(Boolean, default=False, nullable=False)
    
    # Personal info
    address = Column(String(255), nullable=True)
    
    # Performance metrics
    rating = Column(Float, default=5.0, nullable=False)
    total_rides = Column(Integer, default=0, nullable=False)
    total_earnings = Column(Float, default=0.0, nullable=False)
    
    # Status and timestamps
    # Use VARCHAR for broad DB compatibility (legacy DBs may not have enum type created).
    status = Column(String(20), default=DriverStatusEnum.PENDING.value, nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    
    # Relationships
    # user relationship defined in User model
    payouts = relationship("Payout", cascade="all, delete-orphan")
    
    # We define a primaryjoin relationship to Vehicle directly
    # A vehicle belongs to a driver if its owner_id == driver.user_id or driver_id == driver.id
    vehicles = relationship(
        "Vehicle",
        primaryjoin="or_(foreign(Vehicle.owner_id) == DriverProfile.user_id, foreign(Vehicle.driver_id) == DriverProfile.id)",
        viewonly=True
    )

    def __repr__(self):
        return f"<DriverProfile(id={self.id}, user_id={self.user_id}, status={self.status})>"


# Vehicle class is imported from app.models.vehicle (canonical location)
# The duplicate definition has been removed to avoid SQLAlchemy table conflicts


# Backwards compatibility alias: some parts of the codebase import `Driver`
# but the model class is named `DriverProfile`. Provide an alias to avoid
# import errors until callers are updated.
Driver = DriverProfile
