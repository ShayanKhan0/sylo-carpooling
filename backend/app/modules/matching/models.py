"""
Module: Matching - Database Models
Purpose: Database models for ride-driver matching records and preferences.
Authors: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: Stores match history, scores, and user-specific matching preferences.
"""

import enum
from uuid import uuid4
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, Enum as SQLEnum, ForeignKey, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class MatchStatusEnum(str, enum.Enum):
    """
    Enum for match record status.
    
    Values:
    - PROPOSED: Match suggestion generated but not yet acted upon
    - ACCEPTED: Driver accepted the match
    - REJECTED: Driver rejected the match
    - ASSIGNED: Match successfully assigned and ride created
    - EXPIRED: Match suggestion expired (timeout)
    - CANCELLED: Match cancelled before assignment
    """
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ASSIGNED = "assigned"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class MatchRecord(Base):
    """
    Database model for storing match history and scores.
    
    Purpose:
    - Track all matching attempts between riders and drivers
    - Store computed match scores for analytics
    - Enable match history retrieval for users
    - Support machine learning model training data
    
    Business Rules:
    - Each match attempt is recorded with timestamp
    - Scores range from 0-100 (higher is better)
    - Status tracks match lifecycle from proposal to assignment
    - Records are never deleted (for audit trail)
    
    Relationships:
    - ride_id → rides.id (CASCADE delete when ride deleted)
    - driver_id → drivers.id (CASCADE delete when driver deleted)
    - passenger_id → users.id (CASCADE delete when user deleted)
    
    Fields:
    - id: UUID primary key
    - ride_id: Reference to ride being matched
    - driver_id: Reference to matched driver
    - passenger_id: Reference to requesting passenger
    - match_score: Overall match score (0-100)
    - distance_score: Distance compatibility score (0-100)
    - time_score: Time compatibility score (0-100)
    - preference_score: Preference matching score (0-100)
    - distance_km: Actual distance between driver and pickup (km)
    - estimated_pickup_time: Estimated time for driver to reach pickup (minutes)
    - status: Current match status (proposed/accepted/rejected/assigned/expired/cancelled)
    - created_at: When match was generated
    - updated_at: Last status update
    - expires_at: When match suggestion expires
    - match_metadata: JSON field for additional matching context
    """
    
    __tablename__ = "match_records"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    
    # Foreign Keys
    ride_id = Column(UUID(as_uuid=True), ForeignKey("rides.id", ondelete="CASCADE"), nullable=False, index=True)
    driver_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    passenger_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Match Scores (0-100 range)
    match_score = Column(Float, nullable=False, index=True, comment="Overall weighted match score")
    distance_score = Column(Float, nullable=False, comment="Score based on pickup distance")
    time_score = Column(Float, nullable=False, comment="Score based on time compatibility")
    preference_score = Column(Float, nullable=False, default=100.0, comment="Score based on user preferences")
    
    # Match Metrics
    distance_km = Column(Float, nullable=False, comment="Distance from driver to pickup in kilometers")
    estimated_pickup_time = Column(Integer, nullable=False, comment="Estimated pickup time in minutes")
    
    # Status and Lifecycle
    status = Column(
        SQLEnum(MatchStatusEnum),
        nullable=False,
        default=MatchStatusEnum.PROPOSED,
        index=True,
        comment="Current status of match"
    )
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True, comment="When match suggestion expires")
    
    # Metadata (JSON)
    match_metadata = Column(Text, nullable=True, comment="Additional matching context as JSON")
    
    # Relationships
    ride = relationship("Ride", lazy="selectin")
    passenger = relationship("User", lazy="selectin")
    
    def __repr__(self):
        return f"<MatchRecord(id={self.id}, ride_id={self.ride_id}, driver_id={self.driver_id}, score={self.match_score}, status={self.status})>"


class MatchPreference(Base):
    """
    Database model for user-specific matching preferences.
    
    Purpose:
    - Store passenger preferences for driver matching
    - Enable preference-based filtering in matching algorithm
    - Support personalized matching experience
    
    Business Rules:
    - One preference record per user (unique constraint)
    - Preferences are optional (all defaults to permissive)
    - Can be updated anytime by user
    - Affects preference_score in match calculation
    
    Relationships:
    - user_id → users.id (CASCADE delete when user deleted)
    
    Fields:
    - id: UUID primary key
    - user_id: Reference to user who owns preferences
    - prefer_verified_drivers: Only match with verified drivers
    - prefer_same_gender: Prefer drivers of same gender
    - prefer_non_smoking: Prefer non-smoking drivers
    - max_pickup_distance_km: Maximum acceptable pickup distance (km)
    - max_pickup_time_minutes: Maximum acceptable pickup time (minutes)
    - min_driver_rating: Minimum acceptable driver rating (0-5)
    - prefer_vehicle_types: Comma-separated vehicle types (sedan,suv,etc)
    - created_at: When preferences were created
    - updated_at: When preferences were last modified
    """
    
    __tablename__ = "match_preferences"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    
    # Foreign Key (unique - one preference per user)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    # Driver Preferences
    prefer_verified_drivers = Column(Boolean, nullable=False, default=True, comment="Only match with verified drivers")
    prefer_same_gender = Column(Boolean, nullable=False, default=False, comment="Prefer drivers of same gender")
    prefer_non_smoking = Column(Boolean, nullable=False, default=False, comment="Prefer non-smoking drivers")
    
    # Distance and Time Constraints
    max_pickup_distance_km = Column(Float, nullable=True, default=10.0, comment="Maximum pickup distance in km")
    max_pickup_time_minutes = Column(Integer, nullable=True, default=15, comment="Maximum pickup time in minutes")
    
    # Driver Quality Preferences
    min_driver_rating = Column(Float, nullable=True, default=3.0, comment="Minimum acceptable driver rating (0-5)")
    
    # Vehicle Preferences (comma-separated)
    prefer_vehicle_types = Column(String(255), nullable=True, comment="Preferred vehicle types: sedan,suv,hatchback")
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = relationship("User", lazy="selectin")
    
    def __repr__(self):
        return f"<MatchPreference(user_id={self.user_id}, verified={self.prefer_verified_drivers}, max_distance={self.max_pickup_distance_km})>"
