"""
Purpose: RideRequest model — passenger-initiated ride requests.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Notes: Passengers post a ride request; nearby drivers see & accept them.
"""

import uuid
import enum
from datetime import datetime

from sqlalchemy import String, Integer, Float, ForeignKey, Text, Enum as SQLEnum, Index
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class RideRequestStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class RideRequest(Base):
    """Passenger-created ride request visible to nearby drivers."""

    __tablename__ = "ride_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )

    passenger_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Origin
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    origin_lat: Mapped[float] = mapped_column(Float, nullable=False)
    origin_lng: Mapped[float] = mapped_column(Float, nullable=False)

    # Destination
    destination: Mapped[str] = mapped_column(Text, nullable=False)
    destination_lat: Mapped[float] = mapped_column(Float, nullable=False)
    destination_lng: Mapped[float] = mapped_column(Float, nullable=False)

    # Ride details
    seats_needed: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    departure_time: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )

    # Status
    status: Mapped[RideRequestStatus] = mapped_column(
        SQLEnum(RideRequestStatus, name="ride_request_status", create_type=True),
        nullable=False,
        default=RideRequestStatus.PENDING,
    )

    # If accepted, which driver accepted
    accepted_by_driver_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Linked ride (created when driver accepts)
    ride_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rides.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_rr_passenger", "passenger_id"),
        Index("idx_rr_status", "status"),
        Index("idx_rr_origin", "origin_lat", "origin_lng"),
        Index("idx_rr_departure", "departure_time"),
    )

    def __repr__(self) -> str:
        return f"<RideRequest(id={self.id}, passenger={self.passenger_id}, status={self.status})>"
