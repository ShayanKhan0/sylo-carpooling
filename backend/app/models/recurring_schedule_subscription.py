"""
Module: Recurring Schedule Subscription Model
Purpose: Store passenger subscriptions to recurring schedules
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: April 19, 2026
"""

import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Time
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.recurring_schedule import RecurringSchedule
    from app.modules.auth.models import User


class RecurringScheduleSubscription(Base):
    """Passenger subscription to a driver's recurring schedule."""

    __tablename__ = "recurring_schedule_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recurring_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    passenger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    overlap_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    overlap_end_date: Mapped[date] = mapped_column(Date, nullable=False)

    departure_window_start: Mapped[time] = mapped_column(Time, nullable=False)
    departure_window_end: Mapped[time] = mapped_column(Time, nullable=False)

    seats_reserved: Mapped[int] = mapped_column(nullable=False, default=1)

    pickup_lat: Mapped[float | None] = mapped_column(nullable=True)
    pickup_lng: Mapped[float | None] = mapped_column(nullable=True)
    pickup_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pickup_place_id: Mapped[str | None] = mapped_column(String(191), nullable=True)

    dropoff_lat: Mapped[float | None] = mapped_column(nullable=True)
    dropoff_lng: Mapped[float | None] = mapped_column(nullable=True)
    dropoff_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dropoff_place_id: Mapped[str | None] = mapped_column(String(191), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    schedule: Mapped["RecurringSchedule"] = relationship("RecurringSchedule")
    passenger: Mapped["User"] = relationship("User")

    __table_args__ = (
        Index("idx_recurring_subscriptions_schedule_status", "schedule_id", "status"),
        Index("idx_recurring_subscriptions_passenger_status", "passenger_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            "<RecurringScheduleSubscription("
            f"id={self.id}, schedule_id={self.schedule_id}, passenger_id={self.passenger_id}, status={self.status}"
            ")>"
        )
