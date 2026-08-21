"""
Module: Rides - Test Suite
Purpose: Comprehensive async tests for ride creation, booking, cancellation, and lifecycle management.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 8, 2025
Notes: 30+ tests covering CRUD, API endpoints, business logic, validation, and security.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.modules.auth.models import User, UserRole
from app.modules.drivers.models import DriverProfile
from app.models.vehicle import Vehicle
from app.models.ride import Ride
from app.modules.rides.models import RideBooking, RideStatusEnum, BookingStatusEnum
from app.modules.rides import crud
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
    
    ride = await crud.create_ride(db_session, test_driver_profile.id, ride_data)
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
# CRUD LAYER TESTS
# ============================================

@pytest.mark.asyncio
async def test_create_ride_success(
    db_session: AsyncSession,
    test_driver_profile: DriverProfile,
    test_vehicle: Vehicle
):
    """Test successful ride creation."""
    from app.modules.rides.schemas import RideCreate
    
    ride_data = RideCreate(
        origin="FAST NUCES",
        destination="Mall Road",
        departure_time=datetime.now() + timedelta(hours=3),
        available_seats=4,
        price_per_seat=200.0,
        vehicle_id=test_vehicle.id,
        estimated_duration=45
    )
    
    ride = await crud.create_ride(db_session, test_driver_profile.id, ride_data)
    
    assert ride is not None
    assert ride.origin == "FAST NUCES"
    assert ride.destination == "Mall Road"
    assert ride.available_seats == 4
    assert ride.price_per_seat == 200.0
    assert ride.status == RideStatusEnum.SCHEDULED
    assert ride.total_earnings == 0.0
    assert ride.driver_id == test_driver_profile.id
    assert ride.vehicle_id == test_vehicle.id


@pytest.mark.asyncio
async def test_get_ride_by_id(db_session: AsyncSession, test_ride: Ride):
    """Test fetching ride by ID."""
    ride = await crud.get_ride_by_id(db_session, test_ride.id)
    
    assert ride is not None
    assert ride.id == test_ride.id
    assert ride.origin == test_ride.origin


@pytest.mark.asyncio
async def test_list_available_rides_no_filters(db_session: AsyncSession, test_ride: Ride):
    """Test listing available rides without filters."""
    rides = await crud.list_available_rides(db_session)
    
    assert len(rides) >= 1
    assert any(r.id == test_ride.id for r in rides)


@pytest.mark.asyncio
async def test_list_available_rides_with_origin_filter(db_session: AsyncSession, test_ride: Ride):
    """Test filtering rides by origin."""
    rides = await crud.list_available_rides(db_session, origin="FAST")
    
    assert len(rides) >= 1
    assert all("FAST" in r.origin.upper() for r in rides)


@pytest.mark.asyncio
async def test_list_available_rides_with_destination_filter(db_session: AsyncSession, test_ride: Ride):
    """Test filtering rides by destination."""
    rides = await crud.list_available_rides(db_session, destination="Liberty")
    
    assert len(rides) >= 1
    assert all("LIBERTY" in r.destination.upper() for r in rides)


@pytest.mark.asyncio
async def test_book_ride_success(
    db_session: AsyncSession,
    test_ride: Ride,
    test_passenger: User
):
    """Test successful ride booking."""
    from app.modules.rides.schemas import RideBookingCreate
    
    initial_seats = test_ride.available_seats
    
    booking_data = RideBookingCreate(
        ride_id=test_ride.id,
        booked_seats=2
    )
    
    booking = await crud.book_ride(db_session, test_passenger.id, booking_data)
    await db_session.refresh(test_ride)
    
    assert booking is not None
    assert booking.passenger_id == test_passenger.id
    assert booking.ride_id == test_ride.id
    assert booking.booked_seats == 2
    assert booking.total_price == 2 * test_ride.price_per_seat
    assert booking.status == BookingStatusEnum.BOOKED
    assert test_ride.available_seats == initial_seats - 2


@pytest.mark.asyncio
async def test_book_ride_insufficient_seats(
    db_session: AsyncSession,
    test_ride: Ride,
    test_passenger: User
):
    """Test booking fails when insufficient seats available."""
    from app.modules.rides.schemas import RideBookingCreate
    from fastapi import HTTPException
    
    # Try to book more seats than available
    booking_data = RideBookingCreate(
        ride_id=test_ride.id,
        booked_seats=10
    )
    
    with pytest.raises(HTTPException) as exc_info:
        await crud.book_ride(db_session, test_passenger.id, booking_data)
    
    assert exc_info.value.status_code == 400
    assert "not enough seats" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_cancel_booking_restores_seats(
    db_session: AsyncSession,
    test_ride: Ride,
    test_passenger: User
):
    """Test cancelling booking restores seats to ride."""
    from app.modules.rides.schemas import RideBookingCreate
    
    # Book ride
    booking_data = RideBookingCreate(ride_id=test_ride.id, booked_seats=2)
    booking = await crud.book_ride(db_session, test_passenger.id, booking_data)
    await db_session.refresh(test_ride)
    
    seats_after_booking = test_ride.available_seats
    
    # Cancel booking
    cancelled = await crud.cancel_booking(db_session, booking.id, test_passenger.id, "Change of plans")
    await db_session.refresh(test_ride)
    
    assert cancelled is True
    await db_session.refresh(booking)
    assert booking.status == BookingStatusEnum.CANCELLED
    assert booking.cancellation_reason == "Change of plans"
    assert test_ride.available_seats == seats_after_booking + 2


@pytest.mark.asyncio
async def test_get_user_bookings(
    db_session: AsyncSession,
    test_ride: Ride,
    test_passenger: User
):
    """Test fetching user bookings."""
    from app.modules.rides.schemas import RideBookingCreate
    
    # Create booking
    booking_data = RideBookingCreate(ride_id=test_ride.id, booked_seats=1)
    await crud.book_ride(db_session, test_passenger.id, booking_data)
    
    # Fetch bookings
    bookings = await crud.get_user_bookings(db_session, test_passenger.id)
    
    assert len(bookings) >= 1
    assert any(b.passenger_id == test_passenger.id for b in bookings)


@pytest.mark.asyncio
async def test_get_driver_rides(
    db_session: AsyncSession,
    test_driver_profile: DriverProfile,
    test_ride: Ride
):
    """Test fetching driver's rides."""
    rides = await crud.get_driver_rides(db_session, test_driver_profile.id)
    
    assert len(rides) >= 1
    assert any(r.id == test_ride.id for r in rides)


@pytest.mark.asyncio
async def test_update_ride_status(db_session: AsyncSession, test_ride: Ride):
    """Test updating ride status."""
    updated = await crud.update_ride_status(
        db_session,
        test_ride.id,
        RideStatusEnum.ONGOING
    )
    
    assert updated is True
    await db_session.refresh(test_ride)
    assert test_ride.status == RideStatusEnum.ONGOING


# ============================================
# API ENDPOINT TESTS
# ============================================

@pytest.mark.asyncio
async def test_create_ride_endpoint_success(
    test_driver_user: User,
    test_driver_profile: DriverProfile,
    test_vehicle: Vehicle,
    driver_auth_headers: dict
):
    """Test POST /rides/create endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/rides/create",
            headers=driver_auth_headers,
            json={
                "origin": "DHA Phase 5",
                "destination": "Packages Mall",
                "departure_time": (datetime.now() + timedelta(hours=4)).isoformat(),
                "available_seats": 3,
                "price_per_seat": 180.0,
                "vehicle_id": str(test_vehicle.id),
                "estimated_duration": 25
            }
        )
    
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["origin"] == "DHA Phase 5"
    assert data["data"]["destination"] == "Packages Mall"
    assert data["data"]["status"] == "scheduled"


@pytest.mark.asyncio
async def test_create_ride_unauthorized(test_passenger: User, passenger_auth_headers: dict):
    """Test ride creation fails for non-driver."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/rides/create",
            headers=passenger_auth_headers,
            json={
                "origin": "Location A",
                "destination": "Location B",
                "departure_time": (datetime.now() + timedelta(hours=2)).isoformat(),
                "available_seats": 2,
                "price_per_seat": 100.0,
                "vehicle_id": str(uuid4())
            }
        )
    
    assert response.status_code in [400, 403, 404]


@pytest.mark.asyncio
async def test_list_available_rides_endpoint(test_ride: Ride):
    """Test GET /rides/available endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/rides/available")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert isinstance(data["data"], list)
    assert len(data["data"]) >= 1


@pytest.mark.asyncio
async def test_list_available_rides_with_filters(test_ride: Ride):
    """Test GET /rides/available with query filters."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/rides/available",
            params={"origin": "FAST", "min_seats": 2}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_get_ride_details_endpoint(test_ride: Ride):
    """Test GET /rides/{id} endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/api/v1/rides/{test_ride.id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["id"] == str(test_ride.id)


@pytest.mark.asyncio
async def test_book_ride_endpoint_success(
    test_ride: Ride,
    test_passenger: User,
    passenger_auth_headers: dict
):
    """Test POST /rides/book endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/rides/book",
            headers=passenger_auth_headers,
            json={
                "ride_id": str(test_ride.id),
                "booked_seats": 1
            }
        )
    
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ok"
    assert data["data"]["ride_id"] == str(test_ride.id)
    assert data["data"]["booked_seats"] == 1


@pytest.mark.asyncio
async def test_book_ride_without_auth():
    """Test booking requires authentication."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/rides/book",
            json={"ride_id": str(uuid4()), "booked_seats": 1}
        )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_my_bookings_endpoint(
    test_ride: Ride,
    test_passenger: User,
    passenger_auth_headers: dict,
    db_session: AsyncSession
):
    """Test GET /rides/my/bookings endpoint."""
    from app.modules.rides.schemas import RideBookingCreate
    
    # Create a booking first
    booking_data = RideBookingCreate(ride_id=test_ride.id, booked_seats=1)
    await crud.book_ride(db_session, test_passenger.id, booking_data)
    await db_session.commit()
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/rides/my/bookings",
            headers=passenger_auth_headers
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert len(data["data"]) >= 1


@pytest.mark.asyncio
async def test_cancel_booking_endpoint(
    test_ride: Ride,
    test_passenger: User,
    passenger_auth_headers: dict,
    db_session: AsyncSession
):
    """Test PUT /rides/bookings/{id}/cancel endpoint."""
    from app.modules.rides.schemas import RideBookingCreate
    
    # Create booking
    booking_data = RideBookingCreate(ride_id=test_ride.id, booked_seats=1)
    booking = await crud.book_ride(db_session, test_passenger.id, booking_data)
    await db_session.commit()
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.put(
            f"/api/v1/rides/bookings/{booking.id}/cancel",
            headers=passenger_auth_headers,
            json={"reason": "Emergency came up"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_get_driver_rides_endpoint(
    test_ride: Ride,
    test_driver_user: User,
    driver_auth_headers: dict
):
    """Test GET /rides/my/driver endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/rides/my/driver",
            headers=driver_auth_headers
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert len(data["data"]) >= 1


@pytest.mark.asyncio
async def test_update_ride_status_endpoint(
    test_ride: Ride,
    test_driver_user: User,
    driver_auth_headers: dict
):
    """Test PUT /rides/{id}/status endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.put(
            f"/api/v1/rides/{test_ride.id}/status",
            headers=driver_auth_headers,
            json={"status": "ongoing"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


# ============================================
# VALIDATION TESTS
# ============================================

@pytest.mark.asyncio
async def test_create_ride_invalid_departure_time(
    test_driver_profile: DriverProfile,
    test_vehicle: Vehicle,
    driver_auth_headers: dict
):
    """Test ride creation fails with past departure time."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/rides/create",
            headers=driver_auth_headers,
            json={
                "origin": "Location A",
                "destination": "Location B",
                "departure_time": (datetime.now() - timedelta(hours=1)).isoformat(),
                "available_seats": 3,
                "price_per_seat": 150.0,
                "vehicle_id": str(test_vehicle.id)
            }
        )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_ride_invalid_price(
    test_driver_profile: DriverProfile,
    test_vehicle: Vehicle,
    driver_auth_headers: dict
):
    """Test ride creation fails with invalid price."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/rides/create",
            headers=driver_auth_headers,
            json={
                "origin": "Location A",
                "destination": "Location B",
                "departure_time": (datetime.now() + timedelta(hours=2)).isoformat(),
                "available_seats": 3,
                "price_per_seat": 20.0,  # Below minimum
                "vehicle_id": str(test_vehicle.id)
            }
        )
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_ride_invalid_seats(
    test_driver_profile: DriverProfile,
    test_vehicle: Vehicle,
    driver_auth_headers: dict
):
    """Test ride creation fails with invalid seat count."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/rides/create",
            headers=driver_auth_headers,
            json={
                "origin": "Location A",
                "destination": "Location B",
                "departure_time": (datetime.now() + timedelta(hours=2)).isoformat(),
                "available_seats": 15,  # More than maximum
                "price_per_seat": 150.0,
                "vehicle_id": str(test_vehicle.id)
            }
        )
    
    assert response.status_code == 422


# ============================================
# BUSINESS LOGIC TESTS
# ============================================

@pytest.mark.asyncio
async def test_prevent_double_booking_same_user(
    db_session: AsyncSession,
    test_ride: Ride,
    test_passenger: User
):
    """Test user cannot book same ride twice."""
    from app.modules.rides.schemas import RideBookingCreate
    from fastapi import HTTPException
    
    # First booking
    booking_data = RideBookingCreate(ride_id=test_ride.id, booked_seats=1)
    await crud.book_ride(db_session, test_passenger.id, booking_data)
    
    # Try second booking
    with pytest.raises(HTTPException) as exc_info:
        await crud.book_ride(db_session, test_passenger.id, booking_data)
    
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_ride_status_lifecycle(db_session: AsyncSession, test_ride: Ride):
    """Test ride status transitions."""
    # SCHEDULED → ONGOING
    await crud.update_ride_status(db_session, test_ride.id, RideStatusEnum.ONGOING)
    await db_session.refresh(test_ride)
    assert test_ride.status == RideStatusEnum.ONGOING
    
    # ONGOING → COMPLETED
    await crud.update_ride_status(db_session, test_ride.id, RideStatusEnum.COMPLETED)
    await db_session.refresh(test_ride)
    assert test_ride.status == RideStatusEnum.COMPLETED


@pytest.mark.asyncio
async def test_earnings_tracking(
    db_session: AsyncSession,
    test_ride: Ride,
    test_passenger: User
):
    """Test total_earnings updates on booking."""
    from app.modules.rides.schemas import RideBookingCreate
    
    initial_earnings = test_ride.total_earnings
    
    booking_data = RideBookingCreate(ride_id=test_ride.id, booked_seats=2)
    booking = await crud.book_ride(db_session, test_passenger.id, booking_data)
    
    await db_session.refresh(test_ride)
    
    expected_earnings = initial_earnings + (2 * test_ride.price_per_seat)
    assert test_ride.total_earnings == expected_earnings


@pytest.mark.asyncio
async def test_cannot_book_cancelled_ride(
    db_session: AsyncSession,
    test_ride: Ride,
    test_passenger: User
):
    """Test cannot book a cancelled ride."""
    from app.modules.rides.schemas import RideBookingCreate
    from fastapi import HTTPException
    
    # Cancel the ride
    await crud.update_ride_status(db_session, test_ride.id, RideStatusEnum.CANCELLED)
    
    # Try to book
    booking_data = RideBookingCreate(ride_id=test_ride.id, booked_seats=1)
    
    with pytest.raises(HTTPException) as exc_info:
        await crud.book_ride(db_session, test_passenger.id, booking_data)
    
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_cannot_cancel_ongoing_ride_booking(
    db_session: AsyncSession,
    test_ride: Ride,
    test_passenger: User
):
    """Test cannot cancel booking for ongoing ride."""
    from app.modules.rides.schemas import RideBookingCreate
    from fastapi import HTTPException
    
    # Book ride
    booking_data = RideBookingCreate(ride_id=test_ride.id, booked_seats=1)
    booking = await crud.book_ride(db_session, test_passenger.id, booking_data)
    
    # Start the ride
    await crud.update_ride_status(db_session, test_ride.id, RideStatusEnum.ONGOING)
    
    # Try to cancel
    with pytest.raises(HTTPException) as exc_info:
        await crud.cancel_booking(db_session, booking.id, test_passenger.id)
    
    assert exc_info.value.status_code == 400


# ============================================
# SECURITY TESTS
# ============================================

@pytest.mark.asyncio
async def test_passenger_cannot_cancel_others_booking(
    db_session: AsyncSession,
    test_ride: Ride,
    test_passenger: User,
    test_driver_user: User
):
    """Test passenger can only cancel their own bookings."""
    from app.modules.rides.schemas import RideBookingCreate
    from fastapi import HTTPException
    
    # Passenger books ride
    booking_data = RideBookingCreate(ride_id=test_ride.id, booked_seats=1)
    booking = await crud.book_ride(db_session, test_passenger.id, booking_data)
    
    # Other user tries to cancel
    with pytest.raises(HTTPException) as exc_info:
        await crud.cancel_booking(db_session, booking.id, test_driver_user.id)
    
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_jwt_protection_on_create_ride():
    """Test ride creation requires valid JWT."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/rides/create",
            json={
                "origin": "A",
                "destination": "B",
                "departure_time": (datetime.now() + timedelta(hours=2)).isoformat(),
                "available_seats": 3,
                "price_per_seat": 150.0,
                "vehicle_id": str(uuid4())
            }
        )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_jwt_protection_on_book_ride():
    """Test ride booking requires valid JWT."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/rides/book",
            json={"ride_id": str(uuid4()), "booked_seats": 1}
        )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_invalid_jwt_returns_401():
    """Test invalid JWT returns 401."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/rides/my/bookings",
            headers={"Authorization": "Bearer invalid_token"}
        )
    
    assert response.status_code == 401
