import 'api_client.dart';
import '../constants/app_constants.dart';

class ScheduleService {
  final ApiClient _api = ApiClient();

  /// POST /api/v2/rides/schedule — create recurring schedule
  Future<Map<String, dynamic>> createSchedule({
    required List<String> daysOfWeek,
    required String rideTime,
    required double startLat,
    required double startLng,
    required String startAddress,
    required double endLat,
    required double endLng,
    required String endAddress,
    required int seatsOffered,
    required double basePrice,
    required String startDate,
    required String endDate,
    int bufferSeats = 0,
  }) async {
    final res = await _api.dio.post(
      '${AppConstants.baseUrlV2}/rides/schedule',
      data: {
        'days_of_week': daysOfWeek,
        'ride_time': rideTime,
        'start_point': {
          'lat': startLat,
          'lng': startLng,
          'address': startAddress,
        },
        'end_point': {
          'lat': endLat,
          'lng': endLng,
          'address': endAddress,
        },
        'seats_offered': seatsOffered,
        'buffer_seats': bufferSeats,
        'base_price': basePrice,
        'start_date': startDate,
        'end_date': endDate,
      },
    );
    return Map<String, dynamic>.from(res.data);
  }

  /// GET /api/v2/rides/schedule/my-schedules — get my schedules
  Future<List<Map<String, dynamic>>> getMySchedules(
      {bool activeOnly = true}) async {
    final res = await _api.dio.get(
      '${AppConstants.baseUrlV2}/rides/schedule/my-schedules',
      queryParameters: {'active_only': activeOnly},
    );
    return List<Map<String, dynamic>>.from(res.data ?? []);
  }

  /// POST /api/v2/rides/schedule/discover — discover recurring schedules
  Future<List<Map<String, dynamic>>> discoverSchedules({
    required double originLat,
    required double originLng,
    required String originAddress,
    required double destinationLat,
    required double destinationLng,
    required String destinationAddress,
    required String passengerFromDate,
    required String passengerUntilDate,
    required String departureWindowStart,
    required String departureWindowEnd,
    int minSeats = 1,
    int? driverTotalSeats,
    double radiusKm = 5.0,
    double? maxPrice,
  }) async {
    final res = await _api.dio.post(
      '${AppConstants.baseUrlV2}/rides/schedule/discover',
      data: {
        'origin': {
          'lat': originLat,
          'lng': originLng,
          'address': originAddress,
        },
        'destination': {
          'lat': destinationLat,
          'lng': destinationLng,
          'address': destinationAddress,
        },
        'passenger_from_date': passengerFromDate,
        'passenger_until_date': passengerUntilDate,
        'departure_window_start': departureWindowStart,
        'departure_window_end': departureWindowEnd,
        'min_seats': minSeats,
        if (driverTotalSeats != null) 'driver_total_seats': driverTotalSeats,
        'radius_km': radiusKm,
        if (maxPrice != null) 'max_price': maxPrice,
      },
    );
    return List<Map<String, dynamic>>.from(res.data ?? []);
  }

  /// PUT /api/v2/rides/schedule/{scheduleId} — update recurring schedule
  Future<Map<String, dynamic>> updateSchedule({
    required String scheduleId,
    required List<String> daysOfWeek,
    required String rideTime,
    required double startLat,
    required double startLng,
    required String startAddress,
    required double endLat,
    required double endLng,
    required String endAddress,
    required int seatsOffered,
    required int bufferSeats,
    required double basePrice,
    required String startDate,
    required String endDate,
    bool isActive = true,
    bool purgeFutureRides = true,
  }) async {
    final res = await _api.dio.put(
      '${AppConstants.baseUrlV2}/rides/schedule/$scheduleId',
      queryParameters: {'purge_future_rides': purgeFutureRides},
      data: {
        'days_of_week': daysOfWeek,
        'ride_time': rideTime,
        'start_point': {
          'lat': startLat,
          'lng': startLng,
          'address': startAddress,
        },
        'end_point': {
          'lat': endLat,
          'lng': endLng,
          'address': endAddress,
        },
        'seats_offered': seatsOffered,
        'buffer_seats': bufferSeats,
        'base_price': basePrice,
        'start_date': startDate,
        'end_date': endDate,
        'is_active': isActive,
      },
    );
    return Map<String, dynamic>.from(res.data);
  }

  /// DELETE /api/v2/rides/schedule/{scheduleId} — deactivate recurring schedule
  Future<Map<String, dynamic>> deleteSchedule(
    String scheduleId, {
    bool purgeFutureRides = true,
  }) async {
    final res = await _api.dio.delete(
      '${AppConstants.baseUrlV2}/rides/schedule/$scheduleId',
      queryParameters: {'purge_future_rides': purgeFutureRides},
    );
    return Map<String, dynamic>.from(res.data);
  }

  /// POST /api/v2/rides/schedule/{scheduleId}/book-series
  Future<Map<String, dynamic>> bookRecurringSeries({
    required String scheduleId,
    required String passengerFromDate,
    required String passengerUntilDate,
    required String departureWindowStart,
    required String departureWindowEnd,
    required int seatsReserved,
    required double pickupLat,
    required double pickupLng,
    required String pickupAddress,
    required double dropoffLat,
    required double dropoffLng,
    required String dropoffAddress,
  }) async {
    final res = await _api.dio.post(
      '${AppConstants.baseUrlV2}/rides/schedule/$scheduleId/book-series',
      data: {
        'passenger_from_date': passengerFromDate,
        'passenger_until_date': passengerUntilDate,
        'departure_window_start': departureWindowStart,
        'departure_window_end': departureWindowEnd,
        'seats_reserved': seatsReserved,
        'pickup_point': {
          'lat': pickupLat,
          'lng': pickupLng,
          'address': pickupAddress,
        },
        'dropoff_point': {
          'lat': dropoffLat,
          'lng': dropoffLng,
          'address': dropoffAddress,
        },
      },
    );
    return Map<String, dynamic>.from(res.data ?? {});
  }

  /// GET /api/v2/rides/schedule/my-home/driver
  Future<List<Map<String, dynamic>>> getDriverRecurringHome() async {
    final res = await _api.dio.get(
      '${AppConstants.baseUrlV2}/rides/schedule/my-home/driver',
    );
    return List<Map<String, dynamic>>.from(res.data ?? []);
  }

  /// GET /api/v2/rides/schedule/my-home/passenger
  Future<List<Map<String, dynamic>>> getPassengerRecurringHome() async {
    final res = await _api.dio.get(
      '${AppConstants.baseUrlV2}/rides/schedule/my-home/passenger',
    );
    return List<Map<String, dynamic>>.from(res.data ?? []);
  }

  /// GET /api/v2/rides/schedule/{scheduleId}/resolve-next
  Future<Map<String, dynamic>> resolveDriverScheduleNextRide(
      String scheduleId) async {
    final res = await _api.dio.get(
      '${AppConstants.baseUrlV2}/rides/schedule/$scheduleId/resolve-next',
    );
    return Map<String, dynamic>.from(res.data ?? {});
  }

  /// GET /api/v2/rides/schedule/subscriptions/{subscriptionId}/resolve-next
  Future<Map<String, dynamic>> resolvePassengerSubscriptionNextRide(
      String subscriptionId) async {
    final res = await _api.dio.get(
      '${AppConstants.baseUrlV2}/rides/schedule/subscriptions/$subscriptionId/resolve-next',
    );
    return Map<String, dynamic>.from(res.data ?? {});
  }

  /// DELETE /api/v2/rides/schedule/subscriptions/{subscriptionId}
  Future<Map<String, dynamic>> cancelPassengerRecurringSeries(
    String subscriptionId, {
    String? reason,
  }) async {
    final res = await _api.dio.delete(
      '${AppConstants.baseUrlV2}/rides/schedule/subscriptions/$subscriptionId',
      queryParameters: {
        if (reason != null && reason.trim().isNotEmpty) 'reason': reason.trim(),
      },
    );
    return Map<String, dynamic>.from(res.data ?? {});
  }
}
