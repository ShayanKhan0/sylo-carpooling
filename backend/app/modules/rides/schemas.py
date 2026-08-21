"""
Module: Rides - Pydantic Schemas
Purpose: Request/response validation models for ride and booking operations.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: All schemas include examples for FastAPI documentation and comprehensive field validation.
       Schemas now include lat/lng coordinates, polyline, and human-readable addresses
       to support full Google Maps integration.
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, validator, AliasChoices


# ============================================
# RIDE SCHEMAS
# ============================================

class RideBase(BaseModel):
    """Base schema for ride data (shared fields)."""
    # Human-readable addresses (for display)
    origin: str = Field(..., min_length=2, max_length=500, description="Starting location address")
    destination: str = Field(..., min_length=2, max_length=500, description="Ending location address")
    
    # Coordinates (for maps & geo-search)
    origin_lat: float = Field(..., ge=-90, le=90, description="Starting point latitude")
    origin_lng: float = Field(..., ge=-180, le=180, description="Starting point longitude")
    destination_lat: float = Field(..., ge=-90, le=90, description="Destination latitude")
    destination_lng: float = Field(..., ge=-180, le=180, description="Destination longitude")
    
    departure_time: datetime = Field(..., description="Scheduled departure time (timezone-aware)")
    available_seats: int = Field(..., ge=1, le=8, description="Number of available seats")
    price_per_seat: float = Field(..., gt=0, description="Price per seat in PKR")
    
    @validator("departure_time")
    def validate_departure_time(cls, v):
        """Ensure departure time is in the future."""
        if v <= datetime.now(v.tzinfo):
            raise ValueError("Departure time must be in the future")
        return v
    
    @validator("price_per_seat")
    def validate_price(cls, v):
        """Ensure price is reasonable (50 PKR to 10,000 PKR per seat)."""
        if v < 50:
            raise ValueError("Price per seat must be at least 50 PKR")
        if v > 10000:
            raise ValueError("Price per seat cannot exceed 10,000 PKR")
        return v


class RideCreate(RideBase):
    """Schema for creating a new ride (driver only)."""
    vehicle_id: UUID = Field(..., description="UUID of the vehicle to use for this ride")
    estimated_duration: Optional[int] = Field(None, ge=1, le=720, description="Estimated trip duration in minutes")
    route_distance_km: Optional[float] = Field(None, gt=0, le=2000, description="Route distance in kilometers")
    polyline: Optional[str] = Field(None, description="Google Maps encoded polyline for route visualization")
    
    class Config:
        json_schema_extra = {
            "example": {
                "origin": "FAST NUCES, Lahore",
                "destination": "Liberty Market, Gulberg",
                "origin_lat": 31.4697,
                "origin_lng": 74.2728,
                "destination_lat": 31.5150,
                "destination_lng": 74.3461,
                "departure_time": "2025-11-08T09:00:00+05:00",
                "available_seats": 3,
                "price_per_seat": 150.0,
                "vehicle_id": "550e8400-e29b-41d4-a716-446655440000",
                "estimated_duration": 30,
                "route_distance_km": 12.5,
                "polyline": "e~klE{cyiMoBsC..."
            }
        }


class RideUpdate(BaseModel):
    """Schema for updating ride details (partial update)."""
    departure_time: Optional[datetime] = None
    available_seats: Optional[int] = Field(None, ge=0, le=8)
    price_per_seat: Optional[float] = Field(None, gt=0)
    estimated_duration: Optional[int] = Field(None, ge=5, le=720)
    
    @validator("departure_time")
    def validate_departure_time(cls, v):
        """Ensure departure time is in the future."""
        if v and v <= datetime.now(v.tzinfo):
            raise ValueError("Departure time must be in the future")
        return v


class RideDriverSummaryPublic(BaseModel):
    """Compact driver details shown on the passenger ride detail sheet."""

    driver_user_id: UUID
    name: str = Field(..., min_length=1, max_length=120)
    profile_photo: Optional[str] = None
    rating_avg: Optional[float] = None
    completed_rides: int = Field(0, ge=0)
    car_name: Optional[str] = None
    vehicle_plate: Optional[str] = None


class RidePublic(BaseModel):
    """Schema for ride response (public-facing data)."""
    id: UUID
    driver_id: UUID
    vehicle_id: Optional[UUID] = None
    origin: str = Field(validation_alias=AliasChoices("origin", "start_point_address"))
    destination: str = Field(validation_alias=AliasChoices("destination", "end_point_address"))
    origin_lat: float = Field(validation_alias=AliasChoices("origin_lat", "start_point_lat"))
    origin_lng: float = Field(validation_alias=AliasChoices("origin_lng", "start_point_lng"))
    destination_lat: float = Field(validation_alias=AliasChoices("destination_lat", "end_point_lat"))
    destination_lng: float = Field(validation_alias=AliasChoices("destination_lng", "end_point_lng"))
    departure_time: datetime
    estimated_duration: Optional[int] = Field(None, validation_alias=AliasChoices("estimated_duration", "estimated_duration_minutes"))
    available_seats: int = Field(validation_alias=AliasChoices("available_seats", "seats_available"))
    total_seats: Optional[int] = Field(
        None,
        validation_alias=AliasChoices("total_seats", "seats_offered", "seats_total"),
    )
    price_per_seat: float
    total_earnings: float = 0.0
    status: str
    display_status: Optional[str] = None
    display_substatus: Optional[str] = None
    can_driver_start: Optional[bool] = None
    can_driver_complete: Optional[bool] = None
    can_driver_cancel: Optional[bool] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    route_distance_km: Optional[float] = None
    polyline: Optional[str] = None
    route_plan_version: int = 0
    route_selected_key: Optional[str] = None
    route_alternatives: Optional[List[Dict[str, Any]]] = None
    driver_summary: Optional[RideDriverSummaryPublic] = None
    recurrence: Optional[Dict[str, Any]] = None
    recurring_start_date: Optional[date] = None
    recurring_end_date: Optional[date] = None
    
    class Config:
        from_attributes = True
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id": "770e8400-e29b-41d4-a716-446655440002",
                "driver_id": "660e8400-e29b-41d4-a716-446655440001",
                "vehicle_id": "550e8400-e29b-41d4-a716-446655440000",
                "origin": "FAST NUCES, Lahore",
                "destination": "Liberty Market, Gulberg",
                "origin_lat": 31.4697,
                "origin_lng": 74.2728,
                "destination_lat": 31.5150,
                "destination_lng": 74.3461,
                "departure_time": "2025-11-08T09:00:00+05:00",
                "estimated_duration": 30,
                "available_seats": 3,
                "total_seats": 4,
                "price_per_seat": 150.0,
                "total_earnings": 0.0,
                "status": "open",
                "created_at": "2025-11-07T10:00:00+05:00",
                "updated_at": None,
                "route_distance_km": 12.5,
                "polyline": "e~klE{cyiMoBsC...",
                "driver_summary": {
                    "driver_user_id": "660e8400-e29b-41d4-a716-446655440001",
                    "name": "Ali Raza",
                    "profile_photo": "/static/uploads/profile_photos/driver_660e84.jpg",
                    "rating_avg": 4.8,
                    "completed_rides": 42,
                    "car_name": "Toyota Corolla",
                    "vehicle_plate": "LEA-1234"
                }
            }
        }


class RideWithBookingsPublic(RidePublic):
    """Schema for ride with all bookings included."""
    bookings: List["RideBookingPublic"] = []
    booked_seats_count: int = Field(0, description="Total seats booked across all bookings")
    
    class Config:
        from_attributes = True


class RideStatusUpdate(BaseModel):
    """Schema for updating ride status."""
    status: str = Field(..., description="New ride status (scheduled/ongoing/completed/cancelled)")
    
    @validator("status")
    def validate_status(cls, v):
        """Ensure status is valid (matches DB ride_status enum)."""
        allowed_statuses = ["open", "in_progress", "completed", "cancelled"]
        if v.lower() not in allowed_statuses:
            raise ValueError(f"Status must be one of: {', '.join(allowed_statuses)}")
        return v.lower()
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "in_progress"
            }
        }


# ============================================
# RIDE BOOKING SCHEMAS
# ============================================

class RideBookingBase(BaseModel):
    """Base schema for ride booking data."""
    booked_seats: int = Field(1, ge=1, le=8, description="Number of seats to book")


class RideBookingCreate(RideBookingBase):
    """Schema for creating a new booking (passenger)."""
    ride_id: UUID = Field(..., description="UUID of the ride to book")
    pickup_lat: Optional[float] = Field(None, ge=-90, le=90)
    pickup_lng: Optional[float] = Field(None, ge=-180, le=180)
    pickup_address: Optional[str] = Field(None, min_length=2, max_length=500)
    pickup_place_id: Optional[str] = Field(None, max_length=191)
    dropoff_lat: Optional[float] = Field(None, ge=-90, le=90)
    dropoff_lng: Optional[float] = Field(None, ge=-180, le=180)
    dropoff_address: Optional[str] = Field(None, min_length=2, max_length=500)
    dropoff_place_id: Optional[str] = Field(None, max_length=191)
    
    class Config:
        json_schema_extra = {
            "example": {
                "ride_id": "770e8400-e29b-41d4-a716-446655440002",
                "booked_seats": 2
            }
        }


class RideBookingPublic(BaseModel):
    """Schema for booking response (public-facing data)."""
    id: UUID
    ride_id: UUID
    passenger_id: UUID
    passenger_name: Optional[str] = None
    passenger_phone: Optional[str] = None
    passenger_profile_photo: Optional[str] = None
    booked_seats: int = Field(validation_alias=AliasChoices("booked_seats", "seats_reserved"))
    total_price: float = Field(validation_alias=AliasChoices("total_price", "fare"))
    booking_time: Optional[datetime] = Field(None, validation_alias=AliasChoices("booking_time", "created_at"))
    status: str
    normalized_status: Optional[str] = None
    display_status: Optional[str] = None
    display_substatus: Optional[str] = None
    can_passenger_cancel: Optional[bool] = None
    payment_status: str = "pending"
    individual_fare: Optional[float] = Field(None, description="Per-passenger dynamic fare (PKR)")
    estimated_pickup_time: Optional[datetime] = Field(None, description="Estimated pickup time for this passenger")
    segment_km: Optional[float] = Field(None, description="Distance this passenger travels on driver route")
    pickup_pct: Optional[float] = Field(None, description="Pickup point position along route (0.0 to 1.0)")
    dropoff_pct: Optional[float] = Field(None, description="Dropoff point position along route (0.0 to 1.0)")
    pickup_route_km: Optional[float] = Field(None, description="Distance from route start to pickup")
    dropoff_route_km: Optional[float] = Field(None, description="Distance from route start to dropoff")
    rate_per_km_used: Optional[float] = Field(None, description="Dynamic pricing rate captured at booking time")
    pickup_lat: Optional[float] = None
    pickup_lng: Optional[float] = None
    pickup_address: Optional[str] = None
    pickup_place_id: Optional[str] = None
    dropoff_lat: Optional[float] = None
    dropoff_lng: Optional[float] = None
    dropoff_address: Optional[str] = None
    dropoff_place_id: Optional[str] = None
    pickup_stop_order: Optional[int] = None
    dropoff_stop_order: Optional[int] = None
    planned_pickup_eta: Optional[datetime] = None
    planned_dropoff_eta: Optional[datetime] = None
    actual_pickup_time: Optional[datetime] = None
    actual_dropoff_time: Optional[datetime] = None
    pickup_completed: bool = False
    dropoff_completed: bool = False
    booking_stage: Optional[str] = None
    route_plan_version: int = 0
    cancellation_time: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    
    class Config:
        from_attributes = True
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "id": "880e8400-e29b-41d4-a716-446655440003",
                "ride_id": "770e8400-e29b-41d4-a716-446655440002",
                "passenger_id": "990e8400-e29b-41d4-a716-446655440004",
                "booked_seats": 2,
                "total_price": 300.0,
                "booking_time": "2025-11-07T11:00:00+05:00",
                "status": "booked",
                "payment_status": "pending",
                "cancellation_time": None,
                "cancellation_reason": None
            }
        }


class RideBookingWithRidePublic(RideBookingPublic):
    """Schema for booking with complete ride details."""
    ride: RidePublic
    
    class Config:
        from_attributes = True


class BookingCancellation(BaseModel):
    """Schema for cancelling a booking."""
    reason: Optional[str] = Field(None, max_length=255, description="Reason for cancellation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "reason": "Change of plans"
            }
        }


class RideRouteSelectionUpdate(BaseModel):
    """Driver selects an alternate constrained route option for an open ride."""

    route_key: str = Field(..., min_length=2, max_length=64)


# ============================================
# QUERY FILTER SCHEMAS
# ============================================

class RideSearchFilter(BaseModel):
    """Schema for filtering available rides (supports geo-proximity search)."""
    origin: Optional[str] = Field(None, description="Filter by origin location text (partial match)")
    destination: Optional[str] = Field(None, description="Filter by destination location text (partial match)")
    
    # Geo-proximity search params
    origin_lat: Optional[float] = Field(None, ge=-90, le=90, description="Search near this origin latitude")
    origin_lng: Optional[float] = Field(None, ge=-180, le=180, description="Search near this origin longitude")
    destination_lat: Optional[float] = Field(None, ge=-90, le=90, description="Search near this destination latitude")
    destination_lng: Optional[float] = Field(None, ge=-180, le=180, description="Search near this destination longitude")
    radius_km: Optional[float] = Field(5.0, gt=0, le=100, description="Search radius in km (default 5km)")
    
    departure_date: Optional[datetime] = Field(None, description="Filter by departure date")
    min_seats: Optional[int] = Field(None, ge=1, le=8, description="Minimum available seats required")
    driver_total_seats: Optional[int] = Field(
        None,
        ge=1,
        le=8,
        description="Exact total seats originally offered by the driver for this ride",
    )
    max_price: Optional[float] = Field(None, gt=0, description="Maximum price per seat")
    
    class Config:
        json_schema_extra = {
            "example": {
                "origin_lat": 31.4697,
                "origin_lng": 74.2728,
                "destination_lat": 31.5150,
                "destination_lng": 74.3461,
                "radius_km": 3.0,
                "min_seats": 2,
                "driver_total_seats": 3,
                "max_price": 200.0
            }
        }


# ============================================
# STATISTICS SCHEMAS
# ============================================

class RideStatistics(BaseModel):
    """Schema for ride statistics summary."""
    total_rides_created: int
    total_rides_completed: int
    total_rides_cancelled: int
    total_rides_all_excluding_draft: int = 0
    scheduled_rides_current: int = 0
    total_earnings: float
    average_occupancy_rate: float
    carbon_footprint_saved_kg: float = 0.0
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_rides_created": 25,
                "total_rides_completed": 20,
                "total_rides_cancelled": 2,
                "total_rides_all_excluding_draft": 25,
                "scheduled_rides_current": 3,
                "total_earnings": 15000.0,
                "average_occupancy_rate": 0.75,
                "carbon_footprint_saved_kg": 42.2
            }
        }


class PassengerBookingHistory(BaseModel):
    """Schema for passenger booking history summary."""
    total_bookings: int
    total_spent: float
    active_bookings: int
    completed_rides: int
    cancelled_bookings: int
    carbon_footprint_saved_kg: float = 0.0

    class Config:
        json_schema_extra = {
            "example": {
                "total_bookings": 15,
                "total_spent": 4500.0,
                "active_bookings": 2,
                "completed_rides": 12,
                "cancelled_bookings": 1,
                "carbon_footprint_saved_kg": 12.5
            }
        }


# ============================================
# RIDE REQUEST SCHEMAS (Passenger-initiated)
# ============================================

class RideRequestCreate(BaseModel):
    """Schema for a passenger creating a ride request."""
    origin: str = Field(..., min_length=2, max_length=500)
    origin_lat: float = Field(..., ge=-90, le=90)
    origin_lng: float = Field(..., ge=-180, le=180)
    destination: str = Field(..., min_length=2, max_length=500)
    destination_lat: float = Field(..., ge=-90, le=90)
    destination_lng: float = Field(..., ge=-180, le=180)
    seats_needed: int = Field(1, ge=1, le=6)
    max_budget: Optional[float] = Field(None, gt=0)
    departure_time: datetime = Field(...)


class RideRequestPublic(BaseModel):
    """Public schema returned for a ride request."""
    id: UUID
    passenger_id: UUID
    origin: str
    origin_lat: float
    origin_lng: float
    destination: str
    destination_lat: float
    destination_lng: float
    seats_needed: int
    max_budget: Optional[float] = None
    departure_time: datetime
    status: str
    accepted_by_driver_id: Optional[UUID] = None
    ride_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================
# FARE CALCULATOR SCHEMAS
# ============================================

class FareEstimateRequest(BaseModel):
    """Request schema for fare estimate calculation."""
    distance_km: float = Field(..., gt=0, le=2000, description="Route distance in kilometres")
    total_seats: int = Field(4, ge=1, le=8, description="Number of seats to split fare across")
    duration_minutes: Optional[float] = Field(
        None,
        ge=0,
        le=1440,
        description="Optional trip duration in minutes for time-based fare component",
    )
    petrol_price: Optional[float] = Field(None, gt=0, description="Override petrol price per litre (PKR)")
    fuel_average: Optional[float] = Field(None, gt=0, description="Override fuel average (km/L)")

    class Config:
        json_schema_extra = {
            "example": {
                "distance_km": 15.3,
                "total_seats": 3,
                "duration_minutes": 28,
            }
        }


class FareEstimateResponse(BaseModel):
    """Response schema for fare estimate."""
    distance_km: float
    total_seats: int
    fuel_cost_raw: float
    time_cost: float
    duration_minutes: float
    base_fare: float
    platform_fee: float
    total_fare: float
    fare_per_seat: float
    petrol_price_used: float
    fuel_average_used: float
    markup_percent: float
    summary: str

    class Config:
        json_schema_extra = {
            "example": {
                "distance_km": 15.3,
                "total_seats": 3,
                "fuel_cost_raw": 341.70,
                "base_fare": 50.0,
                "platform_fee": 102.51,
                "total_fare": 494.21,
                "fare_per_seat": 170.0,
                "petrol_price_used": 268.0,
                "fuel_average_used": 12.0,
                "markup_percent": 30.0,
                "summary": "Rs 170/seat × 3 seats = Rs 510 total (15.3 km)"
            }
        }
