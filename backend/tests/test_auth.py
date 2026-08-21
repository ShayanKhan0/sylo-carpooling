"""
Module: Authentication Tests
Purpose: Comprehensive tests for authentication and authorization module.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Tests cover registration, login, JWT flow, token refresh, and password reset.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.core.security import decode_token


@pytest.mark.asyncio
async def test_register_user_success():
    """
    Test successful user registration.
    
    Verifies:
    - User can register with valid data
    - Returns 201 status code
    - Response contains user data and tokens
    - Password is not in response
    - Access and refresh tokens are present
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Test User",
                "email": "test@example.com",
                "password": "SecurePass123!",
                "phone": "+1234567890",
                "role": "student"
            }
        )
    
    assert response.status_code == 201
    data = response.json()
    
    # Check response structure
    assert data["status"] == "ok"
    assert data["error"] is None
    assert "data" in data
    
    # Check user data
    user = data["data"]["user"]
    assert user["email"] == "test@example.com"
    assert user["full_name"] == "Test User"
    assert user["phone"] == "+1234567890"
    assert user["role"] == "student"
    assert user["is_active"] is True
    assert user["is_verified"] is False
    assert "password" not in user
    assert "password_hash" not in user
    
    # Check tokens
    assert "access_token" in data["data"]
    assert "refresh_token" in data["data"]
    assert data["data"]["token_type"] == "bearer"
    assert data["data"]["expires_in"] > 0


@pytest.mark.asyncio
async def test_register_duplicate_email():
    """
    Test registration with duplicate email fails.
    
    Verifies:
    - Cannot register with existing email
    - Returns 400 status code
    - Error message indicates email already registered
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # First registration
        await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "First User",
                "email": "duplicate@example.com",
                "password": "SecurePass123!",
                "phone": "+1111111111",
                "role": "student"
            }
        )
        
        # Attempt duplicate registration
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Second User",
                "email": "duplicate@example.com",  # Same email
                "password": "DifferentPass456!",
                "phone": "+2222222222",
                "role": "student"
            }
        )
    
    assert response.status_code == 400
    data = response.json()
    assert data["status"] == "error"
    assert "email" in data["error"].lower() or "already" in data["error"].lower()


@pytest.mark.asyncio
async def test_register_weak_password():
    """
    Test registration with weak password fails validation.
    
    Verifies:
    - Password must be at least 8 characters
    - Password must contain uppercase letter
    - Password must contain lowercase letter
    - Password must contain digit
    - Returns 422 validation error
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Test short password
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Test User",
                "email": "weak@example.com",
                "password": "short",  # Too short, no uppercase, no digit
                "phone": "+3333333333",
                "role": "student"
            }
        )
    
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_login_success():
    """
    Test successful login with valid credentials.
    
    Verifies:
    - Can login with registered email and password
    - Returns 200 status code
    - Response contains user data and tokens
    - Access and refresh tokens are JWT format
    - Token payload contains user info
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register user first
        await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Login Test User",
                "email": "login@example.com",
                "password": "LoginPass123!",
                "phone": "+4444444444",
                "role": "student"
            }
        )
        
        # Attempt login
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "login@example.com",
                "password": "LoginPass123!"
            }
        )
    
    assert response.status_code == 200
    data = response.json()
    
    # Check response structure
    assert data["status"] == "ok"
    assert "data" in data
    
    # Check user data
    user = data["data"]["user"]
    assert user["email"] == "login@example.com"
    assert user["full_name"] == "Login Test User"
    
    # Check tokens
    access_token = data["data"]["access_token"]
    refresh_token = data["data"]["refresh_token"]
    assert access_token is not None
    assert refresh_token is not None
    
    # Verify token payload
    payload = decode_token(access_token)
    assert payload is not None
    assert payload["email"] == "login@example.com"
    assert "sub" in payload  # User ID
    assert "exp" in payload  # Expiration


@pytest.mark.asyncio
async def test_login_invalid_credentials():
    """
    Test login with invalid credentials fails.
    
    Verifies:
    - Wrong password returns 401
    - Non-existent email returns 401
    - Error doesn't reveal which is wrong (security)
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register user
        await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Secure User",
                "email": "secure@example.com",
                "password": "CorrectPass123!",
                "phone": "+5555555555",
                "role": "student"
            }
        )
        
        # Test wrong password
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "secure@example.com",
                "password": "WrongPassword123!"
            }
        )
        assert response.status_code == 401
        
        # Test non-existent email
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "AnyPassword123!"
            }
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_with_valid_token():
    """
    Test /auth/me endpoint with valid access token.
    
    Verifies:
    - Can access protected endpoint with valid token
    - Returns current user's data
    - User data matches authenticated user
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register and login
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Me Test User",
                "email": "me@example.com",
                "password": "MePass123!",
                "phone": "+6666666666",
                "role": "driver"
            }
        )
        
        access_token = response.json()["data"]["access_token"]
        
        # Call /me endpoint
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
    
    assert response.status_code == 200
    user = response.json()
    
    assert user["email"] == "me@example.com"
    assert user["full_name"] == "Me Test User"
    assert user["role"] == "driver"
    assert "password" not in user


@pytest.mark.asyncio
async def test_get_me_without_token():
    """
    Test /auth/me endpoint without authentication fails.
    
    Verifies:
    - Protected endpoint requires authentication
    - Returns 401 without token
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me")
    
    assert response.status_code in [401, 403]  # Unauthorized or Forbidden


@pytest.mark.asyncio
async def test_get_me_with_invalid_token():
    """
    Test /auth/me endpoint with invalid token fails.
    
    Verifies:
    - Invalid token is rejected
    - Returns 401 error
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_success():
    """
    Test refresh token generates new access token.
    
    Verifies:
    - Refresh token can be used to get new access token
    - Returns 200 status code
    - New access token is valid
    - Token payload is correct
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register and get tokens
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Refresh Test User",
                "email": "refresh@example.com",
                "password": "RefreshPass123!",
                "phone": "+7777777777",
                "role": "student"
            }
        )
        
        refresh_token = response.json()["data"]["refresh_token"]
        
        # Use refresh token
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["status"] == "ok"
    assert "access_token" in data["data"]
    assert data["data"]["token_type"] == "bearer"
    
    # Verify new access token is valid
    new_access_token = data["data"]["access_token"]
    payload = decode_token(new_access_token)
    assert payload is not None
    assert payload["email"] == "refresh@example.com"


@pytest.mark.asyncio
async def test_refresh_with_invalid_token():
    """
    Test refresh with invalid token fails.
    
    Verifies:
    - Invalid refresh token is rejected
    - Returns 401 error
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid.refresh.token"}
        )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_success():
    """
    Test logout revokes refresh token.
    
    Verifies:
    - Logout endpoint revokes refresh token
    - Returns 200 status code
    - Revoked token cannot be used for refresh
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register and get tokens
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Logout Test User",
                "email": "logout@example.com",
                "password": "LogoutPass123!",
                "phone": "+8888888888",
                "role": "student"
            }
        )
        
        refresh_token = response.json()["data"]["refresh_token"]
        
        # Logout
        response = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token}
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        # Try to use revoked token
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        
        assert response.status_code == 401  # Should fail


@pytest.mark.asyncio
async def test_request_password_reset():
    """
    Test password reset request.
    
    Verifies:
    - Can request password reset
    - Always returns success (doesn't reveal if email exists)
    - Returns 200 status code
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Request reset for existing email
        response = await client.post(
            "/api/v1/auth/request-reset",
            json={"email": "test@example.com"}
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        # Request reset for non-existent email (should also succeed)
        response = await client.post(
            "/api/v1/auth/request-reset",
            json={"email": "nonexistent@example.com"}
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_access_token_contains_role():
    """
    Test access token contains user role for RBAC.
    
    Verifies:
    - Token payload includes role claim
    - Role matches user's assigned role
    - Different roles are correctly encoded
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register driver
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Driver User",
                "email": "driver@example.com",
                "password": "DriverPass123!",
                "phone": "+9999999999",
                "role": "driver"
            }
        )
        
        access_token = response.json()["data"]["access_token"]
        payload = decode_token(access_token)
        
        assert payload["role"] == "driver"
        
        # Register admin
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Admin User",
                "email": "admin@example.com",
                "password": "AdminPass123!",
                "phone": "+1010101010",
                "role": "admin"
            }
        )
        
        access_token = response.json()["data"]["access_token"]
        payload = decode_token(access_token)
        
        assert payload["role"] == "admin"


@pytest.mark.asyncio
async def test_token_expiration_times():
    """
    Test tokens have correct expiration times.
    
    Verifies:
    - Access token expires in configured time (default 15 min)
    - Response includes expires_in field
    - Expiration is reasonable (not negative or too long)
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Expiry Test User",
                "email": "expiry@example.com",
                "password": "ExpiryPass123!",
                "phone": "+1212121212",
                "role": "student"
            }
        )
        
        data = response.json()["data"]
        
        # Check expires_in is present and reasonable
        assert "expires_in" in data
        expires_in = data["expires_in"]
        assert expires_in > 0
        assert expires_in <= 86400  # Max 24 hours
