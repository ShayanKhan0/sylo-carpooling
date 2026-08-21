"""
Module: Rides & Scheduling - Comprehensive Tests (Prompt 5)
Purpose: Test atomic booking, geo-radius search, recurring schedules, and race conditions
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: December 8, 2025
Notes: 20+ tests covering all Prompt 5 requirements including concurrency testing
"""

import pytest
import asyncio
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.models.ride import Ride, RideStatus
from app.models.booking import Booking, BookingStatus
from app.models.recurring_schedule import RecurringSchedule
from app.modules.auth.models import User
from app.modules.rides import crud_v2, service_v2
from app.modules.rides.schemas_v2 import (
    RideCreateV2,
    RideSearchRequest,
    BookingRequest,
    ScheduleCreate,
    GeoPoint
)
from app.core.exceptions import NotFoundError, ConflictError, ValidationError


# ============================================
# FIXTURES
# ============================================

@pytest.fixture
async def db_session():
    """Create test database session."""
    engine = create_async_engine(
        "postgresql+asyncpg://test:test@localhost/test_db",
        echo=False
    )
    
    async_session_maker = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session
    
    await engine.dispose()


@pytest.fixture
async def test_driver(db_session):
    """Create test driver user."""
    user = User(
        id=uuid4(),
        email="driver@test.com",
        hashed_password="hashed",
        role="driver"
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def test_passenger(db_session):
    """Create test passenger user."""
    user = User(
        id=uuid4(),
        email="passenger@test.com",
        hashed_password="hashed",
        role="passenger"
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.fixture
async def test_ride(db_session, test_driver):
    """Create test ride."""
    ride = await crud_v2.create_ride(
        db=db_session,
        driver_id=test_driver.id,
        start_point_lat=31.4697,
        start_point_lng=74.2728,
        start_point_address="FAST NUCES, Lahore",
        end_point_lat=31.5204,
        end_point_lng=74.3587,
        end_point_address="Liberty Market, Gulberg",
        start_time=datetime.now() + timedelta(hours=2),
        seats_offered=4,
        base_price=Decimal("150.00"),
        buffer_seats=1
    )
    return ride


# ============================================
# TEST 1-3: RIDE CREATION
# ============================================

@pytest.mark.asyncio
async def test_create_ride_with_buffer_seats(db_session, test_driver):
    """Test creating ride with buffer seats."""
    ride = await crud_v2.create_ride(
        db=db_session,
        driver_id=test_driver.id,
        start_point_lat=31.4697,
        start_point_lng=74.2728,
        start_point_address="FAST NUCES",
        end_point_lat=31.5204,
        end_point_lng=74.3587,
        end_point_address="Liberty Market",
        start_time=datetime.now() + timedelta(hours=1),
        seats_offered=4,
        base_price=Decimal("150.00"),
        buffer_seats=1,
        polyline_main="u~o{Aq~{rMoB_@..."
    )
    
    assert ride.id is not None
    assert ride.seats_offered == 4
    assert ride.buffer_seats == 1
    assert ride.seats_booked == 0
    assert ride.polyline_main == "u~o{Aq~{rMoB_@..."
    assert ride.status == RideStatus.OPEN


@pytest.mark.asyncio
async def test_create_ride_with_polyline_alternates(db_session, test_driver):
    """Test creating ride with multiple route options."""
    ride = await crud_v2.create_ride(
        db=db_session,
        driver_id=test_driver.id,
        start_point_lat=31.4697,
        start_point_lng=74.2728,
        start_point_address="FAST NUCES",
        end_point_lat=31.5204,
        end_point_lng=74.3587,
        end_point_address="Liberty Market",
        start_time=datetime.now() + timedelta(hours=1),
        seats_offered=4,
        base_price=Decimal("150.00"),
        polyline_main="main_route...",
        polyline_alternates={
            "route_1": "alt_route_1...",
            "route_2": "alt_route_2..."
        }
    )
    
    assert ride.polyline_alternates is not None
    assert "route_1" in ride.polyline_alternates
    assert "route_2" in ride.polyline_alternates


@pytest.mark.asyncio
async def test_update_ride_fields(db_session, test_ride, test_driver):
    """Test updating ride fields."""
    updated_ride = await crud_v2.update_ride(
        db=db_session,
        ride_id=test_ride.id,
        seats_offered=5,
        buffer_seats=2,
        base_price=Decimal("200.00")
    )
    
    assert updated_ride.seats_offered == 5
    assert updated_ride.buffer_seats == 2
    assert updated_ride.base_price == Decimal("200.00")


# ============================================
# TEST 4-8: ATOMIC BOOKING (PROMPT 5 CORE)
# ============================================

@pytest.mark.asyncio
async def test_atomic_booking_success(db_session, test_ride, test_passenger):
    """Test successful atomic booking."""
    booking = await crud_v2.book_seat_atomic(
        db=db_session,
        ride_id=test_ride.id,
        passenger_id=test_passenger.id,
        seats_reserved=2
    )
    
    assert booking.id is not None
    assert booking.seats_reserved == 2
    assert booking.status == BookingStatus.RESERVED
    assert booking.version == 0
    
    # Verify ride seats updated
    await db_session.refresh(test_ride)
    assert test_ride.seats_booked == 2


@pytest.mark.asyncio
async def test_atomic_booking_respects_buffer_seats(db_session, test_ride, test_passenger):
    """Test that booking respects buffer seats."""
    # Ride has 4 seats offered, 1 buffer = 3 available
    # Try to book all 4 (should fail)
    with pytest.raises(ConflictError, match="Not enough seats available"):
        await crud_v2.book_seat_atomic(
            db=db_session,
            ride_id=test_ride.id,
            passenger_id=test_passenger.id,
            seats_reserved=4  # Exceeds available (3)
        )


@pytest.mark.asyncio
async def test_atomic_booking_prevents_duplicate(db_session, test_ride, test_passenger):
    """Test that passenger can't book same ride twice."""
    # First booking
    await crud_v2.book_seat_atomic(
        db=db_session,
        ride_id=test_ride.id,
        passenger_id=test_passenger.id,
        seats_reserved=1
    )
    
    # Second booking (should fail)
    with pytest.raises(ValidationError, match="already have a booking"):
        await crud_v2.book_seat_atomic(
            db=db_session,
            ride_id=test_ride.id,
            passenger_id=test_passenger.id,
            seats_reserved=1
        )


@pytest.mark.asyncio
async def test_atomic_booking_race_condition(db_session, test_ride):
    """Test atomic booking prevents race conditions (concurrent bookings)."""
    # Create 3 passengers
    passengers = []
    for i in range(3):
        passenger = User(
            id=uuid4(),
            email=f"passenger{i}@test.com",
            hashed_password="hashed",
            role="passenger"
        )
        db_session.add(passenger)
        passengers.append(passenger)
    await db_session.commit()
    
    # Ride has 4 seats, 1 buffer = 3 available
    # 3 passengers try to book 2 seats each concurrently (6 seats total)
    # Only first 1-2 should succeed
    
    async def try_book(passenger_id):
        try:
            booking = await crud_v2.book_seat_atomic(
                db=db_session,
                ride_id=test_ride.id,
                passenger_id=passenger_id,
                seats_reserved=2
            )
            return ("success", booking)
        except ConflictError as e:
            return ("conflict", str(e))
    
    # Execute bookings concurrently
    results = await asyncio.gather(
        *[try_book(p.id) for p in passengers],
        return_exceptions=True
    )
    
    # Count successes and conflicts
    successes = [r for r in results if isinstance(r, tuple) and r[0] == "success"]
    conflicts = [r for r in results if isinstance(r, tuple) and r[0] == "conflict"]
    
    # Should have 1 success (2 seats) and 2 conflicts
    assert len(successes) == 1
    assert len(conflicts) == 2
    
    # Verify ride seats
    await db_session.refresh(test_ride)
    assert test_ride.seats_booked == 2


@pytest.mark.asyncio
async def test_cancel_booking_releases_seats(db_session, test_ride, test_passenger):
    """Test cancelling booking releases seats atomically."""
    # Book seats
    booking = await crud_v2.book_seat_atomic(
        db=db_session,
        ride_id=test_ride.id,
        passenger_id=test_passenger.id,
        seats_reserved=2
    )
    
    await db_session.refresh(test_ride)
    assert test_ride.seats_booked == 2
    
    # Cancel booking
    cancelled_booking = await crud_v2.cancel_booking(
        db=db_session,
        booking_id=booking.id,
        user_id=test_passenger.id
    )
    
    assert cancelled_booking.status == BookingStatus.CANCELLED
    assert cancelled_booking.version == 1  # Version incremented
    
    # Verify seats released
    await db_session.refresh(test_ride)
    assert test_ride.seats_booked == 0


# ============================================
# TEST 9-12: GEO-RADIUS SEARCH (PROMPT 5 CORE)
# ============================================

@pytest.mark.asyncio
async def test_haversine_distance_calculation():
    """Test Haversine distance formula accuracy."""
    # FAST NUCES to Liberty Market (known distance ~9 km)
    distance = crud_v2.haversine_distance(
        31.4697, 74.2728,  # FAST NUCES
        31.5204, 74.3587   # Liberty Market
    )
    
    assert 8.0 <= distance <= 10.0  # Approximately 9 km


@pytest.mark.asyncio
async def test_geo_radius_search_finds_nearby_rides(db_session, test_driver):
    """Test geo-radius search finds rides within radius."""
    # Create rides at different locations
    ride1 = await crud_v2.create_ride(
        db=db_session,
        driver_id=test_driver.id,
        start_point_lat=31.4697,
        start_point_lng=74.2728,
        start_point_address="FAST NUCES",
        end_point_lat=31.5204,
        end_point_lng=74.3587,
        end_point_address="Liberty Market",
        start_time=datetime.now() + timedelta(hours=1),
        seats_offered=4,
        base_price=Decimal("150.00")
    )
    
    # Search near FAST NUCES with 5km radius
    results = await crud_v2.search_rides_geo_radius(
        db=db_session,
        origin_lat=31.4700,  # Very close to FAST NUCES
        origin_lng=74.2730,
        dest_lat=31.5200,  # Very close to Liberty Market
        dest_lng=74.3590,
        radius_km=5.0,
        min_seats=1
    )
    
    assert len(results) >= 1
    assert ride1.id in [r.id for r in results]


@pytest.mark.asyncio
async def test_geo_radius_search_excludes_far_rides(db_session, test_driver):
    """Test geo-radius search excludes rides outside radius."""
    # Create ride in Islamabad (far from Lahore)
    await crud_v2.create_ride(
        db=db_session,
        driver_id=test_driver.id,
        start_point_lat=33.6844,  # Islamabad
        start_point_lng=73.0479,
        start_point_address="Islamabad",
        end_point_lat=33.7294,
        end_point_lng=73.0931,
        end_point_address="Rawalpindi",
        start_time=datetime.now() + timedelta(hours=1),
        seats_offered=4,
        base_price=Decimal("150.00")
    )
    
    # Search in Lahore with 10km radius
    results = await crud_v2.search_rides_geo_radius(
        db=db_session,
        origin_lat=31.4697,  # Lahore
        origin_lng=74.2728,
        dest_lat=31.5204,
        dest_lng=74.3587,
        radius_km=10.0,
        min_seats=1
    )
    
    # Should not find Islamabad ride
    assert all(r.start_point_lat < 32.0 for r in results)


@pytest.mark.asyncio
async def test_geo_radius_search_filters_by_date(db_session, test_driver):
    """Test geo-radius search filters by target date."""
    tomorrow = date.today() + timedelta(days=1)
    
    # Create ride for tomorrow
    await crud_v2.create_ride(
        db=db_session,
        driver_id=test_driver.id,
        start_point_lat=31.4697,
        start_point_lng=74.2728,
        start_point_address="FAST NUCES",
        end_point_lat=31.5204,
        end_point_lng=74.3587,
        end_point_address="Liberty Market",
        start_time=datetime.combine(tomorrow, time(8, 0)),
        seats_offered=4,
        base_price=Decimal("150.00")
    )
    
    # Search for today (should find nothing)
    results_today = await crud_v2.search_rides_geo_radius(
        db=db_session,
        origin_lat=31.4697,
        origin_lng=74.2728,
        dest_lat=31.5204,
        dest_lng=74.3587,
        radius_km=10.0,
        target_date=date.today()
    )
    
    # Search for tomorrow (should find ride)
    results_tomorrow = await crud_v2.search_rides_geo_radius(
        db=db_session,
        origin_lat=31.4697,
        origin_lng=74.2728,
        dest_lat=31.5204,
        dest_lng=74.3587,
        radius_km=10.0,
        target_date=tomorrow
    )
    
    assert len(results_today) == 0
    assert len(results_tomorrow) >= 1


# ============================================
# TEST 13-17: RECURRING SCHEDULES (PROMPT 5)
# ============================================

@pytest.mark.asyncio
async def test_create_recurring_schedule(db_session, test_driver):
    """Test creating recurring schedule."""
    schedule = await crud_v2.save_recurring_schedule(
        db=db_session,
        user_id=test_driver.id,
        days_of_week=["Mon", "Wed", "Fri"],
        time=time(8, 0),
        start_point_lat=31.4697,
        start_point_lng=74.2728,
        start_point_address="FAST NUCES",
        end_point_lat=31.5204,
        end_point_lng=74.3587,
        end_point_address="Liberty Market",
        seats_offered=4,
        base_price=Decimal("150.00"),
        start_date=date.today(),
        end_date=date.today() + timedelta(days=90),
        buffer_seats=1
    )
    
    assert schedule.id is not None
    assert schedule.days_of_week == ["Mon", "Wed", "Fri"]
    assert schedule.time == time(8, 0)
    assert schedule.is_active is True


@pytest.mark.asyncio
async def test_list_user_schedules(db_session, test_driver):
    """Test listing user's schedules."""
    # Create 2 schedules
    await crud_v2.save_recurring_schedule(
        db=db_session,
        user_id=test_driver.id,
        days_of_week=["Mon", "Tue"],
        time=time(8, 0),
        start_point_lat=31.4697,
        start_point_lng=74.2728,
        start_point_address="FAST",
        end_point_lat=31.5204,
        end_point_lng=74.3587,
        end_point_address="Liberty",
        seats_offered=4,
        base_price=Decimal("150.00"),
        start_date=date.today(),
        end_date=date.today() + timedelta(days=90)
    )
    
    schedules = await crud_v2.list_user_schedules(db_session, test_driver.id)
    assert len(schedules) >= 1


@pytest.mark.asyncio
async def test_update_recurring_schedule(db_session, test_driver):
    """Test updating recurring schedule."""
    schedule = await crud_v2.save_recurring_schedule(
        db=db_session,
        user_id=test_driver.id,
        days_of_week=["Mon"],
        time=time(8, 0),
        start_point_lat=31.4697,
        start_point_lng=74.2728,
        start_point_address="FAST",
        end_point_lat=31.5204,
        end_point_lng=74.3587,
        end_point_address="Liberty",
        seats_offered=4,
        base_price=Decimal("150.00"),
        start_date=date.today(),
        end_date=date.today() + timedelta(days=90)
    )
    
    updated = await crud_v2.update_schedule(
        db=db_session,
        schedule_id=schedule.id,
        days_of_week=["Mon", "Wed", "Fri"],
        seats_offered=5
    )
    
    assert updated.days_of_week == ["Mon", "Wed", "Fri"]
    assert updated.seats_offered == 5


@pytest.mark.asyncio
async def test_get_active_schedules_for_date(db_session, test_driver):
    """Test getting schedules for specific date."""
    # Create schedule for Mon/Wed/Fri
    await crud_v2.save_recurring_schedule(
        db=db_session,
        user_id=test_driver.id,
        days_of_week=["Mon", "Wed", "Fri"],
        time=time(8, 0),
        start_point_lat=31.4697,
        start_point_lng=74.2728,
        start_point_address="FAST",
        end_point_lat=31.5204,
        end_point_lng=74.3587,
        end_point_address="Liberty",
        seats_offered=4,
        base_price=Decimal("150.00"),
        start_date=date.today(),
        end_date=date.today() + timedelta(days=90)
    )
    
    # Find next Monday
    today = date.today()
    days_ahead = (0 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    next_monday = today + timedelta(days=days_ahead)
    
    schedules = await crud_v2.get_active_schedules_for_date(db_session, next_monday)
    assert len(schedules) >= 1


@pytest.mark.asyncio
async def test_materialize_scheduled_rides(db_session, test_driver):
    """Test materializing schedules into rides."""
    # Create schedule
    await crud_v2.save_recurring_schedule(
        db=db_session,
        user_id=test_driver.id,
        days_of_week=["Mon", "Tue", "Wed", "Thu", "Fri"],
        time=time(8, 0),
        start_point_lat=31.4697,
        start_point_lng=74.2728,
        start_point_address="FAST",
        end_point_lat=31.5204,
        end_point_lng=74.3587,
        end_point_address="Liberty",
        seats_offered=4,
        base_price=Decimal("150.00"),
        start_date=date.today(),
        end_date=date.today() + timedelta(days=90)
    )
    
    # Materialize for today
    result = await service_v2.materialize_scheduled_rides_service(
        db=db_session,
        target_date=date.today()
    )
    
    assert result["target_date"] == str(date.today())
    assert result["rides_created"] >= 0


# ============================================
# TEST 18-20: SERVICE LAYER
# ============================================

@pytest.mark.asyncio
async def test_service_create_ride(db_session, test_driver):
    """Test service layer ride creation."""
    data = RideCreateV2(
        start_point=GeoPoint(lat=31.4697, lng=74.2728, address="FAST NUCES"),
        end_point=GeoPoint(lat=31.5204, lng=74.3587, address="Liberty Market"),
        start_time=datetime.now() + timedelta(hours=1),
        seats_offered=4,
        buffer_seats=1,
        base_price=Decimal("150.00")
    )
    
    ride = await service_v2.create_ride_service(db_session, test_driver.id, data)
    assert ride.id is not None


@pytest.mark.asyncio
async def test_service_search_rides(db_session, test_driver):
    """Test service layer geo-radius search."""
    # Create test ride
    await crud_v2.create_ride(
        db=db_session,
        driver_id=test_driver.id,
        start_point_lat=31.4697,
        start_point_lng=74.2728,
        start_point_address="FAST",
        end_point_lat=31.5204,
        end_point_lng=74.3587,
        end_point_address="Liberty",
        start_time=datetime.now() + timedelta(hours=1),
        seats_offered=4,
        base_price=Decimal("150.00")
    )
    
    search_request = RideSearchRequest(
        origin=GeoPoint(lat=31.4697, lng=74.2728),
        destination=GeoPoint(lat=31.5204, lng=74.3587),
        radius_km=5.0,
        min_seats=1
    )
    
    rides = await service_v2.search_rides_service(db_session, search_request)
    assert len(rides) >= 1


@pytest.mark.asyncio
async def test_service_notification_stub(test_ride):
    """Test notification stub logging."""
    result = await service_v2.send_booking_notification(
        ride_id=test_ride.id,
        notification_type="BOOKING_CONFIRMED",
        message="Test notification",
        data={"test": "data"}
    )
    
    assert result["websocket"] is True
    assert result["fcm"] is True


# ============================================
# RUN TESTS
# ============================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
