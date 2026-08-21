import sys

with open(r'd:\Projects\Projects Inprogress\FYP\SmartCarpoolingApp\backend\app\modules\rides\service.py', 'r', encoding='utf-8') as f:
    text = f.read()

target = '''async def accept_ride_request_service(
    db: AsyncSession, driver_user_id: UUID, request_id: UUID
) -> Dict[str, Any]:
    """Driver accepts a passenger ride request."""
    try:
        from app.models.ride_request import RideRequest, RideRequestStatus
        from sqlalchemy import select

        stmt = select(RideRequest).where(RideRequest.id == request_id)
        result = await db.execute(stmt)
        req = result.scalar_one_or_none()

        if not req:
            raise HTTPException(status_code=404, detail="Ride request not found")
        if req.status != RideRequestStatus.PENDING:
            raise HTTPException(status_code=400, detail="Request is no longer pending")

        req.status = RideRequestStatus.ACCEPTED
        req.accepted_by_driver_id = driver_user_id
        await db.commit()
        await db.refresh(req)

        logger.info(f"Driver {driver_user_id} accepted request {request_id}")
        return _format_response(
            data=RideRequestPublic.model_validate(req).model_dump()
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error accepting ride request: {e}")
        return _format_response(error="Failed to accept ride request")'''

replacement = '''async def accept_ride_request_service(
    db: AsyncSession, driver_user_id: UUID, request_id: UUID
) -> Dict[str, Any]:
    """Driver accepts a passenger ride request, generating a Ride and Booking."""
    try:
        from app.models.ride_request import RideRequest, RideRequestStatus
        from app.models.ride import Ride
        from app.models.enums import RideStatus, BookingStatus
        from app.models.booking import Booking
        from sqlalchemy import select
        import uuid
        from datetime import datetime, timezone

        stmt = select(RideRequest).where(RideRequest.id == request_id)
        result = await db.execute(stmt)
        req = result.scalar_one_or_none()

        if not req:
            raise HTTPException(status_code=404, detail="Ride request not found")
        if req.status != RideRequestStatus.PENDING:
            raise HTTPException(status_code=400, detail="Request is no longer pending")

        # Create actual Ride for the driver
        import decimal
        new_ride = Ride(
            driver_id=driver_user_id,
            start_point_lat=req.origin_lat,
            start_point_lng=req.origin_lng,
            end_point_lat=req.destination_lat,
            end_point_lng=req.destination_lng,
            start_point_address=req.origin,
            end_point_address=req.destination,
            departure_time=req.departure_time,
            seats_available=max(0, 4 - req.seats_needed), # basic formula
            price_per_seat=decimal.Decimal(str(req.max_budget if req.max_budget else 500.0)),
            status=RideStatus.OPEN,
        )
        db.add(new_ride)
        await db.flush()

        # Create Booking for passenger
        new_booking = Booking(
            ride_id=new_ride.id,
            passenger_id=req.passenger_id,
            seats_reserved=req.seats_needed,
            fare=float((req.max_budget if req.max_budget else 500.0) * req.seats_needed),
            status=BookingStatus.RESERVED,
            booking_time=datetime.now(timezone.utc)
        )
        db.add(new_booking)

        # Mark Request as accepted
        req.status = RideRequestStatus.ACCEPTED
        req.accepted_by_driver_id = driver_user_id
        req.ride_id = new_ride.id

        await db.commit()
        await db.refresh(req)

        data = RideRequestPublic.model_validate(req).model_dump()
        # Ensure we inject the generated ride_id to help the frontend open Chat
        data['ride_id'] = str(new_ride.id) 

        logger.info(f"Driver {driver_user_id} accepted request {request_id} mapped to ride {new_ride.id}")
        return _format_response(
            data=data,
            message="Ride successfully matched and generated!"
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error accepting ride request: {e}")
        raise HTTPException(status_code=500, detail="Failed to accept ride request")'''

text = text.replace(target, replacement)

with open(r'd:\Projects\Projects Inprogress\FYP\SmartCarpoolingApp\backend\app\modules\rides\service.py', 'w', encoding='utf-8') as f:
    f.write(text)
print("Updated successfully")