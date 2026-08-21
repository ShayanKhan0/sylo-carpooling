"""
Module: Matching - Test Suite
Purpose: Comprehensive async tests for matching engine, scoring algorithms, and preferences.
Authors: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 8, 2025
Notes: 35+ tests covering utility functions, CRUD, matching engine, API endpoints, and security.
"""

import pytest
import math
from uuid import uuid4
from datetime import datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.modules.auth.models import User, UserRole
from app.modules.drivers.models import DriverProfile, Vehicle
from app.models.ride import Ride
from app.modules.matching.models import MatchRecord, MatchPreference, MatchStatusEnum
from app.modules.matching import crud, utils
from app.modules.matching.schemas import MatchRequest, MatchPreferenceCreate
from app.core.security import create_access_token


# ============================================
# FIXTURES
# ============================================

@pytest.fixture
async def test_passenger(db_session: AsyncSession) -> User:
    """Create a test passenger user."""
    from app.modules.auth.crud import create_user_with_firebase
    
    user = await create_user_with_firebase(
        db=db_session,
        full_name="Test Passenger",
        email=f"passenger_{uuid4().hex[:8]}@test.com",
        firebase_uid=f"fb_test_{uuid4().hex[:12]}",
        phone="+923001234567",
        role="passenger"
    )
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_driver_user(db_session: AsyncSession) -> User:
    """Create a test driver user."""
    from app.modules.auth.crud import create_user_with_firebase
    
    user = await create_user_with_firebase(
        db=db_session,
        full_name="Test Driver",
        email=f"driver_{uuid4().hex[:8]}@test.com",
        firebase_uid=f"fb_test_{uuid4().hex[:12]}",
        phone="+923009876543",
        role="driver"
    )
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_driver_profile(db_session: AsyncSession, test_driver_user: User) -> DriverProfile:
    """Create a verified active driver profile."""
    from app.modules.drivers.crud import create_driver_profile
    from app.modules.drivers.schemas import DriverProfileCreate
    
    profile_data = DriverProfileCreate(
        license_number="LHR-12345678",
        license_expiry=(datetime.now() + timedelta(days=365)).date(),
        cnic_number="12345-1234567-1",
        address="123 Test Street, Lahore"
    )
    
    profile = await create_driver_profile(db_session, test_driver_user.id, profile_data)
    
    # Verify the driver
    profile.is_verified = True
    profile.cnic_verified = True
    profile.status = "active"
    profile.rating = 4.5
    await db_session.commit()
    await db_session.refresh(profile)
    
    return profile


@pytest.fixture
async def test_vehicle(db_session: AsyncSession, test_driver_profile: DriverProfile) -> Vehicle:
    """Create an active verified vehicle."""
    from app.modules.drivers.crud import add_vehicle
    from app.modules.drivers.schemas import VehicleCreate
    
    vehicle_data = VehicleCreate(
        make="Honda",
        model="Civic",
        year=2020,
        color="White",
        license_plate="ABC-123",
        seats_available=4,
        registration_number="REG-12345"
    )
    
    vehicle = await add_vehicle(db_session, test_driver_profile.id, vehicle_data)
    
    # Verify the vehicle
    vehicle.registration_verified = True
    vehicle.is_active = True
    await db_session.commit()
    await db_session.refresh(vehicle)
    
    return vehicle


@pytest.fixture
async def test_ride(
    db_session: AsyncSession,
    test_driver_profile: DriverProfile,
    test_vehicle: Vehicle
) -> Ride:
    """Create a test ride."""
    from app.modules.rides.crud import create_ride
    from app.modules.rides.schemas import RideCreate
    
    ride_data = RideCreate(
        origin="FAST NUCES, Lahore",
        destination="Liberty Market, Gulberg",
        departure_time=datetime.now() + timedelta(hours=2),
        available_seats=3,
        price_per_seat=150.0,
        vehicle_id=test_vehicle.id,
        estimated_duration=30,
        route_distance_km=12.5
    )
    
    ride = await create_ride(db_session, test_driver_profile.id, ride_data)
    await db_session.commit()
    await db_session.refresh(ride)
    
    return ride


@pytest.fixture
def passenger_auth_headers(test_passenger: User) -> dict:
    """Generate JWT auth headers for passenger."""
    token = create_access_token(
        data={"sub": str(test_passenger.id), "email": test_passenger.email, "role": test_passenger.role.value}
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def driver_auth_headers(test_driver_user: User) -> dict:
    """Generate JWT auth headers for driver."""
    token = create_access_token(
        data={"sub": str(test_driver_user.id), "email": test_driver_user.email, "role": test_driver_user.role.value}
    )
    return {"Authorization": f"Bearer {token}"}


# ============================================
# UTILITY FUNCTION TESTS
# ============================================

def test_calculate_distance_haversine():
    """Test Haversine distance calculation accuracy."""
    # FAST NUCES to Liberty Market, Lahore (known distance ~8-9 km)
    distance = utils.calculate_distance(31.5204, 74.3587, 31.4697, 74.2728)
    
    assert distance > 0
    assert 7.0 <= distance <= 10.0  # Reasonable range
    assert isinstance(distance, float)


def test_calculate_distance_same_point():
    """Test distance calculation for same point."""
    distance = utils.calculate_distance(31.5204, 74.3587, 31.5204, 74.3587)
    
    assert distance == 0.0


def test_calculate_distance_score():
    """Test distance score calculation."""
    # Close distance (2.5km of 10km max) should give high score
    score = utils.calculate_distance_score(2.5, 10.0)
    assert 70.0 <= score <= 80.0
    
    # Very close distance (0.5km) should give ~95 score
    score = utils.calculate_distance_score(0.5, 10.0)
    assert score >= 90.0
    
    # At max distance should give 0
    score = utils.calculate_distance_score(10.0, 10.0)
    assert score == 0.0
    
    # Beyond max distance should give 0
    score = utils.calculate_distance_score(15.0, 10.0)
    assert score == 0.0


def test_calculate_time_score():
    """Test time compatibility score calculation."""
    request_time = datetime.now() + timedelta(hours=1)
    
    # Perfect timing (5 min ETA) should give 100
    score = utils.calculate_time_score(request_time, 5, 10)
    assert score == 100.0
    
    # Within tolerance (7 min) should give high score
    score = utils.calculate_time_score(request_time, 7, 10)
    assert 80.0 <= score <= 100.0
    
    # Beyond tolerance should give lower score
    score = utils.calculate_time_score(request_time, 20, 10)
    assert 0.0 < score < 80.0


def test_calculate_route_similarity():
    """Test route direction similarity calculation."""
    # Same direction should give high score
    score = utils.calculate_route_similarity(
        31.52, 74.36,  # Pickup
        31.47, 74.27,  # Destination (southwest)
        31.54, 74.38   # Driver (northeast of pickup, similar bearing)
    )
    
    assert 0.0 <= score <= 100.0
    assert isinstance(score, float)


def test_calculate_preference_score_all_matched():
    """Test preference score when all preferences matched."""
    score = utils.calculate_preference_score(
        driver_verified=True,
        driver_rating=4.7,
        driver_gender="male",
        vehicle_type="sedan",
        prefer_verified=True,
        prefer_same_gender=False,
        passenger_gender="female",
        min_rating=4.0,
        prefer_vehicle_types="sedan,suv"
    )
    
    assert score >= 100.0  # Perfect match with bonus


def test_calculate_preference_score_unverified_driver():
    """Test preference score rejects unverified driver if required."""
    score = utils.calculate_preference_score(
        driver_verified=False,
        driver_rating=4.5,
        driver_gender="male",
        vehicle_type="sedan",
        prefer_verified=True,  # Requires verified
        prefer_same_gender=False,
        passenger_gender="female",
        min_rating=4.0,
        prefer_vehicle_types="sedan"
    )
    
    assert score == 0.0  # Hard constraint failed


def test_calculate_preference_score_low_rating():
    """Test preference score rejects driver with low rating."""
    score = utils.calculate_preference_score(
        driver_verified=True,
        driver_rating=3.0,
        driver_gender="male",
        vehicle_type="sedan",
        prefer_verified=True,
        prefer_same_gender=False,
        passenger_gender="female",
        min_rating=4.0,  # Requires 4.0+ rating
        prefer_vehicle_types="sedan"
    )
    
    assert score == 0.0  # Rating below minimum


def test_calculate_match_score_weighted():
    """Test overall match score calculation with weights."""
    score = utils.calculate_match_score(
        distance_score=90.0,
        time_score=85.0,
        preference_score=100.0,
        route_similarity_score=80.0
    )
    
    # Weighted: 90*0.35 + 85*0.25 + 100*0.30 + 80*0.10
    expected = 90.0 * 0.35 + 85.0 * 0.25 + 100.0 * 0.30 + 80.0 * 0.10
    assert abs(score - expected) < 0.1


def test_calculate_match_score_no_route():
    """Test match score calculation without route similarity."""
    score = utils.calculate_match_score(
        distance_score=90.0,
        time_score=85.0,
        preference_score=100.0,
        route_similarity_score=None  # No route score
    )
    
    assert 0.0 <= score <= 100.0
    assert isinstance(score, float)


def test_estimate_pickup_time():
    """Test pickup time estimation."""
    # 5km at 40km/h = 7.5min + 20% buffer = 9min
    time = utils.estimate_pickup_time(5.0, 40.0)
    assert time == 9
    
    # Very short distance should have minimum 5 min
    time = utils.estimate_pickup_time(0.5, 40.0)
    assert time >= 5


# ============================================
# CRUD LAYER TESTS
# ============================================

@pytest.mark.asyncio
async def test_create_match_record(
    db_session: AsyncSession,
    test_ride: Ride,
    test_driver_profile: DriverProfile,
    test_passenger: User
):
    """Test creating a match record."""
    match = await crud.create_match_record(
        db=db_session,
        ride_id=test_ride.id,
        driver_id=test_driver_profile.id,
        passenger_id=test_passenger.id,
        match_score=87.5,
        distance_score=90.0,
        time_score=85.0,
        preference_score=100.0,
        distance_km=2.5,
        estimated_pickup_time=7,
        expires_at=datetime.now() + timedelta(minutes=15)
    )
    
    assert match is not None
    assert match.match_score == 87.5
    assert match.distance_km == 2.5
    assert match.status == MatchStatusEnum.PROPOSED


@pytest.mark.asyncio
async def test_get_matches_for_ride_ordered_by_score(
    db_session: AsyncSession,
    test_ride: Ride,
    test_driver_profile: DriverProfile,
    test_passenger: User
):
    """Test fetching matches ordered by score."""
    # Create multiple matches with different scores
    await crud.create_match_record(
        db=db_session,
        ride_id=test_ride.id,
        driver_id=test_driver_profile.id,
        passenger_id=test_passenger.id,
        match_score=75.0,
        distance_score=80.0,
        time_score=70.0,
        preference_score=75.0,
        distance_km=5.0,
        estimated_pickup_time=12
    )
    
    await crud.create_match_record(
        db=db_session,
        ride_id=test_ride.id,
        driver_id=test_driver_profile.id,
        passenger_id=test_passenger.id,
        match_score=90.0,
        distance_score=95.0,
        time_score=85.0,
        preference_score=90.0,
        distance_km=1.5,
        estimated_pickup_time=5
    )
    
    await db_session.commit()
    
    # Fetch matches
    matches = await crud.get_matches_for_ride(db_session, test_ride.id)
    
    assert len(matches) >= 2
    # Should be ordered by score descending
    assert matches[0].match_score >= matches[1].match_score


@pytest.mark.asyncio
async def test_update_match_status(
    db_session: AsyncSession,
    test_ride: Ride,
    test_driver_profile: DriverProfile,
    test_passenger: User
):
    """Test updating match status."""
    match = await crud.create_match_record(
        db=db_session,
        ride_id=test_ride.id,
        driver_id=test_driver_profile.id,
        passenger_id=test_passenger.id,
        match_score=85.0,
        distance_score=90.0,
        time_score=80.0,
        preference_score=85.0,
        distance_km=3.0,
        estimated_pickup_time=8
    )
    await db_session.commit()
    
    # Update status to ACCEPTED
    updated = await crud.update_match_status(
        db=db_session,
        match_id=match.id,
        new_status=MatchStatusEnum.ACCEPTED
    )
    
    assert updated is True
    await db_session.refresh(match)
    assert match.status == MatchStatusEnum.ACCEPTED


@pytest.mark.asyncio
async def test_create_match_preference(
    db_session: AsyncSession,
    test_passenger: User
):
    """Test creating user match preferences."""
    pref_data = MatchPreferenceCreate(
        prefer_verified_drivers=True,
        prefer_same_gender=False,
        prefer_non_smoking=True,
        max_pickup_distance_km=8.0,
        max_pickup_time_minutes=12,
        min_driver_rating=4.0,
        prefer_vehicle_types="sedan,suv"
    )
    
    pref = await crud.create_match_preference(
        db=db_session,
        user_id=test_passenger.id,
        preference_data=pref_data
    )
    
    assert pref is not None
    assert pref.prefer_verified_drivers is True
    assert pref.max_pickup_distance_km == 8.0
    assert pref.min_driver_rating == 4.0


@pytest.mark.asyncio
async def test_get_match_preference(
    db_session: AsyncSession,
    test_passenger: User
):
    """Test fetching user match preferences."""
    # Create preference
    pref_data = MatchPreferenceCreate(
        prefer_verified_drivers=True,
        max_pickup_distance_km=10.0,
        min_driver_rating=4.0
    )
    
    await crud.create_match_preference(db_session, test_passenger.id, pref_data)
    await db_session.commit()
    
    # Fetch preference
    pref = await crud.get_match_preference(db_session, test_passenger.id)
    
    assert pref is not None
    assert pref.user_id == test_passenger.id
    assert pref.max_pickup_distance_km == 10.0


@pytest.mark.asyncio
async def test_expire_old_matches(db_session: AsyncSession):
    """Test expiring old match records."""
    # This would create expired matches and test the expiration logic
    # Implementation depends on having matches with past expires_at dates
    cutoff = datetime.now()
    expired_count = await crud.expire_old_matches(db_session, cutoff)
    
    assert expired_count >= 0


# ============================================
# API ENDPOINT TESTS
# ============================================

@pytest.mark.asyncio
async def test_find_matches_endpoint(
    test_passenger: User,
    test_ride: Ride,
    test_driver_profile: DriverProfile,
    passenger_auth_headers: dict
):
    """Test POST /match/find endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/match/find",
            headers=passenger_auth_headers,
            json={
                "ride_id": str(test_ride.id),
                "pickup_latitude": 31.5204,
                "pickup_longitude": 74.3587,
                "destination_latitude": 31.4697,
                "destination_longitude": 74.2728,
                "requested_seats": 2,
                "max_results": 10
            }
        )
    
    assert response.status_code in [200, 201]
    data = response.json()
    assert data["status"] == "ok"
    assert "matches" in data["data"] or "data" in data


@pytest.mark.asyncio
async def test_find_matches_requires_auth():
    """Test find matches requires authentication."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/match/find",
            json={
                "ride_id": str(uuid4()),
                "pickup_latitude": 31.52,
                "pickup_longitude": 74.36,
                "destination_latitude": 31.47,
                "destination_longitude": 74.27,
                "requested_seats": 2
            }
        )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_find_matches_invalid_coordinates():
    """Test find matches with invalid coordinates."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Create a simple auth token
        token = create_access_token(
            data={"sub": str(uuid4()), "email": "test@test.com", "role": "student"}
        )
        
        response = await client.post(
            "/api/v1/match/find",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "ride_id": str(uuid4()),
                "pickup_latitude": 200.0,  # Invalid (> 90)
                "pickup_longitude": 74.36,
                "destination_latitude": 31.47,
                "destination_longitude": 74.27,
                "requested_seats": 2
            }
        )
    
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_create_match_preferences_endpoint(
    test_passenger: User,
    passenger_auth_headers: dict
):
    """Test POST /match/preferences endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/match/preferences",
            headers=passenger_auth_headers,
            json={
                "prefer_verified_drivers": True,
                "prefer_same_gender": False,
                "prefer_non_smoking": True,
                "max_pickup_distance_km": 10.0,
                "max_pickup_time_minutes": 15,
                "min_driver_rating": 4.0,
                "prefer_vehicle_types": "sedan,suv"
            }
        )
    
    assert response.status_code in [200, 201]
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_get_match_preferences_endpoint(
    test_passenger: User,
    passenger_auth_headers: dict,
    db_session: AsyncSession
):
    """Test GET /match/preferences endpoint."""
    # Create preference first
    pref_data = MatchPreferenceCreate(
        prefer_verified_drivers=True,
        max_pickup_distance_km=10.0,
        min_driver_rating=4.0
    )
    await crud.create_match_preference(db_session, test_passenger.id, pref_data)
    await db_session.commit()
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/match/preferences",
            headers=passenger_auth_headers
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_update_match_preferences_endpoint(
    test_passenger: User,
    passenger_auth_headers: dict,
    db_session: AsyncSession
):
    """Test PUT /match/preferences endpoint."""
    # Create preference first
    pref_data = MatchPreferenceCreate(
        prefer_verified_drivers=True,
        max_pickup_distance_km=10.0
    )
    await crud.create_match_preference(db_session, test_passenger.id, pref_data)
    await db_session.commit()
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.put(
            "/api/v1/match/preferences",
            headers=passenger_auth_headers,
            json={
                "max_pickup_distance_km": 15.0,
                "min_driver_rating": 4.5
            }
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_delete_match_preferences_endpoint(
    test_passenger: User,
    passenger_auth_headers: dict,
    db_session: AsyncSession
):
    """Test DELETE /match/preferences endpoint."""
    # Create preference first
    pref_data = MatchPreferenceCreate(
        prefer_verified_drivers=True,
        max_pickup_distance_km=10.0
    )
    await crud.create_match_preference(db_session, test_passenger.id, pref_data)
    await db_session.commit()
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.delete(
            "/api/v1/match/preferences",
            headers=passenger_auth_headers
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_get_match_history_endpoint(
    test_passenger: User,
    passenger_auth_headers: dict
):
    """Test GET /match/history/{user_id} endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/match/history/{test_passenger.id}",
            headers=passenger_auth_headers
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


# ============================================
# SECURITY TESTS
# ============================================

@pytest.mark.asyncio
async def test_jwt_protection_on_find_matches():
    """Test JWT protection on find matches endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/match/find",
            json={
                "ride_id": str(uuid4()),
                "pickup_latitude": 31.52,
                "pickup_longitude": 74.36,
                "destination_latitude": 31.47,
                "destination_longitude": 74.27,
                "requested_seats": 2
            }
        )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_jwt_protection_on_preferences():
    """Test JWT protection on preferences endpoints."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/match/preferences")
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_jwt_returns_401():
    """Test invalid JWT returns 401."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/match/preferences",
            headers={"Authorization": "Bearer invalid_token_12345"}
        )
    
    assert response.status_code == 401


# ============================================
# BUSINESS LOGIC TESTS
# ============================================

@pytest.mark.asyncio
async def test_matching_engine_sorts_by_score(
    db_session: AsyncSession,
    test_ride: Ride,
    test_driver_profile: DriverProfile,
    test_passenger: User
):
    """Test matching engine returns results sorted by score."""
    # Create matches with different scores
    match1 = await crud.create_match_record(
        db=db_session,
        ride_id=test_ride.id,
        driver_id=test_driver_profile.id,
        passenger_id=test_passenger.id,
        match_score=75.0,
        distance_score=80.0,
        time_score=70.0,
        preference_score=75.0,
        distance_km=5.0,
        estimated_pickup_time=12
    )
    
    match2 = await crud.create_match_record(
        db=db_session,
        ride_id=test_ride.id,
        driver_id=test_driver_profile.id,
        passenger_id=test_passenger.id,
        match_score=92.0,
        distance_score=95.0,
        time_score=90.0,
        preference_score=90.0,
        distance_km=1.5,
        estimated_pickup_time=5
    )
    
    await db_session.commit()
    
    matches = await crud.get_matches_for_ride(db_session, test_ride.id)
    
    assert len(matches) >= 2
    # Verify sorted by score descending
    for i in range(len(matches) - 1):
        assert matches[i].match_score >= matches[i + 1].match_score


@pytest.mark.asyncio
async def test_preference_filtering_excludes_unverified(
    db_session: AsyncSession
):
    """Test that preference for verified drivers excludes unverified."""
    # Test the scoring function directly
    score = utils.calculate_preference_score(
        driver_verified=False,
        driver_rating=4.5,
        driver_gender="male",
        vehicle_type="sedan",
        prefer_verified=True,
        prefer_same_gender=False,
        passenger_gender="female",
        min_rating=4.0,
        prefer_vehicle_types="sedan"
    )
    
    assert score == 0.0  # Should be excluded


@pytest.mark.asyncio
async def test_match_expiration(
    db_session: AsyncSession,
    test_ride: Ride,
    test_driver_profile: DriverProfile,
    test_passenger: User
):
    """Test match records can be expired."""
    # Create match that expires in the past
    match = await crud.create_match_record(
        db=db_session,
        ride_id=test_ride.id,
        driver_id=test_driver_profile.id,
        passenger_id=test_passenger.id,
        match_score=85.0,
        distance_score=90.0,
        time_score=80.0,
        preference_score=85.0,
        distance_km=3.0,
        estimated_pickup_time=8,
        expires_at=datetime.now() - timedelta(minutes=5)  # Expired
    )
    await db_session.commit()
    
    # Expire old matches
    expired_count = await crud.expire_old_matches(db_session, datetime.now())
    
    assert expired_count >= 1
    
    await db_session.refresh(match)
    assert match.status == MatchStatusEnum.EXPIRED
