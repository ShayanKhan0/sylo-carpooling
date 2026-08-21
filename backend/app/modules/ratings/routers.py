"""
Ratings API Router (Prompt 11A - EXACT SPECIFICATION)

Implements exact API endpoints from Prompt 11A:
- POST /api/v1/ratings - Create rating
- GET /api/v1/ratings/user/{user_id} - List user ratings (pagination)
- GET /api/v1/ratings/average/{user_id} - Weighted average (70% last 20, 30% older)

Author: Smart Carpooling Backend Team  
Date: December 19, 2025
Prompt: 11A - Ratings System
"""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.ratings.service import RatingService
from app.modules.ratings import schemas
from app.core.exceptions import NotFoundException, BadRequestException, ForbiddenException

router = APIRouter(prefix="/ratings", tags=["Ratings (Prompt 11A)"])


@router.post(
    "",  # POST /api/v1/ratings (Prompt 11A exact spec)
    response_model=schemas.RatingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create rating (Prompt 11A)",
    description="""
    **Prompt 11A Specification**
    
    Submit a rating for a completed ride.
    
    **Constraints:**
    - One rating per (ride_id, from_user_id, to_user_id)
    - Rating allowed after passenger dropoff completion (or when ride is completed)
    - Passenger can rate driver, driver can rate passenger
    - Prevent self-rating
    - Rating value: 1-5 (integer)
    - Comment: max 500 characters (optional)
    - to_user_id / booking_id can be provided for explicit target context
    
    **Updates Cached Averages:**
    - users.rating_avg
    - users.rating_count
    - drivers.rating_avg (if applicable)
    - drivers.rating_count
    
    **Returns:** HTTP 201 with rating details
    **Errors:** 
    - 400: Invalid request (duplicate, incomplete ride)
    - 403: Not authorized (not ride participant)
    - 404: Ride not found
    - 409: Duplicate rating
    """
)
async def create_rating(
    data: schemas.RatingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create rating (Prompt 11A).
    
    Body: ride_id, rating (1-5), comment (optional)
    """
    try:
        service = RatingService(db)
        rating = await service.submit_rating(
            ride_id=data.ride_id,
            from_user_id=current_user.id,
            rating_value=data.rating,
            target_user_id=data.to_user_id,
            booking_id=data.booking_id,
            comment=data.comment
        )
        return rating
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BadRequestException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.get(
    "/user/{user_id}",
    response_model=schemas.RatingListResponse,
    summary="List user ratings (Prompt 11A)",
    description="""
    **Prompt 11A Specification**
    
    Get paginated list of ratings for a user.
    
    **Query Parameters:**
    - as_rater: If true, get ratings user gave; if false, get ratings user received
    - page: Page number (1-indexed, default 1)
    - page_size: Items per page (default 20, max 100)
    
    **Returns:**
    - Paginated list of ratings
    - Total count
    - Page metadata
    """
)
async def get_user_ratings(
    user_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    as_rater: bool = Query(False, description="Get ratings user gave vs received"),
    db: AsyncSession = Depends(get_db)
):
    """Get paginated list of ratings for a user (Prompt 11A)."""
    service = RatingService(db)
    result = await service.get_user_ratings(
        user_id=user_id,
        page=page,
        page_size=page_size,
        as_rater=as_rater
    )
    return result


@router.get(
    "/average/{user_id}",
    response_model=schemas.WeightedAverageResponse,
    summary="Get weighted average rating (Prompt 11A)",
    description="""
    **Prompt 11A Specification**
    
    Get weighted average rating for a user (driver or passenger).
    
    **Weighting Algorithm (EXACT from Prompt 11A):**
    - Last 20 ratings: 70% weight
    - Remaining older ratings: 30% weight
    
    **Formula:**
    ```
    weighted_avg = (avg_last_20 * 0.7) + (avg_older * 0.3)
    ```
    
    **Purpose:**
    - Emphasize recent performance
    - Maintain historical context
    - Fair and balanced rating system
    
    **Returns:**
    - Weighted average (1-5)
    - Total ratings count
    - Recent ratings count (last 20)
    - Rating distribution (breakdown by star)
    """
)
async def get_average_rating(
    user_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get weighted average rating for a user (Prompt 11A)."""
    service = RatingService(db)
    return await service.get_weighted_average_prompt11a(user_id=user_id)


@router.get(
    "/passenger/{passenger_id}/average",
    response_model=schemas.WeightedAverageResponse,
    summary="Get passenger weighted average rating",
    description="Get weighted average rating for a passenger (same algorithm as drivers)"
)
async def get_passenger_average(
    passenger_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get weighted average rating for a passenger."""
    service = RatingService(db)
    return await service.get_weighted_average(user_id=passenger_id)


@router.get(
    "/ride/{ride_id}",
    response_model=Optional[schemas.RatingResponse],
    summary="Get rating for a specific ride",
    description="""
    Get rating for a specific ride by the current user.
    
    **Use Case:**
    - Check if user already rated a ride
    - Display user's submitted rating
    """
)
async def get_ride_rating(
    ride_id: UUID,
    to_user_id: Optional[UUID] = Query(
        default=None,
        description="Optional target user UUID to fetch a specific counterpart rating",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get rating for a specific ride by current user."""
    service = RatingService(db)
    rating = await service.get_ride_rating(
        ride_id=ride_id,
        user_id=current_user.id,
        to_user_id=to_user_id,
    )
    return rating


@router.get(
    "/stats/{user_id}",
    response_model=schemas.RatingStatsResponse,
    summary="Get comprehensive rating statistics",
    description="""
    Get detailed rating statistics for a user.
    
    **Includes:**
    - Total ratings count
    - Simple average rating
    - Weighted average rating
    - Breakdown by star (5-star, 4-star, etc.)
    - Most recent rating received
    """
)
async def get_rating_stats(
    user_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive rating statistics."""
    service = RatingService(db)
    return await service.get_rating_stats(user_id=user_id)


@router.put(
    "/{rating_id}",
    response_model=schemas.RatingResponse,
    summary="Update an existing rating",
    description="""
    Update an existing rating.
    
    **Authorization:**
    - Only the user who created the rating can update it
    
    **Note:**
    - Updated ratings reset the updated_at timestamp
    - Original creation date is preserved
    """
)
async def update_rating(
    rating_id: UUID,
    data: schemas.RatingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an existing rating."""
    try:
        service = RatingService(db)
        rating = await service.update_rating(
            rating_id=rating_id,
            user_id=current_user.id,
            rating_value=data.rating,
            comment=data.comment
        )
        return rating
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.delete(
    "/{rating_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a rating",
    description="""
    Delete a rating.
    
    **Authorization:**
    - Only the user who created the rating can delete it
    
    **Note:**
    - This is a permanent deletion
    - Cannot be undone
    """
)
async def delete_rating(
    rating_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a rating."""
    try:
        service = RatingService(db)
        await service.delete_rating(rating_id=rating_id, user_id=current_user.id)
        return None
    except NotFoundException as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ForbiddenException as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
