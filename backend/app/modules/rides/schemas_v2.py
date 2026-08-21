"""
Module: Rides & Scheduling - Pydantic Schemas (Prompt 5)
Purpose: Request/response validation models for atomic booking, geo-search, and recurring schedules
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: December 8, 2025
Notes: Includes atomic booking, geo-radius search, and recurring schedule schemas
"""

from datetime import datetime, date, time
from typing import Optional, List, Dict, Any
from uuid import UUID
from decimal import Decimal
from pydantic import BaseModel, Field, validator, root_validator


# ============================================
# GEO-LOCATION SCHEMAS
# ============================================

class GeoPoint(BaseModel):
    """Geographic coordinates."""
    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lng: float = Field(..., ge=-180, le=180, description="Longitude")
    address: Optional[str] = Field(None, max_length=500, description="Human-readable address")
    
    class Config:
        json_schema_extra = {
            "example": {
                "lat": 31.4697,
                "lng": 74.2728,
                "address": "FAST NUCES, Lahore"
            }
        }


# ============================================
# RIDE SCHEMAS (PROMPT 5 ENHANCED)
# ============================================

class RideCreateV2(BaseModel):
    """Schema for creating a ride with full Prompt 5 features."""
    start_point: GeoPoint = Field(..., description="Starting point coordinates")
    end_point: GeoPoint = Field(..., description="Destination coordinates")
    start_time: datetime = Field(..., description="Departure time")
    polyline_main: Optional[str] = Field(None, description="Encoded polyline for main route")
    polyline_alternates: Optional[Dict[str, str]] = Field(None, description="Alternative routes: {name: polyline}")
    seats_offered: int = Field(..., ge=1, le=8, description="Total seats offered")
    buffer_seats: int = Field(0, ge=0, le=3, description="Seats kept aside from immediate booking")
    base_price: Decimal = Field(..., gt=0, description="Base price per seat")
    vehicle_id: Optional[UUID] = Field(None, description="Vehicle to use")
    recurrence: Optional[Dict[str, Any]] = Field(None, description="Recurrence pattern metadata")
    
    @validator("start_time")
    def validate_start_time(cls, v):
        """Ensure start time is in the future."""
        if v <= datetime.now(v.tzinfo if v.tzinfo else None):
            raise ValueError("Start time must be in the future")
        return v
    
    @validator("buffer_seats")
    def validate_buffer_seats(cls, v, values):
        """Ensure buffer_seats doesn't exceed seats_offered."""
        if "seats_offered" in values and v >= values["seats_offered"]:
            raise ValueError("Buffer seats must be less than seats offered")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "start_point": {
                    "lat": 31.4697,
                    "lng": 74.2728,
                    "address": "FAST NUCES, Lahore"
                },
                "end_point": {
                    "lat": 31.5204,
                    "lng": 74.3587,
                    "address": "Liberty Market, Gulberg"
                },
                "start_time": "2025-12-09T08:00:00+05:00",
                "polyline_main": "u~o{Aq~{rMoB_@...",
                "seats_offered": 4,
                "buffer_seats": 1,
                "base_price": 150.00
            }
        }


class RideUpdateV2(BaseModel):
    """Schema for updating ride details."""
    start_time: Optional[datetime] = None
    seats_offered: Optional[int] = Field(None, ge=1, le=8)
    buffer_seats: Optional[int] = Field(None, ge=0, le=3)
    base_price: Optional[Decimal] = Field(None, gt=0)
    status: Optional[str] = Field(None, pattern="^(OPEN|IN_PROGRESS|COMPLETED|CANCELLED)$")
    
    @validator("start_time")
    def validate_start_time(cls, v):
        if v and v <= datetime.now(v.tzinfo if v.tzinfo else None):
            raise ValueError("Start time must be in the future")
        return v


class RideSearchRequest(BaseModel):
    """Schema for geo-radius ride search (Prompt 5 core feature)."""
    origin: GeoPoint = Field(..., description="Search origin point")
    destination: GeoPoint = Field(..., description="Search destination point")
    radius_km: float = Field(5.0, ge=0.5, le=50, description="Search radius in kilometers")
    date: Optional[date] = None  # Specific date to search (defaults to today)
    min_seats: int = Field(1, ge=1, le=8, description="Minimum available seats required")
    max_price: Optional[Decimal] = Field(None, gt=0, description="Maximum price per seat")
    
    class Config:
        json_schema_extra = {
            "example": {
                "origin": {
                    "lat": 31.4697,
                    "lng": 74.2728
                },
                "destination": {
                    "lat": 31.5204,
                    "lng": 74.3587
                },
                "radius_km": 5.0,
                "date": "2025-12-09",
                "min_seats": 2,
                "max_price": 200.00
            }
        }


class RidePublicV2(BaseModel):
    """Schema for ride response with Prompt 5 enhancements."""
    id: UUID
    driver_id: UUID
    start_point: GeoPoint
    end_point: GeoPoint
    start_time: datetime
    polyline_main: Optional[str]
    seats_offered: int
    seats_booked: int
    seats_available: int
    buffer_seats: int
    base_price: Decimal
    status: str
    created_at: datetime
    updated_at: datetime
    driver_name: Optional[str] = None
    driver_rating: Optional[float] = None
    vehicle_info: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


# ============================================
# BOOKING SCHEMAS (PROMPT 5 ATOMIC)
# ============================================

class BookingRequest(BaseModel):
    """Schema for atomic seat booking (Prompt 5 core feature)."""
    ride_id: UUID = Field(..., description="Ride to book")
    seats_reserved: int = Field(..., ge=1, le=8, description="Number of seats to reserve")
    expected_fare: Optional[Decimal] = Field(None, gt=0, description="Expected fare for validation")
    
    @validator("seats_reserved")
    def validate_seats(cls, v):
        if v < 1:
            raise ValueError("Must reserve at least 1 seat")
        if v > 8:
            raise ValueError("Cannot reserve more than 8 seats")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "ride_id": "550e8400-e29b-41d4-a716-446655440000",
                "seats_reserved": 2,
                "expected_fare": 300.00
            }
        }


class BookingResponse(BaseModel):
    """Schema for booking confirmation."""
    id: UUID
    ride_id: UUID
    passenger_id: UUID
    seats_reserved: int
    fare: Decimal
    status: str
    version: int
    created_at: datetime
    booking_code: Optional[str] = None
    
    class Config:
        from_attributes = True


class BookingCancelRequest(BaseModel):
    """Schema for cancelling a booking."""
    reason: Optional[str] = Field(None, max_length=500, description="Cancellation reason")


# ============================================
# RECURRING SCHEDULE SCHEMAS (PROMPT 5)
# ============================================

class ScheduleCreate(BaseModel):
    """Schema for creating recurring schedule (Prompt 5 feature)."""
    days_of_week: List[str] = Field(
        ...,
        description="Days of week: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']"
    )
    ride_time: time = Field(..., description="Time of day for ride (e.g., 08:00)")
    start_point: GeoPoint = Field(..., description="Starting point")
    end_point: GeoPoint = Field(..., description="Destination")
    polyline_main: Optional[str] = Field(None, description="Route polyline")
    seats_offered: int = Field(..., ge=1, le=8, description="Seats to offer")
    buffer_seats: int = Field(0, ge=0, le=3, description="Buffer seats")
    base_price: Decimal = Field(..., gt=0, description="Price per seat")
    start_date: date = Field(..., description="Schedule start date")
    end_date: date = Field(..., description="Schedule end date")
    recurrence_meta: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional metadata: {exclude_dates: [], preferences: {}}"
    )
    
    @validator("days_of_week")
    def validate_days(cls, v):
        """Validate day names."""
        valid_days = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
        if not v:
            raise ValueError("Must specify at least one day")
        for day in v:
            if day not in valid_days:
                raise ValueError(f"Invalid day: {day}. Must be one of {valid_days}")
        return v

    @root_validator(skip_on_failure=True)
    def validate_required_route_points(cls, values):
        """Ensure start and destination addresses are provided."""
        start_point = values.get("start_point")
        end_point = values.get("end_point")
        if not start_point or not end_point:
            raise ValueError("Both start and destination locations are required")

        start_address = (start_point.address or "").strip()
        end_address = (end_point.address or "").strip()
        if not start_address or not end_address:
            raise ValueError("Both start and destination addresses are required")
        return values
    
    @root_validator(skip_on_failure=True)
    def validate_date_range(cls, values):
        """Ensure end_date is after start_date."""
        start_date = values.get("start_date")
        end_date = values.get("end_date")
        if start_date and end_date and end_date <= start_date:
            raise ValueError("End date must be after start date")
        return values
    
    class Config:
        json_schema_extra = {
            "example": {
                "days_of_week": ["Mon", "Wed", "Fri"],
                "time": "08:00:00",
                "start_point": {
                    "lat": 31.4697,
                    "lng": 74.2728,
                    "address": "FAST NUCES, Lahore"
                },
                "end_point": {
                    "lat": 31.5204,
                    "lng": 74.3587,
                    "address": "Liberty Market"
                },
                "seats_offered": 4,
                "buffer_seats": 1,
                "base_price": 150.00,
                "start_date": "2025-12-09",
                "end_date": "2026-06-30"
            }
        }


class ScheduleUpdate(BaseModel):
    """Schema for updating recurring schedule."""
    days_of_week: Optional[List[str]] = None
    ride_time: Optional[time] = Field(None, alias="time")
    start_point: Optional[GeoPoint] = None
    end_point: Optional[GeoPoint] = None
    polyline_main: Optional[str] = None
    seats_offered: Optional[int] = Field(None, ge=1, le=8)
    buffer_seats: Optional[int] = Field(None, ge=0, le=3)
    base_price: Optional[Decimal] = Field(None, gt=0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_active: Optional[bool] = None
    
    @validator("days_of_week")
    def validate_days(cls, v):
        if v is not None:
            valid_days = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
            for day in v:
                if day not in valid_days:
                    raise ValueError(f"Invalid day: {day}")
        return v

    @validator("buffer_seats")
    def validate_buffer_seats(cls, v, values):
        seats_offered = values.get("seats_offered")
        if v is not None and seats_offered is not None and v >= seats_offered:
            raise ValueError("Buffer seats must be less than seats offered")
        return v

    @root_validator(skip_on_failure=True)
    def validate_date_range(cls, values):
        start_date = values.get("start_date")
        end_date = values.get("end_date")
        if start_date and end_date and end_date <= start_date:
            raise ValueError("End date must be after start date")
        return values

    class Config:
        allow_population_by_field_name = True


class SchedulePublic(BaseModel):
    """Schema for recurring schedule response."""
    id: UUID
    user_id: UUID
    days_of_week: List[str]
    time: time
    start_point: GeoPoint
    end_point: GeoPoint
    polyline_main: Optional[str]
    seats_offered: int
    buffer_seats: int
    base_price: Decimal
    start_date: date
    end_date: date
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class RecurringScheduleDiscoverRequest(BaseModel):
    """Schema for passenger recurring schedule discovery (no weekday selection)."""

    origin: GeoPoint = Field(..., description="Passenger start point")
    destination: GeoPoint = Field(..., description="Passenger destination point")
    passenger_from_date: date = Field(..., description="Passenger recurring range start date")
    passenger_until_date: date = Field(..., description="Passenger recurring range end date")
    departure_window_start: time = Field(..., description="Earliest departure time preference")
    departure_window_end: time = Field(..., description="Latest departure time preference")
    min_seats: int = Field(1, ge=1, le=8, description="Minimum seats passenger needs")
    driver_total_seats: Optional[int] = Field(
        None,
        ge=1,
        le=8,
        description="Optional exact driver total offered seats filter",
    )
    radius_km: float = Field(5.0, ge=0.5, le=50, description="Matching radius in kilometers")
    max_price: Optional[Decimal] = Field(None, gt=0, description="Optional max fare per seat")

    @root_validator(skip_on_failure=True)
    def validate_search_range(cls, values):
        from_date = values.get("passenger_from_date")
        until_date = values.get("passenger_until_date")
        if from_date and until_date and until_date < from_date:
            raise ValueError("Passenger until date must be on or after from date")

        window_start = values.get("departure_window_start")
        window_end = values.get("departure_window_end")
        if window_start and window_end and window_end <= window_start:
            raise ValueError("Departure window end must be after start")
        return values

    class Config:
        json_schema_extra = {
            "example": {
                "origin": {
                    "lat": 31.4697,
                    "lng": 74.2728,
                    "address": "FAST NUCES, Lahore"
                },
                "destination": {
                    "lat": 31.5204,
                    "lng": 74.3587,
                    "address": "Liberty Market, Gulberg"
                },
                "passenger_from_date": "2026-04-20",
                "passenger_until_date": "2026-05-20",
                "departure_window_start": "08:00:00",
                "departure_window_end": "10:00:00",
                "min_seats": 1,
                "driver_total_seats": 4,
                "radius_km": 5.0
            }
        }


class RecurringScheduleDiscoverPublic(BaseModel):
    """Schema for recurring schedule discovery results."""

    schedule_id: UUID
    driver_id: UUID
    driver_name: Optional[str] = None
    days_of_week: List[str]
    ride_time: time
    start_point: GeoPoint
    end_point: GeoPoint
    seats_offered: int
    buffer_seats: int
    template_available_seats: int
    base_price: Decimal
    schedule_start_date: date
    schedule_end_date: date
    overlap_start_date: date
    overlap_end_date: date
    first_matching_date: date
    matching_days_count: int
    distance_from_origin_km: float
    distance_to_destination_km: float


class RecurringScheduleBookSeriesRequest(BaseModel):
    """Request payload for booking a full recurring series for a passenger."""

    passenger_from_date: date = Field(..., description="Passenger recurring range start date")
    passenger_until_date: date = Field(..., description="Passenger recurring range end date")
    departure_window_start: time = Field(..., description="Earliest departure preference")
    departure_window_end: time = Field(..., description="Latest departure preference")
    seats_reserved: int = Field(1, ge=1, le=8, description="Seats to reserve on each matching day")
    pickup_point: GeoPoint = Field(..., description="Passenger pickup point")
    dropoff_point: GeoPoint = Field(..., description="Passenger dropoff point")

    @root_validator(skip_on_failure=True)
    def validate_booking_window(cls, values):
        from_date = values.get("passenger_from_date")
        until_date = values.get("passenger_until_date")
        if from_date and until_date and until_date < from_date:
            raise ValueError("Passenger until date must be on or after from date")

        window_start = values.get("departure_window_start")
        window_end = values.get("departure_window_end")
        if window_start and window_end and window_end <= window_start:
            raise ValueError("Departure window end must be after start")

        return values


class RecurringScheduleBookSeriesResponse(BaseModel):
    """Response payload after a recurring series booking request."""

    subscription_id: UUID
    schedule_id: UUID
    overlap_start_date: date
    overlap_end_date: date
    matching_days_count: int
    bookings_created: int
    next_ride_id: Optional[UUID] = None
    next_departure_time: Optional[datetime] = None


class RecurringDriverHomePublic(BaseModel):
    """Driver recurring card payload for Home dashboard section."""

    schedule_id: UUID
    start_point: GeoPoint
    end_point: GeoPoint
    ride_time: time
    start_date: date
    end_date: date
    seats_offered: int
    base_price: Decimal
    next_ride_id: Optional[UUID] = None
    next_departure_time: Optional[datetime] = None
    next_ride_status: Optional[str] = None


class RecurringPassengerHomePublic(BaseModel):
    """Passenger recurring card payload for Home dashboard section."""

    subscription_id: UUID
    schedule_id: UUID
    driver_id: UUID
    driver_name: Optional[str] = None
    pickup_address: Optional[str] = None
    dropoff_address: Optional[str] = None
    seats_reserved: int
    base_price: Decimal
    overlap_start_date: date
    overlap_end_date: date
    status: str
    booked_instances_count: int = 0
    next_ride_id: Optional[UUID] = None
    next_departure_time: Optional[datetime] = None
    next_ride_status: Optional[str] = None


class RecurringRideResolutionPublic(BaseModel):
    """Resolved nearest ride instance for a recurring schedule/subscription."""

    ride_id: Optional[UUID] = None
    departure_time: Optional[datetime] = None
    ride_status: Optional[str] = None


class RecurringSeriesCancelResponse(BaseModel):
    """Response payload for full recurring-series cancellation."""

    subscription_id: UUID
    status: str
    cancelled_future_bookings: int


# ============================================
# NOTIFICATION SCHEMAS
# ============================================

class NotificationPayload(BaseModel):
    """Schema for booking notification payload."""
    type: str = Field(..., pattern="^(BOOKING_CONFIRMED|BOOKING_CANCELLED|RIDE_UPDATED|RIDE_STARTING)$")
    ride_id: UUID
    booking_id: Optional[UUID] = None
    message: str
    data: Optional[Dict[str, Any]] = None


# ============================================
# UTILITY SCHEMAS
# ============================================

class AvailableSeatsResponse(BaseModel):
    """Schema for checking available seats."""
    ride_id: UUID
    seats_offered: int
    seats_booked: int
    buffer_seats: int
    seats_available: int


class DistanceCalculation(BaseModel):
    """Schema for distance calculation response."""
    origin: GeoPoint
    destination: GeoPoint
    distance_km: float
    method: str = "haversine"
