import 'dart:convert';

String _normalizeRideStatus(String? raw) {
  final status = (raw ?? '').trim().toLowerCase();
  switch (status) {
    case 'scheduled':
      return 'open';
    case 'ongoing':
    case 'inprogress':
    case 'in-progress':
      return 'in_progress';
    case 'open':
    case 'in_progress':
    case 'completed':
    case 'cancelled':
      return status;
    default:
      return status.isEmpty ? 'open' : status;
  }
}

String _normalizeBookingStatus(String? raw) {
  final status = (raw ?? '').trim().toLowerCase();
  switch (status) {
    case 'reserved':
    case 'confirmed':
      return 'booked';
    case 'canceled':
      return 'cancelled';
    case 'booked':
    case 'cancelled':
    case 'completed':
      return status;
    default:
      return status.isEmpty ? 'booked' : status;
  }
}

String _defaultRideDisplayStatus(String status, int availableSeats) {
  switch (status) {
    case 'open':
      return availableSeats <= 0 ? 'All Seats Booked' : 'Open';
    case 'in_progress':
      return 'Ride Started';
    case 'completed':
      return 'Ride Completed';
    case 'cancelled':
      return 'Ride Cancelled';
    default:
      return status.replaceAll('_', ' ');
  }
}

double? _toNullableDouble(dynamic value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  return double.tryParse(value.toString());
}

int? _toNullableInt(dynamic value) {
  if (value == null) return null;
  if (value is int) return value;
  return int.tryParse(value.toString());
}

class RideRouteStop {
  final int order;
  final String bookingId;
  final String eventType; // pickup | dropoff
  final double? lat;
  final double? lng;
  final String? address;

  RideRouteStop({
    required this.order,
    required this.bookingId,
    required this.eventType,
    this.lat,
    this.lng,
    this.address,
  });

  factory RideRouteStop.fromJson(Map<String, dynamic> json) {
    final orderRaw = json['order'];
    final parsedOrder = orderRaw is int
        ? orderRaw
        : int.tryParse((orderRaw ?? '').toString()) ?? 0;
    return RideRouteStop(
      order: parsedOrder,
      bookingId: (json['booking_id'] ?? '').toString(),
      eventType: (json['event_type'] ?? '').toString().toLowerCase(),
      lat: _toNullableDouble(json['lat']),
      lng: _toNullableDouble(json['lng']),
      address: json['address']?.toString(),
    );
  }
}

class RideRouteAlternative {
  final String key;
  final String label;
  final bool isOptimal;
  final double distanceKm;
  final int durationMinutes;
  final String? polyline;
  final String? summary;
  final List<RideRouteStop> stopSequence;

  RideRouteAlternative({
    required this.key,
    required this.label,
    required this.isOptimal,
    required this.distanceKm,
    required this.durationMinutes,
    this.polyline,
    this.summary,
    this.stopSequence = const [],
  });

  factory RideRouteAlternative.fromJson(Map<String, dynamic> json) {
    final durationRaw = json['duration_minutes'];
    final durationMinutes = durationRaw is int
        ? durationRaw
        : int.tryParse((durationRaw ?? '').toString()) ?? 0;

    final stopsRaw = json['stop_sequence'];
    final stops = (stopsRaw is List)
        ? stopsRaw
            .whereType<Map>()
            .map((e) => RideRouteStop.fromJson(Map<String, dynamic>.from(e)))
            .toList()
        : const <RideRouteStop>[];

    return RideRouteAlternative(
      key: (json['key'] ?? '').toString(),
      label: (json['label'] ?? 'Route').toString(),
      isOptimal: json['is_optimal'] == true,
      distanceKm: _toNullableDouble(json['distance_km']) ?? 0.0,
      durationMinutes: durationMinutes,
      polyline: json['polyline']?.toString(),
      summary: json['summary']?.toString(),
      stopSequence: stops,
    );
  }
}

class RideExecutionProgress {
  final int activeBookings;
  final int completedBookings;
  final int totalStops;
  final int completedStops;
  final double completionPct;
  final int? nextStopOrder;
  final String? nextStopType;
  final String? nextStopBookingId;

  RideExecutionProgress({
    required this.activeBookings,
    required this.completedBookings,
    required this.totalStops,
    required this.completedStops,
    required this.completionPct,
    this.nextStopOrder,
    this.nextStopType,
    this.nextStopBookingId,
  });

  factory RideExecutionProgress.fromJson(Map<String, dynamic> json) {
    final nextStop = json['next_stop'];
    final nextMap = nextStop is Map
        ? Map<String, dynamic>.from(nextStop)
        : const <String, dynamic>{};

    return RideExecutionProgress(
      activeBookings: _toNullableInt(json['active_bookings']) ?? 0,
      completedBookings: _toNullableInt(json['completed_bookings']) ?? 0,
      totalStops: _toNullableInt(json['total_stops']) ?? 0,
      completedStops: _toNullableInt(json['completed_stops']) ?? 0,
      completionPct: _toNullableDouble(json['completion_pct']) ?? 0.0,
      nextStopOrder: _toNullableInt(nextMap['order']),
      nextStopType: nextMap['event_type']?.toString(),
      nextStopBookingId: nextMap['booking_id']?.toString(),
    );
  }
}

class Ride {
  final String id;
  final String driverId;
  final String? vehicleId;
  final String origin;
  final String destination;
  final String departureTime;
  final int? estimatedDuration;
  final int availableSeats;
  final int? totalSeats;
  final double pricePerSeat;
  final double totalEarnings;
  final String status; // open, in_progress, completed, cancelled
  final String? displayStatus;
  final String? displaySubstatus;
  final bool? canDriverStart;
  final bool? canDriverComplete;
  final bool? canDriverCancel;
  final String? createdAt;
  final String? updatedAt;
  final double? routeDistanceKm;
  final Map<String, dynamic>? recurrence;
  final String? recurringScheduleId;
  final String? recurringStartDate;
  final String? recurringEndDate;

  // Map/geo fields
  final double? originLat;
  final double? originLng;
  final double? destinationLat;
  final double? destinationLng;
  final String? polyline;
  final int routePlanVersion;
  final String? routeSelectedKey;
  final List<RideRouteAlternative>? routeAlternatives;
  final RideDriverSummary? driverSummary;
  final RideExecutionProgress? executionProgress;

  // Expanded fields (from RideWithBookingsPublic)
  final List<RideBooking>? bookings;
  final int? bookedSeatsCount;

  Ride({
    required this.id,
    required this.driverId,
    this.vehicleId,
    required this.origin,
    required this.destination,
    required this.departureTime,
    this.estimatedDuration,
    required this.availableSeats,
    this.totalSeats,
    required this.pricePerSeat,
    this.totalEarnings = 0,
    required this.status,
    this.displayStatus,
    this.displaySubstatus,
    this.canDriverStart,
    this.canDriverComplete,
    this.canDriverCancel,
    this.createdAt,
    this.updatedAt,
    this.routeDistanceKm,
    this.recurrence,
    this.recurringScheduleId,
    this.recurringStartDate,
    this.recurringEndDate,
    this.originLat,
    this.originLng,
    this.destinationLat,
    this.destinationLng,
    this.polyline,
    this.routePlanVersion = 0,
    this.routeSelectedKey,
    this.routeAlternatives,
    this.driverSummary,
    this.executionProgress,
    this.bookings,
    this.bookedSeatsCount,
  });

  factory Ride.fromJson(Map<String, dynamic> json) {
    final parsedAvailableSeats =
        json['available_seats'] ?? json['seats_available'] ?? 0;
    final availableSeats = parsedAvailableSeats is int
        ? parsedAvailableSeats
        : int.tryParse(parsedAvailableSeats.toString()) ?? 0;
    final parsedBookedSeatsCount = json['booked_seats_count'];
    final bookedSeatsCount = parsedBookedSeatsCount is int
        ? parsedBookedSeatsCount
        : int.tryParse((parsedBookedSeatsCount ?? '').toString());
    Map<String, dynamic>? recurrence;
    final recurrenceRaw = json['recurrence'];
    if (recurrenceRaw is Map) {
      recurrence = Map<String, dynamic>.from(recurrenceRaw);
    } else if (recurrenceRaw is String) {
      final raw = recurrenceRaw.trim();
      if (raw.isNotEmpty && raw.startsWith('{')) {
        try {
          final decoded = jsonDecode(raw);
          if (decoded is Map) {
            recurrence = Map<String, dynamic>.from(decoded);
          }
        } catch (_) {
          recurrence = null;
        }
      }
    }
    String? recurringScheduleId = recurrence?['schedule_id']?.toString().trim();
    if (recurringScheduleId == null || recurringScheduleId.isEmpty) {
      final fallback = json['recurring_schedule_id']?.toString().trim() ?? '';
      recurringScheduleId = fallback.isEmpty ? null : fallback;
    }
    String? recurringStartDate =
        (json['recurring_start_date'] ?? recurrence?['start_date'])?.toString();
    if (recurringStartDate != null && recurringStartDate.trim().isEmpty) {
      recurringStartDate = null;
    }
    String? recurringEndDate =
        (json['recurring_end_date'] ?? recurrence?['end_date'])?.toString();
    if (recurringEndDate != null && recurringEndDate.trim().isEmpty) {
      recurringEndDate = null;
    }
    final normalizedStatus =
        _normalizeRideStatus((json['status'] ?? 'open').toString());

    return Ride(
      id: json['id'] ?? '',
      driverId: json['driver_id'] ?? '',
      vehicleId: json['vehicle_id'],
      origin: json['origin'] ?? json['start_point_address'] ?? '',
      destination: json['destination'] ?? json['end_point_address'] ?? '',
      departureTime: json['departure_time'] ?? '',
      estimatedDuration:
          json['estimated_duration'] ?? json['estimated_duration_minutes'],
      availableSeats: availableSeats,
      totalSeats:
          json['total_seats'] ?? json['seats_total'] ?? json['seats_offered'],
      pricePerSeat: (json['price_per_seat'] ?? 0).toDouble(),
      totalEarnings: (json['total_earnings'] ?? 0).toDouble(),
      status: normalizedStatus,
      displayStatus: json['display_status']?.toString(),
      displaySubstatus: json['display_substatus']?.toString(),
      canDriverStart: json['can_driver_start'] == true,
      canDriverComplete: json['can_driver_complete'] == true,
      canDriverCancel: json['can_driver_cancel'] == true,
      createdAt: json['created_at'],
      updatedAt: json['updated_at'],
      routeDistanceKm: json['route_distance_km']?.toDouble(),
      recurrence: recurrence,
      recurringScheduleId: recurringScheduleId,
      recurringStartDate: recurringStartDate,
      recurringEndDate: recurringEndDate,
      originLat: (json['origin_lat'] ?? json['start_point_lat'])?.toDouble(),
      originLng: (json['origin_lng'] ?? json['start_point_lng'])?.toDouble(),
      destinationLat:
          (json['destination_lat'] ?? json['end_point_lat'])?.toDouble(),
      destinationLng:
          (json['destination_lng'] ?? json['end_point_lng'])?.toDouble(),
      polyline: json['polyline'],
      routePlanVersion: (json['route_plan_version'] is int)
          ? json['route_plan_version'] as int
          : int.tryParse((json['route_plan_version'] ?? '').toString()) ?? 0,
      routeSelectedKey: json['route_selected_key']?.toString(),
      routeAlternatives: (json['route_alternatives'] as List<dynamic>?)
          ?.whereType<Map>()
          .map((e) =>
              RideRouteAlternative.fromJson(Map<String, dynamic>.from(e)))
          .toList(),
      driverSummary: json['driver_summary'] is Map<String, dynamic>
          ? RideDriverSummary.fromJson(json['driver_summary'])
          : null,
      executionProgress: json['execution_progress'] is Map
          ? RideExecutionProgress.fromJson(
              Map<String, dynamic>.from(json['execution_progress']),
            )
          : null,
      bookings: (json['bookings'] as List<dynamic>?)
          ?.map((b) => RideBooking.fromJson(b))
          .toList(),
      bookedSeatsCount: bookedSeatsCount,
    );
  }

  Map<String, dynamic> toCreateJson() => {
        'origin': origin,
        'destination': destination,
        'origin_lat': originLat,
        'origin_lng': originLng,
        'destination_lat': destinationLat,
        'destination_lng': destinationLng,
        'departure_time': departureTime,
        'available_seats': availableSeats,
        if (totalSeats != null) 'total_seats': totalSeats,
        'price_per_seat': pricePerSeat,
        'vehicle_id': vehicleId,
        if (estimatedDuration != null) 'estimated_duration': estimatedDuration,
        if (routeDistanceKm != null) 'route_distance_km': routeDistanceKm,
        if (polyline != null) 'polyline': polyline,
      };

  DateTime? get departureDatetime {
    final parsed = DateTime.tryParse(departureTime);
    if (parsed == null) return null;
    return parsed.isUtc ? parsed.toLocal() : parsed;
  }

  String get effectiveDisplayStatus {
    final value = displayStatus?.trim();
    if (value != null && value.isNotEmpty) return value;
    return _defaultRideDisplayStatus(status, availableSeats);
  }

  bool get isActive => status == 'open' || status == 'in_progress';

  bool get isRecurringRide {
    final id = (recurringScheduleId ?? '').trim();
    return id.isNotEmpty;
  }

  int get remainingSeats => availableSeats - (bookedSeatsCount ?? 0);

  /// Whether this ride has full geo data for map display
  bool get hasGeoData =>
      originLat != null &&
      originLng != null &&
      destinationLat != null &&
      destinationLng != null;
}

class RideBooking {
  final String id;
  final String rideId;
  final String passengerId;
  final String? passengerName;
  final String? passengerPhone;
  final String? passengerProfilePhoto;
  final int bookedSeats;
  final double totalPrice;
  final double? individualFare;
  final String bookingTime;
  final DateTime? estimatedPickupTime;
  final double? segmentKm;
  final double? pickupPct;
  final double? dropoffPct;
  final double? pickupRouteKm;
  final double? dropoffRouteKm;
  final double? ratePerKmUsed;
  final double? pickupLat;
  final double? pickupLng;
  final String? pickupAddress;
  final String? pickupPlaceId;
  final double? dropoffLat;
  final double? dropoffLng;
  final String? dropoffAddress;
  final String? dropoffPlaceId;
  final int? pickupStopOrder;
  final int? dropoffStopOrder;
  final DateTime? plannedPickupEta;
  final DateTime? plannedDropoffEta;
  final DateTime? actualPickupTime;
  final DateTime? actualDropoffTime;
  final bool pickupCompleted;
  final bool dropoffCompleted;
  final String? bookingStage;
  final int routePlanVersion;
  final String status; // booked, cancelled, completed
  final String? normalizedStatus;
  final String? displayStatus;
  final String? displaySubstatus;
  final bool? canPassengerCancel;
  final String paymentStatus; // pending, paid, refunded
  final String? cancellationTime;
  final String? cancellationReason;

  // Expanded field from RideBookingWithRidePublic
  final Ride? ride;

  RideBooking({
    required this.id,
    required this.rideId,
    required this.passengerId,
    this.passengerName,
    this.passengerPhone,
    this.passengerProfilePhoto,
    required this.bookedSeats,
    required this.totalPrice,
    this.individualFare,
    required this.bookingTime,
    this.estimatedPickupTime,
    this.segmentKm,
    this.pickupPct,
    this.dropoffPct,
    this.pickupRouteKm,
    this.dropoffRouteKm,
    this.ratePerKmUsed,
    this.pickupLat,
    this.pickupLng,
    this.pickupAddress,
    this.pickupPlaceId,
    this.dropoffLat,
    this.dropoffLng,
    this.dropoffAddress,
    this.dropoffPlaceId,
    this.pickupStopOrder,
    this.dropoffStopOrder,
    this.plannedPickupEta,
    this.plannedDropoffEta,
    this.actualPickupTime,
    this.actualDropoffTime,
    this.pickupCompleted = false,
    this.dropoffCompleted = false,
    this.bookingStage,
    this.routePlanVersion = 0,
    required this.status,
    this.normalizedStatus,
    this.displayStatus,
    this.displaySubstatus,
    this.canPassengerCancel,
    required this.paymentStatus,
    this.cancellationTime,
    this.cancellationReason,
    this.ride,
  });

  factory RideBooking.fromJson(Map<String, dynamic> json) {
    final normalized = _normalizeBookingStatus(
      (json['normalized_status'] ?? json['status'] ?? 'booked').toString(),
    );
    final actualPickupTime = json['actual_pickup_time'] != null
        ? DateTime.tryParse(json['actual_pickup_time'].toString())
        : null;
    final actualDropoffTime = json['actual_dropoff_time'] != null
        ? DateTime.tryParse(json['actual_dropoff_time'].toString())
        : null;
    final pickupCompleted =
        json['pickup_completed'] == true || actualPickupTime != null;
    final dropoffCompleted = json['dropoff_completed'] == true ||
        actualDropoffTime != null ||
        normalized == 'completed';

    return RideBooking(
      id: json['id'] ?? '',
      rideId: json['ride_id'] ?? '',
      passengerId: json['passenger_id'] ?? '',
      passengerName: json['passenger_name']?.toString(),
      passengerPhone: json['passenger_phone']?.toString(),
      passengerProfilePhoto: json['passenger_profile_photo']?.toString(),
      bookedSeats: json['booked_seats'] ?? 1,
      totalPrice: (json['total_price'] ?? 0).toDouble(),
      individualFare: _toNullableDouble(json['individual_fare']),
      bookingTime: json['booking_time'] ?? '',
      estimatedPickupTime: json['estimated_pickup_time'] != null
          ? DateTime.tryParse(json['estimated_pickup_time'].toString())
          : null,
      segmentKm: _toNullableDouble(json['segment_km']),
      pickupPct: _toNullableDouble(json['pickup_pct']),
      dropoffPct: _toNullableDouble(json['dropoff_pct']),
      pickupRouteKm: _toNullableDouble(json['pickup_route_km']),
      dropoffRouteKm: _toNullableDouble(json['dropoff_route_km']),
      ratePerKmUsed: _toNullableDouble(json['rate_per_km_used']),
      pickupLat: _toNullableDouble(json['pickup_lat']),
      pickupLng: _toNullableDouble(json['pickup_lng']),
      pickupAddress: json['pickup_address']?.toString(),
      pickupPlaceId: json['pickup_place_id']?.toString(),
      dropoffLat: _toNullableDouble(json['dropoff_lat']),
      dropoffLng: _toNullableDouble(json['dropoff_lng']),
      dropoffAddress: json['dropoff_address']?.toString(),
      dropoffPlaceId: json['dropoff_place_id']?.toString(),
      pickupStopOrder: json['pickup_stop_order'] is int
          ? json['pickup_stop_order'] as int
          : int.tryParse((json['pickup_stop_order'] ?? '').toString()),
      dropoffStopOrder: json['dropoff_stop_order'] is int
          ? json['dropoff_stop_order'] as int
          : int.tryParse((json['dropoff_stop_order'] ?? '').toString()),
      plannedPickupEta: json['planned_pickup_eta'] != null
          ? DateTime.tryParse(json['planned_pickup_eta'].toString())
          : null,
      plannedDropoffEta: json['planned_dropoff_eta'] != null
          ? DateTime.tryParse(json['planned_dropoff_eta'].toString())
          : null,
      actualPickupTime: actualPickupTime,
      actualDropoffTime: actualDropoffTime,
      pickupCompleted: pickupCompleted,
      dropoffCompleted: dropoffCompleted,
      bookingStage: json['booking_stage']?.toString(),
      routePlanVersion: json['route_plan_version'] is int
          ? json['route_plan_version'] as int
          : int.tryParse((json['route_plan_version'] ?? '').toString()) ?? 0,
      status: normalized,
      normalizedStatus: normalized,
      displayStatus: json['display_status']?.toString(),
      displaySubstatus: json['display_substatus']?.toString(),
      canPassengerCancel: json['can_passenger_cancel'] == true,
      paymentStatus: json['payment_status'] ?? 'pending',
      cancellationTime: json['cancellation_time'],
      cancellationReason: json['cancellation_reason'],
      ride: json['ride'] != null ? Ride.fromJson(json['ride']) : null,
    );
  }

  String get effectiveDisplayStatus {
    final value = displayStatus?.trim();
    if (value != null && value.isNotEmpty) return value;
    if (status == 'cancelled') return 'Passenger Cancelled';
    if (ride?.status == 'cancelled') return 'Driver Cancelled';
    if (status == 'completed' || ride?.status == 'completed') {
      return 'Ride Completed';
    }
    if (status == 'booked') return 'Booked';
    return status;
  }

  String get effectiveStage {
    final stage = (bookingStage ?? '').trim().toLowerCase();
    if (stage.isNotEmpty) return stage;
    if (isCancelled) return 'cancelled';
    if (dropoffCompleted || isCompleted) return 'dropped_off';
    if (pickupCompleted) return 'onboard';
    return 'awaiting_pickup';
  }

  bool get hasPickedUp => pickupCompleted || actualPickupTime != null;
  bool get hasDroppedOff =>
      dropoffCompleted || actualDropoffTime != null || isCompleted;

  bool get canCancel => canPassengerCancel ?? isActive;

  bool get isActive =>
      status == 'booked' || status == 'reserved' || status == 'confirmed';
  bool get isCancelled => status == 'cancelled';
  bool get isCompleted => status == 'completed';
}

class RideDriverSummary {
  final String driverUserId;
  final String name;
  final String? profilePhoto;
  final double? ratingAvg;
  final int completedRides;
  final String? carName;
  final String? vehiclePlate;

  RideDriverSummary({
    required this.driverUserId,
    required this.name,
    this.profilePhoto,
    this.ratingAvg,
    this.completedRides = 0,
    this.carName,
    this.vehiclePlate,
  });

  factory RideDriverSummary.fromJson(Map<String, dynamic> json) {
    final ratingRaw = json['rating_avg'];
    final ridesRaw = json['completed_rides'];

    return RideDriverSummary(
      driverUserId: (json['driver_user_id'] ?? '').toString(),
      name: (json['name'] ?? 'Driver').toString(),
      profilePhoto: json['profile_photo']?.toString(),
      ratingAvg: ratingRaw == null ? null : (ratingRaw as num).toDouble(),
      completedRides: ridesRaw is int
          ? ridesRaw
          : int.tryParse((ridesRaw ?? '0').toString()) ?? 0,
      carName: json['car_name']?.toString(),
      vehiclePlate: json['vehicle_plate']?.toString(),
    );
  }
}

class RideStatistics {
  final int totalRidesCreated;
  final int totalRidesCompleted;
  final int totalRidesCancelled;
  final int totalRidesAllExcludingDraft;
  final int scheduledRidesCurrent;
  final double totalEarnings;
  final double averageOccupancyRate;
  final double carbonFootprintSavedKg;

  RideStatistics({
    required this.totalRidesCreated,
    required this.totalRidesCompleted,
    required this.totalRidesCancelled,
    required this.totalRidesAllExcludingDraft,
    required this.scheduledRidesCurrent,
    required this.totalEarnings,
    required this.averageOccupancyRate,
    required this.carbonFootprintSavedKg,
  });

  factory RideStatistics.fromJson(Map<String, dynamic> json) {
    return RideStatistics(
      totalRidesCreated: json['total_rides_created'] ?? 0,
      totalRidesCompleted: json['total_rides_completed'] ?? 0,
      totalRidesCancelled: json['total_rides_cancelled'] ?? 0,
      totalRidesAllExcludingDraft: json['total_rides_all_excluding_draft'] ??
          json['total_rides_created'] ??
          0,
      scheduledRidesCurrent: json['scheduled_rides_current'] ?? 0,
      totalEarnings: (json['total_earnings'] ?? 0).toDouble(),
      averageOccupancyRate: (json['average_occupancy_rate'] ?? 0).toDouble(),
      carbonFootprintSavedKg:
          (json['carbon_footprint_saved_kg'] ?? 0).toDouble(),
    );
  }
}

class PassengerBookingHistory {
  final int totalBookings;
  final double totalSpent;
  final int activeBookings;
  final int completedRides;
  final int cancelledBookings;
  final double carbonFootprintSavedKg;

  PassengerBookingHistory({
    required this.totalBookings,
    required this.totalSpent,
    required this.activeBookings,
    required this.completedRides,
    required this.cancelledBookings,
    this.carbonFootprintSavedKg = 0.0,
  });

  factory PassengerBookingHistory.fromJson(Map<String, dynamic> json) {
    return PassengerBookingHistory(
      totalBookings: json['total_bookings'] ?? 0,
      totalSpent: (json['total_spent'] ?? 0).toDouble(),
      activeBookings: json['active_bookings'] ?? 0,
      completedRides: json['completed_rides'] ?? 0,
      cancelledBookings: json['cancelled_bookings'] ?? 0,
      carbonFootprintSavedKg:
          (json['carbon_footprint_saved_kg'] ?? 0).toDouble(),
    );
  }
}
