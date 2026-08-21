"""
Module: Matching - Service Layer
Purpose: Core business logic for ride-driver matching algorithm.
Authors: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: Implements smart matching with distance, time, preference, and route scoring.
"""

import logging
from uuid import UUID
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.modules.matching import crud
from app.modules.matching.models import MatchRecord, MatchStatusEnum
from app.modules.matching.schemas import (
    MatchRequest, MatchResponse, DriverMatchInfo,
    MatchAssignRequest, MatchAssignResponse,
    MatchHistoryResponse, MatchHistoryRecord
)
from app.modules.matching import utils
from app.modules.drivers.models import DriverProfile
from app.modules.auth.models import User
from app.models.ride import Ride

logger = logging.getLogger(__name__)


# ============================================
# CORE MATCHING ALGORITHM
# ============================================

async def find_matches_service(
    db: AsyncSession,
    current_user: User,
    match_request: MatchRequest
) -> Dict[str, Any]:
    """
    Find and rank suitable drivers for a ride request.
    
    Algorithm Steps:
    1. Get user's matching preferences (if any)
    2. Query available drivers within max distance
    3. For each driver:
       - Calculate distance score
       - Calculate time compatibility score
       - Calculate preference matching score
       - Calculate route direction similarity
       - Compute weighted overall match score
    4. Create match records in database
    5. Return top N matches sorted by score
    
    Args:
        db: Async database session
        current_user: Requesting user (passenger)
        match_request: MatchRequest with ride details and preferences
    
    Returns:
        Standardized response with list of matched drivers
    
    Raises:
        HTTPException: If ride not found or matching fails
    
    Example Response:
        {
            "status": "ok",
            "data": {
                "matches": [
                    {
                        "match_id": "uuid",
                        "driver_id": "uuid",
                        "match_score": 87.5,
                        ...
                    }
                ],
                "total_matches": 10
            },
            "error": null
        }
    """
    
    try:
        logger.info(f"Finding matches for user {current_user.id}, ride {match_request.ride_id}")
        
        # Step 1: Verify ride exists and belongs to user
        ride = await _verify_ride_access(db, match_request.ride_id, current_user.id)
        
        # Step 2: Get user's matching preferences
        user_prefs = await crud.get_match_preference(db, current_user.id)
        max_distance_km = user_prefs.max_pickup_distance_km if user_prefs else 10.0
        max_time_minutes = user_prefs.max_pickup_time_minutes if user_prefs else 15
        
        # Step 3: Find available drivers
        available_drivers = await _find_available_drivers(
            db,
            match_request.pickup_latitude,
            match_request.pickup_longitude,
            max_distance_km,
            match_request.requested_seats
        )
        
        logger.info(f"Found {len(available_drivers)} potentially available drivers")
        
        # Step 4: Score each driver and create match records
        matches = []
        for driver, vehicle, driver_location in available_drivers:
            try:
                # Calculate distance
                distance_km = utils.calculate_distance(
                    driver_location['latitude'],
                    driver_location['longitude'],
                    match_request.pickup_latitude,
                    match_request.pickup_longitude
                )
                
                # Skip if beyond max distance
                if distance_km > max_distance_km:
                    continue
                
                # Calculate scores
                distance_score = utils.calculate_distance_score(distance_km, max_distance_km)
                
                estimated_pickup_time = utils.estimate_pickup_time(distance_km)
                time_score = utils.calculate_time_score(
                    match_request.preferred_pickup_time or datetime.now(),
                    estimated_pickup_time,
                    max_time_minutes
                )
                
                # Calculate preference score
                preference_score = 100.0  # Default
                if user_prefs:
                    preference_score = utils.calculate_preference_score(
                        driver_verified=driver.is_verified,
                        driver_rating=driver.rating or 4.0,
                        driver_gender=driver.user.gender if hasattr(driver.user, 'gender') else 'unknown',
                        vehicle_type=None,
                        prefer_verified=user_prefs.prefer_verified_drivers,
                        prefer_same_gender=user_prefs.prefer_same_gender,
                        passenger_gender=current_user.gender if hasattr(current_user, 'gender') else 'unknown',
                        min_rating=user_prefs.min_driver_rating or 3.0,
                        prefer_vehicle_types=user_prefs.prefer_vehicle_types
                    )
                
                # Skip if preference score is 0 (hard constraint failed)
                if preference_score == 0.0:
                    logger.info(f"Driver {driver.id} filtered out by preferences")
                    continue
                
                # Calculate route similarity
                route_score = utils.calculate_route_similarity(
                    match_request.pickup_latitude,
                    match_request.pickup_longitude,
                    match_request.destination_latitude,
                    match_request.destination_longitude,
                    driver_location['latitude'],
                    driver_location['longitude']
                )
                
                # Calculate overall match score
                match_score = utils.calculate_match_score(
                    distance_score,
                    time_score,
                    preference_score,
                    route_score
                )
                
                # Create match record in database
                match_record = await crud.create_match_record(
                    db=db,
                    ride_id=match_request.ride_id,
                    driver_id=driver.id,
                    passenger_id=current_user.id,
                    match_score=match_score,
                    distance_score=distance_score,
                    time_score=time_score,
                    preference_score=preference_score,
                    distance_km=distance_km,
                    estimated_pickup_time=estimated_pickup_time,
                    expires_minutes=15,
                    metadata=None
                )
                
                # Build response object
                driver_match = DriverMatchInfo(
                    match_id=match_record.id,
                    driver_id=driver.id,
                    driver_name=driver.user.full_name if hasattr(driver.user, 'full_name') else "Unknown",
                    driver_rating=driver.rating,
                    vehicle_type=None,
                    vehicle_model=f"{vehicle.make} {vehicle.model}" if vehicle else None,
                    available_seats=vehicle.seats_available if vehicle else 4,
                    match_score=match_score,
                    distance_score=distance_score,
                    time_score=time_score,
                    preference_score=preference_score,
                    distance_km=distance_km,
                    estimated_pickup_time=estimated_pickup_time,
                    status=match_record.status,
                    created_at=match_record.created_at,
                    expires_at=match_record.expires_at
                )
                
                matches.append(driver_match)
                
            except Exception as e:
                logger.error(f"Error scoring driver {driver.id}: {str(e)}")
                continue
        
        # Step 5: Sort by match score and limit results
        matches.sort(key=lambda x: x.match_score, reverse=True)
        matches = matches[:match_request.max_results]
        
        logger.info(f"Returning {len(matches)} matches for ride {match_request.ride_id}")
        
        return {
            "status": "ok",
            "data": {
                "matches": [match.model_dump() for match in matches],
                "total_matches": len(matches)
            },
            "error": None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in find_matches_service: {str(e)}")
        return {
            "status": "error",
            "data": None,
            "error": f"Failed to find matches: {str(e)}"
        }


async def assign_match_service(
    db: AsyncSession,
    current_user: User,
    assign_request: MatchAssignRequest
) -> Dict[str, Any]:
    """
    Assign a driver to a ride by accepting a match.
    
    Business Logic:
    1. Verify match exists and is in PROPOSED status
    2. Verify user is the passenger for this match
    3. Check driver is still available
    4. Update match status to ASSIGNED
    5. Update driver status (future: set as busy)
    6. Create ride booking (future integration)
    
    Args:
        db: Async database session
        current_user: User accepting the match (passenger)
        assign_request: MatchAssignRequest with match_id
    
    Returns:
        Standardized response with assignment confirmation
    
    Raises:
        HTTPException: If match not found, unauthorized, or already assigned
    
    Example Response:
        {
            "status": "ok",
            "data": {
                "match_id": "uuid",
                "ride_id": "uuid",
                "driver_id": "uuid",
                "status": "assigned",
                "assigned_at": "2025-11-07T15:35:00"
            },
            "error": null
        }
    """
    
    try:
        logger.info(f"Assigning match {assign_request.match_id} for user {current_user.id}")
        
        # Step 1: Get match record
        match_record = await crud.get_match_by_id_with_relations(db, assign_request.match_id)
        if not match_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Match record {assign_request.match_id} not found"
            )
        
        # Step 2: Verify ownership
        if match_record.passenger_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only assign matches for your own rides"
            )
        
        # Step 3: Verify match is still valid
        if match_record.status != MatchStatusEnum.PROPOSED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Match is already {match_record.status}. Only PROPOSED matches can be assigned."
            )
        
        # Check if expired
        if match_record.expires_at and match_record.expires_at < datetime.utcnow():
            await crud.update_match_status(db, match_record.id, MatchStatusEnum.EXPIRED)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Match has expired. Please request new matches."
            )
        
        # Step 4: Verify driver is still available
        # TODO: Check driver's current status in real-time system
        
        # Step 5: Update match status to ASSIGNED
        updated_match = await crud.update_match_status(db, match_record.id, MatchStatusEnum.ASSIGNED)
        
        # Step 6: TODO - Create ride booking
        # This will be integrated with rides module in future
        # await rides.book_ride_service(db, driver_id, ride_id, ...)
        
        logger.info(f"Successfully assigned driver {match_record.driver_id} to ride {match_record.ride_id}")
        
        return {
            "status": "ok",
            "data": {
                "match_id": updated_match.id,
                "ride_id": updated_match.ride_id,
                "driver_id": updated_match.driver_id,
                "passenger_id": updated_match.passenger_id,
                "status": updated_match.status,
                "assigned_at": updated_match.updated_at.isoformat()
            },
            "error": None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in assign_match_service: {str(e)}")
        return {
            "status": "error",
            "data": None,
            "error": f"Failed to assign match: {str(e)}"
        }


async def get_match_history_service(
    db: AsyncSession,
    current_user: User,
    user_id: UUID,
    as_driver: bool = False,
    limit: int = 100
) -> Dict[str, Any]:
    """
    Get match history for a user.
    
    Args:
        db: Async database session
        current_user: Requesting user
        user_id: User to get history for
        as_driver: If True, get driver matches; else passenger matches
        limit: Maximum number of records to return
    
    Returns:
        Standardized response with match history
    
    Raises:
        HTTPException: If unauthorized to view history
    
    Example Response:
        {
            "status": "ok",
            "data": {
                "matches": [...],
                "total_count": 15
            },
            "error": null
        }
    """
    
    try:
        # Verify authorization (can only view own history unless admin)
        if current_user.id != user_id:
            # TODO: Check if user is admin
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own match history"
            )
        
        # Get match history
        matches = await crud.get_user_match_history(db, user_id, as_driver, limit)
        
        # Convert to response schema
        match_records = [
            MatchHistoryRecord(
                match_id=m.id,
                ride_id=m.ride_id,
                driver_id=m.driver_id,
                passenger_id=m.passenger_id,
                match_score=m.match_score,
                distance_km=m.distance_km,
                status=m.status,
                created_at=m.created_at,
                updated_at=m.updated_at
            )
            for m in matches
        ]
        
        return {
            "status": "ok",
            "data": {
                "matches": [m.model_dump() for m in match_records],
                "total_count": len(match_records)
            },
            "error": None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_match_history_service: {str(e)}")
        return {
            "status": "error",
            "data": None,
            "error": f"Failed to get match history: {str(e)}"
        }


# ============================================
# HELPER FUNCTIONS
# ============================================

async def _verify_ride_access(db: AsyncSession, ride_id: UUID, user_id: UUID) -> Ride:
    """
    Verify ride exists and user has access to it.
    
    Args:
        db: Async database session
        ride_id: UUID of the ride
        user_id: UUID of the user
    
    Returns:
        Ride instance
    
    Raises:
        HTTPException: If ride not found or access denied
    """
    
    stmt = select(Ride).where(Ride.id == ride_id)
    result = await db.execute(stmt)
    ride = result.scalar_one_or_none()
    
    if not ride:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ride {ride_id} not found"
        )
    
    # For now, allow any authenticated user to request matches
    # In production, add additional access control as needed
    
    return ride


async def _find_available_drivers(
    db: AsyncSession,
    pickup_lat: float,
    pickup_lon: float,
    max_distance_km: float,
    required_seats: int
) -> List[Tuple[DriverProfile, Any, Dict[str, float]]]:
    """
    Find available drivers within distance range.
    
    This is a simplified version. In production, this would:
    - Query Redis geospatial index for nearby drivers
    - Check real-time driver availability status
    - Filter by vehicle capacity and availability
    
    Args:
        db: Async database session
        pickup_lat: Pickup latitude
        pickup_lon: Pickup longitude
        max_distance_km: Maximum search radius
        required_seats: Minimum seats needed
    
    Returns:
        List of tuples: (DriverProfile, Vehicle, location_dict)
    
    Note:
        Current implementation returns all active verified drivers.
        TODO: Implement Redis geospatial indexing for performance.
        TODO: Add real-time driver location tracking.
    """
    
    try:
        # Query active verified drivers with active vehicles
        # In production, this would be a Redis GEORADIUS query for performance
        
        stmt = (
            select(DriverProfile)
            .where(
                and_(
                    DriverProfile.is_verified == True,
                    DriverProfile.status == 'active'
                )
            )
            .limit(100)  # Limit for performance
        )
        
        result = await db.execute(stmt)
        drivers = list(result.scalars().all())
        
        # Build result list with driver, vehicle, and mock location
        available_drivers = []
        for driver in drivers:
            # Get driver's active vehicle
            # TODO: Properly query vehicles table
            vehicle = None  # Placeholder
            
            # Mock driver location (in production, get from real-time tracking system)
            # For now, use random nearby location
            mock_location = {
                'latitude': pickup_lat + (hash(str(driver.id)) % 100 - 50) / 1000,
                'longitude': pickup_lon + (hash(str(driver.id)) % 100 - 50) / 1000
            }
            
            available_drivers.append((driver, vehicle, mock_location))
        
        return available_drivers
        
    except Exception as e:
        logger.error(f"Error finding available drivers: {str(e)}")
        return []

