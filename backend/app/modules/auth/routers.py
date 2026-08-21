"""
Module: Authentication
Purpose: REST API endpoints for Firebase-based authentication.
         Handles user registration and login using Firebase ID tokens.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: February 14, 2026
Notes: All endpoints return standardized {status, data, error} format.
       Uses Firebase Admin SDK for token verification.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth import service
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    UserCreate,
    UserLogin,
    UserPublic,
    RefreshTokenRequest,
    LogoutRequest,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=dict)
async def register(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    """
    Register a new user using Firebase authentication.

    **Request Body:**
    - `firebase_id_token`: Firebase ID token from client
    - `full_name`: User's full name (2-120 characters)
    - `phone`: Phone number with country code (e.g., +923001234567)
    - `role`: User role - passenger or driver (default: passenger)

    **Response:**
    Returns user data and backend JWT tokens (access + refresh).

    **Security:**
    - Firebase token is verified with Firebase Admin SDK
    - Email and Firebase UID extracted from token
    - Email verification status synced from Firebase
    - Authentication is handled entirely by Firebase
    - PostgreSQL stores profile data only (no passwords)
    - Auto-creates user profile and wallet

    **Example Request:**
    ```json
    {
        "firebase_id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6...",
        "full_name": "John Doe",
        "phone": "+923001234567",
        "role": "passenger"
    }
    ```

    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "user": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "full_name": "John Doe",
                "email": "john.doe@example.com",
                "phone": "+923001234567",
                "role": "passenger",
                "firebase_uid": "abc123xyz...",
                "is_active": true,
                "is_verified": true,
                "created_at": "2026-02-14T12:00:00Z"
            },
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer",
            "expires_in": 900
        },
        "error": null
    }
    ```

    **Error Responses:**
    - `400`: Email or phone already registered
    - `401`: Invalid Firebase token
    - `422`: Validation error (invalid phone, etc.)
    - `500`: Server error
    """
    result = await service.register_user(db, user_in)
    return JSONResponse(content=jsonable_encoder(result))


@router.post("/login", response_model=dict)
async def login(user_in: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    Authenticate user using Firebase token.

    **Request Body:**
    - `firebase_id_token`: Firebase ID token from client

    **Response:**
    Returns user data and backend JWT tokens (access + refresh).

    **Security:**
    - Firebase token is verified with Firebase Admin SDK
    - User must exist in database (registered)
    - Account must be active (is_active=true)

    **Example Request:**
    ```json
    {
        "firebase_id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6..."
    }
    ```

    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "user": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "full_name": "John Doe",
                "email": "john.doe@example.com",
                "phone": "+923001234567",
                "role": "passenger",
                "firebase_uid": "abc123xyz...",
                "is_active": true,
                "is_verified": true,
                "created_at": "2026-02-14T12:00:00Z"
            },
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer",
            "expires_in": 900
        },
        "error": null
    }
    ```

    **Error Responses:**
    - `401`: Invalid Firebase token or user not found
    - `403`: Account is disabled
    - `422`: Validation error
    - `500`: Server error
    """
    result = await service.login_user(db, user_in.firebase_id_token)
    return JSONResponse(content=jsonable_encoder(result))


@router.post("/refresh", response_model=dict)
async def refresh_token(refresh_in: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """
    Refresh access token using refresh token.

    **Request Body:**
    - `refresh_token`: Valid refresh token string

    **Response:**
    Returns new access token (refresh token remains same).

    **Security:**
    - Refresh token must exist in database
    - Token must not be revoked
    - Token must not be expired
    - User account must still be active

    **Token Rotation:**
    For enhanced security, consider rotating refresh tokens on each use.

    **Example Request:**
    ```json
    {
        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
    ```

    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer",
            "expires_in": 900
        },
        "error": null
    }
    ```

    **Error Responses:**
    - `401`: Invalid or revoked refresh token
    - `403`: User account disabled
    - `422`: Validation error
    - `500`: Server error
    """
    return await service.refresh_access_token(db, refresh_in.refresh_token)


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user information.

    **Authorization:**
    Requires valid JWT access token in Authorization header:
    `Authorization: Bearer <access_token>`

    **Response:**
    Returns authenticated user's profile data.

    **Usage:**
    This endpoint is protected and requires authentication.
    Use the access token from login/register response.

    **Example Request:**
    ```
    GET /api/v1/auth/me
    Headers:
        Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    ```

    **Example Response:**
    ```json
    {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "full_name": "John Doe",
        "email": "john.doe@university.edu",
        "phone": "+1234567890",
        "role": "student",
        "is_active": true,
        "is_verified": false,
        "created_at": "2025-11-08T12:00:00Z"
    }
    ```

    **Error Responses:**
    - `401`: Invalid or expired access token
    - `403`: Account disabled
    - `404`: User not found
    """
    return UserPublic.from_orm(current_user)


@router.post("/logout", response_model=dict)
async def logout(logout_in: LogoutRequest, db: AsyncSession = Depends(get_db)):
    """
    Logout user and invalidate refresh token.

    **Request Body:**
    - `refresh_token`: Refresh token to revoke

    **Response:**
    Returns success message. Token is marked as revoked in database.

    **Security:**
    - Revoked tokens cannot be used for refresh
    - Access tokens remain valid until expiration (15 min default)

    **Example Request:**
    ```json
    {
        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
    ```

    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "message": "Logged out successfully"
        },
        "error": null
    }
    ```

    **Error Responses:**
    - `500`: Server error
    """
    return await service.logout_user(db, logout_in.refresh_token)
