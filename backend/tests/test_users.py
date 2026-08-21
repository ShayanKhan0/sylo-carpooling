"""
Module: Users Module Tests
Purpose: Comprehensive async tests for user profile and saved address management.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Tests profile auto-creation, CRUD operations, validation, and JWT protection.
       Uses AsyncClient for integration testing with FastAPI.
"""

import pytest
from httpx import AsyncClient
from datetime import date
from uuid import uuid4

from app.main import app
from app.core.security import decode_token


# ==================== Test Profile Auto-Creation ====================

@pytest.mark.asyncio
async def test_profile_auto_creation_after_registration():
    """
    Test that an empty UserProfile is automatically created when user registers.
    
    Flow:
        1. Register new user via POST /auth/register
        2. Get user profile via GET /users/me
        3. Verify profile exists (even if empty)
        4. Verify profile fields are all None/default values
    
    Expected: Profile exists with user_id linked, all fields nullable
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register new user
        register_data = {
            "full_name": "Test User",
            "email": f"test_{uuid4()}@example.com",
            "password": "TestPass123",
            "phone": f"+92300{str(uuid4().int)[:7]}",
            "role": "student"
        }
        
        register_response = await client.post("/api/v1/auth/register", json=register_data)
        assert register_response.status_code == 200, f"Registration failed: {register_response.text}"
        
        register_json = register_response.json()
        assert register_json["status"] == "ok"
        assert "access_token" in register_json["data"]
        
        access_token = register_json["data"]["access_token"]
        
        # Get user profile with JWT token
        headers = {"Authorization": f"Bearer {access_token}"}
        profile_response = await client.get("/api/v1/users/me", headers=headers)
        
        assert profile_response.status_code == 200
        profile_json = profile_response.json()
        
        assert profile_json["status"] == "ok"
        assert "profile" in profile_json["data"]
        
        # Verify profile exists and is linked to user
        profile = profile_json["data"]["profile"]
        assert profile is not None, "Profile should be auto-created"
        assert profile["user_id"] is not None
        
        # Verify all fields start as None (empty profile)
        assert profile["profile_photo"] is None
        assert profile["gender"] is None
        assert profile["date_of_birth"] is None
        assert profile["organization_name"] is None
        assert profile["cnic"] is None
        assert profile["address_verification"] is False


# ==================== Test Profile Updates ====================

@pytest.mark.asyncio
async def test_update_profile_fields():
    """
    Test updating user profile fields.
    
    Flow:
        1. Register user and get access token
        2. Update profile with valid data via PUT /users/me
        3. Verify updated fields are saved
        4. Verify unchanged fields remain None
    
    Expected: Partial update works, only provided fields updated
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register user
        register_data = {
            "full_name": "Profile Update Test",
            "email": f"profile_{uuid4()}@example.com",
            "password": "UpdatePass123",
            "phone": f"+92301{str(uuid4().int)[:7]}",
            "role": "student"
        }
        
        register_response = await client.post("/api/v1/auth/register", json=register_data)
        access_token = register_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Update profile with partial data
        update_data = {
            "gender": "male",
            "date_of_birth": "2000-05-15",
            "organization_name": "Bahria University",
            "organization_type": "university"
        }
        
        update_response = await client.put("/api/v1/users/me", json=update_data, headers=headers)
        assert update_response.status_code == 200
        
        update_json = update_response.json()
        assert update_json["status"] == "ok"
        
        profile = update_json["data"]["profile"]
        assert profile["gender"] == "male"
        assert profile["date_of_birth"] == "2000-05-15"
        assert profile["organization_name"] == "Bahria University"
        assert profile["organization_type"] == "university"
        
        # Fields not updated should remain None
        assert profile["cnic"] is None
        assert profile["driving_license"] is None


@pytest.mark.asyncio
async def test_invalid_cnic_format_fails():
    """
    Test CNIC validation rejects invalid formats.
    
    Expected: 422 Validation Error for invalid CNIC (must be: 12345-1234567-1)
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register user
        register_data = {
            "full_name": "CNIC Test",
            "email": f"cnic_{uuid4()}@example.com",
            "password": "CnicPass123",
            "phone": f"+92302{str(uuid4().int)[:7]}",
            "role": "driver"
        }
        
        register_response = await client.post("/api/v1/auth/register", json=register_data)
        access_token = register_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Try to update with invalid CNIC format
        invalid_cnic_data = {
            "cnic": "12345678901234"  # No dashes - invalid format
        }
        
        update_response = await client.put("/api/v1/users/me", json=invalid_cnic_data, headers=headers)
        assert update_response.status_code == 422, "Should reject invalid CNIC format"
        
        # Try with correct format
        valid_cnic_data = {
            "cnic": "12345-1234567-1"
        }
        
        update_response = await client.put("/api/v1/users/me", json=valid_cnic_data, headers=headers)
        assert update_response.status_code == 200, "Should accept valid CNIC format"


@pytest.mark.asyncio
async def test_age_validation():
    """
    Test date of birth validation (minimum 13 years old).
    
    Expected: 422 Validation Error for DOB less than 13 years ago
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register user
        register_data = {
            "full_name": "Age Test",
            "email": f"age_{uuid4()}@example.com",
            "password": "AgePass123",
            "phone": f"+92303{str(uuid4().int)[:7]}",
            "role": "student"
        }
        
        register_response = await client.post("/api/v1/auth/register", json=register_data)
        access_token = register_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Try to update with DOB less than 13 years ago (too young)
        from datetime import date, timedelta
        too_young_dob = (date.today() - timedelta(days=365 * 10)).isoformat()  # 10 years old
        
        invalid_age_data = {
            "date_of_birth": too_young_dob
        }
        
        update_response = await client.put("/api/v1/users/me", json=invalid_age_data, headers=headers)
        assert update_response.status_code == 422, "Should reject age under 13"
        
        # Try with valid age (20 years old)
        valid_dob = (date.today() - timedelta(days=365 * 20)).isoformat()
        
        valid_age_data = {
            "date_of_birth": valid_dob
        }
        
        update_response = await client.put("/api/v1/users/me", json=valid_age_data, headers=headers)
        assert update_response.status_code == 200, "Should accept age 13+"


# ==================== Test Photo Upload ====================

@pytest.mark.asyncio
async def test_upload_photo():
    """
    Test profile photo upload via URL.
    
    Flow:
        1. Register user
        2. Upload photo via POST /users/me/photo
        3. Verify photo URL saved in profile
    
    Expected: Photo URL stored correctly
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register user
        register_data = {
            "full_name": "Photo Test",
            "email": f"photo_{uuid4()}@example.com",
            "password": "PhotoPass123",
            "phone": f"+92304{str(uuid4().int)[:7]}",
            "role": "student"
        }
        
        register_response = await client.post("/api/v1/auth/register", json=register_data)
        access_token = register_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Upload photo URL
        photo_data = {
            "photo_url": "https://example.com/photos/user123.jpg"
        }
        
        photo_response = await client.post("/api/v1/users/me/photo", json=photo_data, headers=headers)
        assert photo_response.status_code == 200
        
        photo_json = photo_response.json()
        assert photo_json["status"] == "ok"
        assert photo_json["data"]["profile"]["profile_photo"] == photo_data["photo_url"]


# ==================== Test Saved Addresses ====================

@pytest.mark.asyncio
async def test_add_saved_address():
    """
    Test adding a saved address.
    
    Flow:
        1. Register user
        2. Add address via POST /users/addresses
        3. Verify address created with correct data
    
    Expected: Address saved with label, address, coordinates
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register user
        register_data = {
            "full_name": "Address Test",
            "email": f"address_{uuid4()}@example.com",
            "password": "AddressPass123",
            "phone": f"+92305{str(uuid4().int)[:7]}",
            "role": "student"
        }
        
        register_response = await client.post("/api/v1/auth/register", json=register_data)
        access_token = register_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Add saved address
        address_data = {
            "label": "Home",
            "address": "123 Main Street, Islamabad",
            "latitude": 33.6844,
            "longitude": 73.0479
        }
        
        add_response = await client.post("/api/v1/users/addresses", json=address_data, headers=headers)
        assert add_response.status_code == 201
        
        add_json = add_response.json()
        assert add_json["status"] == "ok"
        
        saved_address = add_json["data"]
        assert saved_address["label"] == "Home"
        assert saved_address["address"] == "123 Main Street, Islamabad"
        assert saved_address["latitude"] == 33.6844
        assert saved_address["longitude"] == 73.0479
        assert "id" in saved_address
        assert "created_at" in saved_address


@pytest.mark.asyncio
async def test_get_saved_addresses():
    """
    Test retrieving all saved addresses.
    
    Flow:
        1. Register user
        2. Add multiple addresses
        3. Get addresses via GET /users/addresses
        4. Verify all addresses returned
    
    Expected: All addresses returned in response
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register user
        register_data = {
            "full_name": "Get Address Test",
            "email": f"getaddr_{uuid4()}@example.com",
            "password": "GetAddrPass123",
            "phone": f"+92306{str(uuid4().int)[:7]}",
            "role": "student"
        }
        
        register_response = await client.post("/api/v1/auth/register", json=register_data)
        access_token = register_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Add multiple addresses
        addresses = [
            {"label": "Home", "address": "Home Address", "latitude": 33.6844, "longitude": 73.0479},
            {"label": "Office", "address": "Office Address", "latitude": 33.7077, "longitude": 73.0422},
            {"label": "University", "address": "Bahria University", "latitude": 33.5651, "longitude": 73.0169}
        ]
        
        for addr_data in addresses:
            await client.post("/api/v1/users/addresses", json=addr_data, headers=headers)
        
        # Get all addresses
        get_response = await client.get("/api/v1/users/addresses", headers=headers)
        assert get_response.status_code == 200
        
        get_json = get_response.json()
        assert get_json["status"] == "ok"
        assert len(get_json["data"]) == 3
        
        # Verify all labels present
        labels = [addr["label"] for addr in get_json["data"]]
        assert "Home" in labels
        assert "Office" in labels
        assert "University" in labels


@pytest.mark.asyncio
async def test_delete_saved_address():
    """
    Test deleting a saved address.
    
    Flow:
        1. Register user
        2. Add address
        3. Delete address via DELETE /users/addresses/{id}
        4. Verify address no longer in list
    
    Expected: Address deleted successfully
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register user
        register_data = {
            "full_name": "Delete Address Test",
            "email": f"deladdr_{uuid4()}@example.com",
            "password": "DelAddrPass123",
            "phone": f"+92307{str(uuid4().int)[:7]}",
            "role": "student"
        }
        
        register_response = await client.post("/api/v1/auth/register", json=register_data)
        access_token = register_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Add address
        address_data = {
            "label": "Temporary",
            "address": "Temp Address",
            "latitude": 33.6844,
            "longitude": 73.0479
        }
        
        add_response = await client.post("/api/v1/users/addresses", json=address_data, headers=headers)
        address_id = add_response.json()["data"]["id"]
        
        # Delete address
        delete_response = await client.delete(f"/api/v1/users/addresses/{address_id}", headers=headers)
        assert delete_response.status_code == 200
        
        # Verify address no longer exists
        get_response = await client.get("/api/v1/users/addresses", headers=headers)
        addresses = get_response.json()["data"]
        
        address_ids = [addr["id"] for addr in addresses]
        assert address_id not in address_ids


@pytest.mark.asyncio
async def test_max_addresses_limit():
    """
    Test that users cannot add more than 5 saved addresses.
    
    Expected: 400 Bad Request when trying to add 6th address
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register user
        register_data = {
            "full_name": "Max Address Test",
            "email": f"maxaddr_{uuid4()}@example.com",
            "password": "MaxAddrPass123",
            "phone": f"+92308{str(uuid4().int)[:7]}",
            "role": "student"
        }
        
        register_response = await client.post("/api/v1/auth/register", json=register_data)
        access_token = register_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Add 5 addresses (max limit)
        for i in range(5):
            address_data = {
                "label": f"Address{i+1}",
                "address": f"Address {i+1}",
                "latitude": 33.6844 + i * 0.01,
                "longitude": 73.0479 + i * 0.01
            }
            
            add_response = await client.post("/api/v1/users/addresses", json=address_data, headers=headers)
            assert add_response.status_code == 201, f"Should allow address {i+1}/5"
        
        # Try to add 6th address (should fail)
        address_data = {
            "label": "Address6",
            "address": "Address 6",
            "latitude": 33.7,
            "longitude": 73.1
        }
        
        add_response = await client.post("/api/v1/users/addresses", json=address_data, headers=headers)
        assert add_response.status_code == 400, "Should reject 6th address (max 5)"
        
        error_json = add_response.json()
        assert "maximum" in error_json["error"].lower() or "limit" in error_json["error"].lower()


@pytest.mark.asyncio
async def test_duplicate_label_fails():
    """
    Test that duplicate address labels are rejected (case-insensitive).
    
    Expected: 400 Bad Request when trying to add address with duplicate label
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register user
        register_data = {
            "full_name": "Duplicate Label Test",
            "email": f"duplabel_{uuid4()}@example.com",
            "password": "DupLabelPass123",
            "phone": f"+92309{str(uuid4().int)[:7]}",
            "role": "student"
        }
        
        register_response = await client.post("/api/v1/auth/register", json=register_data)
        access_token = register_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Add first address
        address_data = {
            "label": "Home",
            "address": "First Home Address",
            "latitude": 33.6844,
            "longitude": 73.0479
        }
        
        add_response = await client.post("/api/v1/users/addresses", json=address_data, headers=headers)
        assert add_response.status_code == 201
        
        # Try to add address with same label (case-insensitive test)
        duplicate_address = {
            "label": "home",  # Same as "Home" (case-insensitive)
            "address": "Second Home Address",
            "latitude": 33.7,
            "longitude": 73.1
        }
        
        dup_response = await client.post("/api/v1/users/addresses", json=duplicate_address, headers=headers)
        assert dup_response.status_code == 400, "Should reject duplicate label"
        
        error_json = dup_response.json()
        assert "duplicate" in error_json["error"].lower() or "already exists" in error_json["error"].lower()


# ==================== Test JWT Protection ====================

@pytest.mark.asyncio
async def test_unauthorized_access_returns_401():
    """
    Test that protected endpoints return 401 without valid JWT token.
    
    Expected: All /users/* endpoints return 401 without Authorization header
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Try to access GET /users/me without token
        response = await client.get("/api/v1/users/me")
        assert response.status_code in [401, 403], "Should reject request without JWT"
        
        # Try to update profile without token
        update_data = {"gender": "male"}
        response = await client.put("/api/v1/users/me", json=update_data)
        assert response.status_code in [401, 403], "Should reject request without JWT"
        
        # Try to add address without token
        address_data = {
            "label": "Home",
            "address": "Test",
            "latitude": 33.6844,
            "longitude": 73.0479
        }
        response = await client.post("/api/v1/users/addresses", json=address_data)
        assert response.status_code in [401, 403], "Should reject request without JWT"
        
        # Try to get addresses without token
        response = await client.get("/api/v1/users/addresses")
        assert response.status_code in [401, 403], "Should reject request without JWT"


@pytest.mark.asyncio
async def test_invalid_token_returns_401():
    """
    Test that invalid JWT token is rejected.
    
    Expected: 401 Unauthorized for invalid/malformed tokens
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Try with invalid token
        headers = {"Authorization": "Bearer invalid_token_12345"}
        
        response = await client.get("/api/v1/users/me", headers=headers)
        assert response.status_code == 401, "Should reject invalid JWT token"


@pytest.mark.asyncio
async def test_user_can_only_access_own_profile():
    """
    Test that users can only access their own profile data.
    
    Flow:
        1. Register two users
        2. User A adds address
        3. User B tries to access User A's data
        4. Verify User B only sees their own data
    
    Expected: Each user only sees their own profile and addresses
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Register User A
        user_a_data = {
            "full_name": "User A",
            "email": f"usera_{uuid4()}@example.com",
            "password": "UserAPass123",
            "phone": f"+92310{str(uuid4().int)[:7]}",
            "role": "student"
        }
        
        reg_a_response = await client.post("/api/v1/auth/register", json=user_a_data)
        token_a = reg_a_response.json()["data"]["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}
        
        # User A adds address
        address_a = {
            "label": "User A Home",
            "address": "User A Address",
            "latitude": 33.6844,
            "longitude": 73.0479
        }
        await client.post("/api/v1/users/addresses", json=address_a, headers=headers_a)
        
        # Register User B
        user_b_data = {
            "full_name": "User B",
            "email": f"userb_{uuid4()}@example.com",
            "password": "UserBPass123",
            "phone": f"+92311{str(uuid4().int)[:7]}",
            "role": "student"
        }
        
        reg_b_response = await client.post("/api/v1/auth/register", json=user_b_data)
        token_b = reg_b_response.json()["data"]["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}
        
        # User B gets their own addresses (should be empty)
        response_b = await client.get("/api/v1/users/addresses", headers=headers_b)
        addresses_b = response_b.json()["data"]
        
        assert len(addresses_b) == 0, "User B should not see User A's addresses"
        
        # Verify User A still has their address
        response_a = await client.get("/api/v1/users/addresses", headers=headers_a)
        addresses_a = response_a.json()["data"]
        
        assert len(addresses_a) == 1, "User A should see their own address"
        assert addresses_a[0]["label"] == "User A Home"
