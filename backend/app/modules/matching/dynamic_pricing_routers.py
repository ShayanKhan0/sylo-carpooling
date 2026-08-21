"""
Dynamic Pricing & Route Membership API Endpoints
=================================================

New endpoints that expose all 4 new modules to Flutter clients:

    GET  /api/v2/pricing/config          — View live fuel price config
    PUT  /api/v2/pricing/config          — Admin: update fuel price settings
    POST /api/v2/pricing/fare-estimate   — Per-passenger fare preview
    POST /api/v2/pricing/route-check     — Check if passenger is on a driver's route
    POST /api/v2/pricing/ride-fares      — Full multi-passenger fare breakdown
    GET  /api/v2/pricing/booking/{id}    — Booking details inc. fare + pickup ETA

Author: M. Mobeen Shoukat Ch & M. Shayan Khan
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.core.fuel_price_engine import (
    load_fuel_config,
    upsert_config_key,
    get_default_config,
    FuelPriceConfig,
)
from app.core.dynamic_fare import (
    PassengerSegment,
    calculate_full_ride_fares,
    quick_fare_estimate,
)
from app.core.route_membership import check_route_membership
from app.core.pickup_time_estimator import compute_all_pickup_times

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pricing", tags=["Dynamic Pricing"])


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class FuelConfigResponse(BaseModel):
    petrol_price_per_litre: float
    fuel_avg_km_per_litre: float
    platform_fee_pct: float
    driver_margin_pct: float
    min_fare_pkr: float
    base_fare_pkr: float
    avg_speed_kmh: float
    fuel_cost_per_km: float
    rate_per_km: float


class UpdateFuelConfigRequest(BaseModel):
    petrol_price_per_litre: Optional[float] = Field(None, gt=0, description="PKR per litre")
    fuel_avg_km_per_litre: Optional[float] = Field(None, gt=0, description="km per litre")
    platform_fee_pct: Optional[float] = Field(None, ge=0, le=1, description="0.0 – 1.0")
    driver_margin_pct: Optional[float] = Field(None, ge=0, le=1, description="0.0 – 1.0")
    min_fare_pkr: Optional[float] = Field(None, gt=0)
    base_fare_pkr: Optional[float] = Field(None, ge=0)
    avg_speed_kmh: Optional[float] = Field(None, gt=0)


class QuickFareRequest(BaseModel):
    segment_km: float = Field(..., gt=0, description="Distance passenger travels on the route (km)")
    seats: int = Field(1, ge=1, le=8)


class RouteCheckRequest(BaseModel):
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float
    passenger_departure_time: datetime
    encoded_polyline: str = Field(..., description="Google Maps Encoded Polyline of the driver's route")
    ride_departure_time: datetime
    threshold_m: float = Field(400.0, gt=0, le=5000)
    time_window_min: float = Field(15.0, gt=0, le=120)


class PassengerSegmentInput(BaseModel):
    passenger_id: UUID
    request_id: UUID
    segment_km: float = Field(..., gt=0)
    seats_needed: int = Field(1, ge=1, le=8)
    pickup_pct: float = Field(0.0, ge=0.0, le=1.0)
    dropoff_pct: float = Field(1.0, ge=0.0, le=1.0)


class RideFaresRequest(BaseModel):
    passengers: List[PassengerSegmentInput] = Field(..., min_items=1)
    total_route_km: float = Field(..., gt=0)


class PickupEtaRequest(BaseModel):
    passengers: List[Dict[str, Any]] = Field(..., description="Each dict: passenger_id, request_id, pickup_lat/lng, pickup_pct, pickup_route_km, ...")
    ride_departure_time: datetime
    route_start_lat: float
    route_start_lng: float


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get(
    "/config",
    response_model=Dict[str, Any],
    summary="Get Live Fuel Price Config",
    description="Returns the current fuel price parameters used for fare calculation.",
)
async def get_fuel_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current fuel price configuration."""
    config = await load_fuel_config(db)
    return {
        "status": "ok",
        "data": config.to_dict(),
        "error": None,
    }


@router.put(
    "/config",
    response_model=Dict[str, Any],
    summary="Update Fuel Price Config (Admin)",
    description="Admin endpoint to update fuel price parameters. Any field can be updated independently.",
)
async def update_fuel_config(
    updates: UpdateFuelConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update one or more fuel price config values.

    Only admin users should call this endpoint in production.
    When petrol price changes, all future fare calculations automatically
    use the new value — no restart required.
    """
    update_map = {
        "petrol_price_per_litre": updates.petrol_price_per_litre,
        "fuel_avg_km_per_litre": updates.fuel_avg_km_per_litre,
        "platform_fee_pct": updates.platform_fee_pct,
        "driver_margin_pct": updates.driver_margin_pct,
        "min_fare_pkr": updates.min_fare_pkr,
        "base_fare_pkr": updates.base_fare_pkr,
        "avg_speed_kmh": updates.avg_speed_kmh,
    }
    updated_keys = []
    for key, value in update_map.items():
        if value is not None:
            try:
                await upsert_config_key(db, key, str(value))
                updated_keys.append(key)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

    if not updated_keys:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    # Return fresh config after update
    config = await load_fuel_config(db)
    return {
        "status": "ok",
        "data": {
            "updated_keys": updated_keys,
            "new_config": config.to_dict(),
        },
        "error": None,
    }


@router.post(
    "/fare-estimate",
    response_model=Dict[str, Any],
    summary="Quick Per-Passenger Fare Estimate",
    description="Returns a quick fare estimate for a single passenger based on their segment distance.",
)
async def quick_fare_preview(
    data: QuickFareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Estimate fare for a single passenger (no sharing split).
    Useful before the full ride is matched to give the passenger a price preview.
    """
    config = await load_fuel_config(db)
    fare = quick_fare_estimate(data.segment_km * data.seats, config)
    return {
        "status": "ok",
        "data": {
            "segment_km": round(data.segment_km, 2),
            "seats": data.seats,
            "estimated_fare_pkr": fare,
            "rate_per_km": round(config.rate_per_km, 4),
            "petrol_price_used": config.petrol_price_per_litre,
        },
        "error": None,
    }


@router.post(
    "/route-check",
    response_model=Dict[str, Any],
    summary="Check If Passenger Is On Driver Route",
    description="""
    Checks whether a passenger's pickup and dropoff points lie on a driver's
    fixed polyline route (no detour allowed).

    Returns:
    - is_eligible: bool
    - If eligible: pickup_pct, dropoff_pct, segment_km, pickup_perp_m, dropoff_perp_m
    - If not eligible: rejection_reason
    """,
)
async def check_passenger_route_membership(
    data: RouteCheckRequest,
    current_user: User = Depends(get_current_user),
):
    """Check route membership for a passenger against a driver's fixed route."""
    result = check_route_membership(
        pickup_lat=data.pickup_lat,
        pickup_lng=data.pickup_lng,
        dropoff_lat=data.dropoff_lat,
        dropoff_lng=data.dropoff_lng,
        passenger_departure_time=data.passenger_departure_time,
        encoded_polyline=data.encoded_polyline,
        ride_departure_time=data.ride_departure_time,
        threshold_m=data.threshold_m,
        time_window_min=data.time_window_min,
    )
    return {
        "status": "ok",
        "data": result.to_dict(),
        "error": None,
    }


@router.post(
    "/ride-fares",
    response_model=Dict[str, Any],
    summary="Full Multi-Passenger Fare Breakdown",
    description="""
    Calculate proportional fares for all passengers on a shared ride.

    Each passenger's fare is proportional to the distance they travel on the
    driver's fixed route (Approach B — Simple Proportional Distance).

    Also shows the live rate_per_km derived from current petrol price.
    """,
)
async def calculate_ride_fares(
    data: RideFaresRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full proportional fare breakdown for a multi-passenger ride."""
    config = await load_fuel_config(db)
    segments = [
        PassengerSegment(
            passenger_id=p.passenger_id,
            request_id=p.request_id,
            segment_km=p.segment_km,
            seats_needed=p.seats_needed,
            pickup_pct=p.pickup_pct,
            dropoff_pct=p.dropoff_pct,
        )
        for p in data.passengers
    ]
    breakdown = calculate_full_ride_fares(
        passengers=segments,
        total_route_km=data.total_route_km,
        config=config,
    )
    return {
        "status": "ok",
        "data": breakdown.to_dict(),
        "error": None,
    }


@router.post(
    "/pickup-etas",
    response_model=Dict[str, Any],
    summary="Compute Per-Passenger Pickup ETAs",
    description="""
    Pre-compute estimated pickup times for each passenger on a scheduled ride.

    ETAs are computed from route distance and average city speed (40 km/h by default).
    Results are sorted by pickup position along the route.
    """,
)
async def compute_pickup_etas(
    data: PickupEtaRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pre-compute pickup ETAs for all passengers on a shared ride."""
    config = await load_fuel_config(db)
    eta_map = await compute_all_pickup_times(
        passengers=data.passengers,
        ride_departure_time=data.ride_departure_time,
        route_start_lat=data.route_start_lat,
        route_start_lng=data.route_start_lng,
        config=config,
    )
    return {
        "status": "ok",
        "data": {
            request_id: result.to_dict()
            for request_id, result in eta_map.items()
        },
        "error": None,
    }


@router.get(
    "/booking/{booking_id}/details",
    response_model=Dict[str, Any],
    summary="Booking Fare & ETA Details",
    description="Returns the full fare breakdown and estimated pickup time for a specific booking.",
)
async def get_booking_fare_details(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return per-booking fare details including:
    - individual_fare (their specific share)
    - estimated_pickup_time
    - segment_km, pickup_pct, dropoff_pct
    - rate_per_km_used (snapshot at booking time)
    """
    from app.models.booking import Booking
    result = await db.execute(
        select(Booking).where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Ensure only the booking's passenger can see their own booking details
    if booking.passenger_id != current_user.id:
        # Allow drivers to see all bookings on their ride
        from app.models.ride import Ride
        ride_result = await db.execute(
            select(Ride).where(Ride.id == booking.ride_id)
        )
        ride = ride_result.scalar_one_or_none()
        if not ride or ride.driver_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")

    return {
        "status": "ok",
        "data": {
            "booking_id": str(booking.id),
            "ride_id": str(booking.ride_id),
            "passenger_id": str(booking.passenger_id),
            "seats_reserved": booking.seats_reserved,
            "fare": float(booking.fare),
            "individual_fare": float(booking.individual_fare) if booking.individual_fare else None,
            "estimated_pickup_time": (
                booking.estimated_pickup_time.isoformat()
                if booking.estimated_pickup_time else None
            ),
            "segment_km": booking.segment_km,
            "pickup_pct": booking.pickup_pct,
            "dropoff_pct": booking.dropoff_pct,
            "pickup_route_km": booking.pickup_route_km,
            "dropoff_route_km": booking.dropoff_route_km,
            "rate_per_km_used": booking.rate_per_km_used,
            "status": str(booking.status),
        },
        "error": None,
    }
