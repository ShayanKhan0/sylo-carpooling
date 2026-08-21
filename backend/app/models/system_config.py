"""
SystemConfig model — stores global platform configuration key/value pairs.

Used by the Fuel Price Engine to store petrol prices, fuel averages,
platform fees and driver margins that affect per-passenger fare computation.

Author: M. Mobeen Shoukat Ch & M. Shayan Khan
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class SystemConfig(Base):
    """
    Key-value store for dynamic platform settings.

    Rows:
        petrol_price_per_litre   → float  (PKR, e.g. 378.0)
        fuel_avg_km_per_litre    → float  (km/L, e.g. 12.0)
        platform_fee_pct         → float  (fraction, e.g. 0.15 = 15 %)
        driver_margin_pct        → float  (fraction, e.g. 0.15 = 15 %)
        min_fare_pkr             → float  (PKR, e.g. 50.0)
        base_fare_pkr            → float  (PKR, e.g. 30.0)
        avg_speed_kmh            → float  (km/h for ETA fallback, e.g. 40.0)
    """

    __tablename__ = "system_config"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    key: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Configuration key, e.g. 'petrol_price_per_litre'",
    )

    value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Configuration value stored as text (cast on read)",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Human-readable description of this setting",
    )

    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_system_config_key", "key"),
    )

    def __repr__(self) -> str:
        return f"<SystemConfig(key={self.key!r}, value={self.value!r})>"
