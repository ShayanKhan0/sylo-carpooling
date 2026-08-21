"""
Ratings Module Schemas (Prompt 11A)

Request/Response schemas for rating system with weighted averages.
Implements exact specifications from Prompt 11A.

Author: Smart Carpooling Backend Team
Date: December 19, 2025
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class RatingCreate(BaseModel):
    """
    Schema for creating a new rating (Prompt 11A).
    
    One rating per (ride_id, from_user_id, to_user_id).
    Rating is allowed once the participant dropoff is completed.
    
    Attributes:
        ride_id: ID of the completed ride
        rating: Integer rating value (1-5)
        to_user_id: Optional explicit target user (required for unambiguous
            multi-passenger driver ratings)
        booking_id: Optional booking context for dropoff-triggered ratings
        comment: Optional review comment (max 500 chars)
    
    Example:
        {
            "ride_id": "123e4567-e89b-12d3-a456-426614174000",
            "rating": 5,
            "to_user_id": "223e4567-e89b-12d3-a456-426614174111",
            "booking_id": "323e4567-e89b-12d3-a456-426614174222",
            "comment": "Great ride, friendly driver!"
        }
    """
    
    ride_id: UUID = Field(..., description="ID of the completed ride")
    rating: int = Field(..., ge=1, le=5, description="Rating value from 1 to 5")
    to_user_id: Optional[UUID] = Field(
        None,
        description="Optional explicit target user UUID for this rating"
    )
    booking_id: Optional[UUID] = Field(
        None,
        description="Optional booking UUID to bind rating to a specific dropoff"
    )
    comment: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional comment (max 500 characters)"
    )
    
    @field_validator("comment")
    @classmethod
    def validate_comment(cls, v: Optional[str]) -> Optional[str]:
        """Validate and sanitize comment - trim whitespace."""
        if v is not None:
            v = v.strip()
            if len(v) == 0:
                return None
        return v


class RatingResponse(BaseModel):
    """
    Rating response schema (Prompt 11A).
    
    Attributes:
        id: Rating UUID
        ride_id: Ride UUID
        from_user_id: User who gave the rating (API field for rater_id)
        to_user_id: User who received the rating (API field for ratee_id)
        rating: Integer rating value (1-5) (API field for score)
        comment: Review comment
        created_at: Creation timestamp
    """
    
    id: UUID
    ride_id: UUID
    from_user_id: UUID = Field(validation_alias="rater_id", serialization_alias="from_user_id")
    to_user_id: UUID = Field(validation_alias="ratee_id", serialization_alias="to_user_id")
    rating: int = Field(validation_alias="score", serialization_alias="rating", ge=1, le=5)
    comment: Optional[str] = None
    created_at: datetime
    
    # Optional user details for enriched responses
    from_user_name: Optional[str] = None
    to_user_name: Optional[str] = None
    from_user_profile_photo: Optional[str] = None
    to_user_profile_photo: Optional[str] = None
    
    class Config:
        from_attributes = True
        populate_by_name = True


class RatingUpdate(BaseModel):
    """
    Schema for updating an existing rating.
    
    Attributes:
        rating: Updated rating value (1-5)
        comment: Updated comment (optional, max 500 chars)
    """
    
    rating: Optional[int] = Field(None, ge=1, le=5, description="Updated rating value")
    comment: Optional[str] = Field(None, max_length=500, description="Updated comment")
    
    @field_validator("comment")
    @classmethod
    def validate_comment(cls, v: Optional[str]) -> Optional[str]:
        """Validate and sanitize comment."""
        if v is not None:
            v = v.strip()
            if len(v) == 0:
                return None
        return v


class RatingListResponse(BaseModel):
    """
    Paginated list of ratings (Prompt 11A GET /api/v1/ratings/user/{user_id}).
    
    Attributes:
        ratings: List of ratings
        total: Total count of ratings
        page: Current page number
        page_size: Items per page
        total_pages: Total number of pages
    """
    
    ratings: list[RatingResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class WeightedAverageResponse(BaseModel):
    """
    Weighted average rating response (Prompt 11A GET /api/v1/ratings/average/{user_id}).
    
    **Prompt 11A Algorithm:**
    - Last 20 ratings: 70% weight
    - Remaining older ratings: 30% weight
    
    Formula: weighted_avg = (avg_last_20 * 0.7) + (avg_older * 0.3)
    
    Attributes:
        user_id: User UUID
        weighted_average: Weighted average rating (1.0-5.0)
        total_ratings: Total number of ratings received
        recent_ratings: Count of last 20 ratings (used in calculation)
        rating_distribution: Breakdown by star (5, 4, 3, 2, 1)
    
    Example Response:
        {
            "user_id": "123e4567-e89b-12d3-a456-426614174000",
            "weighted_average": 4.65,
            "total_ratings": 150,
            "recent_ratings": 20,
            "rating_distribution": {
                "5": 80,
                "4": 50,
                "3": 15,
                "2": 3,
                "1": 2
            }
        }
    """
    
    user_id: str
    weighted_average: float = Field(..., description="Weighted average (1-5)")
    total_ratings: int = Field(..., description="Total number of ratings")
    recent_ratings: int = Field(..., description="Count of last 20 ratings")
    rating_distribution: dict[str, int] = Field(..., description="Breakdown by star")


class RatingStatsResponse(BaseModel):
    """
    Rating statistics for a user.
    
    Attributes:
        user_id: User UUID
        total_ratings: Total number of ratings
        average_rating: Simple average
        weighted_average: Weighted average (outliers reduced)
        five_star: Count of 5-star ratings
        four_star: Count of 4-star ratings
        three_star: Count of 3-star ratings
        two_star: Count of 2-star ratings
        one_star: Count of 1-star ratings
        most_recent_rating: Latest rating received
    
    Example Response:
        {
            "user_id": "123e4567-e89b-12d3-a456-426614174000",
            "total_ratings": 150,
            "average_rating": 4.6,
            "weighted_average": 4.7,
            "five_star": 80,
            "four_star": 50,
            "three_star": 15,
            "two_star": 3,
            "one_star": 2,
            "most_recent_rating": 5.0
        }
    """
    
    user_id: UUID
    total_ratings: int
    average_rating: float
    weighted_average: float
    five_star: int = Field(..., alias="5_star")
    four_star: int = Field(..., alias="4_star")
    three_star: int = Field(..., alias="3_star")
    two_star: int = Field(..., alias="2_star")
    one_star: int = Field(..., alias="1_star")
    most_recent_rating: Optional[float] = None
    
    class Config:
        populate_by_name = True
