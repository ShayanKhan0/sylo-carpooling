"""
Module: Rides - Database Models
Purpose: Manage ride creation, booking, and lifecycle for SmartCarpoolingApp.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: Core module linking drivers and passengers. Fully async and modular.

Tables:
- rides: Driver-created rides with origin, destination, pricing, and status
- ride_bookings: Passenger bookings linked to rides with payment tracking
"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    ForeignKey, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base import Base

# Import Ride from the canonical location to avoid duplicate table definition
from app.models.ride import Ride  # noqa: F401


class RideStatusEnum(str, enum.Enum):
    """
    Enum for ride lifecycle status.
    
    Values:
    - SCHEDULED: Ride created, awaiting departure time
    - ONGOING: Ride in progress (driver started trip)
    - COMPLETED: Ride finished successfully
    - CANCELLED: Ride cancelled by driver or system
    """
    SCHEDULED = "scheduled"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BookingStatusEnum(str, enum.Enum):
    """
    Enum for individual booking status.
    
    Values:
    - BOOKED: Passenger successfully booked seat(s)
    - CANCELLED: Passenger cancelled their booking
    - COMPLETED: Ride completed for this passenger
    """
    RESERVED = "reserved"
    BOOKED = "booked"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class PaymentStatusEnum(str, enum.Enum):
    """
    Enum for booking payment status.
    
    Values:
    - PENDING: Payment not yet processed
    - PAID: Payment received and confirmed
    - REFUNDED: Payment refunded after cancellation
    """
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"


# Ride class is imported from app.models.ride (canonical location)
# The duplicate definition has been removed to avoid SQLAlchemy table conflicts


class RideBooking(Base):
    """
    RideBooking table storing passenger bookings for rides.
    
    Fields:
    - id: Primary key (UUID)
    - ride_id: Foreign key to rides (CASCADE delete)
    - passenger_id: Foreign key to users (CASCADE delete)
    - booked_seats: Number of seats booked by passenger
    - total_price: Total cost (booked_seats × price_per_seat)
    - booking_time: Timestamp when booking was made
    - status: Booking status (booked/cancelled/completed)
    - payment_status: Payment tracking (pending/paid/refunded)
    - cancellation_time: Timestamp when booking was cancelled (optional)
    - cancellation_reason: Reason for cancellation (optional)
    
    Relationships:
    - ride: Many-to-one with Ride
    - passenger: Many-to-one with User
    
    Business Rules:
    - booked_seats must be <= ride.available_seats at booking time
    - total_price = booked_seats × ride.price_per_seat (computed)
    - Cannot cancel after ride status = "ongoing"
    - Cancellation restores available_seats to ride
    - Payment integration ready for phase 3
    """
    __tablename__ = "ride_bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    ride_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rides.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    recurring_subscription_id = Column(
        UUID(as_uuid=True),
        ForeignKey("recurring_schedule_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    passenger_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Booking details
    booked_seats = Column(Integer, default=1, nullable=False)
    total_price = Column(Float, nullable=False)

    # Passenger route anchors (exact pickup/dropoff visibility enabled)
    pickup_lat = Column(Float, nullable=True)
    pickup_lng = Column(Float, nullable=True)
    pickup_address = Column(String(500), nullable=True)
    pickup_place_id = Column(String(191), nullable=True)

    dropoff_lat = Column(Float, nullable=True)
    dropoff_lng = Column(Float, nullable=True)
    dropoff_address = Column(String(500), nullable=True)
    dropoff_place_id = Column(String(191), nullable=True)

    segment_km = Column(Float, nullable=True)

    # Route-plan placement and ETA snapshots
    pickup_stop_order = Column(Integer, nullable=True)
    dropoff_stop_order = Column(Integer, nullable=True)
    planned_pickup_eta = Column(DateTime(timezone=True), nullable=True)
    planned_dropoff_eta = Column(DateTime(timezone=True), nullable=True)
    actual_pickup_time = Column(DateTime(timezone=True), nullable=True)
    actual_dropoff_time = Column(DateTime(timezone=True), nullable=True)
    route_plan_version = Column(Integer, nullable=False, server_default="0")
    
    # Status tracking
    booking_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String(20), default=BookingStatusEnum.RESERVED.value, nullable=False)
    payment_status = Column(String(20), default=PaymentStatusEnum.PENDING.value, nullable=False)
    
    # Cancellation tracking
    cancellation_time = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(String(255), nullable=True)
    
    # Relationships
    ride = relationship("Ride")
    # passenger relationship defined in User model

    def __repr__(self):
        return f"<RideBooking(id={self.id}, ride_id={self.ride_id}, passenger_id={self.passenger_id}, status={self.status})>"
