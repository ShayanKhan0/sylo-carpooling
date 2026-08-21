"""
Purpose: Rating model for ride ratings and reviews.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Stores ratings and reviews between drivers and passengers.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Text, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ride import Ride
    from app.modules.auth.models import User


class Rating(Base):
    """
    Rating model for ride ratings and reviews.
    
    Attributes:
        id: Unique identifier (UUID)
        ride_id: Foreign key to ride
        from_user_id: User giving the rating
        to_user_id: User receiving the rating
        rating: Rating value (1-5)
        comment: Optional review comment
        created_at: Rating timestamp
        updated_at: Last update timestamp
    
    Relationships:
        ride: Associated ride
        from_user_rel: User who gave this rating
        to_user_rel: User who received this rating
    
    Notes:
        - Ratings can be bidirectional (driver rates passenger, passenger rates driver)
        - Rating must be between 1 and 5
    """
    
    __tablename__ = "ratings"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    
    # Ride Reference
    ride_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rides.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Rating Direction (bidirectional) - using database column names
    rater_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User giving the rating"
    )
    
    ratee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User receiving the rating"
    )
    
    # Rating Details - using database column name 'score'
    score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Rating value (1-5)"
    )
    
    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional review comment"
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
        back_populates="ratings"
    )
    
    rater: Mapped["User"] = relationship(
        "User",
        back_populates="ratings_given",
        foreign_keys=[rater_id]
    )
    
    ratee: Mapped["User"] = relationship(
        "User",
        back_populates="ratings_received",
        foreign_keys=[ratee_id]
    )
    
    # Indexes and Constraints
    __table_args__ = (
        # UNIQUE constraint: One rating per (ride_id, rater_id, ratee_id)
        UniqueConstraint(
            "ride_id",
            "rater_id",
            "ratee_id",
            name="uq_rating_ride_rater_ratee",
        ),
        # Indexes
        Index("idx_ratings_ride_id", "ride_id"),
        Index("idx_ratings_rater_id", "rater_id"),
        Index("idx_ratings_ratee_id", "ratee_id"),
        Index("idx_ratings_created_at", "created_at"),
        # Composite indexes for common queries
        Index("idx_ratings_ride_rater", "ride_id", "rater_id"),
        Index("idx_ratings_ride_rater_ratee", "ride_id", "rater_id", "ratee_id"),
        Index("idx_ratings_ratee_score", "ratee_id", "score"),
    )
    
    def __repr__(self) -> str:
        return f"<Rating(id={self.id}, ride_id={self.ride_id}, rater={self.rater_id}, ratee={self.ratee_id}, score={self.score})>"
