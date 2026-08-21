"""
Prompt 11D — Analytics Database Models

Daily aggregated metrics for admin analytics.

Author: Smart Carpooling Backend Team
Date: January 23, 2026
"""

import uuid
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import Date, Integer, Index, UniqueConstraint, DECIMAL
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base


class DailyAggregate(Base):
    """
    Daily aggregation table for admin analytics.
    
    One row per date with pre-aggregated KPIs to avoid heavy realtime queries.
    """
    
    __tablename__ = "daily_aggregates"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Aggregation date (unique)"
    )
    
    rides_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total rides for the day"
    )
    
    completed_rides: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Completed rides for the day"
    )
    
    cancelled_rides: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Cancelled rides for the day"
    )
    
    gross_revenue: Mapped[Decimal] = mapped_column(
        DECIMAL(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Gross revenue for the day"
    )
    
    commission_revenue: Mapped[Decimal] = mapped_column(
        DECIMAL(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Platform commission revenue for the day"
    )
    
    active_drivers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Unique active drivers for the day"
    )

    verification_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Verification failures for the day"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now()
    )
    
    __table_args__ = (
        UniqueConstraint("date", name="uq_daily_aggregates_date"),
        Index("idx_daily_aggregates_date", "date"),
    )
    
    def __repr__(self) -> str:
        return f"<DailyAggregate(date={self.date}, rides={self.rides_count}, gross={self.gross_revenue})>"
