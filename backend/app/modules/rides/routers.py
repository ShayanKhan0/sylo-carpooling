"""
Module: Rides - API Router
Purpose: REST API endpoints for ride creation, booking, and lifecycle management.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: All endpoints are JWT-protected and follow standardized response format.
"""

from uuid import UUID
from typing import Dict, Any, Optional
from datetime import date, datetime
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.rides import service
from app.modules.rides.schemas import (
    RideCreate, RideUpdate, RidePublic,
    RideBookingCreate, RideBookingPublic,
    RideStatusUpdate, BookingCancellation,
    RideRequestCreate, RideRequestPublic,
    FareEstimateRequest, FareEstimateResponse,
    RideRouteSelectionUpdate,
)

router = APIRouter(prefix="/rides", tags=["Rides"])


# ============================================
# RIDE MANAGEMENT ENDPOINTS (DRIVER)
# ============================================

@router.post(
    "/create",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Create New Ride",
    description="""
    Create a new ride offer (driver only).
    
    **Requirements:**
    - Valid JWT token
    - User must be a verified active driver
    - Vehicle must be active and verified
    - Available seats must be <= vehicle capacity
    
    **Business Rules:**
    - Departure time must be in the future
    - Price per seat: 50 PKR to 10,000 PKR
    - Seats: 1-8 passengers
    - Initial status: "scheduled"
    
    **Example Request:**
    ```json
    {
        "origin": "FAST NUCES, Lahore",
        "destination": "Liberty Market, Gulberg",
        "departure_time": "2025-11-08T09:00:00+05:00",
        "available_seats": 3,
        "price_per_seat": 150.0,
        "vehicle_id": "550e8400-e29b-41d4-a716-446655440000",
        "estimated_duration": 30,
        "route_distance_km": 12.5
    }
    ```
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "id": "770e8400-e29b-41d4-a716-446655440002",
            "driver_id": "660e8400-e29b-41d4-a716-446655440001",
            "origin": "FAST NUCES, Lahore",
            "destination": "Liberty Market, Gulberg",
            "available_seats": 3,
            "price_per_seat": 150.0,
            "status": "scheduled"
        },
        "error": null
    }
    ```
    """
)
async def create_ride(
    ride_data: RideCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new ride offer (driver only)."""
    return await service.create_ride_service(db, current_user.id, ride_data)


@router.get(
    "/available",
    response_model=Dict[str, Any],
    summary="List Available Rides",
    description="""
    Get all available rides with optional filters.
    
    **Filters:**
    - `origin`: Filter by origin location (partial match)
    - `destination`: Filter by destination location (partial match)
    - `min_seats`: Minimum available seats required
    - `driver_total_seats`: Exact total seats the driver offered for the ride
    - `max_price`: Maximum price per seat
    - `departure_after`: Filter by departure time
    
    **Response:**
    - Only returns rides with status = "scheduled"
    - Only returns rides with available_seats > 0
    - Only returns future rides (departure_time > now)
    - Ordered by departure time (earliest first)
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": [
            {
                "id": "770e8400-e29b-41d4-a716-446655440002",
                "origin": "FAST NUCES, Lahore",
                "destination": "Liberty Market",
                "departure_time": "2025-11-08T09:00:00+05:00",
                "available_seats": 3,
                "price_per_seat": 150.0,
                "status": "scheduled"
            }
        ],
        "error": null
    }
    ```
    """
)
async def list_available_rides(
    origin: Optional[str] = Query(None, description="Filter by origin text"),
    destination: Optional[str] = Query(None, description="Filter by destination text"),
    origin_lat: Optional[float] = Query(None, ge=-90, le=90, description="Origin latitude for geo search"),
    origin_lng: Optional[float] = Query(None, ge=-180, le=180, description="Origin longitude for geo search"),
    destination_lat: Optional[float] = Query(None, ge=-90, le=90, description="Destination latitude for geo search"),
    destination_lng: Optional[float] = Query(None, ge=-180, le=180, description="Destination longitude for geo search"),
    radius_km: float = Query(5.0, gt=0, le=100, description="Search radius in km"),
    min_seats: Optional[int] = Query(None, ge=1, le=8, description="Minimum available seats"),
    driver_total_seats: Optional[int] = Query(
        None,
        ge=1,
        le=8,
        description="Exact total seats offered by driver",
    ),
    max_price: Optional[float] = Query(None, gt=0, description="Maximum price per seat"),
    departure_after: Optional[datetime] = Query(None, description="Filter by departure time"),
    departure_before: Optional[datetime] = Query(
        None, description="Filter by latest allowed departure time"
    ),
    include_recurring: bool = Query(
        False,
        description="Include rides materialized from recurring schedules",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all available rides with optional text or geo-proximity filters."""
    return await service.list_available_rides_service(
        db,
        origin=origin,
        destination=destination,
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        destination_lat=destination_lat,
        destination_lng=destination_lng,
        radius_km=radius_km,
        min_seats=min_seats,
        driver_total_seats=driver_total_seats,
        max_price=max_price,
        departure_after=departure_after,
        departure_before=departure_before,
        include_recurring=include_recurring,
    )


# ============================================
# STATIC /my/* ROUTES — MUST BE BEFORE /{ride_id}
# ============================================

@router.get(
    "/my/driver",
    response_model=Dict[str, Any],
    summary="Get My Rides (Driver)",
)
async def get_my_driver_rides(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all rides created by current driver."""
    return await service.get_driver_rides_service(db, current_user.id, status_filter)


@router.get(
    "/my/bookings",
    response_model=Dict[str, Any],
    summary="Get My Bookings (Passenger)",
)
async def get_my_bookings(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all bookings made by current passenger."""
    return await service.get_user_bookings_service(db, current_user.id, status_filter)


@router.get(
    "/my/occupied-slots",
    response_model=Dict[str, Any],
    summary="Get My Occupied Time Slots",
)
async def get_my_occupied_slots(
    target_date: date = Query(
        ...,
        description=(
            "Selected date in YYYY-MM-DD format. Interpreted as local date "
            "when timezone_offset_minutes is provided."
        ),
    ),
    mode: str = Query("driver", pattern="^(driver|passenger)$", description="Slot source mode"),
    timezone_offset_minutes: Optional[int] = Query(
        None,
        ge=-840,
        le=840,
        description="Client UTC offset in minutes (for example +300 for PKT)",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get occupied windows for the selected day for either driver or passenger context."""
    return await service.get_my_occupied_slots_service(
        db=db,
        user_id=current_user.id,
        target_date=target_date,
        mode=mode,
        timezone_offset_minutes=timezone_offset_minutes,
    )


@router.get(
    "/my/stats/driver",
    response_model=Dict[str, Any],
    summary="Get Driver Ride Statistics",
)
async def get_driver_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive ride statistics for driver."""
    return await service.get_driver_ride_statistics_service(db, current_user.id)


@router.get(
    "/my/stats/passenger",
    response_model=Dict[str, Any],
    summary="Get Passenger Booking History",
)
async def get_passenger_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive booking history for passenger."""
    return await service.get_passenger_booking_history_service(db, current_user.id)


# ============================================
# PARAMETRIC RIDE ROUTES  (/{ride_id} must come AFTER /my/*)
# ============================================

@router.get(
    "/{ride_id}",
    response_model=Dict[str, Any],
    summary="Get Ride Details",
)
async def get_ride_details(
    ride_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed information about a specific ride."""
    return await service.get_ride_details_service(db, current_user.id, ride_id)


@router.put(
    "/{ride_id}",
    response_model=Dict[str, Any],
    summary="Update Ride Details",
)
async def update_ride(
    ride_id: UUID,
    ride_update: RideUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update ride details (driver only, before ride starts)."""
    return await service.update_ride_service(db, current_user.id, ride_id, ride_update)


@router.put(
    "/{ride_id}/status",
    response_model=Dict[str, Any],
    summary="Update Ride Status",
)
async def update_ride_status(
    ride_id: UUID,
    status_update: RideStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update ride status (driver only)."""
    return await service.update_ride_status_service(db, current_user.id, ride_id, status_update)


@router.put(
    "/{ride_id}/route-selection",
    response_model=Dict[str, Any],
    summary="Select Planned Route Option",
)
async def update_ride_route_selection(
    ride_id: UUID,
    route_selection: RideRouteSelectionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Driver can switch to another precomputed route option while ride status is open."""
    return await service.update_ride_route_selection_service(
        db,
        current_user.id,
        ride_id,
        route_selection,
    )


@router.delete(
    "/{ride_id}",
    response_model=Dict[str, Any],
    summary="Delete Ride",
)
async def delete_ride(
    ride_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a ride (only if no active bookings)."""
    return await service.delete_ride_service(db, current_user.id, ride_id)


# ============================================
# BOOKING ENDPOINTS (PASSENGER)
# ============================================

@router.post(
    "/book",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Book a Ride",
)
async def book_ride(
    booking_data: RideBookingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Book a ride as a passenger."""
    return await service.book_ride_service(db, current_user.id, booking_data)


@router.put(
    "/bookings/{booking_id}/cancel",
    response_model=Dict[str, Any],
    summary="Cancel Booking",
)
async def cancel_booking(
    booking_id: UUID,
    cancellation: BookingCancellation = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Cancel a booking and restore seats."""
    return await service.cancel_booking_service(db, current_user.id, booking_id, cancellation)


@router.put(
    "/bookings/{booking_id}/pickup-complete",
    response_model=Dict[str, Any],
    summary="Mark Booking Pickup Complete",
)
async def mark_booking_pickup_complete(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Driver marks a passenger pickup as completed during an in-progress ride."""
    return await service.mark_booking_pickup_completed_service(
        db,
        current_user.id,
        booking_id,
    )


@router.put(
    "/bookings/{booking_id}/dropoff-complete",
    response_model=Dict[str, Any],
    summary="Mark Booking Dropoff Complete",
)
async def mark_booking_dropoff_complete(
    booking_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Driver marks a passenger dropoff as completed during an in-progress ride."""
    return await service.mark_booking_dropoff_completed_service(
        db,
        current_user.id,
        booking_id,
    )


# ============================================
# FARE CALCULATOR ENDPOINTS
# ============================================

@router.post(
    "/fare-estimate",
    response_model=Dict[str, Any],
    summary="Calculate Fare Estimate",
    description="""
    Calculate shared fare estimate for a ride based on distance and seats.

    **Formula:**
    - fuelCost = (distance_km / fuel_average) × petrol_price
    - platformFee = fuelCost × 30%
    - totalFare = baseFare(50) + fuelCost + platformFee
    - farePerSeat = ceil(totalFare / seats / 10) × 10 (rounded UP to nearest 10 PKR)
    - Minimum fare per seat: 80 PKR

    **Default values:**
    - Petrol price: 268 PKR/L
    - Fuel average: 12 km/L
    - Platform markup: 30%
    - Base fare: 50 PKR
    """
)
async def fare_estimate(
    data: FareEstimateRequest,
    current_user: User = Depends(get_current_user),
):
    """Calculate shared fare estimate for a ride."""
    return await service.fare_estimate_service(
        distance_km=data.distance_km,
        total_seats=data.total_seats,
        duration_minutes=data.duration_minutes,
        petrol_price=data.petrol_price,
        fuel_average=data.fuel_average,
    )


@router.get(
    "/fare-estimate",
    response_model=Dict[str, Any],
    summary="Calculate Fare Estimate (GET)",
    description="Quick fare estimate via query params.",
)
async def fare_estimate_get(
    distance_km: float = Query(..., gt=0, le=2000, description="Route distance in km"),
    total_seats: int = Query(4, ge=1, le=8, description="Number of seats"),
    duration_minutes: float | None = Query(None, ge=0, le=1440, description="Optional trip duration in minutes"),
    current_user: User = Depends(get_current_user),
):
    """Quick fare estimate via query parameters."""
    return await service.fare_estimate_service(
        distance_km=distance_km,
        total_seats=total_seats,
        duration_minutes=duration_minutes,
    )


# ============================================
# RIDE REQUEST ENDPOINTS (PASSENGER → DRIVER)
# ============================================

@router.post(
    "/requests",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Create Ride Request (Passenger)",
)
async def create_ride_request(
    data: RideRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Passenger posts a ride request visible to nearby drivers."""
    return await service.create_ride_request_service(db, current_user.id, data)


@router.get(
    "/requests/nearby",
    response_model=Dict[str, Any],
    summary="Get Nearby Ride Requests (Driver)",
)
async def get_nearby_ride_requests(
    lat: float = Query(..., ge=-90, le=90, description="Driver's current latitude"),
    lng: float = Query(..., ge=-180, le=180, description="Driver's current longitude"),
    radius_km: float = Query(10.0, gt=0, le=100, description="Search radius in km"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Driver fetches pending ride requests near their location."""
    return await service.get_nearby_ride_requests_service(db, lat, lng, radius_km)


@router.get(
    "/requests/my",
    response_model=Dict[str, Any],
    summary="Get My Ride Requests (Passenger)",
)
async def get_my_ride_requests(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Passenger gets their own ride requests."""
    return await service.get_my_ride_requests_service(db, current_user.id)


@router.put(
    "/requests/{request_id}/accept",
    response_model=Dict[str, Any],
    summary="Accept Ride Request (Driver)",
)
async def accept_ride_request(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Driver accepts a passenger's ride request."""
    return await service.accept_ride_request_service(db, current_user.id, request_id)


@router.put(
    "/requests/{request_id}/cancel",
    response_model=Dict[str, Any],
    summary="Cancel Ride Request",
)
async def cancel_ride_request(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Passenger cancels their ride request."""
    return await service.cancel_ride_request_service(db, current_user.id, request_id)
