"""
Per-Passenger Pickup Time Estimator — Module 4
===============================================

Pre-computes the estimated pickup time for EACH passenger on a scheduled ride
based on how far along the driver's route their pickup point falls.

Strategy
--------
Two estimation modes (both give the same result for scheduled rides):

    Mode A — Polyline distance (default, no API call needed):
        ETA_pickup_i = ride_departure_time + (pickup_route_km / avg_speed_kmh) * 60 min

        The driver leaves at departure_time from the route start.
        At average speed `avg_speed_kmh`, they reach each passenger's projected
        pickup point at a predictable time.

    Mode B — Google Maps Distance Matrix API (optional, more accurate):
        Calls Google Maps to get actual driving time from ride start to each
        pickup point, then adds that to departure_time.

Mode A is used by default (no API cost, instant, deterministic).
Mode B is called only when a valid GOOGLE_MAPS_KEY is available AND the
`use_google_api=True` flag is passed.

All computed ETAs are stored in the `bookings.estimated_pickup_time` column
so passengers can see them instantly in their dashboard.

Author: M. Mobeen Shoukat Ch & M. Shayan Khan
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from app.core.route_membership import (
    decode_polyline,
    _build_cumulative_distances,
    _haversine_km,
    LatLng,
)
from app.core.fuel_price_engine import FuelPriceConfig, get_default_config

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class PassengerStop:
    """
    Represents one passenger's stop information needed for ETA computation.
    """
    passenger_id: UUID
    request_id: UUID
    pickup_lat: float
    pickup_lng: float
    pickup_pct: float        # fraction along route (0.0 – 1.0)
    pickup_route_km: float   # distance along route to this pickup (km)
    dropoff_lat: float
    dropoff_lng: float
    dropoff_pct: float
    dropoff_route_km: float
    segment_km: float        # km from pickup to dropoff along route


@dataclass
class PickupTimeResult:
    """
    Estimated pickup time for one passenger.
    """
    passenger_id: UUID
    request_id: UUID
    estimated_pickup_time: datetime
    minutes_after_departure: float   # how many minutes after ride starts
    pickup_route_km: float           # confirmed km from route start to pickup

    def to_dict(self) -> dict:
        return {
            "passenger_id": str(self.passenger_id),
            "request_id": str(self.request_id),
            "estimated_pickup_time": self.estimated_pickup_time.isoformat(),
            "minutes_after_departure": round(self.minutes_after_departure, 1),
            "pickup_route_km": round(self.pickup_route_km, 3),
        }


# ── Polyline-based estimator (Mode A) ─────────────────────────────────────────

def estimate_pickup_times_from_polyline(
    stops: List[PassengerStop],
    ride_departure_time: datetime,
    config: Optional[FuelPriceConfig] = None,
) -> List[PickupTimeResult]:
    """
    Estimate pickup times for all passengers using polyline distance + speed.

    The driver starts at departure_time from the route origin (pct = 0.0).
    Each passenger's pickup time = departure_time + (pickup_route_km / avg_speed_kmh) hours.

    Stops are sorted by pickup_pct so results are in route order.

    Args:
        stops:                List of PassengerStop objects
        ride_departure_time:  When the driver leaves the route start
        config:               FuelPriceConfig (used for avg_speed_kmh)

    Returns:
        List of PickupTimeResult sorted by route position (earliest pickup first)
    """
    if config is None:
        config = get_default_config()

    avg_speed = config.avg_speed_kmh
    if avg_speed <= 0:
        avg_speed = 40.0   # safe fallback

    # Sort by pickup position along route
    sorted_stops = sorted(stops, key=lambda s: s.pickup_route_km)

    results: List[PickupTimeResult] = []
    for stop in sorted_stops:
        hours_to_pickup = stop.pickup_route_km / avg_speed
        minutes_to_pickup = hours_to_pickup * 60.0
        eta = ride_departure_time + timedelta(minutes=minutes_to_pickup)

        results.append(
            PickupTimeResult(
                passenger_id=stop.passenger_id,
                request_id=stop.request_id,
                estimated_pickup_time=eta,
                minutes_after_departure=minutes_to_pickup,
                pickup_route_km=stop.pickup_route_km,
            )
        )
        logger.debug(
            f"Passenger {stop.passenger_id}: "
            f"pickup at {stop.pickup_route_km:.2f} km | "
            f"ETA {eta.strftime('%H:%M')} "
            f"(+{minutes_to_pickup:.1f} min)"
        )

    return results


# ── Google Maps estimator (Mode B — optional) ──────────────────────────────────

async def estimate_pickup_times_google_maps(
    stops: List[PassengerStop],
    ride_departure_time: datetime,
    route_start_lat: float,
    route_start_lng: float,
    google_maps_key: str,
) -> List[PickupTimeResult]:
    """
    Use Google Maps Distance Matrix API to get accurate driving times from
    the route start to each passenger's pickup point.

    Falls back silently to polyline-based estimation if the API call fails.

    Args:
        stops:              Passengers to compute ETAs for
        ride_departure_time: Driver's scheduled departure
        route_start_lat/lng: Starting point of the route
        google_maps_key:    API key

    Returns:
        List of PickupTimeResult — ordered by route position
    """
    try:
        import httpx

        origins = f"{route_start_lat},{route_start_lng}"
        destinations = "|".join(
            f"{s.pickup_lat},{s.pickup_lng}" for s in stops
        )

        url = (
            f"https://maps.googleapis.com/maps/api/distancematrix/json"
            f"?origins={origins}"
            f"&destinations={destinations}"
            f"&mode=driving"
            f"&departure_time=now"
            f"&key={google_maps_key}"
        )

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        rows = data.get("rows", [{}])
        elements = rows[0].get("elements", [])

        results: List[PickupTimeResult] = []
        for stop, element in zip(stops, elements):
            if element.get("status") == "OK":
                duration_sec = element["duration"]["value"]
                duration_min = duration_sec / 60.0
                eta = ride_departure_time + timedelta(seconds=duration_sec)
            else:
                # API could not route — fall back to polyline estimate
                logger.warning(
                    f"Google Maps could not route to passenger {stop.passenger_id}: "
                    f"{element.get('status')} — falling back to polyline ETA"
                )
                avg_speed = 40.0
                duration_min = (stop.pickup_route_km / avg_speed) * 60.0
                eta = ride_departure_time + timedelta(minutes=duration_min)

            results.append(
                PickupTimeResult(
                    passenger_id=stop.passenger_id,
                    request_id=stop.request_id,
                    estimated_pickup_time=eta,
                    minutes_after_departure=duration_min,
                    pickup_route_km=stop.pickup_route_km,
                )
            )

        return sorted(results, key=lambda r: r.pickup_route_km)

    except Exception as exc:
        logger.warning(
            f"Google Maps ETA failed: {exc} — falling back to polyline estimation"
        )
        return estimate_pickup_times_from_polyline(stops, ride_departure_time)


# ── Unified entry-point ────────────────────────────────────────────────────────

async def compute_all_pickup_times(
    passengers: List[dict],   # dicts with passenger_id, request_id, pickup_lat/lng, pickup_pct, pickup_route_km, dropoff_lat/lng, dropoff_pct, dropoff_route_km, segment_km
    ride_departure_time: datetime,
    route_start_lat: float,
    route_start_lng: float,
    config: Optional[FuelPriceConfig] = None,
    google_maps_key: Optional[str] = None,
    use_google_api: bool = False,
) -> Dict[str, PickupTimeResult]:
    """
    Unified interface — called by ride_cluster_service.py after fare calculation.

    Converts raw passenger dicts → PassengerStop objects, runs the appropriate
    estimator, and returns a dict keyed by request_id (str) for easy lookup.

    Args:
        passengers:          Output from route_membership.filter_eligible_passengers
                             (each dict must have pickup_pct, pickup_route_km etc.)
        ride_departure_time: Driver's departure time
        route_start_lat/lng: Route origin coordinates
        config:              FuelPriceConfig (for avg_speed_kmh)
        google_maps_key:     Optional API key; if set AND use_google_api=True, uses Maps API
        use_google_api:      Whether to use Google Maps API (costs money per call)

    Returns:
        Dict mapping request_id (str) → PickupTimeResult
    """
    if config is None:
        config = get_default_config()

    stops: List[PassengerStop] = []
    for p in passengers:
        try:
            stops.append(PassengerStop(
                passenger_id=p["passenger_id"],
                request_id=p["request_id"],
                pickup_lat=float(p["pickup_lat"]),
                pickup_lng=float(p["pickup_lng"]),
                pickup_pct=float(p.get("pickup_pct", 0.0)),
                pickup_route_km=float(p.get("pickup_route_km", 0.0)),
                dropoff_lat=float(p["dropoff_lat"]),
                dropoff_lng=float(p["dropoff_lng"]),
                dropoff_pct=float(p.get("dropoff_pct", 1.0)),
                dropoff_route_km=float(p.get("dropoff_route_km", 0.0)),
                segment_km=float(p.get("segment_km", 0.0)),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(f"Skipping passenger ETA due to bad data: {exc}")
            continue

    if not stops:
        return {}

    if use_google_api and google_maps_key:
        results = await estimate_pickup_times_google_maps(
            stops=stops,
            ride_departure_time=ride_departure_time,
            route_start_lat=route_start_lat,
            route_start_lng=route_start_lng,
            google_maps_key=google_maps_key,
        )
    else:
        results = estimate_pickup_times_from_polyline(
            stops=stops,
            ride_departure_time=ride_departure_time,
            config=config,
        )

    return {str(r.request_id): r for r in results}


def format_eta_display(eta: datetime, now: Optional[datetime] = None) -> str:
    """
    Return a human-friendly ETA string, e.g. "4:15 PM (+12 min)".

    Args:
        eta:  The computed pickup datetime
        now:  Reference time (defaults to utcnow)
    """
    if now is None:
        now = datetime.utcnow()
    delta_min = (eta - now).total_seconds() / 60.0
    time_str = eta.strftime("%-I:%M %p") if hasattr(eta, "strftime") else str(eta)
    if delta_min > 0:
        return f"{time_str} (+{delta_min:.0f} min)"
    return time_str
