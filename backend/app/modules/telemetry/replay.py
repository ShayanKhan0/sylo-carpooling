"""
Telemetry Replay and Route Reconstruction

Generates trip replays with encoded polylines and statistics.
"""

import logging
from datetime import datetime
from typing import Dict, List, Tuple
from uuid import UUID

from app.modules.telemetry.schemas import TelemetryReplayResponse

logger = logging.getLogger(__name__)


def encode_polyline(coordinates: List[Tuple[float, float]], precision: int = 5) -> str:
    """
    Encode list of (lat, lng) tuples to Google Maps polyline format.
    
    Args:
        coordinates: List of (lat, lng) tuples
        precision: Encoding precision (5 for standard, 6 for high precision)
        
    Returns:
        Encoded polyline string
    """
    if not coordinates:
        return ""
    
    factor = 10 ** precision
    output = []
    
    prev_lat = 0
    prev_lng = 0
    
    for lat, lng in coordinates:
        # Convert to integer with precision
        lat_int = int(round(lat * factor))
        lng_int = int(round(lng * factor))
        
        # Calculate deltas
        delta_lat = lat_int - prev_lat
        delta_lng = lng_int - prev_lng
        
        prev_lat = lat_int
        prev_lng = lng_int
        
        # Encode deltas
        for delta in [delta_lat, delta_lng]:
            # Shift and invert if negative
            value = delta << 1
            if value < 0:
                value = ~value
            
            # Encode chunks
            while value >= 0x20:
                chunk = (0x20 | (value & 0x1f)) + 63
                output.append(chr(chunk))
                value >>= 5
            
            output.append(chr(value + 63))
    
    return ''.join(output)


def decode_polyline(polyline: str, precision: int = 5) -> List[Tuple[float, float]]:
    """
    Decode Google Maps polyline to list of (lat, lng) tuples.
    
    Args:
        polyline: Encoded polyline string
        precision: Encoding precision (5 for standard)
        
    Returns:
        List of (lat, lng) tuples
    """
    if not polyline:
        return []
    
    coordinates = []
    index = 0
    lat = 0
    lng = 0
    factor = 10 ** precision
    
    while index < len(polyline):
        # Decode latitude
        result = 0
        shift = 0
        while True:
            byte = ord(polyline[index]) - 63
            index += 1
            result |= (byte & 0x1f) << shift
            shift += 5
            if byte < 0x20:
                break
        
        delta_lat = ~(result >> 1) if result & 1 else result >> 1
        lat += delta_lat
        
        # Decode longitude
        result = 0
        shift = 0
        while True:
            byte = ord(polyline[index]) - 63
            index += 1
            result |= (byte & 0x1f) << shift
            shift += 5
            if byte < 0x20:
                break
        
        delta_lng = ~(result >> 1) if result & 1 else result >> 1
        lng += delta_lng
        
        coordinates.append((lat / factor, lng / factor))
    
    return coordinates


def calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate distance between two coordinates using Haversine formula.
    
    Returns distance in meters.
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


def calculate_statistics(points: List[Dict]) -> Dict:
    """
    Calculate trip statistics from telemetry points.
    
    Args:
        points: List of telemetry point dicts with lat, lng, speed, timestamp
        
    Returns:
        Dictionary with duration_minutes, distance_km, avg_speed_kmh, max_speed_kmh
    """
    if not points:
        return {
            "duration_minutes": 0.0,
            "distance_km": 0.0,
            "avg_speed_kmh": 0.0,
            "max_speed_kmh": 0.0
        }
    
    # Sort by timestamp
    sorted_points = sorted(points, key=lambda p: p['timestamp'])
    
    # Calculate duration
    start_time = sorted_points[0]['timestamp']
    end_time = sorted_points[-1]['timestamp']
    duration_seconds = (end_time - start_time).total_seconds()
    duration_minutes = duration_seconds / 60.0
    
    # Calculate distance
    total_distance = 0.0
    for i in range(len(sorted_points) - 1):
        p1 = sorted_points[i]
        p2 = sorted_points[i + 1]
        
        distance = calculate_distance(p1['lat'], p1['lng'], p2['lat'], p2['lng'])
        total_distance += distance
    
    distance_km = total_distance / 1000.0
    
    # Calculate speed statistics
    speeds = [p.get('speed', 0.0) for p in sorted_points if p.get('speed') is not None]
    avg_speed_kmh = sum(speeds) / len(speeds) if speeds else 0.0
    max_speed_kmh = max(speeds) if speeds else 0.0
    
    return {
        "duration_minutes": round(duration_minutes, 2),
        "distance_km": round(distance_km, 2),
        "avg_speed_kmh": round(avg_speed_kmh, 1),
        "max_speed_kmh": round(max_speed_kmh, 1)
    }


async def build_replay(
    ride_id: UUID,
    telemetry_points: List[Dict],
    simplify: bool = True,
    simplification_tolerance: float = 0.0001
) -> TelemetryReplayResponse:
    """
    Build complete trip replay from telemetry points.
    
    Args:
        ride_id: Ride UUID
        telemetry_points: List of telemetry point dicts
        simplify: Whether to simplify polyline
        simplification_tolerance: Tolerance for Douglas-Peucker algorithm
        
    Returns:
        TelemetryReplayResponse with encoded route and statistics
    """
    if not telemetry_points:
        # Empty replay
        return TelemetryReplayResponse(
            ride_id=ride_id,
            encoded_polyline="",
            samples=[],
            start_time=None,
            end_time=None,
            duration_minutes=0.0,
            distance_km=0.0,
            avg_speed_kmh=0.0,
            max_speed_kmh=0.0,
            sample_count=0
        )
    
    # Sort by timestamp
    sorted_points = sorted(telemetry_points, key=lambda p: p['timestamp'])
    
    # Extract coordinates
    coordinates = [(p['lat'], p['lng']) for p in sorted_points]
    
    # Simplify polyline if requested
    if simplify and len(coordinates) > 2:
        coordinates = simplify_polyline(coordinates, simplification_tolerance)
    
    # Encode polyline
    encoded_polyline = encode_polyline(coordinates)
    
    # Calculate statistics
    stats = calculate_statistics(sorted_points)
    
    # Build sample array
    samples = [
        {
            "timestamp": p['timestamp'].isoformat(),
            "lat": p['lat'],
            "lng": p['lng'],
            "speed": p.get('speed', 0.0),
            "bearing": p.get('bearing'),
            "accuracy": p.get('accuracy')
        }
        for p in sorted_points
    ]
    
    logger.info(f"✅ Built replay for ride {ride_id}: {len(sorted_points)} points, {stats['distance_km']} km, {stats['duration_minutes']} min")
    
    return TelemetryReplayResponse(
        ride_id=ride_id,
        encoded_polyline=encoded_polyline,
        samples=samples,
        start_time=sorted_points[0]['timestamp'],
        end_time=sorted_points[-1]['timestamp'],
        duration_minutes=stats['duration_minutes'],
        distance_km=stats['distance_km'],
        avg_speed_kmh=stats['avg_speed_kmh'],
        max_speed_kmh=stats['max_speed_kmh'],
        sample_count=len(sorted_points)
    )


def simplify_polyline(
    coordinates: List[Tuple[float, float]],
    tolerance: float = 0.0001
) -> List[Tuple[float, float]]:
    """
    Simplify polyline using Douglas-Peucker algorithm.
    
    Args:
        coordinates: List of (lat, lng) tuples
        tolerance: Simplification tolerance (smaller = more detail)
        
    Returns:
        Simplified list of coordinates
    """
    if len(coordinates) <= 2:
        return coordinates
    
    # Find point with maximum distance from line
    max_distance = 0.0
    max_index = 0
    
    for i in range(1, len(coordinates) - 1):
        distance = perpendicular_distance(
            coordinates[i],
            coordinates[0],
            coordinates[-1]
        )
        
        if distance > max_distance:
            max_distance = distance
            max_index = i
    
    # If max distance is greater than tolerance, recursively simplify
    if max_distance > tolerance:
        # Recursive call
        left = simplify_polyline(coordinates[:max_index + 1], tolerance)
        right = simplify_polyline(coordinates[max_index:], tolerance)
        
        # Combine results (remove duplicate middle point)
        return left[:-1] + right
    else:
        # Base case: keep only endpoints
        return [coordinates[0], coordinates[-1]]


def perpendicular_distance(
    point: Tuple[float, float],
    line_start: Tuple[float, float],
    line_end: Tuple[float, float]
) -> float:
    """
    Calculate perpendicular distance from point to line segment.
    
    Returns approximate distance in degrees (for simplification purposes).
    """
    x, y = point
    x1, y1 = line_start
    x2, y2 = line_end
    
    # Line segment length
    dx = x2 - x1
    dy = y2 - y1
    
    if dx == 0 and dy == 0:
        # Line segment is a point
        return ((x - x1)**2 + (y - y1)**2)**0.5
    
    # Perpendicular distance formula
    numerator = abs(dy * x - dx * y + x2 * y1 - y2 * x1)
    denominator = (dx**2 + dy**2)**0.5
    
    return numerator / denominator
