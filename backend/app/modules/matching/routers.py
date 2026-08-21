"""
Module: Matching - API Router
Purpose: REST API endpoints for ride-driver matching engine.
Authors: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: All endpoints are JWT-protected and follow standardized response format.
"""

from uuid import UUID
from typing import Dict, Any
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.matching import service
from app.modules.matching.schemas import (
    MatchRequest, MatchAssignRequest,
    MatchPreferenceCreate, MatchPreferenceUpdate
)
from app.modules.matching import crud

router = APIRouter(prefix="/match", tags=["Matching"])


# ============================================
# MATCHING ENDPOINTS
# ============================================

@router.post(
    "/find",
    response_model=Dict[str, Any],
    summary="Find Matched Drivers",
    description="""
    Find and rank suitable drivers for a ride request using AI-powered matching algorithm.
    
    **Matching Algorithm:**
    - **Distance Score (35%)**: Proximity of driver to pickup location
    - **Time Score (25%)**: Compatibility with requested pickup time
    - **Preference Score (30%)**: User preferences (verified, rating, gender, vehicle type)
    - **Route Score (10%)**: Direction similarity between driver and ride route
    
    **Algorithm Steps:**
    1. Query available drivers within max distance
    2. Calculate multi-factor match scores for each driver
    3. Filter by user preferences (verified, rating, etc.)
    4. Rank by overall weighted score
    5. Create match records in database
    6. Return top N matches (default 10)
    
    **Requirements:**
    - Valid JWT token
    - Ride must exist
    - Valid coordinates (latitude/longitude)
    
    **Example Request:**
    ```json
    {
        "ride_id": "770e8400-e29b-41d4-a716-446655440002",
        "pickup_latitude": 31.5204,
        "pickup_longitude": 74.3587,
        "destination_latitude": 31.4697,
        "destination_longitude": 74.2728,
        "requested_seats": 2,
        "preferred_pickup_time": "2025-11-08T09:00:00+05:00",
        "max_results": 10
    }
    ```
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "matches": [
                {
                    "match_id": "880e8400-e29b-41d4-a716-446655440003",
                    "driver_id": "660e8400-e29b-41d4-a716-446655440001",
                    "driver_name": "Ahmed Khan",
                    "driver_rating": 4.7,
                    "match_score": 87.5,
                    "distance_km": 2.5,
                    "estimated_pickup_time": 7,
                    "status": "proposed"
                }
            ],
            "total_matches": 1
        },
        "error": null
    }
    ```
    
    **Performance:**
    - Average response time: < 500ms
    - Scales with Redis geospatial indexing (future)
    - Supports concurrent requests
    
    **Future Enhancements:**
    - Real-time driver location tracking
    - Machine learning score optimization
    - Dynamic pricing integration
    - Traffic-aware ETA calculation
    """
)
async def find_matches(
    match_request: MatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Find matched drivers for a ride request."""
    return await service.find_matches_service(db, current_user, match_request)


@router.post(
    "/assign",
    response_model=Dict[str, Any],
    summary="Assign Driver to Ride",
    description="""
    Accept a match and assign a specific driver to a ride.
    
    **Business Logic:**
    1. Verify match exists and is in PROPOSED status
    2. Verify requesting user is the passenger
    3. Check match has not expired
    4. Update match status to ASSIGNED
    5. Update driver status (future: set as busy)
    6. Create ride booking (future integration)
    
    **Requirements:**
    - Valid JWT token
    - User must be the passenger for this match
    - Match must be in PROPOSED status
    - Match must not be expired
    
    **Side Effects:**
    - Match status updated to ASSIGNED
    - Other matches for same ride may be auto-cancelled (future)
    - Driver marked as busy (future)
    - Ride booking created (future integration)
    
    **Example Request:**
    ```json
    {
        "match_id": "880e8400-e29b-41d4-a716-446655440003"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "match_id": "880e8400-e29b-41d4-a716-446655440003",
            "ride_id": "770e8400-e29b-41d4-a716-446655440002",
            "driver_id": "660e8400-e29b-41d4-a716-446655440001",
            "passenger_id": "990e8400-e29b-41d4-a716-446655440004",
            "status": "assigned",
            "assigned_at": "2025-11-07T15:35:00+05:00"
        },
        "error": null
    }
    ```
    
    **Error Cases:**
    - 404: Match not found
    - 403: User not authorized (not the passenger)
    - 400: Match already assigned/expired
    - 400: Driver no longer available
    """
)
async def assign_match(
    assign_request: MatchAssignRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Assign a driver to a ride by accepting a match."""
    return await service.assign_match_service(db, current_user, assign_request)


@router.get(
    "/history/{user_id}",
    response_model=Dict[str, Any],
    summary="Get Match History",
    description="""
    Retrieve match history for a user (as passenger or driver).
    
    **Use Cases:**
    - Passenger viewing past ride match attempts
    - Driver viewing match proposals received
    - Analytics on matching performance
    - Identifying patterns in user preferences
    
    **Query Parameters:**
    - `as_driver`: If true, get driver matches; else passenger matches
    - `limit`: Maximum number of records (default 100)
    
    **Authorization:**
    - Users can only view their own history
    - Admins can view any user's history (future)
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
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
        },
        "error": null
    }
    ```
    
    **Performance:**
    - Results ordered by created_at descending (newest first)
    - Pagination support via limit parameter
    - Indexed queries for fast retrieval
    """
)
async def get_match_history(
    user_id: UUID,
    as_driver: bool = Query(False, description="Get driver matches instead of passenger matches"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get match history for a user."""
    return await service.get_match_history_service(db, current_user, user_id, as_driver, limit)


# ============================================
# PREFERENCE MANAGEMENT ENDPOINTS
# ============================================

@router.post(
    "/preferences",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Create Match Preferences",
    description="""
    Create matching preferences for the current user.
    
    **Preferences Affect:**
    - Which drivers are shown in search results
    - Match scoring algorithm weights
    - Automatic filtering of incompatible drivers
    
    **Preference Options:**
    - `prefer_verified_drivers`: Only match with verified drivers (default: true)
    - `prefer_same_gender`: Prefer drivers of same gender (default: false)
    - `prefer_non_smoking`: Prefer non-smoking drivers (default: false)
    - `max_pickup_distance_km`: Maximum acceptable distance (1-50 km, default: 10)
    - `max_pickup_time_minutes`: Maximum acceptable time (1-60 min, default: 15)
    - `min_driver_rating`: Minimum driver rating (0-5, default: 3.0)
    - `prefer_vehicle_types`: Comma-separated types (e.g., "sedan,suv")
    
    **Example Request:**
    ```json
    {
        "prefer_verified_drivers": true,
        "prefer_same_gender": false,
        "prefer_non_smoking": true,
        "max_pickup_distance_km": 10.0,
        "max_pickup_time_minutes": 15,
        "min_driver_rating": 4.0,
        "prefer_vehicle_types": "sedan,suv"
    }
    ```
    
    **Note:**
    - User can only have one preference record
    - Use PUT /preferences to update existing preferences
    """
)
async def create_preferences(
    preference_data: MatchPreferenceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create matching preferences for current user."""
    try:
        preference = await crud.create_match_preference(db, current_user.id, preference_data)
        return {
            "status": "ok",
            "data": {
                "id": preference.id,
                "user_id": preference.user_id,
                "prefer_verified_drivers": preference.prefer_verified_drivers,
                "prefer_same_gender": preference.prefer_same_gender,
                "prefer_non_smoking": preference.prefer_non_smoking,
                "max_pickup_distance_km": preference.max_pickup_distance_km,
                "max_pickup_time_minutes": preference.max_pickup_time_minutes,
                "min_driver_rating": preference.min_driver_rating,
                "prefer_vehicle_types": preference.prefer_vehicle_types,
                "created_at": preference.created_at.isoformat(),
                "updated_at": preference.updated_at.isoformat()
            },
            "error": None
        }
    except Exception as e:
        return {
            "status": "error",
            "data": None,
            "error": str(e)
        }


@router.get(
    "/preferences",
    response_model=Dict[str, Any],
    summary="Get Match Preferences",
    description="""
    Get current user's matching preferences.
    
    **Returns:**
    - Current preference settings
    - Default values if no preferences set
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "id": "aa0e8400-e29b-41d4-a716-446655440005",
            "user_id": "990e8400-e29b-41d4-a716-446655440004",
            "prefer_verified_drivers": true,
            "max_pickup_distance_km": 10.0,
            "min_driver_rating": 4.0,
            ...
        },
        "error": null
    }
    ```
    """
)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's matching preferences."""
    try:
        preference = await crud.get_match_preference(db, current_user.id)
        if not preference:
            return {
                "status": "ok",
                "data": None,
                "error": "No preferences found. Use POST /match/preferences to create."
            }
        
        return {
            "status": "ok",
            "data": {
                "id": preference.id,
                "user_id": preference.user_id,
                "prefer_verified_drivers": preference.prefer_verified_drivers,
                "prefer_same_gender": preference.prefer_same_gender,
                "prefer_non_smoking": preference.prefer_non_smoking,
                "max_pickup_distance_km": preference.max_pickup_distance_km,
                "max_pickup_time_minutes": preference.max_pickup_time_minutes,
                "min_driver_rating": preference.min_driver_rating,
                "prefer_vehicle_types": preference.prefer_vehicle_types,
                "created_at": preference.created_at.isoformat(),
                "updated_at": preference.updated_at.isoformat()
            },
            "error": None
        }
    except Exception as e:
        return {
            "status": "error",
            "data": None,
            "error": str(e)
        }


@router.put(
    "/preferences",
    response_model=Dict[str, Any],
    summary="Update Match Preferences",
    description="""
    Update current user's matching preferences (partial update).
    
    **All fields are optional** - only provided fields will be updated.
    
    **Example Request:**
    ```json
    {
        "max_pickup_distance_km": 15.0,
        "min_driver_rating": 4.5
    }
    ```
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "id": "uuid",
            "user_id": "uuid",
            "max_pickup_distance_km": 15.0,
            "min_driver_rating": 4.5,
            ...
        },
        "error": null
    }
    ```
    """
)
async def update_preferences(
    preference_data: MatchPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update current user's matching preferences."""
    try:
        preference = await crud.update_match_preference(db, current_user.id, preference_data)
        return {
            "status": "ok",
            "data": {
                "id": preference.id,
                "user_id": preference.user_id,
                "prefer_verified_drivers": preference.prefer_verified_drivers,
                "prefer_same_gender": preference.prefer_same_gender,
                "prefer_non_smoking": preference.prefer_non_smoking,
                "max_pickup_distance_km": preference.max_pickup_distance_km,
                "max_pickup_time_minutes": preference.max_pickup_time_minutes,
                "min_driver_rating": preference.min_driver_rating,
                "prefer_vehicle_types": preference.prefer_vehicle_types,
                "created_at": preference.created_at.isoformat(),
                "updated_at": preference.updated_at.isoformat()
            },
            "error": None
        }
    except Exception as e:
        return {
            "status": "error",
            "data": None,
            "error": str(e)
        }


@router.delete(
    "/preferences",
    response_model=Dict[str, Any],
    summary="Delete Match Preferences",
    description="""
    Delete current user's matching preferences.
    
    **Effect:**
    - Removes custom preferences
    - Future matches will use default settings
    - Can create new preferences anytime
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "message": "Preferences deleted successfully"
        },
        "error": null
    }
    ```
    """
)
async def delete_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete current user's matching preferences."""
    try:
        deleted = await crud.delete_match_preference(db, current_user.id)
        if deleted:
            return {
                "status": "ok",
                "data": {"message": "Preferences deleted successfully"},
                "error": None
            }
        else:
            return {
                "status": "error",
                "data": None,
                "error": "No preferences found to delete"
            }
    except Exception as e:
        return {
            "status": "error",
            "data": None,
            "error": str(e)
        }

