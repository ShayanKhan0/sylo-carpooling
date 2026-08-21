"""
Module: Matching - Pydantic Schemas
Purpose: Request/response validation schemas for matching engine.
Authors: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: All schemas include examples for Swagger UI documentation.
"""

from uuid import UUID
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator

from app.modules.matching.models import MatchStatusEnum


# ============================================
# MATCH REQUEST SCHEMAS
# ============================================

class MatchRequest(BaseModel):
    """
    Schema for requesting driver matches for a ride.
    
    Used by passengers to find suitable drivers for their ride request.
    """
    
    ride_id: UUID = Field(..., description="UUID of the ride to match drivers for")
    pickup_latitude: float = Field(..., ge=-90, le=90, description="Pickup location latitude")
    pickup_longitude: float = Field(..., ge=-180, le=180, description="Pickup location longitude")
    destination_latitude: float = Field(..., ge=-90, le=90, description="Destination latitude")
    destination_longitude: float = Field(..., ge=-180, le=180, description="Destination longitude")
    requested_seats: int = Field(..., ge=1, le=8, description="Number of seats needed")
    preferred_pickup_time: Optional[datetime] = Field(None, description="Preferred pickup time")
    max_results: int = Field(10, ge=1, le=50, description="Maximum number of matches to return")
    
    class Config:
        json_schema_extra = {
            "example": {
                "ride_id": "770e8400-e29b-41d4-a716-446655440002",
                "pickup_latitude": 31.5204,
                "pickup_longitude": 74.3587,
                "destination_latitude": 31.4697,
                "destination_longitude": 74.2728,
                "requested_seats": 2,
                "preferred_pickup_time": "2025-11-08T09:00:00+05:00",
                "max_results": 10
            }
        }


class MatchAssignRequest(BaseModel):
    """
    Schema for assigning a specific driver to a ride.
    
    Used to lock in a driver-rider match and create booking.
    """
    
    match_id: UUID = Field(..., description="UUID of the match record to assign")
    
    class Config:
        json_schema_extra = {
            "example": {
                "match_id": "880e8400-e29b-41d4-a716-446655440003"
            }
        }


# ============================================
# MATCH RESPONSE SCHEMAS
# ============================================

class DriverMatchInfo(BaseModel):
    """
    Schema for individual driver match information.
    
    Contains driver details and match scoring information.
    """
    
    match_id: UUID = Field(..., description="UUID of this match record")
    driver_id: UUID = Field(..., description="UUID of matched driver")
    driver_name: str = Field(..., description="Driver's full name")
    driver_rating: Optional[float] = Field(None, description="Driver's average rating (0-5)")
    vehicle_type: Optional[str] = Field(None, description="Vehicle type (sedan/suv/etc)")
    vehicle_model: Optional[str] = Field(None, description="Vehicle model")
    available_seats: int = Field(..., description="Number of available seats")
    
    # Match Scores
    match_score: float = Field(..., ge=0, le=100, description="Overall match score (0-100)")
    distance_score: float = Field(..., ge=0, le=100, description="Distance compatibility score")
    time_score: float = Field(..., ge=0, le=100, description="Time compatibility score")
    preference_score: float = Field(..., ge=0, le=100, description="Preference matching score")
    
    # Match Metrics
    distance_km: float = Field(..., description="Distance from driver to pickup (km)")
    estimated_pickup_time: int = Field(..., description="Estimated pickup time (minutes)")
    
    # Status
    status: MatchStatusEnum = Field(..., description="Current match status")
    created_at: datetime = Field(..., description="When match was generated")
    expires_at: Optional[datetime] = Field(None, description="When match expires")
    
    class Config:
        json_schema_extra = {
            "example": {
                "match_id": "880e8400-e29b-41d4-a716-446655440003",
                "driver_id": "660e8400-e29b-41d4-a716-446655440001",
                "driver_name": "Ahmed Khan",
                "driver_rating": 4.7,
                "vehicle_type": "sedan",
                "vehicle_model": "Honda Civic 2020",
                "available_seats": 3,
                "match_score": 87.5,
                "distance_score": 90.0,
                "time_score": 85.0,
                "preference_score": 100.0,
                "distance_km": 2.5,
                "estimated_pickup_time": 7,
                "status": "proposed",
                "created_at": "2025-11-07T15:30:00+05:00",
                "expires_at": "2025-11-07T15:45:00+05:00"
            }
        }


class MatchResponse(BaseModel):
    """
    Schema for match finding response.
    
    Returns list of matched drivers sorted by match score.
    """
    
    matches: List[DriverMatchInfo] = Field(..., description="List of matched drivers")
    total_matches: int = Field(..., description="Total number of matches found")
    
    class Config:
        json_schema_extra = {
            "example": {
                "matches": [
                    {
                        "match_id": "880e8400-e29b-41d4-a716-446655440003",
                        "driver_id": "660e8400-e29b-41d4-a716-446655440001",
                        "driver_name": "Ahmed Khan",
                        "driver_rating": 4.7,
                        "vehicle_type": "sedan",
                        "vehicle_model": "Honda Civic 2020",
                        "available_seats": 3,
                        "match_score": 87.5,
                        "distance_score": 90.0,
                        "time_score": 85.0,
                        "preference_score": 100.0,
                        "distance_km": 2.5,
                        "estimated_pickup_time": 7,
                        "status": "proposed",
                        "created_at": "2025-11-07T15:30:00+05:00",
                        "expires_at": "2025-11-07T15:45:00+05:00"
                    }
                ],
                "total_matches": 1
            }
        }


class MatchAssignResponse(BaseModel):
    """
    Schema for match assignment response.
    
    Confirms successful driver-rider assignment.
    """
    
    match_id: UUID = Field(..., description="UUID of assigned match")
    ride_id: UUID = Field(..., description="UUID of the ride")
    driver_id: UUID = Field(..., description="UUID of assigned driver")
    passenger_id: UUID = Field(..., description="UUID of the passenger")
    status: MatchStatusEnum = Field(..., description="Updated match status (assigned)")
    assigned_at: datetime = Field(..., description="When assignment occurred")
    
    class Config:
        json_schema_extra = {
            "example": {
                "match_id": "880e8400-e29b-41d4-a716-446655440003",
                "ride_id": "770e8400-e29b-41d4-a716-446655440002",
                "driver_id": "660e8400-e29b-41d4-a716-446655440001",
                "passenger_id": "990e8400-e29b-41d4-a716-446655440004",
                "status": "assigned",
                "assigned_at": "2025-11-07T15:35:00+05:00"
            }
        }


# ============================================
# MATCH HISTORY SCHEMAS
# ============================================

class MatchHistoryRecord(BaseModel):
    """
    Schema for individual match history record.
    
    Simplified view for historical match queries.
    """
    
    match_id: UUID = Field(..., description="UUID of match record")
    ride_id: UUID = Field(..., description="UUID of the ride")
    driver_id: UUID = Field(..., description="UUID of driver")
    passenger_id: UUID = Field(..., description="UUID of passenger")
    match_score: float = Field(..., description="Overall match score")
    distance_km: float = Field(..., description="Distance from driver to pickup")
    status: MatchStatusEnum = Field(..., description="Match status")
    created_at: datetime = Field(..., description="When match was created")
    updated_at: datetime = Field(..., description="Last status update")
    
    class Config:
        json_schema_extra = {
            "example": {
                "match_id": "880e8400-e29b-41d4-a716-446655440003",
                "ride_id": "770e8400-e29b-41d4-a716-446655440002",
                "driver_id": "660e8400-e29b-41d4-a716-446655440001",
                "passenger_id": "990e8400-e29b-41d4-a716-446655440004",
                "match_score": 87.5,
                "distance_km": 2.5,
                "status": "assigned",
                "created_at": "2025-11-07T15:30:00+05:00",
                "updated_at": "2025-11-07T15:35:00+05:00"
            }
        }


class MatchHistoryResponse(BaseModel):
    """
    Schema for match history response.
    
    Returns paginated list of user's match history.
    """
    
    matches: List[MatchHistoryRecord] = Field(..., description="List of historical matches")
    total_count: int = Field(..., description="Total number of matches in history")
    
    class Config:
        json_schema_extra = {
            "example": {
                "matches": [
                    {
                        "match_id": "880e8400-e29b-41d4-a716-446655440003",
                        "ride_id": "770e8400-e29b-41d4-a716-446655440002",
                        "driver_id": "660e8400-e29b-41d4-a716-446655440001",
                        "passenger_id": "990e8400-e29b-41d4-a716-446655440004",
                        "match_score": 87.5,
                        "distance_km": 2.5,
                        "status": "assigned",
                        "created_at": "2025-11-07T15:30:00+05:00",
                        "updated_at": "2025-11-07T15:35:00+05:00"
                    }
                ],
                "total_count": 1
            }
        }


# ============================================
# MATCH PREFERENCE SCHEMAS
# ============================================

class MatchPreferenceBase(BaseModel):
    """Base schema for match preferences."""
    
    prefer_verified_drivers: bool = Field(True, description="Only match with verified drivers")
    prefer_same_gender: bool = Field(False, description="Prefer drivers of same gender")
    prefer_non_smoking: bool = Field(False, description="Prefer non-smoking drivers")
    max_pickup_distance_km: Optional[float] = Field(10.0, ge=1, le=50, description="Maximum pickup distance (km)")
    max_pickup_time_minutes: Optional[int] = Field(15, ge=1, le=60, description="Maximum pickup time (minutes)")
    min_driver_rating: Optional[float] = Field(3.0, ge=0, le=5, description="Minimum driver rating (0-5)")
    prefer_vehicle_types: Optional[str] = Field(None, description="Comma-separated vehicle types")


class MatchPreferenceCreate(MatchPreferenceBase):
    """Schema for creating match preferences."""
    
    class Config:
        json_schema_extra = {
            "example": {
                "prefer_verified_drivers": True,
                "prefer_same_gender": False,
                "prefer_non_smoking": True,
                "max_pickup_distance_km": 10.0,
                "max_pickup_time_minutes": 15,
                "min_driver_rating": 4.0,
                "prefer_vehicle_types": "sedan,suv"
            }
        }


class MatchPreferenceUpdate(BaseModel):
    """Schema for updating match preferences (all fields optional)."""
    
    prefer_verified_drivers: Optional[bool] = None
    prefer_same_gender: Optional[bool] = None
    prefer_non_smoking: Optional[bool] = None
    max_pickup_distance_km: Optional[float] = Field(None, ge=1, le=50)
    max_pickup_time_minutes: Optional[int] = Field(None, ge=1, le=60)
    min_driver_rating: Optional[float] = Field(None, ge=0, le=5)
    prefer_vehicle_types: Optional[str] = None


class MatchPreferencePublic(MatchPreferenceBase):
    """Schema for match preference responses."""
    
    id: UUID = Field(..., description="UUID of preference record")
    user_id: UUID = Field(..., description="UUID of user who owns preferences")
    created_at: datetime = Field(..., description="When preferences were created")
    updated_at: datetime = Field(..., description="When preferences were last updated")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "aa0e8400-e29b-41d4-a716-446655440005",
                "user_id": "990e8400-e29b-41d4-a716-446655440004",
                "prefer_verified_drivers": True,
                "prefer_same_gender": False,
                "prefer_non_smoking": True,
                "max_pickup_distance_km": 10.0,
                "max_pickup_time_minutes": 15,
                "min_driver_rating": 4.0,
                "prefer_vehicle_types": "sedan,suv",
                "created_at": "2025-11-05T10:00:00+05:00",
                "updated_at": "2025-11-07T15:00:00+05:00"
            }
        }


# ============================================
# MATCH RECORD SCHEMAS (for direct CRUD)
# ============================================

class MatchRecordPublic(BaseModel):
    """Complete match record for detailed views."""
    
    id: UUID
    ride_id: UUID
    driver_id: UUID
    passenger_id: UUID
    match_score: float
    distance_score: float
    time_score: float
    preference_score: float
    distance_km: float
    estimated_pickup_time: int
    status: MatchStatusEnum
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime]
    metadata: Optional[str]
    
    class Config:
        from_attributes = True

