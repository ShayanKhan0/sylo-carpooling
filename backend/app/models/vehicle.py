"""
Purpose: Vehicle model for storing vehicle information.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Supports both canonical and legacy vehicle fields during migration.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, ForeignKey, JSON, Index, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User


class Vehicle(Base):
    """Vehicle model with canonical + legacy compatibility fields."""

    __tablename__ = "vehicles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    make: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    # Canonical contract fields
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    plate_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    seats_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Legacy contract fields kept for compatibility
    driver_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    license_plate: Mapped[str | None] = mapped_column(String(50), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Shared fields
    seats_available: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    registration_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    photos: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    owner: Mapped["User | None"] = relationship("User", back_populates="vehicles")

    __table_args__ = (
        Index("idx_vehicles_plate_number", "plate_number"),
        Index("idx_vehicles_owner_id", "owner_id"),
        Index("idx_vehicles_driver_id", "driver_id"),
        Index("idx_vehicles_license_plate", "license_plate"),
    )

    @property
    def effective_owner_id(self):
        return self.owner_id or self.driver_id

    @property
    def effective_plate_number(self) -> str:
        return self.plate_number or self.license_plate or ""

    @property
    def effective_seats_total(self) -> int:
        return self.seats_total or self.seats_available

    def __repr__(self) -> str:
        plate = self.effective_plate_number
        return f"<Vehicle(id={self.id}, plate={plate}, make={self.make} {self.model})>"
