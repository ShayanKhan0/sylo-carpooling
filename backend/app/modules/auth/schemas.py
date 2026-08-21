"""
Module: Authentication Schemas

Purpose: Pydantic models for request validation and response serialization.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: All schemas use Pydantic for automatic validation and documentation.
       Follows OAuth2 + JWT standards for enterprise-grade authentication.
"""

from pydantic import BaseModel, EmailStr, Field, validator, ConfigDict
from typing import Optional
from uuid import UUID
from datetime import datetime
import re


def normalize_phone(value: str) -> str:
    raw = re.sub(r"\s+", "", value or "")
    if not raw:
        return value

    if raw.startswith("+"):
        digits = re.sub(r"\D", "", raw)
        return f"+{digits}" if digits else value

    digits = re.sub(r"\D", "", raw)
    if digits.startswith("92"):
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 11:
        return f"+92{digits[1:]}"
    if digits.startswith("3") and len(digits) == 10:
        return f"+92{digits}"

    return value


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class UserCreate(BaseModel):
    """
    Schema for Firebase-based user registration request.
    
    Validation:
    - firebase_id_token: JWT token from Firebase Authentication
    - Phone: E.164 format (+1234567890 to +1234567890123456789)
    - Role: One of [passenger, driver] (student is accepted as alias)
    
    Note: Email comes from Firebase token verification.
          Authentication is handled entirely by Firebase.
          PostgreSQL stores only profile data (no passwords).
    """
    firebase_id_token: str = Field(..., example="eyJhbGciOiJSUzI1NiIsImtpZCI6...")
    full_name: str = Field(..., min_length=2, max_length=120, example="John Doe")
    phone: str = Field(..., example="+923001234567")
    role: str = Field(default="passenger", example="passenger")
    
    @validator("phone")
    def validate_phone(cls, v):
        """Validate E.164 phone format."""
        normalized = normalize_phone(v)
        if not re.match(r"^\+\d{10,19}$", normalized):
            raise ValueError("Phone must be in E.164 format: +923001234567")
        return normalized
    
    @validator("role")
    def validate_role(cls, v):
        """Ensure role is valid and normalize legacy values."""
        normalized = v.lower()
        if normalized == "student":
            return "passenger"
        allowed = ["passenger", "driver"]
        if normalized not in allowed:
            raise ValueError(f"Role must be one of {allowed}")
        return normalized


class UserLogin(BaseModel):
    """
    Schema for Firebase-based user login request.
    
    Authentication is done via Firebase ID token verification.
    """
    firebase_id_token: str = Field(..., example="eyJhbGciOiJSUzI1NiIsImtpZCI6...")


class RefreshTokenRequest(BaseModel):
    """
    Schema for refresh token request.
    
    Used to obtain a new access token without re-authenticating.
    """
    refresh_token: str = Field(..., min_length=32, example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")


class LogoutRequest(BaseModel):
    """
    Schema for logout request.
    
    Revokes the refresh token to prevent reuse.
    """
    refresh_token: str = Field(..., min_length=32, example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class UserPublic(BaseModel):
    """
    Schema for user public data (response).
    
    Excludes sensitive fields like password_hash.
    """
    id: UUID
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    role: str
    firebase_uid: Optional[str] = None
    is_active: bool
    is_verified: bool
    created_at: datetime
    
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        },
    )


class Token(BaseModel):
    """
    Schema for token response.
    
    Returns access + refresh tokens after login or registration.
    """
    access_token: str = Field(..., example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")
    refresh_token: str = Field(..., example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")
    token_type: str = Field(default="bearer", example="bearer")
    expires_in: int = Field(..., example=900, description="Access token expiry in seconds (15 minutes)")


class TokenData(BaseModel):
    """
    Schema for decoded JWT token payload.
    
    Used internally for extracting user info from JWT.
    """
    user_id: Optional[UUID] = None
    email: Optional[str] = None
    role: Optional[str] = None
