"""
Module: Rides & Scheduling - API Routes (Prompt 5)
Purpose: FastAPI endpoints for atomic booking, geo-search, and recurring schedules
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: December 8, 2025
Notes: Driver endpoints, passenger endpoints, and schedule management
"""

from datetime import date
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.rides.schemas_v2 import (
    RideCreateV2,
    RideUpdateV2,
    RidePublicV2,
    RideSearchRequest,
    BookingRequest,
    BookingResponse,
    BookingCancelRequest,
    ScheduleCreate,
    ScheduleUpdate,
    SchedulePublic,
    RecurringScheduleDiscoverRequest,
    RecurringScheduleDiscoverPublic,
    RecurringScheduleBookSeriesRequest,
    RecurringScheduleBookSeriesResponse,
    RecurringDriverHomePublic,
    RecurringPassengerHomePublic,
    RecurringRideResolutionPublic,
    RecurringSeriesCancelResponse,
    GeoPoint,
    AvailableSeatsResponse
)
from app.modules.rides import service_v2
from app.core.exceptions import NotFoundError, ConflictError, ValidationError, ForbiddenError
from app.models.ride import Ride
from app.models.booking import Booking


router = APIRouter(prefix="/api/v2/rides", tags=["Rides & Scheduling (Prompt 5)"])


# ============================================
# DRIVER ENDPOINTS
# ============================================

@router.post(
    "/",
    response_model=RidePublicV2,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new ride (Driver)",
    description="Create a new ride with full Prompt 5 features including buffer seats and polylines"
)
async def create_ride(
    ride_data: RideCreateV2,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new ride (Driver only).
    
    Features:
    - Geo-coordinates for origin/destination
    - Polyline route encoding
    - Buffer seats configuration
    - Recurring ride support
    """
    try:
        ride = await service_v2.create_ride_service(db, current_user.id, ride_data)
        
        # Format response
        return RidePublicV2(
            id=ride.id,
            driver_id=ride.driver_id,
            start_point=GeoPoint(
                lat=ride.start_point_lat,
                lng=ride.start_point_lng,
                address=ride.start_point_address
            ),
            end_point=GeoPoint(
                lat=ride.end_point_lat,
                lng=ride.end_point_lng,
                address=ride.end_point_address
            ),
            start_time=ride.start_time,
            polyline_main=ride.polyline_main,
            seats_offered=ride.seats_offered,
            seats_booked=ride.seats_booked,
            seats_available=ride.seats_offered - ride.seats_booked - ride.buffer_seats,
            buffer_seats=ride.buffer_seats,
            base_price=ride.base_price,
            status=ride.status.value,
            created_at=ride.created_at,
            updated_at=ride.updated_at
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch(
    "/{ride_id}",
    response_model=RidePublicV2,
    summary="Update ride details (Driver)",
    description="Update ride details. Only the driver who created the ride can update it."
)
async def update_ride(
    ride_id: UUID,
    ride_data: RideUpdateV2,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update ride details (Driver only)."""
    try:
        ride = await service_v2.update_ride_service(db, ride_id, current_user.id, ride_data)
        
        return RidePublicV2(
            id=ride.id,
            driver_id=ride.driver_id,
            start_point=GeoPoint(
                lat=ride.start_point_lat,
                lng=ride.start_point_lng,
                address=ride.start_point_address
            ),
            end_point=GeoPoint(
                lat=ride.end_point_lat,
                lng=ride.end_point_lng,
                address=ride.end_point_address
            ),
            start_time=ride.start_time,
            polyline_main=ride.polyline_main,
            seats_offered=ride.seats_offered,
            seats_booked=ride.seats_booked,
            seats_available=ride.seats_offered - ride.seats_booked - ride.buffer_seats,
            buffer_seats=ride.buffer_seats,
            base_price=ride.base_price,
            status=ride.status.value,
            created_at=ride.created_at,
            updated_at=ride.updated_at
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get(
    "/driver/upcoming",
    response_model=List[RidePublicV2],
    summary="Get driver's upcoming rides",
    description="Retrieve all upcoming rides for the authenticated driver"
)
async def get_driver_upcoming_rides(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get driver's upcoming rides."""
    rides = await service_v2.get_driver_upcoming_rides_service(db, current_user.id, limit)
    
    return [
        RidePublicV2(
            id=ride.id,
            driver_id=ride.driver_id,
            start_point=GeoPoint(
                lat=ride.start_point_lat,
                lng=ride.start_point_lng,
                address=ride.start_point_address
            ),
            end_point=GeoPoint(
                lat=ride.end_point_lat,
                lng=ride.end_point_lng,
                address=ride.end_point_address
            ),
            start_time=ride.start_time,
            polyline_main=ride.polyline_main,
            seats_offered=ride.seats_offered,
            seats_booked=ride.seats_booked,
            seats_available=ride.seats_offered - ride.seats_booked - ride.buffer_seats,
            buffer_seats=ride.buffer_seats,
            base_price=ride.base_price,
            status=ride.status.value,
            created_at=ride.created_at,
            updated_at=ride.updated_at
        )
        for ride in rides
    ]


# ============================================
# PASSENGER ENDPOINTS
# ============================================

@router.post(
    "/search",
    response_model=List[RidePublicV2],
    summary="Search rides (Geo-radius) [PROMPT 5 CORE]",
    description="Search for rides within a geographic radius of origin and destination using Haversine formula"
)
async def search_rides(
    search_request: RideSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Search rides using geo-radius (Prompt 5 core feature).
    
    Uses Haversine formula to find rides near both origin and destination.
    """
    rides = await service_v2.search_rides_service(db, search_request)
    
    return [
        RidePublicV2(
            id=ride.id,
            driver_id=ride.driver_id,
            start_point=GeoPoint(
                lat=ride.start_point_lat,
                lng=ride.start_point_lng,
                address=ride.start_point_address
            ),
            end_point=GeoPoint(
                lat=ride.end_point_lat,
                lng=ride.end_point_lng,
                address=ride.end_point_address
            ),
            start_time=ride.start_time,
            polyline_main=ride.polyline_main,
            seats_offered=ride.seats_offered,
            seats_booked=ride.seats_booked,
            seats_available=ride.seats_offered - ride.seats_booked - ride.buffer_seats,
            buffer_seats=ride.buffer_seats,
            base_price=ride.base_price,
            status=ride.status.value,
            created_at=ride.created_at,
            updated_at=ride.updated_at
        )
        for ride in rides
    ]


@router.post(
    "/{ride_id}/book",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Book seats atomically [PROMPT 5 CORE]",
    description="Atomically reserve seats on a ride using SELECT FOR UPDATE to prevent race conditions"
)
async def book_seat(
    ride_id: UUID,
    booking_request: BookingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Book seats atomically (Prompt 5 core feature).
    
    Prevents race conditions using database-level locking.
    """
    # Update booking request with ride_id from path
    booking_request.ride_id = ride_id
    
    try:
        booking = await service_v2.book_seat_service(db, current_user.id, booking_request)
        
        return BookingResponse(
            id=booking.id,
            ride_id=booking.ride_id,
            passenger_id=booking.passenger_id,
            seats_reserved=booking.seats_reserved,
            fare=booking.fare,
            status=booking.status.value,
            version=booking.version,
            created_at=booking.created_at
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/bookings/{booking_id}/cancel",
    response_model=BookingResponse,
    summary="Cancel booking",
    description="Cancel a booking and release seats atomically"
)
async def cancel_booking(
    booking_id: UUID,
    cancel_request: BookingCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel booking and release seats."""
    try:
        booking = await service_v2.cancel_booking_service(
            db,
            booking_id,
            current_user.id,
            cancel_request.reason
        )
        
        return BookingResponse(
            id=booking.id,
            ride_id=booking.ride_id,
            passenger_id=booking.passenger_id,
            seats_reserved=booking.seats_reserved,
            fare=booking.fare,
            status=booking.status.value,
            version=booking.version,
            created_at=booking.created_at
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ============================================
# RECURRING SCHEDULE ENDPOINTS
# ============================================

@router.post(
    "/schedule",
    response_model=SchedulePublic,
    status_code=status.HTTP_201_CREATED,
    summary="Create recurring schedule [PROMPT 5]",
    description="Create a recurring ride schedule (e.g., every Mon/Wed/Fri at 8 AM)"
)
async def create_recurring_schedule(
    schedule_data: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create recurring schedule (Prompt 5 feature).
    
    Schedules will be materialized into actual rides by Celery task.
    """
    try:
        schedule = await service_v2.create_recurring_schedule_service(
            db,
            current_user.id,
            schedule_data
        )
        
        return SchedulePublic(
            id=schedule.id,
            user_id=schedule.user_id,
            days_of_week=schedule.days_of_week,
            time=schedule.time,
            start_point=GeoPoint(
                lat=schedule.start_point_lat,
                lng=schedule.start_point_lng,
                address=schedule.start_point_address
            ),
            end_point=GeoPoint(
                lat=schedule.end_point_lat,
                lng=schedule.end_point_lng,
                address=schedule.end_point_address
            ),
            polyline_main=schedule.polyline_main,
            seats_offered=schedule.seats_offered,
            buffer_seats=schedule.buffer_seats,
            base_price=schedule.base_price,
            start_date=schedule.start_date,
            end_date=schedule.end_date,
            is_active=schedule.is_active,
            created_at=schedule.created_at
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/schedule/my-schedules",
    response_model=List[SchedulePublic],
    summary="Get user's recurring schedules",
    description="Retrieve all recurring schedules for the authenticated user"
)
async def get_my_schedules(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get user's recurring schedules."""
    schedules = await service_v2.list_user_schedules_service(db, current_user.id, active_only)
    
    return [
        SchedulePublic(
            id=schedule.id,
            user_id=schedule.user_id,
            days_of_week=schedule.days_of_week,
            time=schedule.time,
            start_point=GeoPoint(
                lat=schedule.start_point_lat,
                lng=schedule.start_point_lng,
                address=schedule.start_point_address
            ),
            end_point=GeoPoint(
                lat=schedule.end_point_lat,
                lng=schedule.end_point_lng,
                address=schedule.end_point_address
            ),
            polyline_main=schedule.polyline_main,
            seats_offered=schedule.seats_offered,
            buffer_seats=schedule.buffer_seats,
            base_price=schedule.base_price,
            start_date=schedule.start_date,
            end_date=schedule.end_date,
            is_active=schedule.is_active,
            created_at=schedule.created_at
        )
        for schedule in schedules
    ]


@router.post(
    "/schedule/discover",
    response_model=List[RecurringScheduleDiscoverPublic],
    summary="Discover recurring rides (Passenger)",
    description=(
        "Discover recurring schedules by route proximity, date-range overlap, "
        "and departure window. Passenger from/until is treated as every day "
        "in that range."
    ),
)
async def discover_recurring_schedules(
    search_request: RecurringScheduleDiscoverRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Discover recurring schedules for passengers."""
    try:
        return await service_v2.discover_recurring_schedules_service(
            db=db,
            user_id=current_user.id,
            search_request=search_request,
        )
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/schedule/{schedule_id}/book-series",
    response_model=RecurringScheduleBookSeriesResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Book recurring series (Passenger)",
    description=(
        "Book a passenger on all matching recurring instances for date overlap and "
        "departure window. Applies all-or-nothing semantics."
    ),
)
async def book_recurring_schedule_series(
    schedule_id: UUID,
    booking_request: RecurringScheduleBookSeriesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await service_v2.book_recurring_schedule_series_service(
            db=db,
            user_id=current_user.id,
            schedule_id=schedule_id,
            request=booking_request,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ForbiddenError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/schedule/my-home/driver",
    response_model=List[RecurringDriverHomePublic],
    summary="Driver recurring home section",
    description="List driver recurring schedules with nearest active/upcoming ride instance.",
)
async def get_driver_recurring_home(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await service_v2.list_driver_recurring_home_service(
        db=db,
        user_id=current_user.id,
    )


@router.get(
    "/schedule/my-home/passenger",
    response_model=List[RecurringPassengerHomePublic],
    summary="Passenger recurring home section",
    description="List passenger recurring subscriptions with nearest active/upcoming ride instance.",
)
async def get_passenger_recurring_home(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await service_v2.list_passenger_recurring_home_service(
        db=db,
        user_id=current_user.id,
    )


@router.get(
    "/schedule/{schedule_id}/resolve-next",
    response_model=RecurringRideResolutionPublic,
    summary="Resolve next recurring ride (Driver)",
    description=(
        "Resolve nearest active/upcoming ride instance for a driver-owned recurring schedule."
    ),
)
async def resolve_driver_schedule_next_ride(
    schedule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await service_v2.resolve_driver_schedule_next_ride_service(
            db=db,
            user_id=current_user.id,
            schedule_id=schedule_id,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/schedule/subscriptions/{subscription_id}/resolve-next",
    response_model=RecurringRideResolutionPublic,
    summary="Resolve next recurring ride (Passenger)",
    description=(
        "Resolve nearest active/upcoming ride instance for a passenger recurring subscription."
    ),
)
async def resolve_passenger_subscription_next_ride(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return await service_v2.resolve_passenger_subscription_next_ride_service(
            db=db,
            user_id=current_user.id,
            subscription_id=subscription_id,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/schedule/subscriptions/{subscription_id}",
    response_model=RecurringSeriesCancelResponse,
    summary="Cancel full recurring series (Passenger)",
    description="Cancel passenger recurring subscription and all its future open/scheduled instances.",
)
async def cancel_passenger_recurring_subscription(
    subscription_id: UUID,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = await service_v2.cancel_passenger_recurring_subscription_service(
            db=db,
            user_id=current_user.id,
            subscription_id=subscription_id,
            reason=reason,
        )
        return RecurringSeriesCancelResponse(
            subscription_id=result["subscription_id"],
            status=result["status"],
            cancelled_future_bookings=result["cancelled_future_bookings"],
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put(
    "/schedule/{schedule_id}",
    response_model=SchedulePublic,
    summary="Update recurring schedule",
    description="Update an existing recurring schedule for the authenticated user"
)
async def update_schedule(
    schedule_id: UUID,
    schedule_data: ScheduleUpdate,
    purge_future_rides: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update an owned recurring schedule."""
    try:
        schedule = await service_v2.update_user_schedule_service(
            db=db,
            user_id=current_user.id,
            schedule_id=schedule_id,
            data=schedule_data,
            purge_future_rides=purge_future_rides,
        )

        return SchedulePublic(
            id=schedule.id,
            user_id=schedule.user_id,
            days_of_week=schedule.days_of_week,
            time=schedule.time,
            start_point=GeoPoint(
                lat=schedule.start_point_lat,
                lng=schedule.start_point_lng,
                address=schedule.start_point_address
            ),
            end_point=GeoPoint(
                lat=schedule.end_point_lat,
                lng=schedule.end_point_lng,
                address=schedule.end_point_address
            ),
            polyline_main=schedule.polyline_main,
            seats_offered=schedule.seats_offered,
            buffer_seats=schedule.buffer_seats,
            base_price=schedule.base_price,
            start_date=schedule.start_date,
            end_date=schedule.end_date,
            is_active=schedule.is_active,
            created_at=schedule.created_at
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/schedule/{schedule_id}",
    response_model=SchedulePublic,
    summary="Delete recurring schedule",
    description="Soft-delete (deactivate) an existing recurring schedule for the authenticated user"
)
async def delete_schedule(
    schedule_id: UUID,
    purge_future_rides: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Deactivate an owned recurring schedule."""
    try:
        schedule = await service_v2.deactivate_user_schedule_service(
            db=db,
            user_id=current_user.id,
            schedule_id=schedule_id,
            purge_future_rides=purge_future_rides,
        )

        return SchedulePublic(
            id=schedule.id,
            user_id=schedule.user_id,
            days_of_week=schedule.days_of_week,
            time=schedule.time,
            start_point=GeoPoint(
                lat=schedule.start_point_lat,
                lng=schedule.start_point_lng,
                address=schedule.start_point_address
            ),
            end_point=GeoPoint(
                lat=schedule.end_point_lat,
                lng=schedule.end_point_lng,
                address=schedule.end_point_address
            ),
            polyline_main=schedule.polyline_main,
            seats_offered=schedule.seats_offered,
            buffer_seats=schedule.buffer_seats,
            base_price=schedule.base_price,
            start_date=schedule.start_date,
            end_date=schedule.end_date,
            is_active=schedule.is_active,
            created_at=schedule.created_at
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================
# UTILITY ENDPOINTS
# ============================================

@router.get(
    "/{ride_id}",
    response_model=RidePublicV2,
    summary="Get ride details",
    description="Get detailed information about a specific ride"
)
async def get_ride(
    ride_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get ride details."""
    from app.modules.rides import crud_v2
    
    ride = await crud_v2.get_ride_by_id(db, ride_id)
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    return RidePublicV2(
        id=ride.id,
        driver_id=ride.driver_id,
        start_point=GeoPoint(
            lat=ride.start_point_lat,
            lng=ride.start_point_lng,
            address=ride.start_point_address
        ),
        end_point=GeoPoint(
            lat=ride.end_point_lat,
            lng=ride.end_point_lng,
            address=ride.end_point_address
        ),
        start_time=ride.start_time,
        polyline_main=ride.polyline_main,
        seats_offered=ride.seats_offered,
        seats_booked=ride.seats_booked,
        seats_available=ride.seats_offered - ride.seats_booked - ride.buffer_seats,
        buffer_seats=ride.buffer_seats,
        base_price=ride.base_price,
        status=ride.status.value,
        created_at=ride.created_at,
        updated_at=ride.updated_at
    )


@router.get(
    "/{ride_id}/available-seats",
    response_model=AvailableSeatsResponse,
    summary="Check available seats",
    description="Check how many seats are currently available for booking"
)
async def get_available_seats(
    ride_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Check available seats for a ride."""
    from app.modules.rides import crud_v2
    
    ride = await crud_v2.get_ride_by_id(db, ride_id)
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    return AvailableSeatsResponse(
        ride_id=ride.id,
        seats_offered=ride.seats_offered,
        seats_booked=ride.seats_booked,
        buffer_seats=ride.buffer_seats,
        seats_available=ride.seats_offered - ride.seats_booked - ride.buffer_seats
    )
