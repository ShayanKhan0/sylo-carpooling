"""
Module: Matching - Utility Functions
Purpose: Core algorithms for distance, time, and match score calculations.
Authors: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: Implements Haversine formula, scoring algorithms, and vector similarity.
"""

import math
from typing import Tuple
from datetime import datetime, timedelta


def calculate_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Calculate distance between two geographic coordinates using Haversine formula.
    
    Args:
        lat1: Latitude of first point (degrees)
        lon1: Longitude of first point (degrees)
        lat2: Latitude of second point (degrees)
        lon2: Longitude of second point (degrees)
    
    Returns:
        Distance in kilometers
    
    Algorithm:
        Haversine formula:
        a = sin²(Δφ/2) + cos φ1 × cos φ2 × sin²(Δλ/2)
        c = 2 × atan2(√a, √(1−a))
        d = R × c
        
        where:
        - φ is latitude in radians
        - λ is longitude in radians
        - R is earth's radius (6371 km)
    
    Example:
        >>> calculate_distance(31.5204, 74.3587, 31.4697, 74.2728)
        8.23  # km between FAST NUCES and Liberty Market
    """
    
    # Earth's radius in kilometers
    R = 6371.0
    
    # Convert degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Differences
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    # Haversine formula
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    # Distance in kilometers
    distance = R * c
    
    return round(distance, 2)


def calculate_distance_score(
    distance_km: float,
    max_distance_km: float = 10.0
) -> float:
    """
    Calculate distance compatibility score (0-100).
    
    Args:
        distance_km: Actual distance in kilometers
        max_distance_km: Maximum acceptable distance (default 10 km)
    
    Returns:
        Score from 0-100 (100 = closest, 0 = too far)
    
    Algorithm:
        - Linear decay: score = 100 × (1 - distance/max_distance)
        - Distances beyond max_distance get score of 0
        - Closer distances get higher scores
    
    Example:
        >>> calculate_distance_score(2.5, 10.0)
        75.0  # 2.5km is 75% within acceptable range
        
        >>> calculate_distance_score(12.0, 10.0)
        0.0  # Beyond max acceptable distance
    """
    
    if distance_km >= max_distance_km:
        return 0.0
    
    # Linear decay formula
    score = 100.0 * (1.0 - (distance_km / max_distance_km))
    
    return round(max(0.0, min(100.0, score)), 2)


def calculate_time_score(
    request_time: datetime,
    driver_eta_minutes: int,
    tolerance_minutes: int = 10
) -> float:
    """
    Calculate time compatibility score (0-100).
    
    Args:
        request_time: When passenger wants pickup
        driver_eta_minutes: How long driver takes to reach pickup
        tolerance_minutes: Acceptable time difference (default 10 min)
    
    Returns:
        Score from 0-100 (100 = perfect timing, 0 = too late/early)
    
    Algorithm:
        - Calculate driver arrival time
        - Compare with requested pickup time
        - Use Gaussian decay based on time difference
        - Within tolerance: high score (80-100)
        - Beyond tolerance: exponential decay
    
    Example:
        >>> request_time = datetime(2025, 11, 8, 9, 0)  # 9:00 AM
        >>> calculate_time_score(request_time, 7, 10)  # Driver ETA 7 min
        95.0  # Arrives at 9:07, well within tolerance
        
        >>> calculate_time_score(request_time, 15, 10)  # Driver ETA 15 min
        60.0  # Arrives at 9:15, slightly beyond tolerance
    """
    
    # Calculate driver arrival time
    driver_arrival = datetime.now() + timedelta(minutes=driver_eta_minutes)
    
    # Time difference in minutes
    time_diff_minutes = abs((driver_arrival - request_time).total_seconds() / 60)
    
    # Perfect match (within 5 minutes)
    if time_diff_minutes <= 5:
        return 100.0
    
    # Within tolerance (5-10 minutes)
    if time_diff_minutes <= tolerance_minutes:
        # Linear decay from 100 to 80
        score = 100.0 - (20.0 * (time_diff_minutes - 5) / (tolerance_minutes - 5))
        return round(score, 2)
    
    # Beyond tolerance (exponential decay)
    # score = 80 × exp(-0.1 × (diff - tolerance))
    excess_minutes = time_diff_minutes - tolerance_minutes
    score = 80.0 * math.exp(-0.1 * excess_minutes)
    
    return round(max(0.0, score), 2)


def calculate_route_similarity(
    pickup_lat: float,
    pickup_lon: float,
    dest_lat: float,
    dest_lon: float,
    driver_lat: float,
    driver_lon: float
) -> float:
    """
    Calculate route direction similarity score (0-100).
    
    Args:
        pickup_lat: Pickup location latitude
        pickup_lon: Pickup location longitude
        dest_lat: Destination latitude
        dest_lon: Destination longitude
        driver_lat: Driver current location latitude
        driver_lon: Driver current location longitude
    
    Returns:
        Score from 0-100 (100 = same direction, 0 = opposite direction)
    
    Algorithm:
        - Calculate bearing (angle) from pickup to destination
        - Calculate bearing from driver to pickup
        - Use cosine similarity between direction vectors
        - Convert to 0-100 scale
    
    Example:
        >>> calculate_route_similarity(31.52, 74.36, 31.47, 74.27, 31.54, 74.38)
        85.0  # Driver is roughly in same direction as ride route
    """
    
    def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate bearing angle between two points."""
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlon_rad = math.radians(lon2 - lon1)
        
        x = math.sin(dlon_rad) * math.cos(lat2_rad)
        y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon_rad)
        
        bearing = math.atan2(x, y)
        return bearing
    
    # Calculate route bearing (pickup to destination)
    route_bearing = calculate_bearing(pickup_lat, pickup_lon, dest_lat, dest_lon)
    
    # Calculate driver approach bearing (driver to pickup)
    driver_bearing = calculate_bearing(driver_lat, driver_lon, pickup_lat, pickup_lon)
    
    # Calculate angle difference (0 to π)
    angle_diff = abs(route_bearing - driver_bearing)
    if angle_diff > math.pi:
        angle_diff = 2 * math.pi - angle_diff
    
    # Convert to similarity score (0-100)
    # cos(0) = 1 (same direction) → score 100
    # cos(π) = -1 (opposite direction) → score 0
    similarity = (1 + math.cos(angle_diff)) / 2
    score = similarity * 100.0
    
    return round(score, 2)


def calculate_preference_score(
    driver_verified: bool,
    driver_rating: float,
    driver_gender: str,
    vehicle_type: str,
    prefer_verified: bool,
    prefer_same_gender: bool,
    passenger_gender: str,
    min_rating: float,
    prefer_vehicle_types: str = None
) -> float:
    """
    Calculate preference matching score (0-100).
    
    Args:
        driver_verified: Whether driver is verified
        driver_rating: Driver's average rating (0-5)
        driver_gender: Driver's gender
        vehicle_type: Vehicle type (sedan/suv/etc)
        prefer_verified: Passenger prefers verified drivers
        prefer_same_gender: Passenger prefers same gender
        passenger_gender: Passenger's gender
        min_rating: Minimum acceptable rating
        prefer_vehicle_types: Comma-separated preferred vehicle types
    
    Returns:
        Score from 0-100 (100 = all preferences matched, 0 = deal breakers violated)
    
    Algorithm:
        - Check hard constraints (deal breakers): verified, min rating
        - Check soft preferences: gender, vehicle type
        - Weight: 50% hard constraints, 50% soft preferences
        - If any hard constraint fails, return 0 (incompatible)
    
    Example:
        >>> calculate_preference_score(
        ...     driver_verified=True, driver_rating=4.5, driver_gender='male',
        ...     vehicle_type='sedan', prefer_verified=True, prefer_same_gender=False,
        ...     passenger_gender='female', min_rating=4.0, prefer_vehicle_types='sedan,suv'
        ... )
        100.0  # All preferences matched
    """
    
    score = 100.0
    
    # Hard Constraint 1: Verification (deal breaker)
    if prefer_verified and not driver_verified:
        return 0.0  # Unverified driver rejected
    
    # Hard Constraint 2: Minimum Rating (deal breaker)
    if driver_rating < min_rating:
        return 0.0  # Rating too low
    
    # Soft Preference 1: Gender (20 point penalty)
    if prefer_same_gender and driver_gender.lower() != passenger_gender.lower():
        score -= 20.0
    
    # Soft Preference 2: Vehicle Type (15 point penalty)
    if prefer_vehicle_types:
        preferred_types = [vt.strip().lower() for vt in prefer_vehicle_types.split(',')]
        if vehicle_type.lower() not in preferred_types:
            score -= 15.0
    
    # Soft Preference 3: Rating excellence bonus
    if driver_rating >= 4.5:
        score += 5.0  # Bonus for excellent drivers
    
    return round(max(0.0, min(100.0, score)), 2)


def calculate_match_score(
    distance_score: float,
    time_score: float,
    preference_score: float,
    route_similarity_score: float = None,
    distance_weight: float = 0.35,
    time_weight: float = 0.25,
    preference_weight: float = 0.30,
    route_weight: float = 0.10
) -> float:
    """
    Calculate overall weighted match score (0-100).
    
    Args:
        distance_score: Distance compatibility score (0-100)
        time_score: Time compatibility score (0-100)
        preference_score: Preference matching score (0-100)
        route_similarity_score: Route direction similarity (0-100, optional)
        distance_weight: Weight for distance score (default 0.35)
        time_weight: Weight for time score (default 0.25)
        preference_weight: Weight for preference score (default 0.30)
        route_weight: Weight for route similarity (default 0.10)
    
    Returns:
        Overall match score from 0-100
    
    Algorithm:
        - Weighted average of all component scores
        - Default weights: distance 35%, time 25%, preference 30%, route 10%
        - If route_similarity not provided, redistribute its weight to distance
    
    Example:
        >>> calculate_match_score(
        ...     distance_score=90.0, time_score=85.0,
        ...     preference_score=100.0, route_similarity_score=80.0
        ... )
        89.75  # Excellent overall match
    """
    
    # If route similarity not provided, redistribute weight to distance
    if route_similarity_score is None:
        distance_weight += route_weight
        route_weight = 0.0
        route_similarity_score = 0.0
    
    # Weighted average
    match_score = (
        distance_score * distance_weight +
        time_score * time_weight +
        preference_score * preference_weight +
        route_similarity_score * route_weight
    )
    
    return round(max(0.0, min(100.0, match_score)), 2)


def estimate_pickup_time(distance_km: float, avg_speed_kmh: float = 40.0) -> int:
    """
    Estimate time for driver to reach pickup location.
    
    Args:
        distance_km: Distance to pickup in kilometers
        avg_speed_kmh: Average speed in km/h (default 40 for city traffic)
    
    Returns:
        Estimated time in minutes
    
    Algorithm:
        - time = distance / speed
        - Add 20% buffer for traffic and stops
        - Minimum 5 minutes for very short distances
    
    Example:
        >>> estimate_pickup_time(5.0, 40.0)
        9  # 5km at 40km/h = 7.5min + 20% buffer = 9min
    """
    
    # Base calculation: distance / speed = hours
    time_hours = distance_km / avg_speed_kmh
    
    # Convert to minutes
    time_minutes = time_hours * 60
    
    # Add 20% buffer for traffic
    time_with_buffer = time_minutes * 1.2
    
    # Round to nearest minute, minimum 5 minutes
    estimated_time = max(5, round(time_with_buffer))
    
    return estimated_time

from typing import Tuple, Optional

def calculate_distance_with_routes(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    use_google_maps: bool = True
) -> Tuple[float, Optional[str]]:
    """
    Calculate distance with Google Maps API (if available) or fallback to Haversine.
    """
    try:
        if use_google_maps:
            from app.core.google_maps_client import get_google_maps_client
            client = get_google_maps_client()
            result = client.get_directions(
                (origin_lat, origin_lon),
                (dest_lat, dest_lon),
                alternatives=False
            )
            if result:
                return result['distance_km'], result['polyline']
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Google Maps API failed, using Haversine: {str(e)}")
    
    distance = calculate_distance(origin_lat, origin_lon, dest_lat, dest_lon)
    return distance, None

def estimate_pickup_time_with_traffic(
    driver_lat: float,
    driver_lon: float,
    pickup_lat: float,
    pickup_lon: float,
    use_google_maps: bool = True
) -> int:
    """
    Estimate pickup time using Google Maps traffic data or basic calculation.
    """
    try:
        if use_google_maps:
            from app.core.google_maps_client import get_google_maps_client
            client = get_google_maps_client()
            result = client.estimate_pickup_time(
                (driver_lat, driver_lon),
                (pickup_lat, pickup_lon)
            )
            if result:
                return result['eta_minutes']
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Google Maps traffic API failed, using basic: {str(e)}")
    
    distance = calculate_distance(driver_lat, driver_lon, pickup_lat, pickup_lon)
    return estimate_pickup_time(distance)
# Duplicate definitions removed — canonical versions above are used.
