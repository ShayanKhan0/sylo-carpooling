"""
Module: Drivers - Pydantic Schemas
Purpose: Request/response validation models for driver and vehicle operations.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: All schemas include examples for FastAPI documentation and comprehensive field validation.
"""

import re
from datetime import date, datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, validator, AliasChoices


# ============================================
# VEHICLE SCHEMAS
# ============================================

class VehicleBase(BaseModel):
    """Base schema for vehicle data (shared fields)."""
    make: str = Field(..., min_length=2, max_length=50, description="Vehicle manufacturer")
    model: str = Field(..., min_length=2, max_length=50, description="Vehicle model")
    plate_number: str = Field(..., min_length=3, max_length=50, description="Vehicle plate number")
    seats_total: int = Field(..., ge=1, le=12, description="Total seats in vehicle")
    seats_available: int = Field(4, ge=1, le=12, description="Available passenger seats")
    
    @validator("plate_number")
    def validate_plate_number(cls, v):
        """Validate plate number format (alphanumeric, spaces, hyphens)."""
        if not re.match(r"^[A-Z0-9\s\-]+$", v.upper()):
            raise ValueError("Plate number must contain only letters, numbers, spaces, and hyphens")
        return v.upper()


class VehicleCreate(VehicleBase):
    """Schema for creating a new vehicle."""
    photos: Optional[List[str]] = Field(
        None, 
        description="List of vehicle photo URLs"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "make": "Toyota",
                "model": "Corolla",
                "plate_number": "ABC-123",
                "seats_total": 5,
                "seats_available": 4,
                "photos": ["https://example.com/photos/vehicle123.jpg"]
            }
        }


class VehicleUpdate(BaseModel):
    """Schema for updating vehicle details (all fields optional)."""
    make: Optional[str] = Field(None, min_length=2, max_length=50)
    model: Optional[str] = Field(None, min_length=2, max_length=50)
    plate_number: Optional[str] = Field(None, min_length=3, max_length=50)
    seats_total: Optional[int] = Field(None, ge=1, le=12)
    seats_available: Optional[int] = Field(None, ge=1, le=12)
    photos: Optional[List[str]] = None

    @validator("plate_number")
    def validate_plate_number(cls, v):
        """Validate optional plate number format and normalize casing."""
        if v is None:
            return v
        normalized = v.strip().upper()
        if not re.match(r"^[A-Z0-9\s\-]+$", normalized):
            raise ValueError(
                "Plate number must contain only letters, numbers, spaces, and hyphens"
            )
        return normalized

    @validator("seats_available")
    def validate_seat_consistency(cls, v, values):
        """Ensure available seats never exceed total seats when both are provided."""
        seats_total = values.get("seats_total")
        if v is not None and seats_total is not None and v > seats_total:
            raise ValueError("Available seats cannot exceed total seats")
        return v


class VehiclePublic(BaseModel):
    """Schema for vehicle response (public-facing data)."""
    id: UUID
    owner_id: UUID = Field(validation_alias=AliasChoices("owner_id", "driver_id"))
    make: str
    model: str
    plate_number: str = Field(validation_alias=AliasChoices("plate_number", "license_plate"))
    seats_total: int = Field(validation_alias=AliasChoices("seats_total", "seats_available"))
    seats_available: int
    is_active: bool = True
    registration_verified: bool = True
    photos: Optional[List[str]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "owner_id": "660e8400-e29b-41d4-a716-446655440001",
                "make": "Toyota",
                "model": "Corolla",
                "plate_number": "ABC-123",
                "seats_total": 5,
                "seats_available": 4,
                "photos": ["https://example.com/photos/vehicle123.jpg"],
                "created_at": "2025-01-15T10:30:00Z",
                "updated_at": "2025-01-15T10:30:00Z"
            }
        }


# ============================================
# DRIVER PROFILE SCHEMAS
# ============================================

class DriverProfileBase(BaseModel):
    """Base schema for driver profile data."""
    license_number: str = Field(..., min_length=5, max_length=50, description="Driver's license number")
    cnic_number: str = Field(..., description="CNIC number (format: 12345-1234567-1)")
    address: Optional[str] = Field(None, max_length=255, description="Residential address")
    
    @validator("cnic_number")
    def validate_cnic(cls, v):
        """Validate CNIC format for Pakistan (12345-1234567-1)."""
        pattern = r"^\d{5}-\d{7}-\d{1}$"
        if not re.match(pattern, v):
            raise ValueError("CNIC must be in format: 12345-1234567-1")
        return v


class DriverProfileCreate(DriverProfileBase):
    """Schema for driver registration."""
    license_expiry: Optional[date] = Field(None, description="License expiration date")
    
    @validator("license_expiry")
    def validate_license_expiry(cls, v):
        """Ensure license is not already expired."""
        if v and v < date.today():
            raise ValueError("License expiry date cannot be in the past")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "license_number": "DL-12345-2025",
                "license_expiry": "2026-12-31",
                "cnic_number": "12345-1234567-1",
                "address": "123 Main Street, Lahore, Pakistan"
            }
        }


class DriverProfileUpdate(BaseModel):
    """Schema for updating driver profile (all fields optional)."""
    license_number: Optional[str] = Field(None, min_length=5, max_length=50)
    license_expiry: Optional[date] = None
    address: Optional[str] = Field(None, max_length=255)
    
    @validator("license_expiry")
    def validate_license_expiry(cls, v):
        """Ensure license is not already expired."""
        if v and v < date.today():
            raise ValueError("License expiry date cannot be in the past")
        return v


class DriverProfilePublic(BaseModel):
    """Schema for driver profile response (public-facing data)."""
    id: UUID
    user_id: UUID
    is_verified: bool
    license_number: str
    license_expiry: Optional[date]
    cnic_number: Optional[str] = None
    cnic_verified: bool = False
    address: Optional[str]
    rating: float = Field(default=5.0, validation_alias=AliasChoices("rating", "rating_average"))
    total_rides: int
    total_earnings: float = 0.0
    status: str = "pending"
    joined_at: Optional[datetime] = Field(default=None, validation_alias=AliasChoices("joined_at", "created_at"))
    updated_at: Optional[datetime] = Field(default=None, validation_alias=AliasChoices("updated_at", "verification_date"))
    vehicles: List[VehiclePublic] = []
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "660e8400-e29b-41d4-a716-446655440001",
                "user_id": "770e8400-e29b-41d4-a716-446655440002",
                "is_verified": True,
                "license_number": "DL-12345-2025",
                "license_expiry": "2026-12-31",
                "cnic_number": "12345-1234567-1",
                "cnic_verified": True,
                "address": "123 Main Street, Lahore, Pakistan",
                "rating": 4.8,
                "total_rides": 150,
                "total_earnings": 75000.0,
                "status": "active",
                "joined_at": "2025-01-01T10:00:00Z",
                "updated_at": "2025-11-07T15:30:00Z",
                "vehicles": []
            }
        }


class DriverStatsPublic(BaseModel):
    """Schema for driver statistics summary."""
    driver_id: UUID
    rating: float
    total_rides: int
    total_earnings: float
    active_vehicles: int
    is_ride_eligible: bool
    status: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "driver_id": "660e8400-e29b-41d4-a716-446655440001",
                "rating": 4.8,
                "total_rides": 150,
                "total_earnings": 75000.0,
                "active_vehicles": 2,
                "is_ride_eligible": True,
                "status": "active"
            }
        }


class DriverStatusUpdate(BaseModel):
    """Schema for updating driver status."""
    status: str = Field(..., description="New driver status (pending/active/suspended/inactive)")
    
    @validator("status")
    def validate_status(cls, v):
        """Ensure status is valid."""
        allowed_statuses = ["pending", "active", "suspended", "inactive"]
        if v.lower() not in allowed_statuses:
            raise ValueError(f"Status must be one of: {', '.join(allowed_statuses)}")
        return v.lower()
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "active"
            }
        }


# ============================================
# COMBINED RESPONSE SCHEMAS
# ============================================

class DriverWithVehiclesPublic(BaseModel):
    """Complete driver profile with all vehicles."""
    profile: DriverProfilePublic
    vehicles: List[VehiclePublic]
    is_ride_eligible: bool
    
    class Config:
        json_schema_extra = {
            "example": {
                "profile": {
                    "id": "660e8400-e29b-41d4-a716-446655440001",
                    "user_id": "770e8400-e29b-41d4-a716-446655440002",
                    "is_verified": True,
                    "rating": 4.8,
                    "total_rides": 150,
                    "status": "active"
                },
                "vehicles": [],
                "is_ride_eligible": True
            }
        }
