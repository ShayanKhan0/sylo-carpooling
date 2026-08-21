"""
Core Matching Service

Two-stage matching pipeline:
1. Spatial prefilter (< 50ms)
2. Ranking with score breakdown (< 150ms)

Performance target: < 200ms end-to-end
"""

import logging
from datetime import datetime
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.matching import crud_new as crud
from app.modules.matching.schemas_new import (
    MatchCandidate,
    MatchingPreferences,
    MatchingRequest,
    ScoreBreakdown,
    TimeWindow,
)

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Matching weights (tunable via settings)
WEIGHT_DETOUR = getattr(settings, "MATCHING_WEIGHT_DETOUR", 0.5)
WEIGHT_DRIVER = getattr(settings, "MATCHING_WEIGHT_DRIVER", 0.3)
WEIGHT_PREFERENCE = getattr(settings, "MATCHING_WEIGHT_PREFERENCE", 0.2)

# Default parameters
DEFAULT_PREFILTER_RADIUS_KM = getattr(settings, "MATCHING_PREFILTER_RADIUS_DEFAULT_KM", 10.0)
DEFAULT_MAX_CANDIDATES = getattr(settings, "MATCHING_MAX_CANDIDATES", 50)
URBAN_SPEED_KMH = 35.0  # Assumed average urban speed


# ============================================================================
# DISTANCE AND TIME ESTIMATION
# ============================================================================

def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate great-circle distance in kilometers"""
    R = 6371.0  # Earth radius
    lat1_rad, lat2_rad = radians(lat1), radians(lat2)
    dlat, dlng = radians(lat2 - lat1), radians(lng2 - lng1)

    a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlng / 2) ** 2
    c = 2 * asin(sqrt(a))
    return R * c


def estimate_travel_time(distance_km: float, speed_kmh: float = URBAN_SPEED_KMH) -> float:
    """
    Estimate travel time in minutes.
    
    Args:
        distance_km: Distance in kilometers
        speed_kmh: Average speed (default urban ~35 km/h)
        
    Returns:
        Time in minutes
    """
    return (distance_km / speed_kmh) * 60.0


def estimate_eta_to_pickup(
    driver_lat: float,
    driver_lng: float,
    pickup_lat: float,
    pickup_lng: float
) -> float:
    """
    Estimate time for driver to reach pickup location.
    
    Uses straight-line distance as heuristic.
    In production, integrate with routing API for accurate ETAs.
    
    Returns:
        ETA in minutes
    """
    distance = haversine_distance(driver_lat, driver_lng, pickup_lat, pickup_lng)
    return estimate_travel_time(distance)


def estimate_detour_minutes(
    driver_route_start: Tuple[float, float],
    driver_route_end: Tuple[float, float],
    pickup: Tuple[float, float],
    dropoff: Tuple[float, float]
) -> float:
    """
    Estimate additional time for driver to pick up and drop off passenger.
    
    Method:
    1. Calculate original route distance (start -> end)
    2. Calculate detour route distance (start -> pickup -> dropoff -> end)
    3. Detour = (detour_route - original_route) time
    
    Args:
        driver_route_start: (lat, lng) of driver's start
        driver_route_end: (lat, lng) of driver's end
        pickup: (lat, lng) of passenger pickup
        dropoff: (lat, lng) of passenger dropoff
        
    Returns:
        Additional time in minutes
    """
    # Original route distance
    original_distance = haversine_distance(
        driver_route_start[0], driver_route_start[1],
        driver_route_end[0], driver_route_end[1]
    )

    # Detour route: start -> pickup -> dropoff -> end
    detour_distance = (
        haversine_distance(driver_route_start[0], driver_route_start[1], pickup[0], pickup[1]) +
        haversine_distance(pickup[0], pickup[1], dropoff[0], dropoff[1]) +
        haversine_distance(dropoff[0], dropoff[1], driver_route_end[0], driver_route_end[1])
    )

    additional_distance = detour_distance - original_distance
    return estimate_travel_time(max(0, additional_distance))


def calculate_route_overlap(
    driver_route_start: Tuple[float, float],
    driver_route_end: Tuple[float, float],
    pickup: Tuple[float, float],
    dropoff: Tuple[float, float]
) -> float:
    """
    Estimate percentage of route overlap.
    
    Heuristic: Compare passenger route length to detour length.
    High overlap = passenger route aligns with driver route.
    
    Returns:
        Overlap percentage (0-100)
    """
    passenger_distance = haversine_distance(pickup[0], pickup[1], dropoff[0], dropoff[1])

    # Calculate distances from driver's route line to pickup/dropoff
    # Simplified: use distance to midpoint of driver route
    mid_lat = (driver_route_start[0] + driver_route_end[0]) / 2
    mid_lng = (driver_route_start[1] + driver_route_end[1]) / 2

    pickup_deviation = haversine_distance(mid_lat, mid_lng, pickup[0], pickup[1])
    dropoff_deviation = haversine_distance(mid_lat, mid_lng, dropoff[0], dropoff[1])

    # Lower deviation = higher overlap
    avg_deviation = (pickup_deviation + dropoff_deviation) / 2
    max_reasonable_deviation = 5.0  # km

    # Normalize: 0 deviation = 100% overlap, max deviation = 0% overlap
    overlap = max(0, 100 * (1 - avg_deviation / max_reasonable_deviation))
    return min(100, overlap)


# ============================================================================
# RANKING LOGIC
# ============================================================================

def normalize(value: float, min_val: float, max_val: float) -> float:
    """Normalize value to [0, 1] range"""
    if max_val == min_val:
        return 0.5
    return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))


def calculate_detour_cost(
    detour_minutes: float,
    max_allowed_detour: int
) -> float:
    """
    Calculate normalized detour cost (0 = no detour, 1 = max detour).
    
    Args:
        detour_minutes: Actual detour time
        max_allowed_detour: Maximum acceptable detour
        
    Returns:
        Cost in [0, 1] (lower is better)
    """
    if max_allowed_detour == 0:
        return 0.0 if detour_minutes == 0 else 1.0

    cost = detour_minutes / max_allowed_detour
    return min(1.0, cost)


def calculate_driver_score(
    rating: float,
    seats_available: int,
    total_seats: int = 4
) -> float:
    """
    Calculate driver quality score.
    
    Components:
    - Rating: normalized to [0, 1] (0 stars = 0, 5 stars = 1)
    - Seats: more available = higher score
    
    Returns:
        Score in [0, 1]
    """
    rating_score = rating / 5.0  # 5-star scale
    seats_score = seats_available / total_seats

    # Weight rating more heavily (70% rating, 30% seats)
    return 0.7 * rating_score + 0.3 * seats_score


def calculate_preference_score(
    candidate: dict,
    preferences: MatchingPreferences
) -> float:
    """
    Calculate preference match score.
    
    Checks:
    - Driver rating >= min_driver_rating
    - Fare <= max_price (if set)
    - Vehicle type in preferred list (if set)
    
    Returns:
        Score in [0, 1] (1 = all preferences met)
    """
    score = 1.0

    # Rating check
    if candidate["driver_rating"] < preferences.min_driver_rating:
        score *= 0.5  # Penalty for below-threshold rating

    # Price check
    if preferences.max_price is not None:
        if candidate["base_price"] > float(preferences.max_price):
            score *= 0.3  # Heavy penalty for over-budget

    # Vehicle type check (not implemented yet - would require vehicle table join)
    # if preferences.preferred_vehicle_types:
    #     if candidate.get("vehicle_type") not in preferences.preferred_vehicle_types:
    #         score *= 0.8

    return score


def calculate_match_score(
    detour_minutes: float,
    driver_rating: float,
    seats_available: int,
    preferences: MatchingPreferences,
    candidate: dict,
) -> Tuple[float, ScoreBreakdown]:
    """
    Calculate final match score with component breakdown.
    
    Formula:
        match_score = (1 - detour_cost) * w_detour 
                    + driver_score * w_driver
                    + preference_score * w_pref
    
    Args:
        detour_minutes: Estimated detour time
        driver_rating: Driver rating (0-5)
        seats_available: Available seats
        preferences: User preferences
        candidate: Candidate dict with additional data
        
    Returns:
        (match_score, breakdown) tuple
    """
    # Calculate components
    detour_cost = calculate_detour_cost(detour_minutes, preferences.max_detour_minutes)
    driver_score = calculate_driver_score(driver_rating, seats_available)
    pref_score = calculate_preference_score(candidate, preferences)

    # Weighted combination
    match_score = (
        (1 - detour_cost) * WEIGHT_DETOUR +
        driver_score * WEIGHT_DRIVER +
        pref_score * WEIGHT_PREFERENCE
    )

    # Breakdown for explainability
    breakdown = ScoreBreakdown(
        detour_cost=detour_cost,
        rating_score=driver_rating / 5.0,
        seats_score=seats_available / 4.0,  # Assume max 4 seats
        preference_score=pref_score,
        detour_weight=WEIGHT_DETOUR,
        driver_weight=WEIGHT_DRIVER,
        preference_weight=WEIGHT_PREFERENCE,
    )

    return match_score, breakdown


# ============================================================================
# MAIN MATCHING SERVICE
# ============================================================================

async def match_drivers(
    db: AsyncSession,
    request: MatchingRequest,
    explain: bool = False
) -> List[MatchCandidate]:
    """
    Find and rank matching drivers for passenger request.
    
    Pipeline:
    1. Spatial prefilter (< 50ms)
    2. Ranking and scoring (< 150ms)
    
    Args:
        db: Database session
        request: Matching request with pickup/dropoff/preferences
        explain: Include score breakdown in response
        
    Returns:
        List of MatchCandidate ordered by match_score desc
    """
    pickup_lat, pickup_lng = request.pickup.lat, request.pickup.lng
    dropoff_lat, dropoff_lng = request.dropoff.lat, request.dropoff.lng

    # Stage 1: Spatial prefilter
    radius_km = DEFAULT_PREFILTER_RADIUS_KM
    time_start = request.time_window.start if request.time_window else None
    time_end = request.time_window.end if request.time_window else None

    candidates_raw = await crud.find_nearby_drivers(
        db=db,
        lat=pickup_lat,
        lng=pickup_lng,
        radius_km=radius_km,
        min_seats=1,  # At least 1 seat available
        time_window_start=time_start,
        time_window_end=time_end,
    )

    if not candidates_raw:
        logger.info("No drivers found in prefilter")
        return []

    logger.info(f"Prefilter found {len(candidates_raw)} candidates")

    # Stage 2: Ranking
    scored_candidates = []

    for candidate in candidates_raw[:DEFAULT_MAX_CANDIDATES]:  # Limit for performance
        # Get driver route endpoints (start = driver location, end = destination)
        driver_start = (candidate["driver_lat"], candidate["driver_lng"])
        # Note: We don't have driver's destination in schema yet, using pickup as proxy
        # In production, extract from polyline_main or add end_point to Ride model
        driver_end = (dropoff_lat, dropoff_lng)  # Placeholder

        # Calculate metrics
        eta_minutes = estimate_eta_to_pickup(
            candidate["driver_lat"], candidate["driver_lng"],
            pickup_lat, pickup_lng
        )

        detour_minutes = estimate_detour_minutes(
            driver_start, driver_end,
            (pickup_lat, pickup_lng),
            (dropoff_lat, dropoff_lng)
        )

        overlap_pct = calculate_route_overlap(
            driver_start, driver_end,
            (pickup_lat, pickup_lng),
            (dropoff_lat, dropoff_lng)
        )

        # Calculate match score
        match_score, breakdown = calculate_match_score(
            detour_minutes=detour_minutes,
            driver_rating=candidate["driver_rating"],
            seats_available=candidate["seats_available"],
            preferences=request.preferences,
            candidate=candidate,
        )

        # Estimate fare (simple: base_price + distance-based)
        trip_distance = haversine_distance(pickup_lat, pickup_lng, dropoff_lat, dropoff_lng)
        fare_estimate = Decimal(candidate["base_price"]) + Decimal(trip_distance * 10)  # Rs 10/km

        # Build candidate
        match_candidate = MatchCandidate(
            driver_id=candidate["driver_id"],
            ride_id=candidate["ride_id"],
            match_score=match_score,
            estimated_detour_minutes=detour_minutes,
            eta_to_pickup_minutes=eta_minutes,
            fare_estimate=fare_estimate,
            driver_rating=candidate["driver_rating"],
            seats_available=candidate["seats_available"],
            route_overlap_percentage=overlap_pct,
            score_breakdown=breakdown if explain or request.explain else None,
        )

        scored_candidates.append(match_candidate)

    # Sort by match_score descending
    scored_candidates.sort(key=lambda c: c.match_score, reverse=True)

    # Return top candidates
    return scored_candidates[: request.limit]


async def explain_match(
    db: AsyncSession,
    driver_id: UUID,
    ride_id: UUID,
    pickup_lat: float,
    pickup_lng: float,
    dropoff_lat: float,
    dropoff_lng: float,
    preferences: MatchingPreferences,
) -> Optional[Dict]:
    """
    Get detailed explanation for a specific driver match.
    
    Useful for debugging and UI transparency.
    
    Returns:
        Dict with score components and intermediate calculations
    """
    # Fetch driver details
    candidates = await crud.find_nearby_drivers(
        db=db,
        lat=pickup_lat,
        lng=pickup_lng,
        radius_km=50.0,  # Wide search
        min_seats=0,
    )

    driver_candidate = next((c for c in candidates if c["driver_id"] == driver_id), None)
    if not driver_candidate:
        return None

    # Calculate all metrics
    driver_start = (driver_candidate["driver_lat"], driver_candidate["driver_lng"])
    driver_end = (dropoff_lat, dropoff_lng)  # Placeholder

    eta = estimate_eta_to_pickup(
        driver_candidate["driver_lat"], driver_candidate["driver_lng"],
        pickup_lat, pickup_lng
    )

    detour = estimate_detour_minutes(
        driver_start, driver_end,
        (pickup_lat, pickup_lng),
        (dropoff_lat, dropoff_lng)
    )

    overlap = calculate_route_overlap(
        driver_start, driver_end,
        (pickup_lat, pickup_lng),
        (dropoff_lat, dropoff_lng)
    )

    match_score, breakdown = calculate_match_score(
        detour_minutes=detour,
        driver_rating=driver_candidate["driver_rating"],
        seats_available=driver_candidate["seats_available"],
        preferences=preferences,
        candidate=driver_candidate,
    )

    return {
        "driver_id": str(driver_id),
        "ride_id": str(ride_id),
        "match_score": match_score,
        "eta_to_pickup_minutes": eta,
        "estimated_detour_minutes": detour,
        "route_overlap_percentage": overlap,
        "driver_rating": driver_candidate["driver_rating"],
        "seats_available": driver_candidate["seats_available"],
        "breakdown": breakdown.model_dump(),
    }
