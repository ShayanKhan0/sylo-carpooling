"""
Module: Recurring Schedule Model
Purpose: Database model for recurring ride schedules
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: December 8, 2025
Notes: Supports weekly recurring rides for drivers
"""

import uuid
from datetime import datetime, date, time
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Date, Time, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User


class RecurringSchedule(Base):
    """
    Recurring Schedule model for repeating rides.
    
    Attributes:
        id: Unique identifier (UUID)
        user_id: Foreign key to user (driver)
        days_of_week: List of days ["Mon", "Tue", "Wed", ...]
        time: Time of day for ride
        start_point_lat: Starting point latitude
        start_point_lng: Starting point longitude
        start_point_address: Starting address
        end_point_lat: Destination latitude
        end_point_lng: Destination longitude
        end_point_address: Destination address
        polyline_main: Main route polyline
        seats_offered: Number of seats
        base_price: Price per seat
        start_date: Schedule start date
        end_date: Schedule end date
        recurrence_meta: Additional recurrence metadata (JSON)
        is_active: Whether schedule is currently active
        created_at: Creation timestamp
        updated_at: Last update timestamp
    
    Relationships:
        user: User who created this schedule
    
    Example:
        >>> schedule = RecurringSchedule(
        ...     user_id=driver_id,
        ...     days_of_week=["Mon", "Wed", "Fri"],
        ...     time=time(8, 0),
        ...     start_date=date(2025, 12, 8),
        ...     end_date=date(2026, 6, 30)
        ... )
    """
    
    __tablename__ = "recurring_schedules"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    
    # User Reference (Driver)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Schedule Pattern
    days_of_week: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="List of days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']"
    )
    
    time: Mapped[time] = mapped_column(
        "departure_time",
        Time,
        nullable=False,
        comment="Time of day for ride (e.g., 08:00:00)"
    )

    # Route Information
    start_point_lat: Mapped[float] = mapped_column(
        "start_lat",
        nullable=False
    )

    start_point_lng: Mapped[float] = mapped_column(
        "start_lng",
        nullable=False
    )

    start_point_address: Mapped[str] = mapped_column(
        "start_address",
        String(500),
        nullable=False
    )

    end_point_lat: Mapped[float] = mapped_column(
        "end_lat",
        nullable=False
    )

    end_point_lng: Mapped[float] = mapped_column(
        "end_lng",
        nullable=False
    )

    end_point_address: Mapped[str] = mapped_column(
        "end_address",
        String(500),
        nullable=False
    )
    
    polyline_main: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
        comment="Encoded polyline for route"
    )
    
    # Ride Details
    seats_offered: Mapped[int] = mapped_column(
        nullable=False
    )
    
    base_price: Mapped[float] = mapped_column(
        nullable=False
    )
    
    buffer_seats: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="Optional seats kept aside"
    )
    
    # Date Range
    start_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Schedule becomes active from this date"
    )
    
    end_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Schedule ends after this date"
    )
    
    # Metadata
    recurrence_meta: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional metadata: {exclude_dates: [], preferences: {}}"
    )
    
    # Status
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        index=True
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
        back_populates="recurring_schedules"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_schedules_user_id", "user_id"),
        Index("idx_schedules_is_active", "is_active"),
        Index("idx_schedules_date_range", "start_date", "end_date"),
        Index("idx_schedules_user_active", "user_id", "is_active"),
    )
    
    def __repr__(self) -> str:
        return f"<RecurringSchedule(id={self.id}, user_id={self.user_id}, days={self.days_of_week})>"
