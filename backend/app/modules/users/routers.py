"""
Module: Users
Purpose: REST API endpoints for user profile and saved address management.
         All endpoints are protected with JWT authentication.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 7, 2025
Notes: All routes require authentication via get_current_user dependency.
       Returns standardized response format: {status, data, error}
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Dict

from app.db.session import get_db
from app.modules.auth.schemas import UserPublic
from app.modules.users.schemas import (
    UserProfileUpdate,
    SavedAddressCreate,
    SavedAddressUpdate,
    PhotoUploadRequest,
    UserWithProfilePublic,
    UserProfilePublic,
    SavedAddressPublic
)
from app.modules.users import service

# Import get_current_user dependency from auth service
# This will be used to protect all routes
from app.modules.auth.deps import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=Dict,
    summary="Get current user profile",
    description="Get complete profile of authenticated user including profile data and saved addresses"
)
async def get_my_profile(
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current user's complete profile.
    
    Returns:
    - User basic info (email, phone, role)
    - Profile data (photo, gender, DOB, organization, documents)
    - Saved addresses (home, office, university, etc.)
    
    Response:
        {
            "status": "ok",
            "data": {
                "id": "...",
                "full_name": "...",
                "email": "...",
                "phone": "...",
                "role": "student",
                "is_active": true,
                "is_verified": true,
                "created_at": "...",
                "profile": {...},
                "saved_addresses": [...]
            },
            "error": null
        }
    
    Requires: Authentication (JWT token in Authorization header)
    """
    return await service.get_user_profile_service(db, current_user.id)


@router.put(
    "/me",
    response_model=Dict,
    summary="Update current user profile",
    description="Update profile fields for authenticated user. Only provided fields will be updated."
)
async def update_my_profile(
    profile_update: UserProfileUpdate,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update current user's profile.
    
    Supported fields:
    - profile_photo: URL or base64 data URI
    - gender: 'male', 'female', or 'other'
    - date_of_birth: Date (YYYY-MM-DD)
    - organization_name: Name of university/college/office
    - organization_type: 'university', 'college', 'school', or 'office'
    - cnic: Pakistan CNIC (format: 12345-1234567-1)
    - driving_license: Driver's license number
    - car_registration: Vehicle registration number
    
    Notes:
    - All fields are optional (partial update)
    - CNIC validation: Must match Pakistan format
    - Age validation: Must be 13+ years old
    
    Response:
        {
            "status": "ok",
            "data": {
                "id": "...",
                "user_id": "...",
                "profile_photo": "...",
                ...
            },
            "error": null
        }
    
    Requires: Authentication (JWT token)
    """
    return await service.update_user_profile_service(db, current_user.id, profile_update)


@router.post(
    "/me/photo",
    response_model=Dict,
    summary="Upload profile photo",
    description="Upload or update profile photo (URL or base64 encoded)"
)
async def upload_profile_photo(
    photo_request: PhotoUploadRequest,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload or update user profile photo.
    
    Accepted formats:
    1. URL: https://example.com/photo.jpg
    2. Base64 data URI: data:image/jpeg;base64,/9j/4AAQSkZJRg...
    
    Limitations:
    - Base64 size limit: ~100KB
    - Supported formats: JPEG, PNG, GIF
    
    Example request:
        {
            "photo": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD..."
        }
    
    Response:
        {
            "status": "ok",
            "data": {
                "id": "...",
                "user_id": "...",
                "profile_photo": "data:image/jpeg;base64,...",
                ...
            },
            "error": null
        }
    
    Future enhancements:
    - Upload to cloud storage (S3, Cloudinary)
    - Image compression and resizing
    - Multiple photo formats (thumbnail, full-size)
    
    Requires: Authentication (JWT token)
    """
    return await service.upload_profile_photo_service(db, current_user.id, photo_request.photo)


@router.get(
    "/addresses",
    response_model=Dict,
    summary="Get saved addresses",
    description="Get all saved addresses for authenticated user"
)
async def get_saved_addresses(
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all saved addresses for current user.
    
    Returns addresses ordered by creation date (newest first).
    Maximum 5 addresses per user.
    
    Response:
        {
            "status": "ok",
            "data": [
                {
                    "id": "...",
                    "user_id": "...",
                    "label": "Home",
                    "address": "Bahria Town, Islamabad",
                    "latitude": 33.7077,
                    "longitude": 73.0479,
                    "created_at": "..."
                },
                ...
            ],
            "error": null
        }
    
    Use cases:
    - Quick ride request from favorite locations
    - Geospatial matching with nearby rides
    - Personalized ride suggestions
    
    Requires: Authentication (JWT token)
    """
    return await service.get_saved_addresses_service(db, current_user.id)


@router.post(
    "/addresses",
    response_model=Dict,
    status_code=status.HTTP_201_CREATED,
    summary="Add saved address",
    description="Add a new saved address for authenticated user"
)
async def add_saved_address(
    address_in: SavedAddressCreate,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Add a new saved address.
    
    Required fields:
    - label: Human-readable name (e.g., "Home", "Office", "University")
    - address: Full address string
    - latitude: Latitude coordinate (-90 to 90)
    - longitude: Longitude coordinate (-180 to 180)
    
    Validation:
    - Label must be unique per user
    - Maximum 5 addresses per user
    - Coordinates must be valid (within valid ranges)
    
    Example request:
        {
            "label": "Home",
            "address": "House 123, Street 1, Bahria Town, Islamabad",
            "latitude": 33.7077,
            "longitude": 73.0479
        }
    
    Response:
        {
            "status": "ok",
            "data": {
                "id": "...",
                "user_id": "...",
                "label": "Home",
                "address": "...",
                "latitude": 33.7077,
                "longitude": 73.0479,
                "created_at": "..."
            },
            "error": null
        }
    
    Future enhancements:
    - Verify address against Google Maps API
    - Auto-complete address from coordinates
    - Suggest nearby saved addresses
    
    Requires: Authentication (JWT token)
    """
    return await service.add_saved_address_service(db, current_user.id, address_in)


@router.delete(
    "/addresses/{address_id}",
    response_model=Dict,
    summary="Delete saved address",
    description="Delete a saved address by ID"
)
async def delete_saved_address(
    address_id: UUID,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a saved address.
    
    Args:
        address_id: UUID of the address to delete
    
    Validation:
    - User can only delete their own addresses
    - Address must exist
    
    Response:
        {
            "status": "ok",
            "data": {
                "message": "Address deleted successfully"
            },
            "error": null
        }
    
    Error responses:
    - 404: Address not found or unauthorized
    - 401: Not authenticated
    
    Requires: Authentication (JWT token)
    """
    return await service.delete_saved_address_service(db, current_user.id, address_id)


@router.put(
    "/addresses/{address_id}",
    response_model=Dict,
    summary="Update saved address",
    description="Update an existing saved address for authenticated user",
)
async def update_saved_address(
    address_id: UUID,
    address_in: SavedAddressUpdate,
    current_user: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a saved address.

    Supported fields (all optional):
    - label
    - address
    - latitude
    - longitude

    Validation:
    - User can only update their own addresses
    - Updated label must remain unique per user
    - Coordinates must be valid when provided

    Requires: Authentication (JWT token)
    """
    return await service.update_saved_address_service(
        db,
        current_user.id,
        address_id,
        address_in,
    )
