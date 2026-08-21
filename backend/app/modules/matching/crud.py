"""
Module: Matching - CRUD Operations
Purpose: Async database operations for matching records and preferences.
Authors: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: All functions are async and use SQLAlchemy 2.0 style queries.
"""

import logging
from uuid import UUID
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, update, delete, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.modules.matching.models import MatchRecord, MatchPreference, MatchStatusEnum
from app.modules.matching.schemas import MatchPreferenceCreate, MatchPreferenceUpdate

logger = logging.getLogger(__name__)


# ============================================
# MATCH RECORD CRUD OPERATIONS
# ============================================

async def create_match_record(
    db: AsyncSession,
    ride_id: UUID,
    driver_id: UUID,
    passenger_id: UUID,
    match_score: float,
    distance_score: float,
    time_score: float,
    preference_score: float,
    distance_km: float,
    estimated_pickup_time: int,
    expires_minutes: int = 15,
    metadata: str = None
) -> MatchRecord:
    """
    Create a new match record in database.
    
    Args:
        db: Async database session
        ride_id: UUID of the ride
        driver_id: UUID of the driver
        passenger_id: UUID of the passenger
        match_score: Overall match score (0-100)
        distance_score: Distance compatibility score
        time_score: Time compatibility score
        preference_score: Preference matching score
        distance_km: Distance from driver to pickup
        estimated_pickup_time: Estimated pickup time in minutes
        expires_minutes: Minutes until match expires (default 15)
        metadata: Optional JSON metadata string
    
    Returns:
        Created MatchRecord instance
    
    Raises:
        HTTPException: If database operation fails
    
    Example:
        >>> match = await create_match_record(
        ...     db, ride_id, driver_id, passenger_id,
        ...     match_score=87.5, distance_score=90.0,
        ...     time_score=85.0, preference_score=100.0,
        ...     distance_km=2.5, estimated_pickup_time=7
        ... )
    """
    
    try:
        # Calculate expiration time
        expires_at = datetime.utcnow() + timedelta(minutes=expires_minutes)
        
        # Create new match record
        match_record = MatchRecord(
            ride_id=ride_id,
            driver_id=driver_id,
            passenger_id=passenger_id,
            match_score=match_score,
            distance_score=distance_score,
            time_score=time_score,
            preference_score=preference_score,
            distance_km=distance_km,
            estimated_pickup_time=estimated_pickup_time,
            status=MatchStatusEnum.PROPOSED,
            expires_at=expires_at,
            metadata=metadata
        )
        
        db.add(match_record)
        await db.commit()
        await db.refresh(match_record)
        
        logger.info(f"Created match record {match_record.id} for ride {ride_id} with driver {driver_id}")
        return match_record
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating match record: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create match record: {str(e)}"
        )


async def get_match_by_id(db: AsyncSession, match_id: UUID) -> Optional[MatchRecord]:
    """
    Retrieve match record by ID.
    
    Args:
        db: Async database session
        match_id: UUID of the match record
    
    Returns:
        MatchRecord if found, None otherwise
    
    Example:
        >>> match = await get_match_by_id(db, match_id)
        >>> if match:
        ...     print(f"Match score: {match.match_score}")
    """
    
    try:
        stmt = select(MatchRecord).where(MatchRecord.id == match_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
        
    except Exception as e:
        logger.error(f"Error fetching match {match_id}: {str(e)}")
        return None


async def get_match_by_id_with_relations(db: AsyncSession, match_id: UUID) -> Optional[MatchRecord]:
    """
    Retrieve match record by ID with all relationships loaded.
    
    Args:
        db: Async database session
        match_id: UUID of the match record
    
    Returns:
        MatchRecord with loaded ride, driver, passenger relationships
    
    Example:
        >>> match = await get_match_by_id_with_relations(db, match_id)
        >>> print(f"Driver: {match.driver.user.full_name}")
    """
    
    try:
        stmt = (
            select(MatchRecord)
            .where(MatchRecord.id == match_id)
            .options(
                selectinload(MatchRecord.ride),
                selectinload(MatchRecord.driver),
                selectinload(MatchRecord.passenger)
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
        
    except Exception as e:
        logger.error(f"Error fetching match {match_id} with relations: {str(e)}")
        return None


async def get_matches_for_ride(
    db: AsyncSession,
    ride_id: UUID,
    status_filter: Optional[MatchStatusEnum] = None,
    limit: int = 50
) -> List[MatchRecord]:
    """
    Get all match records for a specific ride.
    
    Args:
        db: Async database session
        ride_id: UUID of the ride
        status_filter: Optional status filter (proposed/accepted/etc)
        limit: Maximum number of matches to return
    
    Returns:
        List of MatchRecord instances ordered by match_score descending
    
    Example:
        >>> matches = await get_matches_for_ride(db, ride_id, MatchStatusEnum.PROPOSED, 10)
        >>> for match in matches:
        ...     print(f"Driver {match.driver_id}: score {match.match_score}")
    """
    
    try:
        conditions = [MatchRecord.ride_id == ride_id]
        
        if status_filter:
            conditions.append(MatchRecord.status == status_filter)
        
        stmt = (
            select(MatchRecord)
            .where(and_(*conditions))
            .order_by(desc(MatchRecord.match_score))
            .limit(limit)
        )
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
        
    except Exception as e:
        logger.error(f"Error fetching matches for ride {ride_id}: {str(e)}")
        return []


async def get_user_match_history(
    db: AsyncSession,
    user_id: UUID,
    as_driver: bool = False,
    limit: int = 100
) -> List[MatchRecord]:
    """
    Get match history for a user (as passenger or driver).
    
    Args:
        db: Async database session
        user_id: UUID of the user
        as_driver: If True, get matches where user is driver; else passenger
        limit: Maximum number of matches to return
    
    Returns:
        List of MatchRecord instances ordered by created_at descending
    
    Example:
        >>> # Get passenger match history
        >>> matches = await get_user_match_history(db, user_id, as_driver=False, limit=20)
        
        >>> # Get driver match history
        >>> matches = await get_user_match_history(db, user_id, as_driver=True, limit=20)
    """
    
    try:
        if as_driver:
            condition = MatchRecord.driver_id == user_id
        else:
            condition = MatchRecord.passenger_id == user_id
        
        stmt = (
            select(MatchRecord)
            .where(condition)
            .order_by(desc(MatchRecord.created_at))
            .limit(limit)
        )
        
        result = await db.execute(stmt)
        return list(result.scalars().all())
        
    except Exception as e:
        logger.error(f"Error fetching match history for user {user_id}: {str(e)}")
        return []


async def update_match_status(
    db: AsyncSession,
    match_id: UUID,
    new_status: MatchStatusEnum
) -> Optional[MatchRecord]:
    """
    Update status of a match record.
    
    Args:
        db: Async database session
        match_id: UUID of the match record
        new_status: New status value
    
    Returns:
        Updated MatchRecord if successful, None otherwise
    
    Raises:
        HTTPException: If match not found or update fails
    
    Example:
        >>> match = await update_match_status(db, match_id, MatchStatusEnum.ASSIGNED)
        >>> print(f"Match status updated to: {match.status}")
    """
    
    try:
        # Fetch existing match
        match = await get_match_by_id(db, match_id)
        if not match:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Match record {match_id} not found"
            )
        
        # Update status
        match.status = new_status
        match.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(match)
        
        logger.info(f"Updated match {match_id} status to {new_status}")
        return match
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating match status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update match status: {str(e)}"
        )


async def expire_old_matches(db: AsyncSession, cutoff_time: datetime = None) -> int:
    """
    Expire match records that have passed their expiration time.
    
    Args:
        db: Async database session
        cutoff_time: Expiration cutoff (default: current time)
    
    Returns:
        Number of matches expired
    
    Example:
        >>> expired_count = await expire_old_matches(db)
        >>> print(f"Expired {expired_count} old matches")
    """
    
    if cutoff_time is None:
        cutoff_time = datetime.utcnow()
    
    try:
        stmt = (
            update(MatchRecord)
            .where(
                and_(
                    MatchRecord.expires_at <= cutoff_time,
                    MatchRecord.status == MatchStatusEnum.PROPOSED
                )
            )
            .values(status=MatchStatusEnum.EXPIRED, updated_at=datetime.utcnow())
        )
        
        result = await db.execute(stmt)
        await db.commit()
        
        expired_count = result.rowcount
        logger.info(f"Expired {expired_count} old match records")
        return expired_count
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error expiring old matches: {str(e)}")
        return 0


# ============================================
# MATCH PREFERENCE CRUD OPERATIONS
# ============================================

async def create_match_preference(
    db: AsyncSession,
    user_id: UUID,
    preference_data: MatchPreferenceCreate
) -> MatchPreference:
    """
    Create match preferences for a user.
    
    Args:
        db: Async database session
        user_id: UUID of the user
        preference_data: MatchPreferenceCreate schema
    
    Returns:
        Created MatchPreference instance
    
    Raises:
        HTTPException: If user already has preferences or creation fails
    
    Example:
        >>> prefs = MatchPreferenceCreate(
        ...     prefer_verified_drivers=True,
        ...     max_pickup_distance_km=10.0,
        ...     min_driver_rating=4.0
        ... )
        >>> user_prefs = await create_match_preference(db, user_id, prefs)
    """
    
    try:
        # Check if preferences already exist
        existing = await get_match_preference(db, user_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User {user_id} already has match preferences. Use update instead."
            )
        
        # Create new preference record
        preference = MatchPreference(
            user_id=user_id,
            **preference_data.model_dump()
        )
        
        db.add(preference)
        await db.commit()
        await db.refresh(preference)
        
        logger.info(f"Created match preferences for user {user_id}")
        return preference
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating match preferences: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create match preferences: {str(e)}"
        )


async def get_match_preference(db: AsyncSession, user_id: UUID) -> Optional[MatchPreference]:
    """
    Get match preferences for a user.
    
    Args:
        db: Async database session
        user_id: UUID of the user
    
    Returns:
        MatchPreference if found, None otherwise
    
    Example:
        >>> prefs = await get_match_preference(db, user_id)
        >>> if prefs:
        ...     print(f"Max distance: {prefs.max_pickup_distance_km} km")
    """
    
    try:
        stmt = select(MatchPreference).where(MatchPreference.user_id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
        
    except Exception as e:
        logger.error(f"Error fetching match preferences for user {user_id}: {str(e)}")
        return None


async def update_match_preference(
    db: AsyncSession,
    user_id: UUID,
    preference_data: MatchPreferenceUpdate
) -> Optional[MatchPreference]:
    """
    Update match preferences for a user.
    
    Args:
        db: Async database session
        user_id: UUID of the user
        preference_data: MatchPreferenceUpdate schema (partial update)
    
    Returns:
        Updated MatchPreference if successful, None otherwise
    
    Raises:
        HTTPException: If preferences not found or update fails
    
    Example:
        >>> update_data = MatchPreferenceUpdate(max_pickup_distance_km=15.0)
        >>> prefs = await update_match_preference(db, user_id, update_data)
    """
    
    try:
        # Fetch existing preferences
        preference = await get_match_preference(db, user_id)
        if not preference:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Match preferences not found for user {user_id}"
            )
        
        # Update only provided fields
        update_dict = preference_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(preference, key, value)
        
        preference.updated_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(preference)
        
        logger.info(f"Updated match preferences for user {user_id}")
        return preference
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating match preferences: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update match preferences: {str(e)}"
        )


async def delete_match_preference(db: AsyncSession, user_id: UUID) -> bool:
    """
    Delete match preferences for a user.
    
    Args:
        db: Async database session
        user_id: UUID of the user
    
    Returns:
        True if deleted, False if not found
    
    Example:
        >>> deleted = await delete_match_preference(db, user_id)
        >>> print(f"Preferences deleted: {deleted}")
    """
    
    try:
        stmt = delete(MatchPreference).where(MatchPreference.user_id == user_id)
        result = await db.execute(stmt)
        await db.commit()
        
        deleted = result.rowcount > 0
        if deleted:
            logger.info(f"Deleted match preferences for user {user_id}")
        
        return deleted
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting match preferences: {str(e)}")
        return False

