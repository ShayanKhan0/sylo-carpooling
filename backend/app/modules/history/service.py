"""
History Service Layer (Prompt 11B - Trip History Module)

Business logic for trip history viewing and CSV export.
Fully async, aligned with actual DB schema (Ride, Booking, User, Vehicle).

Author: Smart Carpooling Backend Team
Date: December 19, 2025
Prompt: 11B - Trip History Module
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy import func, and_, select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ride import Ride
from app.models.booking import Booking
from app.models.vehicle import Vehicle
from app.modules.auth.models import User
from app.models.rating import Rating
from app.models.driver import Driver
from app.core.exceptions import NotFoundException, ForbiddenException


class HistoryService:
    """Service for trip history (async, schema-aligned)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Ride History
    # ------------------------------------------------------------------

    async def get_ride_history(
        self,
        user_id: UUID,
        as_driver: bool = False,
        page: int = 1,
        page_size: int = 20,
        status_filter: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> dict:
        """Get paginated ride history for a user."""

        if as_driver:
            # Driver view — rides they created
            base = select(Ride).where(Ride.driver_id == user_id)
        else:
            # Passenger view — rides they booked
            ride_ids_q = select(Booking.ride_id).where(
                Booking.passenger_id == user_id
            )
            base = select(Ride).where(Ride.id.in_(ride_ids_q))

        if status_filter:
            base = base.where(Ride.status == status_filter)

        if from_date:
            try:
                from_dt = datetime.strptime(from_date, "%Y-%m-%d")
                base = base.where(Ride.created_at >= from_dt)
            except ValueError:
                pass

        if to_date:
            try:
                to_dt = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1)
                base = base.where(Ride.created_at < to_dt)
            except ValueError:
                pass

        # Count
        count_result = await self.db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar() or 0

        # Paginated fetch
        offset = (page - 1) * page_size
        data_q = (
            base.options(selectinload(Ride.bookings))
            .order_by(Ride.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(data_q)
        rides = result.scalars().all()

        formatted = []
        for ride in rides:
            # Get driver name
            driver_name = None
            driver_res = await self.db.execute(
                select(Driver).where(Driver.user_id == ride.driver_id)
            )
            driver_obj = driver_res.scalar_one_or_none()
            if driver_obj:
                user_res = await self.db.execute(
                    select(User).where(User.id == driver_obj.user_id)
                )
                driver_user = user_res.scalar_one_or_none()
                if driver_user:
                    driver_name = driver_user.full_name

            # Get passenger names from bookings
            booking_res = await self.db.execute(
                select(Booking).where(Booking.ride_id == ride.id)
            )
            bookings = booking_res.scalars().all()
            passenger_names = []
            total_fare = 0.0
            total_seats = 0
            for bk in bookings:
                total_fare += float(bk.fare or 0)
                total_seats += bk.seats_reserved or 0
                p_res = await self.db.execute(
                    select(User.full_name).where(User.id == bk.passenger_id)
                )
                pname = p_res.scalar_one_or_none()
                if pname:
                    passenger_names.append(pname)

            # Get user's rating for this ride
            rating = None
            if str(ride.status) in ("completed", "RideStatus.completed"):
                rat_res = await self.db.execute(
                    select(Rating.score).where(
                        and_(Rating.ride_id == ride.id, Rating.rater_id == user_id)
                    )
                )
                rating = rat_res.scalar_one_or_none()

            # Vehicle info
            vehicle_info = None
            if ride.vehicle_id:
                v_res = await self.db.execute(
                    select(Vehicle).where(Vehicle.id == ride.vehicle_id)
                )
                veh = v_res.scalar_one_or_none()
                if veh:
                    vehicle_info = f"{veh.make} {veh.model}"

            formatted.append({
                "ride_id": ride.id,
                "date": ride.created_at,
                "pickup_location": ride.start_point_address
                or f"{ride.start_point_lat}, {ride.start_point_lng}",
                "dropoff_location": ride.end_point_address
                or f"{ride.end_point_lat}, {ride.end_point_lng}",
                "distance_km": ride.route_distance_km or 0.0,
                "duration_minutes": ride.estimated_duration_minutes or 0,
                "fare": total_fare,
                "price_per_seat": float(ride.price_per_seat or 0),
                "seats": total_seats,
                "status": str(ride.status).replace("RideStatus.", ""),
                "driver_name": driver_name,
                "passenger_names": passenger_names,
                "vehicle_info": vehicle_info,
                "rating": rating,
            })

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        return {
            "rides": formatted,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    # ------------------------------------------------------------------
    # Ride Detail
    # ------------------------------------------------------------------

    async def get_ride_details(
        self, ride_id: UUID, user_id: UUID
    ) -> Dict[str, Any]:
        """Get detailed information for a specific ride."""

        result = await self.db.execute(select(Ride).where(Ride.id == ride_id))
        ride = result.scalar_one_or_none()
        if not ride:
            raise NotFoundException(f"Ride {ride_id} not found")

        # Authorization — user must be driver or passenger
        is_driver = ride.driver_id == user_id
        bk_res = await self.db.execute(
            select(Booking).where(
                and_(Booking.ride_id == ride_id, Booking.passenger_id == user_id)
            )
        )
        is_passenger = bk_res.scalar_one_or_none() is not None
        if not is_driver and not is_passenger:
            raise ForbiddenException("You are not authorized to view this ride")

        # Driver info
        driver_info: Dict[str, Any] = {}
        dr_res = await self.db.execute(
            select(User).where(User.id == ride.driver_id)
        )
        driver_user = dr_res.scalar_one_or_none()
        if driver_user:
            driver_info = {
                "id": str(driver_user.id),
                "name": driver_user.full_name,
                "phone": driver_user.phone,
            }

        # Passengers from bookings
        passengers = []
        all_bookings_res = await self.db.execute(
            select(Booking).where(Booking.ride_id == ride_id)
        )
        all_bookings = all_bookings_res.scalars().all()
        for bk in all_bookings:
            p_res = await self.db.execute(
                select(User).where(User.id == bk.passenger_id)
            )
            pu = p_res.scalar_one_or_none()
            if pu:
                passengers.append({
                    "id": str(pu.id),
                    "name": pu.full_name,
                    "phone": pu.phone,
                    "seats": bk.seats_reserved,
                    "fare": float(bk.fare or 0),
                })

        # Vehicle
        vehicle_info = None
        if ride.vehicle_id:
            v_res = await self.db.execute(
                select(Vehicle).where(Vehicle.id == ride.vehicle_id)
            )
            veh = v_res.scalar_one_or_none()
            if veh:
                vehicle_info = {
                    "make": veh.make,
                    "model": veh.model,
                    "plate_number": veh.plate_number,
                }

        # User's own rating
        rating_from_user = None
        if str(ride.status) in ("completed", "RideStatus.completed"):
            rat_res = await self.db.execute(
                select(Rating.score).where(
                    and_(Rating.ride_id == ride.id, Rating.rater_id == user_id)
                )
            )
            rating_from_user = rat_res.scalar_one_or_none()

        return {
            "ride_id": ride.id,
            "created_at": ride.created_at,
            "departure_time": ride.departure_time,
            "status": str(ride.status).replace("RideStatus.", ""),
            "pickup": {
                "lat": ride.start_point_lat,
                "lng": ride.start_point_lng,
                "address": ride.start_point_address,
            },
            "dropoff": {
                "lat": ride.end_point_lat,
                "lng": ride.end_point_lng,
                "address": ride.end_point_address,
            },
            "distance_km": ride.route_distance_km or 0.0,
            "duration_minutes": ride.estimated_duration_minutes or 0,
            "price_per_seat": float(ride.price_per_seat or 0),
            "driver": driver_info,
            "passengers": passengers,
            "vehicle": vehicle_info,
            "polyline": ride.polyline,
            "rating_from_user": rating_from_user,
        }
