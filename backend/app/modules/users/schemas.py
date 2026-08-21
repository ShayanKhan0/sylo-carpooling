"""
Module: Users
Purpose: Pydantic validation schemas for user profiles and saved addresses.
         Handles request/response validation with custom validators.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 7, 2025
Notes: All schemas include validation rules, examples, and proper type hints.
       Schemas are separated into Create, Update, and Public for clean API design.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import date, datetime
from uuid import UUID
import re


_ALLOWED_GENDERS = {'male', 'female', 'other'}
_GENDER_ALIASES = {
    'm': 'male',
    'f': 'female',
    'man': 'male',
    'woman': 'female',
}

_ORG_TYPE_ALIASES = {
    'university': 'university',
    'college': 'college',
    'school': 'school',
    'office': 'office',
    'corporate': 'office',
    'company': 'office',
    'government': 'office',
    'govt': 'office',
    'other': 'office',
}


def _normalize_gender(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    return _GENDER_ALIASES.get(normalized, normalized)


def _normalize_org_type(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    return _ORG_TYPE_ALIASES.get(normalized)


# ==================== User Profile Schemas ====================

class UserProfileBase(BaseModel):
    """
    Base schema for user profile with common fields.
    Used as parent class for Create and Update schemas.
    """
    profile_photo: Optional[str] = Field(None, example="https://example.com/photo.jpg")
    gender: Optional[str] = Field(None, example="male")
    date_of_birth: Optional[date] = Field(None, example="2000-01-15")
    organization_name: Optional[str] = Field(None, max_length=255, example="Bahria University")
    organization_type: Optional[str] = Field(None, example="university")
    cnic: Optional[str] = Field(None, max_length=20, example="12345-1234567-1")
    driving_license: Optional[str] = Field(None, max_length=50, example="DL-12345678")
    car_registration: Optional[str] = Field(None, max_length=50, example="ABC-1234")
    push_notifications_enabled: Optional[bool] = Field(True, example=True)
    share_location_enabled: Optional[bool] = Field(True, example=True)
    
    @validator('gender')
    def validate_gender(cls, v):
        """Validate gender is one of allowed values."""
        normalized = _normalize_gender(v)
        if normalized is None:
            return None
        if normalized not in _ALLOWED_GENDERS:
            raise ValueError('Gender must be one of: male, female, other')
        return normalized
    
    @validator('organization_type')
    def validate_org_type(cls, v):
        """Validate organization type is one of allowed values."""
        normalized = _normalize_org_type(v)
        if normalized is None:
            return None
        if normalized not in ['university', 'college', 'school', 'office']:
            raise ValueError('Organization type must be one of: university, college, school, office')
        return normalized
    
    @validator('cnic')
    def validate_cnic(cls, v):
        """
        Validate Pakistan CNIC format: 12345-1234567-1
        13 digits with dashes at positions 5 and 12.
        """
        if v:
            v = v.strip()
            cnic_pattern = r'^\d{5}-\d{7}-\d{1}$'
            if not re.match(cnic_pattern, v):
                raise ValueError('CNIC must be in format: 12345-1234567-1')
        return v
    
    @validator('date_of_birth')
    def validate_dob(cls, v):
        """Validate user is at least 13 years old."""
        if v:
            from datetime import date
            today = date.today()
            age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
            if age < 13:
                raise ValueError('User must be at least 13 years old')
            if age > 120:
                raise ValueError('Invalid date of birth')
        return v


class UserProfileCreate(UserProfileBase):
    """
    Schema for creating a new user profile.
    All fields are optional as profile can be filled gradually.
    """
    pass


class UserProfileUpdate(BaseModel):
    """
    Schema for updating user profile.
    All fields are optional, only provided fields will be updated.
    """
    profile_photo: Optional[str] = Field(None, example="https://example.com/photo.jpg")
    gender: Optional[str] = Field(None, example="male")
    date_of_birth: Optional[date] = Field(None, example="2000-01-15")
    organization_name: Optional[str] = Field(None, max_length=255, example="Bahria University")
    organization_type: Optional[str] = Field(None, example="university")
    cnic: Optional[str] = Field(None, max_length=20, example="12345-1234567-1")
    driving_license: Optional[str] = Field(None, max_length=50, example="DL-12345678")
    car_registration: Optional[str] = Field(None, max_length=50, example="ABC-1234")
    push_notifications_enabled: Optional[bool] = Field(None, example=True)
    share_location_enabled: Optional[bool] = Field(None, example=True)
    
    @validator('gender')
    def validate_gender(cls, v):
        normalized = _normalize_gender(v)
        if normalized is None:
            return None
        if normalized not in _ALLOWED_GENDERS:
            raise ValueError('Gender must be one of: male, female, other')
        return normalized
    
    @validator('organization_type')
    def validate_org_type(cls, v):
        normalized = _normalize_org_type(v)
        if normalized is None:
            return None
        if normalized not in ['university', 'college', 'school', 'office']:
            raise ValueError('Organization type must be one of: university, college, school, office')
        return normalized
    
    @validator('cnic')
    def validate_cnic(cls, v):
        if v:
            v = v.strip()
            cnic_pattern = r'^\d{5}-\d{7}-\d{1}$'
            if not re.match(cnic_pattern, v):
                raise ValueError('CNIC must be in format: 12345-1234567-1')
        return v
    
    @validator('date_of_birth')
    def validate_dob(cls, v):
        if v:
            from datetime import date
            today = date.today()
            age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
            if age < 13:
                raise ValueError('User must be at least 13 years old')
            if age > 120:
                raise ValueError('Invalid date of birth')
        return v


class UserProfilePublic(UserProfileBase):
    """
    Public schema for user profile (response model).
    Includes all fields plus database-generated values.
    """
    id: UUID
    user_id: UUID
    address_verification: bool
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True  # Enable ORM mode for SQLAlchemy models
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "123e4567-e89b-12d3-a456-426614174001",
                "profile_photo": "https://example.com/photo.jpg",
                "gender": "male",
                "date_of_birth": "2000-01-15",
                "organization_name": "Bahria University",
                "organization_type": "university",
                "cnic": None,
                "driving_license": None,
                "car_registration": None,
                "address_verification": False,
                "push_notifications_enabled": True,
                "share_location_enabled": True,
                "created_at": "2025-11-07T10:00:00Z",
                "updated_at": "2025-11-07T12:00:00Z"
            }
        }


# ==================== Saved Address Schemas ====================

class SavedAddressBase(BaseModel):
    """
    Base schema for saved address with common fields.
    """
    label: str = Field(..., min_length=1, max_length=50, example="Home")
    address: str = Field(..., min_length=1, max_length=255, example="Bahria University, Islamabad")
    latitude: float = Field(..., example=33.7077, description="Latitude coordinate")
    longitude: float = Field(..., example=73.0479, description="Longitude coordinate")
    
    @validator('latitude')
    def validate_latitude(cls, v):
        """Validate latitude is in valid range [-90, 90]."""
        if v < -90 or v > 90:
            raise ValueError('Latitude must be between -90 and 90')
        return v
    
    @validator('longitude')
    def validate_longitude(cls, v):
        """Validate longitude is in valid range [-180, 180]."""
        if v < -180 or v > 180:
            raise ValueError('Longitude must be between -180 and 180')
        return v
    
    @validator('label')
    def validate_label(cls, v):
        """Validate label is not empty and contains valid characters."""
        if not v.strip():
            raise ValueError('Label cannot be empty')
        # Only allow alphanumeric, spaces, and common punctuation
        if not re.match(r'^[a-zA-Z0-9\s\-_.,]+$', v):
            raise ValueError('Label contains invalid characters')
        return v.strip()


class SavedAddressCreate(SavedAddressBase):
    """
    Schema for creating a new saved address.
    All fields are required.
    """
    pass


class SavedAddressUpdate(BaseModel):
    """
    Schema for updating a saved address.
    All fields are optional.
    """
    label: Optional[str] = Field(None, min_length=1, max_length=50, example="Office")
    address: Optional[str] = Field(None, min_length=1, max_length=255, example="I-9, Islamabad")
    latitude: Optional[float] = Field(None, example=33.6844)
    longitude: Optional[float] = Field(None, example=73.0479)
    
    @validator('latitude')
    def validate_latitude(cls, v):
        if v is not None and (v < -90 or v > 90):
            raise ValueError('Latitude must be between -90 and 90')
        return v
    
    @validator('longitude')
    def validate_longitude(cls, v):
        if v is not None and (v < -180 or v > 180):
            raise ValueError('Longitude must be between -180 and 180')
        return v
    
    @validator('label')
    def validate_label(cls, v):
        if v is not None:
            if not v.strip():
                raise ValueError('Label cannot be empty')
            if not re.match(r'^[a-zA-Z0-9\s\-_.,]+$', v):
                raise ValueError('Label contains invalid characters')
            return v.strip()
        return v


class SavedAddressPublic(SavedAddressBase):
    """
    Public schema for saved address (response model).
    Includes all fields plus database-generated values.
    """
    id: UUID
    user_id: UUID
    created_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174002",
                "user_id": "123e4567-e89b-12d3-a456-426614174001",
                "label": "Home",
                "address": "House 123, Street 1, Bahria Town, Islamabad",
                "latitude": 33.7077,
                "longitude": 73.0479,
                "created_at": "2025-11-07T10:00:00Z"
            }
        }


# ==================== Combined User Response Schemas ====================

class UserWithProfilePublic(BaseModel):
    """
    Combined schema merging User + UserProfile + SavedAddresses.
    Used for /users/me endpoint to return complete user data.
    """
    # User fields (from auth module)
    id: UUID
    full_name: str
    email: str
    phone: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    
    # Profile fields
    profile: Optional[UserProfilePublic]
    
    # Saved addresses
    saved_addresses: List[SavedAddressPublic] = []
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174001",
                "full_name": "Ahmed Khan",
                "email": "ahmed@example.com",
                "phone": "+923001234567",
                "role": "student",
                "is_active": True,
                "is_verified": True,
                "created_at": "2025-11-07T10:00:00Z",
                "profile": {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "user_id": "123e4567-e89b-12d3-a456-426614174001",
                    "profile_photo": "https://example.com/photo.jpg",
                    "gender": "male",
                    "date_of_birth": "2000-01-15",
                    "organization_name": "Bahria University",
                    "organization_type": "university",
                    "cnic": None,
                    "driving_license": None,
                    "car_registration": None,
                    "address_verification": False,
                    "created_at": "2025-11-07T10:00:00Z",
                    "updated_at": "2025-11-07T12:00:00Z"
                },
                "saved_addresses": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174002",
                        "user_id": "123e4567-e89b-12d3-a456-426614174001",
                        "label": "Home",
                        "address": "Bahria Town, Islamabad",
                        "latitude": 33.7077,
                        "longitude": 73.0479,
                        "created_at": "2025-11-07T10:00:00Z"
                    }
                ]
            }
        }


# ==================== Request Schemas ====================

class PhotoUploadRequest(BaseModel):
    """
    Schema for uploading profile photo.
    Supports base64 encoded image or URL.
    """
    photo: str = Field(
        ..., 
        min_length=10,
        max_length=8000000,  # allows larger base64 payloads; service enforces decoded size limit
        example="data:image/jpeg;base64,/9j/4AAQSkZJRg..."
    )
    
    @validator('photo')
    def validate_photo(cls, v):
        """
        Validate photo is either:
        1. Valid URL (http:// or https://)
        2. Valid base64 data URI (data:image/...)
        """
        if v.startswith('http://') or v.startswith('https://'):
            # Valid URL
            return v
        elif v.startswith('data:image/'):
            # Valid base64 data URI
            if ';base64,' not in v:
                raise ValueError('Invalid base64 data URI format')
            return v
        else:
            raise ValueError('Photo must be a valid URL or base64 data URI')
    
    class Config:
        json_schema_extra = {
            "example": {
                "photo": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD..."
            }
        }
