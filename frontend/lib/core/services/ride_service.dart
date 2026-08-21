import '../models/ride_model.dart';
import 'api_client.dart';

class RideService {
  final ApiClient _api = ApiClient();

  // ── Driver endpoints ──────────────────────────────────

  /// POST /rides/create
  Future<Ride> createRide({
    required String origin,
    required String destination,
    required double originLat,
    required double originLng,
    required double destinationLat,
    required double destinationLng,
    required String departureTime,
    required int availableSeats,
    required double pricePerSeat,
    required String vehicleId,
    int? estimatedDuration,
    double? routeDistanceKm,
    String? polyline,
  }) async {
    final res = await _api.post('/rides/create', data: {
      'origin': origin,
      'destination': destination,
      'origin_lat': originLat,
      'origin_lng': originLng,
      'destination_lat': destinationLat,
      'destination_lng': destinationLng,
      'departure_time': departureTime,
      'available_seats': availableSeats,
      'price_per_seat': pricePerSeat,
      'vehicle_id': vehicleId,
      if (estimatedDuration != null) 'estimated_duration': estimatedDuration,
      if (routeDistanceKm != null) 'route_distance_km': routeDistanceKm,
      if (polyline != null) 'polyline': polyline,
    });
    final data = unwrap(res);
    if (data is Map<String, dynamic>) {
      return Ride.fromJson(data);
    }

    final body = res.data;
    if (body is Map && body['error'] != null) {
      throw Exception(body['error'].toString());
    }

    throw Exception('Unexpected create ride response from server');
  }

  /// GET /rides/my/driver?status_filter=...
  Future<List<Ride>> getMyDriverRides({String? statusFilter}) async {
    final res = await _api.get('/rides/my/driver', queryParameters: {
      if (statusFilter != null) 'status_filter': statusFilter,
    });
    final list = unwrap(res) as List;
    return list.map((r) => Ride.fromJson(r)).toList();
  }

  /// GET /rides/my/stats/driver
  Future<RideStatistics> getDriverStats() async {
    final res = await _api.get('/rides/my/stats/driver');
    return RideStatistics.fromJson(unwrap(res));
  }

  /// PUT /rides/{id}/status
  Future<Ride> updateRideStatus(String rideId, String status) async {
    final res = await _api.put('/rides/$rideId/status', data: {
      'status': status,
    });
    return Ride.fromJson(unwrap(res));
  }

  /// PUT /rides/{id}
  Future<Ride> updateRide(
    String rideId, {
    String? departureTime,
    int? availableSeats,
    double? pricePerSeat,
    int? estimatedDuration,
  }) async {
    final body = <String, dynamic>{};
    if (departureTime != null) body['departure_time'] = departureTime;
    if (availableSeats != null) body['available_seats'] = availableSeats;
    if (pricePerSeat != null) body['price_per_seat'] = pricePerSeat;
    if (estimatedDuration != null) {
      body['estimated_duration'] = estimatedDuration;
    }
    final res = await _api.put('/rides/$rideId', data: body);
    return Ride.fromJson(unwrap(res));
  }

  /// DELETE /rides/{id}
  Future<void> deleteRide(String rideId) async {
    await _api.delete('/rides/$rideId');
  }

  // ── Passenger endpoints ───────────────────────────────

  /// GET /rides/available?... (supports both text and geo-proximity search)
  Future<List<Ride>> searchRides({
    String? origin,
    String? destination,
    double? originLat,
    double? originLng,
    double? destinationLat,
    double? destinationLng,
    double? radiusKm,
    int? minSeats,
    int? driverTotalSeats,
    double? maxPrice,
    String? departureAfter,
    String? departureBefore,
    bool includeRecurring = false,
  }) async {
    final res = await _api.get('/rides/available', queryParameters: {
      if (origin != null) 'origin': origin,
      if (destination != null) 'destination': destination,
      if (originLat != null) 'origin_lat': originLat,
      if (originLng != null) 'origin_lng': originLng,
      if (destinationLat != null) 'destination_lat': destinationLat,
      if (destinationLng != null) 'destination_lng': destinationLng,
      if (radiusKm != null) 'radius_km': radiusKm,
      if (minSeats != null) 'min_seats': minSeats,
      if (driverTotalSeats != null) 'driver_total_seats': driverTotalSeats,
      if (maxPrice != null) 'max_price': maxPrice,
      if (departureAfter != null) 'departure_after': departureAfter,
      if (departureBefore != null) 'departure_before': departureBefore,
      'include_recurring': includeRecurring,
    });
    final list = unwrap(res) as List;
    return list.map((r) => Ride.fromJson(r)).toList();
  }

  /// GET /rides/{id} → RideWithBookingsPublic
  Future<Ride> getRideDetail(String rideId) async {
    final res = await _api.get('/rides/$rideId');
    return Ride.fromJson(unwrap(res));
  }

  /// POST /rides/book
  Future<RideBooking> bookRide({
    required String rideId,
    int bookedSeats = 1,
    double? pickupLat,
    double? pickupLng,
    String? pickupAddress,
    String? pickupPlaceId,
    double? dropoffLat,
    double? dropoffLng,
    String? dropoffAddress,
    String? dropoffPlaceId,
  }) async {
    final res = await _api.post('/rides/book', data: {
      'ride_id': rideId,
      'booked_seats': bookedSeats,
      if (pickupLat != null) 'pickup_lat': pickupLat,
      if (pickupLng != null) 'pickup_lng': pickupLng,
      if (pickupAddress != null && pickupAddress.trim().isNotEmpty)
        'pickup_address': pickupAddress.trim(),
      if (pickupPlaceId != null && pickupPlaceId.trim().isNotEmpty)
        'pickup_place_id': pickupPlaceId.trim(),
      if (dropoffLat != null) 'dropoff_lat': dropoffLat,
      if (dropoffLng != null) 'dropoff_lng': dropoffLng,
      if (dropoffAddress != null && dropoffAddress.trim().isNotEmpty)
        'dropoff_address': dropoffAddress.trim(),
      if (dropoffPlaceId != null && dropoffPlaceId.trim().isNotEmpty)
        'dropoff_place_id': dropoffPlaceId.trim(),
    });
    return RideBooking.fromJson(unwrap(res));
  }

  /// PUT /rides/{id}/route-selection
  Future<Ride> updateRideRouteSelection({
    required String rideId,
    required String routeKey,
  }) async {
    final res = await _api.put('/rides/$rideId/route-selection', data: {
      'route_key': routeKey,
    });
    return Ride.fromJson(unwrap(res));
  }

  /// GET /rides/my/bookings?status_filter=...
  Future<List<RideBooking>> getMyBookings({String? statusFilter}) async {
    final res = await _api.get('/rides/my/bookings', queryParameters: {
      if (statusFilter != null) 'status_filter': statusFilter,
    });
    final list = unwrap(res) as List;
    return list.map((b) => RideBooking.fromJson(b)).toList();
  }

  /// GET /rides/my/occupied-slots?target_date=YYYY-MM-DD&mode=driver|passenger
  Future<List<Map<String, dynamic>>> getMyOccupiedSlots({
    required String targetDate,
    required String mode,
    int? timezoneOffsetMinutes,
  }) async {
    final res = await _api.get('/rides/my/occupied-slots', queryParameters: {
      'target_date': targetDate,
      'mode': mode,
      if (timezoneOffsetMinutes != null)
        'timezone_offset_minutes': timezoneOffsetMinutes,
    });
    final payload = unwrap(res);
    if (payload is Map<String, dynamic>) {
      final slots = payload['slots'];
      if (slots is List) {
        return slots
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
      }
    }
    return const <Map<String, dynamic>>[];
  }

  /// PUT /rides/bookings/{id}/cancel
  Future<RideBooking> cancelBooking(String bookingId, {String? reason}) async {
    final res = await _api.put('/rides/bookings/$bookingId/cancel', data: {
      if (reason != null) 'reason': reason,
    });
    return RideBooking.fromJson(unwrap(res));
  }

  /// PUT /rides/bookings/{id}/pickup-complete
  Future<RideBooking> markBookingPickupComplete(String bookingId) async {
    final res = await _api.put('/rides/bookings/$bookingId/pickup-complete');
    return RideBooking.fromJson(unwrap(res));
  }

  /// PUT /rides/bookings/{id}/dropoff-complete
  Future<RideBooking> markBookingDropoffComplete(String bookingId) async {
    final res = await _api.put('/rides/bookings/$bookingId/dropoff-complete');
    return RideBooking.fromJson(unwrap(res));
  }

  /// GET /rides/my/stats/passenger
  Future<PassengerBookingHistory> getPassengerStats() async {
    final res = await _api.get('/rides/my/stats/passenger');
    return PassengerBookingHistory.fromJson(unwrap(res));
  }

  // ── Ride Request endpoints (passenger→driver) ─────────

  /// POST /rides/requests — Passenger creates a ride request
  Future<Map<String, dynamic>> createRideRequest({
    required String origin,
    required double originLat,
    required double originLng,
    required String destination,
    required double destinationLat,
    required double destinationLng,
    required String departureTime,
    int seatsNeeded = 1,
    double? maxBudget,
  }) async {
    final res = await _api.post('/rides/requests', data: {
      'origin': origin,
      'destination': destination,
      'origin_lat': originLat,
      'origin_lng': originLng,
      'destination_lat': destinationLat,
      'destination_lng': destinationLng,
      'seats_needed': seatsNeeded,
      'departure_time': departureTime,
      if (maxBudget != null) 'max_budget': maxBudget,
    });
    return unwrap(res) as Map<String, dynamic>;
  }

  /// GET /rides/requests/nearby — Driver gets nearby ride requests
  Future<List<Map<String, dynamic>>> getNearbyRideRequests({
    required double lat,
    required double lng,
    double radiusKm = 10.0,
  }) async {
    final res = await _api.get('/rides/requests/nearby', queryParameters: {
      'lat': lat,
      'lng': lng,
      'radius_km': radiusKm,
    });
    final list = unwrap(res) as List;
    return list.cast<Map<String, dynamic>>();
  }

  /// GET /rides/requests/my — Passenger gets their own requests
  Future<List<Map<String, dynamic>>> getMyRideRequests() async {
    final res = await _api.get('/rides/requests/my');
    final list = unwrap(res) as List;
    return list.cast<Map<String, dynamic>>();
  }

  /// PUT /rides/requests/{id}/accept — Driver accepts a request
  Future<Map<String, dynamic>> acceptRideRequest(String requestId) async {
    final res = await _api.put('/rides/requests/$requestId/accept');
    return unwrap(res) as Map<String, dynamic>;
  }

  /// PUT /rides/requests/{id}/cancel — Cancel a ride request
  Future<Map<String, dynamic>> cancelRideRequest(String requestId) async {
    final res = await _api.put('/rides/requests/$requestId/cancel');
    return unwrap(res) as Map<String, dynamic>;
  }

  // ── Fare Calculator endpoint ──────────────────────────

  /// POST /rides/fare-estimate — Get server-calculated fare breakdown
  Future<Map<String, dynamic>> getFareEstimate({
    required double distanceKm,
    int totalSeats = 4,
    double? durationMinutes,
    double? petrolPrice,
    double? fuelAverage,
  }) async {
    final res = await _api.post('/rides/fare-estimate', data: {
      'distance_km': distanceKm,
      'total_seats': totalSeats,
      if (durationMinutes != null) 'duration_minutes': durationMinutes,
      if (petrolPrice != null) 'petrol_price': petrolPrice,
      if (fuelAverage != null) 'fuel_average': fuelAverage,
    });
    return unwrap(res) as Map<String, dynamic>;
  }
}
