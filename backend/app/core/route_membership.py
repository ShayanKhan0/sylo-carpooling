"""
Route Membership Check — Module 3 (No-Detour Design)
=====================================================

Determines whether a passenger's pickup AND dropoff points lie on a driver's
FIXED polyline route — with NO detour allowed.

A passenger is eligible to join a ride if and only if:
    1. Their pickup perpendicular distance from the polyline ≤ threshold (400 m)
    2. Their dropoff perpendicular distance from the polyline ≤ threshold (400 m)
    3. Pickup position % < Dropoff position % (forward movement along the route)
    4. Their desired departure time is within ±15 minutes of the ride departure

If eligible, we also compute:
    - pickup_pct      → where on the route (0.0 – 1.0) the pickup falls
    - dropoff_pct     → where on the route (0.0 – 1.0) the dropoff falls
    - segment_km      → actual route distance between their pickup and dropoff

Polyline encoding:
    Google Maps Encoded Polyline format (ASCII string).
    We decode it to a list of (lat, lng) tuples and walk the segments.

Author: M. Mobeen Shoukat Ch & M. Shayan Khan
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
EARTH_RADIUS_KM: float = 6371.0

# Maximum perpendicular distance from route polyline for a point to be "on route"
DEFAULT_THRESHOLD_M: float = 400.0   # 400 metres

# Maximum time window mismatch between ride departure and passenger's desired time
DEFAULT_TIME_WINDOW_MIN: float = 15.0  # ± 15 minutes


# ── Point type ────────────────────────────────────────────────────────────────
LatLng = Tuple[float, float]   # (latitude, longitude)


# ── Haversine helper ──────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    return _haversine_km(lat1, lng1, lat2, lng2) * 1000.0


# ── Google Encoded Polyline decoder ───────────────────────────────────────────

def decode_polyline(encoded: str) -> List[LatLng]:
    """
    Decode a Google Maps Encoded Polyline string into a list of (lat, lng) tuples.

    Reference: https://developers.google.com/maps/documentation/utilities/polylinealgorithm
    """
    coords: List[LatLng] = []
    index = 0
    lat = 0
    lng = 0
    length = len(encoded)

    while index < length:
        # Decode latitude
        result = 0
        shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if result & 1 else result >> 1
        lat += dlat

        # Decode longitude
        result = 0
        shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if result & 1 else result >> 1
        lng += dlng

        coords.append((lat * 1e-5, lng * 1e-5))

    return coords


def encode_polyline(coords: List[LatLng]) -> str:
    """
    Encode a list of (lat, lng) tuples into a Google Maps Encoded Polyline string.
    """
    def _encode_value(value: int) -> str:
        value = ~(value << 1) if value < 0 else value << 1
        chunks = []
        while value >= 0x20:
            chunks.append(chr((0x20 | (value & 0x1F)) + 63))
            value >>= 5
        chunks.append(chr(value + 63))
        return "".join(chunks)

    result = []
    prev_lat = 0
    prev_lng = 0
    for lat, lng in coords:
        lat_int = round(lat * 1e5)
        lng_int = round(lng * 1e5)
        result.append(_encode_value(lat_int - prev_lat))
        result.append(_encode_value(lng_int - prev_lng))
        prev_lat = lat_int
        prev_lng = lng_int
    return "".join(result)


# ── Segment cumulative distances ──────────────────────────────────────────────

def _build_cumulative_distances(points: List[LatLng]) -> List[float]:
    """
    Return cumulative km at each polyline vertex.

    Result[0] = 0.0 (start of route)
    Result[i] = distance from start to points[i]
    """
    cum = [0.0]
    for i in range(1, len(points)):
        d = _haversine_km(points[i-1][0], points[i-1][1], points[i][0], points[i][1])
        cum.append(cum[-1] + d)
    return cum


# ── Perpendicular projection ───────────────────────────────────────────────────

def _project_point_to_segment(
    px: float, py: float,
    ax: float, ay: float,
    bx: float, by: float,
) -> Tuple[float, float, float]:
    """
    Project point P onto segment AB.

    Works in Cartesian approximation (good enough for city-scale distances).
    Returns:
        (proj_x, proj_y, t)
        where t ∈ [0, 1] is the fractional position along AB,
        proj_x / proj_y is the projected coordinate.
    """
    abx = bx - ax
    aby = by - ay
    ab_sq = abx * abx + aby * aby
    if ab_sq == 0:
        return ax, ay, 0.0
    apx = px - ax
    apy = py - ay
    t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab_sq))
    return ax + t * abx, ay + t * aby, t


def project_point_to_polyline(
    point_lat: float,
    point_lng: float,
    polyline_points: List[LatLng],
    cumulative_km: Optional[List[float]] = None,
) -> Tuple[float, float, float, float]:
    """
    Find the closest projection of `point` onto the polyline.

    Returns:
        (perp_distance_m, route_km, route_pct, segment_index)

        perp_distance_m: perpendicular distance from point to nearest segment (metres)
        route_km:        distance along the polyline to the projection point (km)
        route_pct:       fraction along the full route (0.0 – 1.0)
        segment_index:   which segment of the polyline is closest
    """
    if not polyline_points or len(polyline_points) < 2:
        return float("inf"), 0.0, 0.0, 0

    if cumulative_km is None:
        cumulative_km = _build_cumulative_distances(polyline_points)

    total_km = cumulative_km[-1]
    if total_km <= 0:
        return float("inf"), 0.0, 0.0, 0

    best_dist_m = float("inf")
    best_route_km = 0.0
    best_seg_idx = 0

    for i in range(len(polyline_points) - 1):
        a = polyline_points[i]
        b = polyline_points[i + 1]

        proj_lat, proj_lng, t = _project_point_to_segment(
            point_lat, point_lng,
            a[0], a[1],
            b[0], b[1],
        )

        dist_m = _haversine_m(point_lat, point_lng, proj_lat, proj_lng)

        if dist_m < best_dist_m:
            best_dist_m = dist_m
            seg_km = _haversine_km(a[0], a[1], b[0], b[1])
            best_route_km = cumulative_km[i] + t * seg_km
            best_seg_idx = i

    route_pct = best_route_km / total_km
    return best_dist_m, best_route_km, route_pct, best_seg_idx


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class MembershipResult:
    """Result of checking if a passenger is eligible to join a ride."""
    is_eligible: bool

    # Why they were rejected (if is_eligible = False)
    rejection_reason: Optional[str] = None

    # If eligible — filled with position/distance data
    pickup_pct: float = 0.0          # fraction along route where pickup falls
    dropoff_pct: float = 1.0         # fraction along route where dropoff falls
    pickup_route_km: float = 0.0     # km along route to pickup
    dropoff_route_km: float = 0.0    # km along route to dropoff
    segment_km: float = 0.0          # route km between pickup and dropoff

    pickup_perp_m: float = 0.0       # metres off-route for pickup point
    dropoff_perp_m: float = 0.0      # metres off-route for dropoff point

    def to_dict(self) -> dict:
        return {
            "is_eligible": self.is_eligible,
            "rejection_reason": self.rejection_reason,
            "pickup_pct": round(self.pickup_pct, 4),
            "dropoff_pct": round(self.dropoff_pct, 4),
            "pickup_route_km": round(self.pickup_route_km, 3),
            "dropoff_route_km": round(self.dropoff_route_km, 3),
            "segment_km": round(self.segment_km, 3),
            "pickup_perp_m": round(self.pickup_perp_m, 1),
            "dropoff_perp_m": round(self.dropoff_perp_m, 1),
        }


# ── Main eligibility check ─────────────────────────────────────────────────────

def check_route_membership(
    pickup_lat: float,
    pickup_lng: float,
    dropoff_lat: float,
    dropoff_lng: float,
    passenger_departure_time: datetime,
    encoded_polyline: str,
    ride_departure_time: datetime,
    threshold_m: float = DEFAULT_THRESHOLD_M,
    time_window_min: float = DEFAULT_TIME_WINDOW_MIN,
) -> MembershipResult:
    """
    Check whether a passenger's pickup + dropoff lie on a driver's fixed route.

    Rules (ALL must pass):
        1. Pickup is within `threshold_m` metres of the polyline
        2. Dropoff is within `threshold_m` metres of the polyline
        3. pickup_pct < dropoff_pct  (passenger moves forward on the route)
        4. |passenger_departure_time - ride_departure_time| <= time_window_min

    Args:
        pickup_lat / pickup_lng:   Passenger's desired pickup point
        dropoff_lat / dropoff_lng: Passenger's desired dropoff point
        passenger_departure_time:  When the passenger wants to travel
        encoded_polyline:          Google Maps Encoded Polyline of the driver's route
        ride_departure_time:       When the driver's ride departs
        threshold_m:               Max off-route distance in metres (default 400 m)
        time_window_min:           Max time delta in minutes (default 15 min)

    Returns:
        MembershipResult with is_eligible flag and detailed position data
    """
    # ── Step 0: Decode polyline ───────────────────────────────────────────────
    try:
        points = decode_polyline(encoded_polyline)
    except Exception as exc:
        logger.warning(f"Failed to decode polyline: {exc}")
        return MembershipResult(is_eligible=False, rejection_reason="invalid_polyline")

    if len(points) < 2:
        return MembershipResult(is_eligible=False, rejection_reason="polyline_too_short")

    cum_km = _build_cumulative_distances(points)
    total_km = cum_km[-1]

    # ── Step 1: Check time window ─────────────────────────────────────────────
    time_delta_min = abs(
        (passenger_departure_time - ride_departure_time).total_seconds() / 60.0
    )
    if time_delta_min > time_window_min:
        return MembershipResult(
            is_eligible=False,
            rejection_reason=f"time_mismatch_{time_delta_min:.0f}min_outside_{time_window_min:.0f}min_window",
        )

    # ── Step 2: Project pickup onto route ─────────────────────────────────────
    pickup_perp_m, pickup_route_km, pickup_pct, _ = project_point_to_polyline(
        pickup_lat, pickup_lng, points, cum_km
    )
    if pickup_perp_m > threshold_m:
        return MembershipResult(
            is_eligible=False,
            rejection_reason=f"pickup_off_route_{pickup_perp_m:.0f}m_exceeds_{threshold_m:.0f}m_threshold",
        )

    # ── Step 3: Project dropoff onto route ────────────────────────────────────
    dropoff_perp_m, dropoff_route_km, dropoff_pct, _ = project_point_to_polyline(
        dropoff_lat, dropoff_lng, points, cum_km
    )
    if dropoff_perp_m > threshold_m:
        return MembershipResult(
            is_eligible=False,
            rejection_reason=f"dropoff_off_route_{dropoff_perp_m:.0f}m_exceeds_{threshold_m:.0f}m_threshold",
        )

    # ── Step 4: Forward movement check ───────────────────────────────────────
    # We use a small tolerance to handle cases where pickup ≈ dropoff projection
    if pickup_route_km >= dropoff_route_km - 0.05:
        return MembershipResult(
            is_eligible=False,
            rejection_reason="backward_or_zero_movement_along_route",
        )

    segment_km = dropoff_route_km - pickup_route_km

    logger.debug(
        f"Route membership OK: pickup={pickup_pct:.2%} dropoff={dropoff_pct:.2%} "
        f"segment={segment_km:.2f}km "
        f"perp_pickup={pickup_perp_m:.0f}m perp_drop={dropoff_perp_m:.0f}m"
    )

    return MembershipResult(
        is_eligible=True,
        pickup_pct=pickup_pct,
        dropoff_pct=dropoff_pct,
        pickup_route_km=pickup_route_km,
        dropoff_route_km=dropoff_route_km,
        segment_km=segment_km,
        pickup_perp_m=pickup_perp_m,
        dropoff_perp_m=dropoff_perp_m,
    )


def get_segment_km(
    pickup_pct: float,
    dropoff_pct: float,
    total_route_km: float,
) -> float:
    """
    Simple segment distance from route percentages.
    Use this when you already have pct values from a previous membership check.
    """
    return max(0.0, (dropoff_pct - pickup_pct) * total_route_km)


def filter_eligible_passengers(
    candidates: list,     # List of dicts with keys: passenger_id, request_id, pickup_lat/lng, dropoff_lat/lng, departure_time
    encoded_polyline: str,
    ride_departure_time: datetime,
    total_route_km: float,
    threshold_m: float = DEFAULT_THRESHOLD_M,
    time_window_min: float = DEFAULT_TIME_WINDOW_MIN,
) -> list:
    """
    Filter a list of passenger candidates to only those eligible for this ride.

    Each candidate dict should have:
        passenger_id, request_id, pickup_lat, pickup_lng, dropoff_lat, dropoff_lng,
        departure_time (datetime), seats_needed (int, default 1)

    Returns a list of dicts with the original candidate data PLUS:
        membership: MembershipResult
        segment_km: float
        pickup_pct: float
        dropoff_pct: float
    """
    eligible = []
    for c in candidates:
        result = check_route_membership(
            pickup_lat=c["pickup_lat"],
            pickup_lng=c["pickup_lng"],
            dropoff_lat=c["dropoff_lat"],
            dropoff_lng=c["dropoff_lng"],
            passenger_departure_time=c["departure_time"],
            encoded_polyline=encoded_polyline,
            ride_departure_time=ride_departure_time,
            threshold_m=threshold_m,
            time_window_min=time_window_min,
        )
        if result.is_eligible:
            c = dict(c)
            c["membership"] = result
            c["segment_km"] = result.segment_km
            c["pickup_pct"] = result.pickup_pct
            c["dropoff_pct"] = result.dropoff_pct
            eligible.append(c)
        else:
            logger.debug(
                f"Passenger {c.get('passenger_id')} rejected: {result.rejection_reason}"
            )
    return eligible
