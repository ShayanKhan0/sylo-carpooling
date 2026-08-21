with open('app/modules/rides/service.py', 'r') as f:
    text = f.read()

old_str = '''        if req.status != RideRequestStatus.PENDING:
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
        )'''

new_str = '''        if req.status != RideRequestStatus.PENDING:
            raise HTTPException(status_code=400, detail="Request is no longer pending")

        distance_km = None
        duration_minutes = None
        polyline = None
        try:
            from app.core.google_maps_client import get_google_maps_client
            client = get_google_maps_client()
            route_data = client.get_directions(
                (req.origin_lat, req.origin_lng),
                (req.destination_lat, req.destination_lng),
                alternatives=False
            )
            if route_data:
                distance_km = route_data.get('distance_km')
                duration_minutes = route_data.get('duration_minutes')
                polyline = route_data.get('polyline')
        except Exception as e:
            import logging
            logging.warning(f"Google Maps fail in accept: {e}")
        
        if distance_km is None:
            from app.modules.matching.utils import calculate_distance
            distance_km = calculate_distance(
                req.origin_lat, req.origin_lng,
                req.destination_lat, req.destination_lng
            )

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
            route_distance_km=distance_km,
            estimated_duration_minutes=duration_minutes,
            polyline=polyline
        )'''

if old_str in text:
    text = text.replace(old_str, new_str)
    with open('app/modules/rides/service.py', 'w') as f:
        f.write(text)
    print('Patched successfully!')
else:
    print('Failed to find old string.')
