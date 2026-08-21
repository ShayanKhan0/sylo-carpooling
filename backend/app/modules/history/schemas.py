"""
History Module Schemas (Prompt 11B)

Request/Response schemas for trip history.
Aligned with actual DB columns (Ride, Booking, User, Vehicle models).

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field


class RideHistoryItemResponse(BaseModel):
    """Single ride in history list."""

    ride_id: UUID
    date: datetime
    pickup_location: str
    dropoff_location: str
    distance_km: float = 0.0
    duration_minutes: int = 0
    fare: float = 0.0
    price_per_seat: float = 0.0
    seats: int = 0
    status: str
    driver_name: Optional[str] = None
    passenger_names: Optional[list[str]] = None
    vehicle_info: Optional[str] = None
    rating: Optional[float] = None

    class Config:
        from_attributes = True


class RideHistoryResponse(BaseModel):
    """Paginated ride history response."""

    rides: list[RideHistoryItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RideDetailedResponse(BaseModel):
    """Detailed ride information."""

    ride_id: UUID
    created_at: datetime
    departure_time: Optional[datetime] = None
    status: str

    pickup: Dict[str, Any]
    dropoff: Dict[str, Any]

    distance_km: float = 0.0
    duration_minutes: int = 0
    price_per_seat: float = 0.0

    driver: Dict[str, Any]
    passengers: list[Dict[str, Any]] = []
    vehicle: Optional[Dict[str, Any]] = None

    polyline: Optional[str] = None

    rating_from_user: Optional[float] = None

    class Config:
        from_attributes = True
