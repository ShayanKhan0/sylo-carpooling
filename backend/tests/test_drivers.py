"""
Module: Driver Module Tests
Purpose: Comprehensive test suite for driver registration, vehicle CRUD, and role-based access.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: Uses pytest-asyncio for async database operations and FastAPI TestClient.
"""

import pytest
from uuid import uuid4
from datetime import date
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.modules.drivers.models import DriverProfile, Vehicle
from app.modules.drivers.schemas import DriverProfileCreate, VehicleCreate
from app.modules.drivers import crud


# ============================================
# FIXTURES
# ============================================

@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user for driver tests."""
    from app.modules.auth.models import User
    from app.core.security import get_password_hash
    
    user = User(
        email="driver@test.com",
        username="testdriver",
        hashed_password=get_password_hash("testpass123"),
        full_name="Test Driver",
        phone_number="+923001234567",
        role="user"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_driver_profile(db_session: AsyncSession, test_user):
    """Create a test driver profile."""
    driver_data = DriverProfileCreate(
        license_number="DL-TEST-2025",
        license_expiry=date(2026, 12, 31),
        cnic_number="12345-1234567-1",
        address="Test Address, Lahore"
    )
    
    driver = await crud.create_driver_profile(db_session, test_user.id, driver_data)
    return driver


@pytest.fixture
async def test_vehicle(db_session: AsyncSession, test_driver_profile):
    """Create a test vehicle."""
    vehicle_data = VehicleCreate(
        make="Toyota",
        model="Corolla",
        year=2020,
        color="White",
        license_plate="ABC-123",
        seats_available=4,
        registration_number="REG-2020-TOY-001"
    )
    
    vehicle = await crud.add_vehicle(db_session, test_driver_profile.id, vehicle_data)
    return vehicle


@pytest.fixture
async def auth_headers(test_user):
    """Generate JWT auth headers for test user."""
    from app.modules.auth.service import create_access_token
    
    access_token = create_access_token(data={"sub": test_user.email})
    return {"Authorization": f"Bearer {access_token}"}


# ============================================
# CRUD LAYER TESTS
# ============================================

@pytest.mark.asyncio
async def test_create_driver_profile(db_session: AsyncSession, test_user):
    """Test creating a new driver profile."""
    driver_data = DriverProfileCreate(
        license_number="DL-NEW-2025",
        license_expiry=date(2027, 12, 31),
        cnic_number="54321-7654321-1",
        address="New Driver Address"
    )
    
    driver = await crud.create_driver_profile(db_session, test_user.id, driver_data)
    
    assert driver.user_id == test_user.id
    assert driver.license_number == "DL-NEW-2025"
    assert driver.cnic_number == "54321-7654321-1"
    assert driver.status == "pending"
    assert driver.is_verified is False
    assert driver.rating == 5.0
    assert driver.total_rides == 0
    assert driver.total_earnings == 0.0


@pytest.mark.asyncio
async def test_create_duplicate_driver_profile(db_session: AsyncSession, test_driver_profile, test_user):
    """Test that creating duplicate driver profile raises error."""
    driver_data = DriverProfileCreate(
        license_number="DL-DUP-2025",
        cnic_number="99999-9999999-9",
        address="Duplicate Test"
    )
    
    with pytest.raises(Exception):  # Should raise HTTPException 400
        await crud.create_driver_profile(db_session, test_user.id, driver_data)


@pytest.mark.asyncio
async def test_get_driver_profile(db_session: AsyncSession, test_driver_profile, test_user):
    """Test retrieving driver profile by user_id."""
    driver = await crud.get_driver_profile(db_session, test_user.id)
    
    assert driver is not None
    assert driver.id == test_driver_profile.id
    assert driver.user_id == test_user.id


@pytest.mark.asyncio
async def test_get_nonexistent_driver_profile(db_session: AsyncSession):
    """Test retrieving non-existent driver profile returns None."""
    driver = await crud.get_driver_profile(db_session, uuid4())
    assert driver is None


@pytest.mark.asyncio
async def test_update_driver_status(db_session: AsyncSession, test_driver_profile):
    """Test updating driver status."""
    updated = await crud.update_driver_status(db_session, test_driver_profile.id, "active")
    
    assert updated.status == "active"
    assert updated.id == test_driver_profile.id


@pytest.mark.asyncio
async def test_update_driver_verification(db_session: AsyncSession, test_driver_profile):
    """Test updating driver verification status."""
    updated = await crud.update_driver_verification(
        db_session, 
        test_driver_profile.id, 
        is_verified=True, 
        cnic_verified=True
    )
    
    assert updated.is_verified is True
    assert updated.cnic_verified is True
    assert updated.status == "active"  # Auto-activated when verified


# ============================================
# VEHICLE CRUD TESTS
# ============================================

@pytest.mark.asyncio
async def test_add_vehicle(db_session: AsyncSession, test_driver_profile):
    """Test adding a vehicle to driver profile."""
    vehicle_data = VehicleCreate(
        make="Honda",
        model="Civic",
        year=2019,
        color="Black",
        license_plate="XYZ-789",
        seats_available=4,
        registration_number="REG-2019-HON-001"
    )
    
    vehicle = await crud.add_vehicle(db_session, test_driver_profile.id, vehicle_data)
    
    assert vehicle.driver_id == test_driver_profile.id
    assert vehicle.make == "Honda"
    assert vehicle.model == "Civic"
    assert vehicle.license_plate == "XYZ-789"
    assert vehicle.is_active is True
    assert vehicle.registration_verified is False


@pytest.mark.asyncio
async def test_add_vehicle_duplicate_license_plate(db_session: AsyncSession, test_driver_profile, test_vehicle):
    """Test adding vehicle with duplicate license plate raises error."""
    vehicle_data = VehicleCreate(
        make="Suzuki",
        model="Cultus",
        year=2021,
        color="Red",
        license_plate="ABC-123",  # Duplicate
        seats_available=4,
        registration_number="REG-2021-SUZ-001"
    )
    
    with pytest.raises(Exception):  # Should raise HTTPException 400
        await crud.add_vehicle(db_session, test_driver_profile.id, vehicle_data)


@pytest.mark.asyncio
async def test_get_driver_vehicles(db_session: AsyncSession, test_driver_profile, test_vehicle):
    """Test retrieving all vehicles for a driver."""
    vehicles = await crud.get_driver_vehicles(db_session, test_driver_profile.id)
    
    assert len(vehicles) >= 1
    assert any(v.id == test_vehicle.id for v in vehicles)


@pytest.mark.asyncio
async def test_remove_vehicle(db_session: AsyncSession, test_driver_profile, test_vehicle):
    """Test deleting a vehicle."""
    result = await crud.remove_vehicle(db_session, test_driver_profile.id, test_vehicle.id)
    
    assert result is True
    
    # Verify vehicle is deleted
    vehicle = await crud.get_vehicle_by_id(db_session, test_vehicle.id)
    assert vehicle is None


@pytest.mark.asyncio
async def test_remove_vehicle_unauthorized(db_session: AsyncSession, test_vehicle):
    """Test that removing another driver's vehicle raises error."""
    wrong_driver_id = uuid4()
    
    with pytest.raises(Exception):  # Should raise HTTPException 404
        await crud.remove_vehicle(db_session, wrong_driver_id, test_vehicle.id)


@pytest.mark.asyncio
async def test_count_active_vehicles(db_session: AsyncSession, test_driver_profile, test_vehicle):
    """Test counting active vehicles."""
    count = await crud.count_active_vehicles(db_session, test_driver_profile.id)
    
    assert count >= 1


# ============================================
# API ENDPOINT TESTS
# ============================================

@pytest.mark.asyncio
async def test_register_driver_endpoint(auth_headers):
    """Test POST /drivers/register endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/drivers/register",
            headers=auth_headers,
            json={
                "license_number": "DL-API-2025",
                "license_expiry": "2026-12-31",
                "cnic_number": "11111-1111111-1",
                "address": "API Test Address"
            }
        )
    
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["license_number"] == "DL-API-2025"
    assert data["data"]["is_verified"] is False
    assert data["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_get_driver_profile_endpoint(auth_headers):
    """Test GET /drivers/me endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/drivers/me",
            headers=auth_headers
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "profile" in data["data"]
    assert "is_ride_eligible" in data["data"]


@pytest.mark.asyncio
async def test_get_driver_profile_not_registered():
    """Test GET /drivers/me returns 404 if not registered as driver."""
    # Create new user who is not a driver
    async with AsyncClient(app=app, base_url="http://test") as client:
        # First register new user
        reg_response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "notdriver@test.com",
                "username": "notdriver",
                "password": "testpass123",
                "full_name": "Not A Driver",
                "phone_number": "+923009876543"
            }
        )
        
        # Login
        login_response = await client.post(
            "/api/v1/auth/login",
            data={
                "username": "notdriver@test.com",
                "password": "testpass123"
            }
        )
        
        token = login_response.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try to get driver profile
        response = await client.get(
            "/api/v1/drivers/me",
            headers=headers
        )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_vehicle_endpoint(auth_headers):
    """Test POST /drivers/vehicles endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/drivers/vehicles",
            headers=auth_headers,
            json={
                "make": "Toyota",
                "model": "Corolla",
                "year": 2020,
                "color": "White",
                "license_plate": "API-001",
                "seats_available": 4,
                "registration_number": "REG-API-001"
            }
        )
    
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["make"] == "Toyota"
    assert data["data"]["is_active"] is True


@pytest.mark.asyncio
async def test_get_vehicles_endpoint(auth_headers):
    """Test GET /drivers/vehicles endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/drivers/vehicles",
            headers=auth_headers
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_update_vehicle_endpoint(auth_headers, test_vehicle):
    """Test PUT /drivers/vehicles/{id} endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.put(
            f"/api/v1/drivers/vehicles/{test_vehicle.id}",
            headers=auth_headers,
            json={
                "color": "Black",
                "seats_available": 3
            }
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["color"] == "Black"
    assert data["data"]["seats_available"] == 3


@pytest.mark.asyncio
async def test_delete_vehicle_endpoint(auth_headers, test_vehicle):
    """Test DELETE /drivers/vehicles/{id} endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.delete(
            f"/api/v1/drivers/vehicles/{test_vehicle.id}",
            headers=auth_headers
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "message" in data["data"]
    assert data["data"]["message"] == "Vehicle removed successfully"


@pytest.mark.asyncio
async def test_get_driver_stats_endpoint(auth_headers):
    """Test GET /drivers/stats endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/drivers/stats",
            headers=auth_headers
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "rating" in data["data"]
    assert "total_rides" in data["data"]
    assert "total_earnings" in data["data"]
    assert "is_ride_eligible" in data["data"]


@pytest.mark.asyncio
async def test_update_driver_status_endpoint(auth_headers):
    """Test PUT /drivers/status endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.put(
            "/api/v1/drivers/status",
            headers=auth_headers,
            json={"status": "inactive"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["status"] == "inactive"


@pytest.mark.asyncio
async def test_unauthorized_access():
    """Test that endpoints require authentication."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/drivers/me")
    
    assert response.status_code == 401


# ============================================
# SCHEMA VALIDATION TESTS
# ============================================

def test_vehicle_create_schema_validation():
    """Test VehicleCreate schema validation."""
    from app.modules.drivers.schemas import VehicleCreate
    
    # Valid data
    valid_vehicle = VehicleCreate(
        make="Toyota",
        model="Corolla",
        year=2020,
        color="White",
        license_plate="ABC-123",
        seats_available=4,
        registration_number="REG-2020-001"
    )
    assert valid_vehicle.license_plate == "ABC-123"
    
    # Invalid year (too old)
    with pytest.raises(Exception):
        VehicleCreate(
            make="Toyota",
            model="Corolla",
            year=1985,  # Too old
            color="White",
            license_plate="ABC-123",
            seats_available=4,
            registration_number="REG-1985-001"
        )
    
    # Invalid seats
    with pytest.raises(Exception):
        VehicleCreate(
            make="Toyota",
            model="Corolla",
            year=2020,
            color="White",
            license_plate="ABC-123",
            seats_available=10,  # Too many
            registration_number="REG-2020-001"
        )


def test_driver_profile_create_schema_validation():
    """Test DriverProfileCreate schema validation."""
    from app.modules.drivers.schemas import DriverProfileCreate
    
    # Valid data
    valid_driver = DriverProfileCreate(
        license_number="DL-12345-2025",
        cnic_number="12345-1234567-1",
        address="Test Address"
    )
    assert valid_driver.cnic_number == "12345-1234567-1"
    
    # Invalid CNIC format
    with pytest.raises(Exception):
        DriverProfileCreate(
            license_number="DL-12345-2025",
            cnic_number="invalid-cnic",
            address="Test Address"
        )


# ============================================
# BUSINESS LOGIC TESTS
# ============================================

@pytest.mark.asyncio
async def test_vehicle_limit_enforcement(db_session: AsyncSession, test_driver_profile):
    """Test that drivers cannot exceed 3 active vehicles."""
    from app.modules.drivers.service import add_vehicle_service
    
    # Add 3 vehicles (assuming none exist yet)
    for i in range(3):
        vehicle_data = VehicleCreate(
            make="Test",
            model=f"Model{i}",
            year=2020,
            color="White",
            license_plate=f"TEST-{i}",
            seats_available=4,
            registration_number=f"REG-TEST-{i}"
        )
        await crud.add_vehicle(db_session, test_driver_profile.id, vehicle_data)
    
    # Try to add 4th vehicle
    vehicle_data = VehicleCreate(
        make="Test",
        model="Model4",
        year=2020,
        color="White",
        license_plate="TEST-4",
        seats_available=4,
        registration_number="REG-TEST-4"
    )
    
    # Should raise exception due to limit
    with pytest.raises(Exception):
        await crud.add_vehicle(db_session, test_driver_profile.id, vehicle_data)


@pytest.mark.asyncio
async def test_ride_eligibility_logic(db_session: AsyncSession, test_driver_profile, test_vehicle):
    """Test ride eligibility calculation."""
    from app.modules.drivers.service import _is_ride_eligible
    
    # Initially not eligible (not verified)
    await db_session.refresh(test_driver_profile, ["vehicles"])
    assert _is_ride_eligible(test_driver_profile) is False
    
    # Verify driver and vehicle
    await crud.update_driver_verification(db_session, test_driver_profile.id, True, True)
    test_vehicle.registration_verified = True
    await db_session.commit()
    
    await db_session.refresh(test_driver_profile, ["vehicles"])
    assert _is_ride_eligible(test_driver_profile) is True
    
    # Suspend driver
    await crud.update_driver_status(db_session, test_driver_profile.id, "suspended")
    await db_session.refresh(test_driver_profile, ["vehicles"])
    assert _is_ride_eligible(test_driver_profile) is False
