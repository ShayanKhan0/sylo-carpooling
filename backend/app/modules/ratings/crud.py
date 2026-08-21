"""
Ratings Module - CRUD Operations

Database operations for ratings management.
"""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.rating import Rating
from app.models.ride import Ride
from app.models.booking import Booking
from app.modules.auth.models import User
from app.models.driver import Driver

logger = logging.getLogger(__name__)


async def get_rating_by_ride_and_user(
    db: AsyncSession,
    ride_id: UUID,
    from_user_id: UUID
) -> Optional[Rating]:
    """
    Check if a rating already exists for this ride from this user.
    
    Args:
        db: Database session
        ride_id: ID of the ride
        from_user_id: ID of the user who is rating
        
    Returns:
        Rating object if exists, None otherwise
    """
    query = select(Rating).where(
        and_(
            Rating.ride_id == ride_id,
            Rating.rater_id == from_user_id
        )
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def create_rating(
    db: AsyncSession,
    ride_id: UUID,
    from_user_id: UUID,
    to_user_id: UUID,
    rating: int,
    comment: Optional[str] = None
) -> Rating:
    """
    Create a new rating in the database.
    
    Args:
        db: Database session
        ride_id: ID of the completed ride
        from_user_id: ID of user giving the rating
        to_user_id: ID of user receiving the rating
        rating: Rating value (1-5)
        comment: Optional comment
        
    Returns:
        Created Rating object
    """
    new_rating = Rating(
        ride_id=ride_id,
        rater_id=from_user_id,
        ratee_id=to_user_id,
        score=rating,
        comment=comment
    )
    
    db.add(new_rating)
    await db.commit()
    await db.refresh(new_rating)
    
    logger.info(f"Rating created: {new_rating.id} - User {from_user_id} rated User {to_user_id} with {rating} stars")
    
    return new_rating


async def get_ratings_for_user(
    db: AsyncSession,
    user_id: UUID,
    skip: int = 0,
    limit: int = 10
) -> tuple[list[Rating], int]:
    """
    Get paginated list of ratings received by a user.
    
    Args:
        db: Database session
        user_id: ID of user whose ratings to retrieve
        skip: Number of records to skip (pagination)
        limit: Maximum number of records to return
        
    Returns:
        Tuple of (list of ratings, total count)
    """
    # Count query
    count_query = select(func.count(Rating.id)).where(Rating.ratee_id == user_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Data query with user info
    query = (
        select(Rating)
        .options(
            selectinload(Rating.rater),
            selectinload(Rating.ratee)
        )
        .where(Rating.ratee_id == user_id)
        .order_by(desc(Rating.created_at))
        .offset(skip)
        .limit(limit)
    )
    
    result = await db.execute(query)
    ratings = result.scalars().all()
    
    return list(ratings), total


async def get_user_rating_stats(
    db: AsyncSession,
    user_id: UUID
) -> dict:
    """
    Calculate weighted average rating for a user.
    
    Weighting formula:
    - Last 20 ratings: 70% weight
    - Older ratings: 30% weight
    
    Args:
        db: Database session
        user_id: ID of user
        
    Returns:
        Dictionary with rating statistics
    """
    # Get all ratings ordered by newest first
    query = (
        select(Rating.score)
        .where(Rating.ratee_id == user_id)
        .order_by(desc(Rating.created_at))
    )
    
    result = await db.execute(query)
    all_ratings = result.scalars().all()
    
    total_count = len(all_ratings)
    
    if total_count == 0:
        return {
            "average_rating": 0.0,
            "rating_count": 0,
            "recent_ratings_count": 0,
            "recent_average": None,
            "older_average": None
        }
    
    # Split into recent (last 20) and older
    recent_ratings = all_ratings[:20]
    older_ratings = all_ratings[20:]
    
    recent_avg = sum(recent_ratings) / len(recent_ratings) if recent_ratings else 0.0
    older_avg = sum(older_ratings) / len(older_ratings) if older_ratings else 0.0
    
    # Calculate weighted average
    if len(older_ratings) == 0:
        # If 20 or fewer ratings, use simple average
        weighted_avg = recent_avg
    else:
        # Apply 70/30 weighting
        weighted_avg = (recent_avg * 0.7) + (older_avg * 0.3)
    
    return {
        "average_rating": round(weighted_avg, 2),
        "rating_count": total_count,
        "recent_ratings_count": len(recent_ratings),
        "recent_average": round(recent_avg, 2) if recent_ratings else None,
        "older_average": round(older_avg, 2) if older_ratings else None
    }


async def update_user_cached_rating(
    db: AsyncSession,
    user_id: UUID
) -> None:
    """
    Update cached rating fields in users table.
    
    Updates:
    - users.rating_avg
    - users.rating_count
    
    Args:
        db: Database session
        user_id: ID of user to update
    """
    stats = await get_user_rating_stats(db, user_id)
    
    # Update user table
    user_query = select(User).where(User.id == user_id)
    result = await db.execute(user_query)
    user = result.scalar_one_or_none()
    
    if user:
        user.rating_avg = stats["average_rating"]
        user.rating_count = stats["rating_count"]
        await db.commit()
        logger.info(f"Updated user {user_id} rating cache: {stats['average_rating']} ({stats['rating_count']} ratings)")


async def update_driver_cached_rating(
    db: AsyncSession,
    user_id: UUID
) -> None:
    """
    Update cached rating fields in drivers table.
    
    Updates:
    - drivers.rating_avg
    - drivers.rating_count (if using this field)
    
    Args:
        db: Database session
        user_id: ID of driver to update
    """
    stats = await get_user_rating_stats(db, user_id)
    
    # Check if user is a driver
    driver_query = select(Driver).where(Driver.user_id == user_id)
    result = await db.execute(driver_query)
    driver = result.scalar_one_or_none()
    
    if driver:
        driver.rating_avg = stats["average_rating"]
        # Note: Driver model uses rating_count field name
        if hasattr(driver, 'rating_count'):
            driver.rating_count = stats["rating_count"]
        await db.commit()
        logger.info(f"Updated driver {user_id} rating cache: {stats['average_rating']} ({stats['rating_count']} ratings)")


async def get_ride_details(
    db: AsyncSession,
    ride_id: UUID
) -> Optional[Ride]:
    """
    Get ride details with driver information.
    
    Args:
        db: Database session
        ride_id: ID of ride
        
    Returns:
        Ride object with loaded relationships
    """
    query = (
        select(Ride)
        .options(selectinload(Ride.driver))
        .where(Ride.id == ride_id)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def check_user_in_ride(
    db: AsyncSession,
    ride_id: UUID,
    user_id: UUID
) -> tuple[bool, Optional[str]]:
    """
    Check if user participated in the ride and determine their role.
    
    Args:
        db: Database session
        ride_id: ID of ride
        user_id: ID of user
        
    Returns:
        Tuple of (is_participant, role) where role is 'driver' or 'passenger'
    """
    # Check if user is the driver
    ride_query = select(Ride).where(Ride.id == ride_id)
    ride_result = await db.execute(ride_query)
    ride = ride_result.scalar_one_or_none()
    
    if not ride:
        return False, None
    
    if ride.driver_id == user_id:
        return True, "driver"
    
    # Check if user is a passenger (has a booking)
    booking_query = select(Booking).where(
        and_(
            Booking.ride_id == ride_id,
            Booking.passenger_id == user_id
        )
    )
    booking_result = await db.execute(booking_query)
    booking = booking_result.scalar_one_or_none()
    
    if booking:
        return True, "passenger"
    
    return False, None
