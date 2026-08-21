"""
Module: Drivers - API Router
Purpose: REST API endpoints for driver registration, vehicle management, and statistics.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: All endpoints are JWT-protected and follow standardized response format.
"""

from uuid import UUID
from typing import Dict, Any
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.drivers import service
from app.modules.drivers.schemas import (
    DriverProfileCreate, DriverProfileUpdate, DriverProfilePublic,
    VehicleCreate, VehicleUpdate, VehiclePublic,
    DriverStatsPublic, DriverStatusUpdate
)

router = APIRouter(prefix="/drivers", tags=["Drivers"])


@router.post(
    "/register",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Register as Driver",
    description="""
    Register the current user as a driver or upgrade existing account to driver role.
    
    **Requirements:**
    - Valid JWT token (user must be logged in)
    - CNIC number in format: 12345-1234567-1
    - Valid driver's license number
    - License expiry date (optional, must be future date)
    
    **Response:**
    - Creates DriverProfile with status 'pending'
    - Initial rating: 5.0
    - Total rides/earnings: 0
    - Verification status: False (requires admin approval)
    
    **Example Request:**
    ```json
    {
        "license_number": "DL-12345-2025",
        "license_expiry": "2026-12-31",
        "cnic_number": "12345-1234567-1",
        "address": "123 Main Street, Lahore, Pakistan"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "id": "660e8400-e29b-41d4-a716-446655440001",
            "user_id": "770e8400-e29b-41d4-a716-446655440002",
            "is_verified": false,
            "status": "pending",
            "rating": 5.0,
            "total_rides": 0,
            "total_earnings": 0.0
        },
        "error": null
    }
    ```
    """
)
async def register_driver(
    driver_data: DriverProfileCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Register current user as a driver."""
    return await service.register_driver_service(db, current_user.id, driver_data)


@router.get(
    "/me",
    response_model=Dict[str, Any],
    summary="Get My Driver Profile",
    description="""
    Retrieve the current user's driver profile with all vehicles and ride eligibility status.
    
    **Requirements:**
    - Valid JWT token
    - User must be registered as a driver
    
    **Response Includes:**
    - Complete driver profile (verification status, rating, earnings)
    - List of all registered vehicles
    - Ride eligibility flag (True if verified + active vehicle + good rating)
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "profile": {
                "id": "660e8400-e29b-41d4-a716-446655440001",
                "user_id": "770e8400-e29b-41d4-a716-446655440002",
                "is_verified": true,
                "rating": 4.8,
                "total_rides": 150,
                "total_earnings": 75000.0,
                "status": "active",
                "vehicles": [...]
            },
            "is_ride_eligible": true
        },
        "error": null
    }
    ```
    """
)
async def get_my_driver_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get driver profile for current user."""
    return await service.get_driver_profile_service(db, current_user.id)


@router.put(
    "/me",
    response_model=Dict[str, Any],
    summary="Update My Driver Profile",
    description="""
    Update driver profile information (license, address, etc.).
    
    **Requirements:**
    - Valid JWT token
    - User must be registered as a driver
    
    **Updatable Fields:**
    - license_number
    - license_expiry
    - address
    
    **Note:** Verification status and performance metrics cannot be updated directly.
    
    **Example Request:**
    ```json
    {
        "license_expiry": "2027-12-31",
        "address": "456 New Street, Karachi, Pakistan"
    }
    ```
    """
)
async def update_my_driver_profile(
    profile_update: DriverProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update driver profile for current user."""
    return await service.update_driver_profile_service(db, current_user.id, profile_update)


@router.put(
    "/status",
    response_model=Dict[str, Any],
    summary="Update Driver Status",
    description="""
    Update driver account status.
    
    **Allowed Status Values:**
    - `active`: Driver can accept rides (requires verification)
    - `inactive`: Driver has paused services temporarily
    - `pending`: Awaiting verification (initial state)
    - `suspended`: Account suspended by admin (policy violation)
    
    **Use Cases:**
    - Driver can set status to 'inactive' to pause accepting rides
    - Admin can set 'suspended' or 'active' status
    - Status automatically changes to 'active' when verification is complete
    
    **Example Request:**
    ```json
    {
        "status": "inactive"
    }
    ```
    """
)
async def update_driver_status(
    status_update: DriverStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update driver status (active/inactive/suspended)."""
    return await service.update_driver_status_service(db, current_user.id, status_update)


@router.get(
    "/stats",
    response_model=Dict[str, Any],
    summary="Get Driver Statistics",
    description="""
    Retrieve driver performance statistics and earnings summary.
    
    **Response Includes:**
    - Current rating (1.0 - 5.0)
    - Total completed rides
    - Total earnings (PKR)
    - Number of active vehicles
    - Ride eligibility status
    - Current account status
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "driver_id": "660e8400-e29b-41d4-a716-446655440001",
            "rating": 4.8,
            "total_rides": 150,
            "total_earnings": 75000.0,
            "active_vehicles": 2,
            "is_ride_eligible": true,
            "status": "active"
        },
        "error": null
    }
    ```
    """
)
async def get_driver_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get driver statistics summary."""
    return await service.get_driver_stats_service(db, current_user.id)


# ============================================
# VEHICLE MANAGEMENT ENDPOINTS
# ============================================

@router.post(
    "/vehicles",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Add New Vehicle",
    description="""
    Add a new vehicle to the driver's profile.
    
    **Requirements:**
    - Valid JWT token
    - User must be registered as a driver
    - Maximum 3 vehicles allowed
    - Unique plate number
    
    **Validation:**
    - Plate number: Alphanumeric with hyphens/spaces
    - Seats: 1-12
    """
)
async def add_vehicle(
    vehicle_data: VehicleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a new vehicle to driver's profile."""
    return await service.add_vehicle_service(db, current_user.id, vehicle_data)


@router.get(
    "/vehicles",
    response_model=Dict[str, Any],
    summary="Get All My Vehicles",
    description="""
    Retrieve all vehicles registered under the current driver.
    
    **Response:**
    - List of all vehicles (active and inactive)
    - Ordered by creation date (newest first)
    - Includes verification status for each vehicle
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "make": "Toyota",
                "model": "Corolla",
                "year": 2020,
                "license_plate": "ABC-123",
                "registration_verified": true,
                "is_active": true
            },
            {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "make": "Honda",
                "model": "Civic",
                "year": 2019,
                "license_plate": "XYZ-789",
                "registration_verified": false,
                "is_active": false
            }
        ],
        "error": null
    }
    ```
    """
)
async def get_my_vehicles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all vehicles for current driver."""
    return await service.get_driver_vehicles_service(db, current_user.id)


@router.put(
    "/vehicles/{vehicle_id}",
    response_model=Dict[str, Any],
    summary="Update Vehicle Details",
    description="""
    Update vehicle information (color, seats, photo, active status).
    
    **Requirements:**
    - Valid JWT token
    - User must own the vehicle
    
    **Updatable Fields:**
    - color
    - seats_available
    - vehicle_photo
    - is_active (set to false to deactivate vehicle)
    
    **Note:** Cannot change make, model, year, license plate, or registration number.
    
    **Example Request:**
    ```json
    {
        "color": "Black",
        "seats_available": 3,
        "is_active": false
    }
    ```
    """
)
async def update_vehicle(
    vehicle_id: UUID,
    vehicle_update: VehicleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update vehicle details."""
    return await service.update_vehicle_service(db, current_user.id, vehicle_id, vehicle_update)


@router.delete(
    "/vehicles/{vehicle_id}",
    response_model=Dict[str, Any],
    summary="Remove Vehicle",
    description="""
    Permanently delete a vehicle from the driver's profile.
    
    **Requirements:**
    - Valid JWT token
    - User must own the vehicle
    
    **Warning:**
    - This action cannot be undone
    - Vehicle record is permanently deleted
    - Does not affect past ride history
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "message": "Vehicle removed successfully",
            "vehicle_id": "550e8400-e29b-41d4-a716-446655440000"
        },
        "error": null
    }
    ```
    """
)
async def remove_vehicle(
    vehicle_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a vehicle from driver's profile."""
    return await service.remove_vehicle_service(db, current_user.id, vehicle_id)
