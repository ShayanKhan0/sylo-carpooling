"""
Anomaly Detection for Telemetry Data

Detects suspicious patterns:
- Lateral deviation from expected route
- Unexpected stops (speed <1 km/h for extended periods)
- Overspeed events
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from app.modules.telemetry.schemas import AnomalyAlert

logger = logging.getLogger(__name__)


def calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate distance between two coordinates using Haversine formula.
    
    Args:
        lat1, lng1: First coordinate
        lat2, lng2: Second coordinate
        
    Returns:
        Distance in meters
    """
    from math import radians, sin, cos, sqrt, atan2
    
    R = 6371000  # Earth radius in meters
    
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    delta_lat = radians(lat2 - lat1)
    delta_lng = radians(lng2 - lng1)
    
    a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lng / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    
    return R * c


def point_to_segment_distance(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float
) -> float:
    """
    Calculate minimum distance from point P to line segment AB.
    
    Args:
        px, py: Point coordinates
        ax, ay: Segment start
        bx, by: Segment end
        
    Returns:
        Distance in meters
    """
    # Vector AB
    ab_x = bx - ax
    ab_y = by - ay
    
    # Vector AP
    ap_x = px - ax
    ap_y = py - ay
    
    # AB length squared
    ab_len_sq = ab_x**2 + ab_y**2
    
    if ab_len_sq == 0:
        # A and B are same point
        return calculate_distance(px, py, ax, ay)
    
    # Projection of AP onto AB
    t = max(0, min(1, (ap_x * ab_x + ap_y * ab_y) / ab_len_sq))
    
    # Closest point on segment
    closest_x = ax + t * ab_x
    closest_y = ay + t * ab_y
    
    return calculate_distance(px, py, closest_x, closest_y)


def detect_lateral_deviation(
    lat: float,
    lng: float,
    polyline_coords: List[Tuple[float, float]],
    max_deviation_meters: float = 25.0
) -> Optional[AnomalyAlert]:
    """
    Detect lateral deviation from expected route polyline.
    
    Args:
        lat, lng: Current position
        polyline_coords: List of (lat, lng) tuples forming route
        max_deviation_meters: Threshold in meters
        
    Returns:
        AnomalyAlert if deviation detected, else None
    """
    if not polyline_coords or len(polyline_coords) < 2:
        return None
    
    # Find minimum distance to any polyline segment
    min_distance = float('inf')
    
    for i in range(len(polyline_coords) - 1):
        lat1, lng1 = polyline_coords[i]
        lat2, lng2 = polyline_coords[i + 1]
        
        distance = point_to_segment_distance(lat, lng, lat1, lng1, lat2, lng2)
        min_distance = min(min_distance, distance)
    
    if min_distance > max_deviation_meters:
        return AnomalyAlert(
            anomaly_type="lateral_deviation",
            severity="medium",
            description=f"Vehicle {min_distance:.1f}m off route (threshold: {max_deviation_meters}m)",
            detected_at=datetime.utcnow()
        )
    
    return None


def detect_unexpected_stop(
    recent_points: List[Dict],
    max_stop_minutes: float = 3.0,
    speed_threshold_kmh: float = 1.0,
    pickup_coords: Optional[Tuple[float, float]] = None,
    dropoff_coords: Optional[Tuple[float, float]] = None,
    proximity_threshold_meters: float = 50.0
) -> Optional[AnomalyAlert]:
    """
    Detect unexpected stops (speed <1 km/h for extended period).
    
    Args:
        recent_points: List of recent telemetry points (dicts with timestamp, speed, lat, lng)
        max_stop_minutes: Maximum allowed stop duration
        speed_threshold_kmh: Speed below which is considered stopped
        pickup_coords: (lat, lng) of pickup location
        dropoff_coords: (lat, lng) of dropoff location
        proximity_threshold_meters: Distance within which stop is considered at pickup/dropoff
        
    Returns:
        AnomalyAlert if unexpected stop detected, else None
    """
    if len(recent_points) < 2:
        return None
    
    # Sort by timestamp
    sorted_points = sorted(recent_points, key=lambda p: p['timestamp'])
    
    # Find continuous stop duration
    stop_start = None
    for point in sorted_points:
        if point['speed'] < speed_threshold_kmh:
            if stop_start is None:
                stop_start = point['timestamp']
        else:
            stop_start = None  # Moving again
    
    if stop_start is None:
        return None  # No ongoing stop
    
    # Calculate stop duration
    last_point = sorted_points[-1]
    stop_duration = (last_point['timestamp'] - stop_start).total_seconds() / 60.0
    
    if stop_duration < max_stop_minutes:
        return None  # Stop not long enough
    
    # Check if stopped at pickup or dropoff
    last_lat = last_point['lat']
    last_lng = last_point['lng']
    
    if pickup_coords:
        dist_to_pickup = calculate_distance(last_lat, last_lng, *pickup_coords)
        if dist_to_pickup < proximity_threshold_meters:
            return None  # Stopped at pickup (expected)
    
    if dropoff_coords:
        dist_to_dropoff = calculate_distance(last_lat, last_lng, *dropoff_coords)
        if dist_to_dropoff < proximity_threshold_meters:
            return None  # Stopped at dropoff (expected)
    
    return AnomalyAlert(
        anomaly_type="unexpected_stop",
        severity="high",
        description=f"Vehicle stopped for {stop_duration:.1f} minutes at unexpected location",
        detected_at=datetime.utcnow()
    )


def detect_overspeed(
    speed_kmh: float,
    max_speed_kmh: float = 120.0
) -> Optional[AnomalyAlert]:
    """
    Detect overspeed events.
    
    Args:
        speed_kmh: Current speed
        max_speed_kmh: Maximum allowed speed
        
    Returns:
        AnomalyAlert if overspeed detected, else None
    """
    if speed_kmh > max_speed_kmh:
        return AnomalyAlert(
            anomaly_type="overspeed",
            severity="high" if speed_kmh > max_speed_kmh + 20 else "medium",
            description=f"Vehicle speed {speed_kmh:.1f} km/h exceeds limit of {max_speed_kmh} km/h",
            detected_at=datetime.utcnow()
        )
    
    return None


async def analyze_telemetry_point(
    ride_id: UUID,
    lat: float,
    lng: float,
    speed: float,
    timestamp: datetime,
    polyline_coords: Optional[List[Tuple[float, float]]] = None,
    recent_points: Optional[List[Dict]] = None,
    pickup_coords: Optional[Tuple[float, float]] = None,
    dropoff_coords: Optional[Tuple[float, float]] = None,
    max_deviation_meters: float = 25.0,
    max_stop_minutes: float = 3.0,
    max_speed_kmh: float = 120.0
) -> List[AnomalyAlert]:
    """
    Analyze telemetry point for all anomaly types.
    
    Args:
        ride_id: Ride UUID
        lat, lng: Current position
        speed: Current speed in km/h
        timestamp: Point timestamp
        polyline_coords: Expected route coordinates
        recent_points: Recent telemetry history
        pickup_coords: Pickup location
        dropoff_coords: Dropoff location
        max_deviation_meters: Lateral deviation threshold
        max_stop_minutes: Stop duration threshold
        max_speed_kmh: Speed limit
        
    Returns:
        List of detected anomalies
    """
    anomalies = []
    
    # 1. Check lateral deviation
    if polyline_coords:
        deviation = detect_lateral_deviation(lat, lng, polyline_coords, max_deviation_meters)
        if deviation:
            anomalies.append(deviation)
            logger.warning(f"🚨 Lateral deviation detected for ride {ride_id}: {deviation.description}")
    
    # 2. Check unexpected stop
    if recent_points:
        stop = detect_unexpected_stop(
            recent_points,
            max_stop_minutes,
            pickup_coords=pickup_coords,
            dropoff_coords=dropoff_coords
        )
        if stop:
            anomalies.append(stop)
            logger.warning(f"🚨 Unexpected stop detected for ride {ride_id}: {stop.description}")
    
    # 3. Check overspeed
    overspeed = detect_overspeed(speed, max_speed_kmh)
    if overspeed:
        anomalies.append(overspeed)
        logger.warning(f"🚨 Overspeed detected for ride {ride_id}: {overspeed.description}")
    
    return anomalies


async def enqueue_safety_ai_task(
    ride_id: UUID,
    anomalies: List[AnomalyAlert],
    **kwargs,
) -> bool:
    """
    Run safety AI analysis as an async background task.

    Args:
        ride_id: Ride UUID
        anomalies: List of detected anomalies

    Returns:
        True if task started successfully
    """
    if not anomalies:
        return False

    try:
        import asyncio
        from app.modules.safety_ai.tasks import analyze_telemetry_task

        payload = {
            "ride_id": str(ride_id),
            "anomalies": [
                {
                    "type": a.anomaly_type,
                    "severity": a.severity,
                    "description": a.description,
                    "detected_at": a.detected_at.isoformat()
                }
                for a in anomalies
            ]
        }

        # Fire-and-forget async task
        asyncio.create_task(analyze_telemetry_task(str(ride_id), payload))

        logger.info(f"Enqueued safety AI task for ride {ride_id} ({len(anomalies)} anomalies)")
        return True

    except Exception as e:
        logger.error(f"Failed to enqueue safety AI task: {e}", exc_info=True)
        return False
