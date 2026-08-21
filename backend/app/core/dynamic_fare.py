"""
Dynamic Fare Calculator — Module 2 (Approach B: Simple Proportional Distance)
==============================================================================

Each passenger pays a fare proportional to the distance they travel on the
driver's FIXED route. The driver's route never changes — no detours.

Formula
-------
Given N passengers on a route, each with segment distance s_i km:

    total_pool_cost  = base_fare + (sum(s_i) × rate_per_km)

    passenger_i fare = base_fare_share + (s_i / sum(s_i)) × pool_distance_cost

    where:
        base_fare_share      = base_fare_pkr / N   (split equally)
        pool_distance_cost   = sum(s_i) × rate_per_km

    Minimum fare enforced per passenger:  max(fare_i, min_fare_pkr)
    Rounding: ceil to nearest 10 PKR

Example (from design proposal)
-------
    Route = 26 km, rate = 41 PKR/km, base = 30 PKR, 3 passengers
    P1 segment = 26 km, P2 = 15 km, P3 = 8 km
    sum(segments) = 49 km
    pool_cost     = 49 × 41 = 2009 PKR
    base share    = 30 / 3  = 10 PKR each
    P1 fare = 10 + (26/49) × 2009 = 10 + 1066 = 1076 PKR → rounded → 1080
    P2 fare = 10 + (15/49) × 2009 = 10 +  615 =  625 PKR → rounded →  630
    P3 fare = 10 + ( 8/49) × 2009 = 10 +  328 =  338 PKR → rounded →  340

Author: M. Mobeen Shoukat Ch & M. Shayan Khan
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID

from app.core.fuel_price_engine import FuelPriceConfig, get_default_config

logger = logging.getLogger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class PassengerSegment:
    """
    Input for a single passenger's fare calculation.

    Attributes:
        passenger_id:   UUID of the passenger
        request_id:     UUID of their RideRequest
        segment_km:     Distance they travel on the driver's route (km)
        seats_needed:   Number of seats they are booking (usually 1)
        pickup_pct:     Where on the route their pickup falls (0.0 – 1.0)
        dropoff_pct:    Where on the route their dropoff falls (0.0 – 1.0)
    """
    passenger_id: UUID
    request_id: UUID
    segment_km: float
    seats_needed: int = 1
    pickup_pct: float = 0.0
    dropoff_pct: float = 1.0


@dataclass
class PassengerFare:
    """
    Output fare breakdown for one passenger.
    """
    passenger_id: UUID
    request_id: UUID
    segment_km: float
    seats_needed: int

    base_share_pkr: float       # their share of the flat base fare
    distance_cost_pkr: float    # proportional distance cost (before rounding)
    raw_fare_pkr: float         # sum before rounding
    final_fare_pkr: float       # rounded up to nearest 10 PKR, >= min_fare
    fare_per_seat_pkr: float    # final_fare / seats_needed (for display)

    proportion: float           # fraction of total segment sum (0.0 – 1.0)
    rate_per_km_used: float     # PKR/km used for this calculation

    def to_dict(self) -> dict:
        return {
            "passenger_id": str(self.passenger_id),
            "request_id": str(self.request_id),
            "segment_km": round(self.segment_km, 2),
            "seats_needed": self.seats_needed,
            "base_share_pkr": round(self.base_share_pkr, 2),
            "distance_cost_pkr": round(self.distance_cost_pkr, 2),
            "raw_fare_pkr": round(self.raw_fare_pkr, 2),
            "final_fare_pkr": round(self.final_fare_pkr, 2),
            "fare_per_seat_pkr": round(self.fare_per_seat_pkr, 2),
            "proportion_pct": round(self.proportion * 100, 1),
            "rate_per_km_used": round(self.rate_per_km_used, 4),
        }


@dataclass
class RideFareBreakdown:
    """
    Complete fare breakdown for an entire multi-passenger ride.
    """
    total_route_km: float
    total_pool_cost_pkr: float          # cost if it were one person riding the full sum of segments
    total_collected_pkr: float          # sum of all final_fare_pkr values
    rate_per_km_used: float
    passenger_fares: List[PassengerFare] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_route_km": round(self.total_route_km, 2),
            "total_pool_cost_pkr": round(self.total_pool_cost_pkr, 2),
            "total_collected_pkr": round(self.total_collected_pkr, 2),
            "rate_per_km_used": round(self.rate_per_km_used, 4),
            "passenger_fares": [pf.to_dict() for pf in self.passenger_fares],
        }


# ── Core calculation functions ─────────────────────────────────────────────────

def calculate_passenger_fare(
    segment_km: float,
    total_segment_sum_km: float,
    n_passengers: int,
    config: FuelPriceConfig,
    seats_needed: int = 1,
    passenger_id: Optional[UUID] = None,
    request_id: Optional[UUID] = None,
    pickup_pct: float = 0.0,
    dropoff_pct: float = 1.0,
) -> PassengerFare:
    """
    Calculate fare for a SINGLE passenger given their segment length and
    the total sum of all passengers' segment lengths on the same ride.

    Args:
        segment_km:          How many km this passenger travels
        total_segment_sum_km: Sum of ALL passengers' segment_km on this ride
        n_passengers:        Total number of passengers (for base fare split)
        config:              Live fuel price configuration
        seats_needed:        Number of seats booked by this passenger
        passenger_id:        UUID (optional, for output)
        request_id:          UUID (optional, for output)
        pickup_pct:          Position along route where passenger boards (0–1)
        dropoff_pct:         Position along route where passenger alights (0–1)

    Returns:
        PassengerFare with full breakdown
    """
    if total_segment_sum_km <= 0:
        total_segment_sum_km = max(segment_km, 0.1)

    rate = config.rate_per_km
    proportion = segment_km / total_segment_sum_km

    # Base fare is split equally regardless of distance
    base_share = (config.base_fare_pkr / max(n_passengers, 1)) * seats_needed

    # Distance cost: proportional share of total pool's distance cost
    pool_distance_cost = total_segment_sum_km * rate
    distance_cost = proportion * pool_distance_cost * seats_needed

    raw_fare = base_share + distance_cost

    # Enforce minimum and round UP to nearest 10 PKR
    min_fare = config.min_fare_pkr * seats_needed
    final_fare = math.ceil(max(raw_fare, min_fare) / 10.0) * 10.0

    return PassengerFare(
        passenger_id=passenger_id or UUID(int=0),
        request_id=request_id or UUID(int=0),
        segment_km=segment_km,
        seats_needed=seats_needed,
        base_share_pkr=base_share,
        distance_cost_pkr=distance_cost,
        raw_fare_pkr=raw_fare,
        final_fare_pkr=final_fare,
        fare_per_seat_pkr=final_fare / seats_needed,
        proportion=proportion,
        rate_per_km_used=rate,
    )


def calculate_full_ride_fares(
    passengers: List[PassengerSegment],
    total_route_km: float,
    config: Optional[FuelPriceConfig] = None,
) -> RideFareBreakdown:
    """
    Calculate fares for ALL passengers on a shared ride in one call.

    The driver's total route distance is used for context only (display).
    The actual pooled cost is based on the sum of passenger segments.

    Args:
        passengers:      List of PassengerSegment — one per passenger
        total_route_km:  Driver's full route distance (for display / context)
        config:          FuelPriceConfig (uses defaults if not provided)

    Returns:
        RideFareBreakdown with per-passenger fares and totals
    """
    if config is None:
        config = get_default_config()

    if not passengers:
        return RideFareBreakdown(
            total_route_km=total_route_km,
            total_pool_cost_pkr=0.0,
            total_collected_pkr=0.0,
            rate_per_km_used=config.rate_per_km,
            passenger_fares=[],
        )

    total_seg_sum = sum(
        p.segment_km * p.seats_needed for p in passengers
    )
    n_passengers = len(passengers)
    fares: List[PassengerFare] = []

    for p in passengers:
        fare = calculate_passenger_fare(
            segment_km=p.segment_km,
            total_segment_sum_km=total_seg_sum,
            n_passengers=n_passengers,
            config=config,
            seats_needed=p.seats_needed,
            passenger_id=p.passenger_id,
            request_id=p.request_id,
            pickup_pct=p.pickup_pct,
            dropoff_pct=p.dropoff_pct,
        )
        fares.append(fare)

    total_collected = sum(f.final_fare_pkr for f in fares)
    pool_cost = total_seg_sum * config.rate_per_km

    logger.debug(
        f"Fare calc: {n_passengers} passengers | "
        f"sum_segments={total_seg_sum:.1f}km | "
        f"rate={config.rate_per_km:.2f} PKR/km | "
        f"total_collected={total_collected:.0f} PKR"
    )

    return RideFareBreakdown(
        total_route_km=total_route_km,
        total_pool_cost_pkr=pool_cost,
        total_collected_pkr=total_collected,
        rate_per_km_used=config.rate_per_km,
        passenger_fares=fares,
    )


def quick_fare_estimate(
    segment_km: float,
    config: Optional[FuelPriceConfig] = None,
) -> float:
    """
    Quick single-passenger fare estimate (no sharing).
    Used for displaying preview before booking confirmation.

    Returns fare in PKR (rounded up to nearest 10).
    """
    if config is None:
        config = get_default_config()
    raw = config.base_fare_pkr + segment_km * config.rate_per_km
    return math.ceil(max(raw, config.min_fare_pkr) / 10.0) * 10.0
