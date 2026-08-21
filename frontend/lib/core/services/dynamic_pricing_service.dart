/// Dynamic Pricing Service — Flutter client for Modules 1-4 backend APIs.
///
/// Exposes:
///   - getFuelConfig()         → current petrol price & rate_per_km
///   - updateFuelConfig()      → admin: update petrol price
///   - quickFareEstimate()     → single-passenger fare preview
///   - checkRouteEligibility() → is passenger on driver's route?
///   - getRideFares()          → full multi-passenger fare breakdown
///   - getPickupEtas()         → per-passenger pickup ETA computation
///   - getBookingFareDetails() → per-booking fare + ETA for display
library;

import '../services/api_client.dart';

// ── Data models ──────────────────────────────────────────────────────────────

class FuelConfig {
  final double petrolPricePerLitre;
  final double fuelAvgKmPerLitre;
  final double platformFeePct;
  final double driverMarginPct;
  final double minFarePkr;
  final double baseFarePkr;
  final double avgSpeedKmh;
  final double fuelCostPerKm;
  final double ratePerKm;

  const FuelConfig({
    required this.petrolPricePerLitre,
    required this.fuelAvgKmPerLitre,
    required this.platformFeePct,
    required this.driverMarginPct,
    required this.minFarePkr,
    required this.baseFarePkr,
    required this.avgSpeedKmh,
    required this.fuelCostPerKm,
    required this.ratePerKm,
  });

  factory FuelConfig.fromJson(Map<String, dynamic> j) => FuelConfig(
        petrolPricePerLitre: (j['petrol_price_per_litre'] as num).toDouble(),
        fuelAvgKmPerLitre: (j['fuel_avg_km_per_litre'] as num).toDouble(),
        platformFeePct: (j['platform_fee_pct'] as num).toDouble(),
        driverMarginPct: (j['driver_margin_pct'] as num).toDouble(),
        minFarePkr: (j['min_fare_pkr'] as num).toDouble(),
        baseFarePkr: (j['base_fare_pkr'] as num).toDouble(),
        avgSpeedKmh: (j['avg_speed_kmh'] as num).toDouble(),
        fuelCostPerKm: (j['fuel_cost_per_km'] as num).toDouble(),
        ratePerKm: (j['rate_per_km'] as num).toDouble(),
      );

  String get ratePerKmDisplay => 'Rs ${ratePerKm.toStringAsFixed(1)}/km';
  String get petrolPriceDisplay => 'Rs ${petrolPricePerLitre.toStringAsFixed(0)}/L';
}


class RouteEligibilityResult {
  final bool isEligible;
  final String? rejectionReason;
  final double pickupPct;
  final double dropoffPct;
  final double pickupRouteKm;
  final double dropoffRouteKm;
  final double segmentKm;
  final double pickupPerpM;
  final double dropoffPerpM;

  const RouteEligibilityResult({
    required this.isEligible,
    this.rejectionReason,
    this.pickupPct = 0.0,
    this.dropoffPct = 1.0,
    this.pickupRouteKm = 0.0,
    this.dropoffRouteKm = 0.0,
    this.segmentKm = 0.0,
    this.pickupPerpM = 0.0,
    this.dropoffPerpM = 0.0,
  });

  factory RouteEligibilityResult.fromJson(Map<String, dynamic> j) =>
      RouteEligibilityResult(
        isEligible: j['is_eligible'] as bool,
        rejectionReason: j['rejection_reason'] as String?,
        pickupPct: (j['pickup_pct'] as num?)?.toDouble() ?? 0.0,
        dropoffPct: (j['dropoff_pct'] as num?)?.toDouble() ?? 1.0,
        pickupRouteKm: (j['pickup_route_km'] as num?)?.toDouble() ?? 0.0,
        dropoffRouteKm: (j['dropoff_route_km'] as num?)?.toDouble() ?? 0.0,
        segmentKm: (j['segment_km'] as num?)?.toDouble() ?? 0.0,
        pickupPerpM: (j['pickup_perp_m'] as num?)?.toDouble() ?? 0.0,
        dropoffPerpM: (j['dropoff_perp_m'] as num?)?.toDouble() ?? 0.0,
      );

  String get rejectionDisplayText {
    if (isEligible) return '';
    if (rejectionReason == null) return 'Not eligible for this ride';
    if (rejectionReason!.contains('pickup_off_route')) {
      return 'Your pickup point is too far from the driver\'s route';
    }
    if (rejectionReason!.contains('dropoff_off_route')) {
      return 'Your dropoff point is too far from the driver\'s route';
    }
    if (rejectionReason!.contains('time_mismatch')) {
      return 'Departure time is outside the ride\'s schedule window';
    }
    if (rejectionReason!.contains('backward')) {
      return 'Your pickup is after your dropoff on the route';
    }
    return 'Not on driver\'s route';
  }
}


class PassengerFareBreakdown {
  final String passengerId;
  final String requestId;
  final double segmentKm;
  final int seatsNeeded;
  final double baseSharePkr;
  final double distanceCostPkr;
  final double rawFarePkr;
  final double finalFarePkr;
  final double farePerSeatPkr;
  final double proportionPct;
  final double ratePerKmUsed;

  const PassengerFareBreakdown({
    required this.passengerId,
    required this.requestId,
    required this.segmentKm,
    required this.seatsNeeded,
    required this.baseSharePkr,
    required this.distanceCostPkr,
    required this.rawFarePkr,
    required this.finalFarePkr,
    required this.farePerSeatPkr,
    required this.proportionPct,
    required this.ratePerKmUsed,
  });

  factory PassengerFareBreakdown.fromJson(Map<String, dynamic> j) =>
      PassengerFareBreakdown(
        passengerId: j['passenger_id'] as String,
        requestId: j['request_id'] as String,
        segmentKm: (j['segment_km'] as num).toDouble(),
        seatsNeeded: j['seats_needed'] as int,
        baseSharePkr: (j['base_share_pkr'] as num).toDouble(),
        distanceCostPkr: (j['distance_cost_pkr'] as num).toDouble(),
        rawFarePkr: (j['raw_fare_pkr'] as num).toDouble(),
        finalFarePkr: (j['final_fare_pkr'] as num).toDouble(),
        farePerSeatPkr: (j['fare_per_seat_pkr'] as num).toDouble(),
        proportionPct: (j['proportion_pct'] as num).toDouble(),
        ratePerKmUsed: (j['rate_per_km_used'] as num).toDouble(),
      );

  String get fareDisplay => 'Rs ${finalFarePkr.toStringAsFixed(0)}';
  String get segmentDisplay => '${segmentKm.toStringAsFixed(1)} km';
  String get proportionDisplay => '${proportionPct.toStringAsFixed(1)}%';
}


class RideFaresBreakdown {
  final double totalRouteKm;
  final double totalPoolCostPkr;
  final double totalCollectedPkr;
  final double ratePerKmUsed;
  final List<PassengerFareBreakdown> passengerFares;

  const RideFaresBreakdown({
    required this.totalRouteKm,
    required this.totalPoolCostPkr,
    required this.totalCollectedPkr,
    required this.ratePerKmUsed,
    required this.passengerFares,
  });

  factory RideFaresBreakdown.fromJson(Map<String, dynamic> j) =>
      RideFaresBreakdown(
        totalRouteKm: (j['total_route_km'] as num).toDouble(),
        totalPoolCostPkr: (j['total_pool_cost_pkr'] as num).toDouble(),
        totalCollectedPkr: (j['total_collected_pkr'] as num).toDouble(),
        ratePerKmUsed: (j['rate_per_km_used'] as num).toDouble(),
        passengerFares: (j['passenger_fares'] as List)
            .map((e) => PassengerFareBreakdown.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}


class BookingFareDetails {
  final String bookingId;
  final String rideId;
  final String passengerId;
  final int seatsReserved;
  final double fare;
  final double? individualFare;
  final DateTime? estimatedPickupTime;
  final double? segmentKm;
  final double? pickupPct;
  final double? dropoffPct;
  final double? ratePerKmUsed;
  final String status;

  const BookingFareDetails({
    required this.bookingId,
    required this.rideId,
    required this.passengerId,
    required this.seatsReserved,
    required this.fare,
    this.individualFare,
    this.estimatedPickupTime,
    this.segmentKm,
    this.pickupPct,
    this.dropoffPct,
    this.ratePerKmUsed,
    required this.status,
  });

  factory BookingFareDetails.fromJson(Map<String, dynamic> j) =>
      BookingFareDetails(
        bookingId: j['booking_id'] as String,
        rideId: j['ride_id'] as String,
        passengerId: j['passenger_id'] as String,
        seatsReserved: j['seats_reserved'] as int,
        fare: (j['fare'] as num).toDouble(),
        individualFare: (j['individual_fare'] as num?)?.toDouble(),
        estimatedPickupTime: j['estimated_pickup_time'] != null
            ? DateTime.tryParse(j['estimated_pickup_time'] as String)
            : null,
        segmentKm: (j['segment_km'] as num?)?.toDouble(),
        pickupPct: (j['pickup_pct'] as num?)?.toDouble(),
        dropoffPct: (j['dropoff_pct'] as num?)?.toDouble(),
        ratePerKmUsed: (j['rate_per_km_used'] as num?)?.toDouble(),
        status: j['status'] as String,
      );

  String get fareDisplay =>
      'Rs ${(individualFare ?? fare).toStringAsFixed(0)}';

  String get pickupTimeDisplay {
    if (estimatedPickupTime == null) return 'TBD';
    final h = estimatedPickupTime!.hour;
    final m = estimatedPickupTime!.minute.toString().padLeft(2, '0');
    final period = h >= 12 ? 'PM' : 'AM';
    final h12 = h > 12 ? h - 12 : (h == 0 ? 12 : h);
    final now = DateTime.now();
    final diff = estimatedPickupTime!.difference(now);
    if (diff.isNegative) return '$h12:$m $period';
    final mins = diff.inMinutes;
    return '$h12:$m $period (+$mins min)';
  }
}


// ── Service class ─────────────────────────────────────────────────────────────

class DynamicPricingService {
  final _api = ApiClient();

  static const _base = '/api/v2/pricing';

  /// Get current fuel price configuration from the backend.
  Future<FuelConfig?> getFuelConfig() async {
    try {
      final resp = await _api.get('$_base/config');
      final data = resp.data['data'] as Map<String, dynamic>;
      return FuelConfig.fromJson(data);
    } catch (e) {
      return null;
    }
  }

  /// Update fuel price config (admin only).
  Future<bool> updatePetrolPrice(double newPricePkr) async {
    try {
      await _api.put('$_base/config', data: {
        'petrol_price_per_litre': newPricePkr,
      });
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Update any fuel config field (admin only).
  Future<bool> updateFuelConfig(Map<String, dynamic> updates) async {
    try {
      await _api.put('$_base/config', data: updates);
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Get quick fare estimate for a single passenger.
  Future<double?> quickFareEstimate({
    required double segmentKm,
    int seats = 1,
  }) async {
    try {
      final resp = await _api.post('$_base/fare-estimate', data: {
        'segment_km': segmentKm,
        'seats': seats,
      });
      return (resp.data['data']['estimated_fare_pkr'] as num).toDouble();
    } catch (_) {
      return null;
    }
  }

  /// Check if a passenger's pickup/dropoff are on a driver's fixed route.
  Future<RouteEligibilityResult?> checkRouteEligibility({
    required double pickupLat,
    required double pickupLng,
    required double dropoffLat,
    required double dropoffLng,
    required DateTime passengerDepartureTime,
    required String encodedPolyline,
    required DateTime rideDepartureTime,
    double thresholdM = 400.0,
    double timeWindowMin = 15.0,
  }) async {
    try {
      final resp = await _api.post('$_base/route-check', data: {
        'pickup_lat': pickupLat,
        'pickup_lng': pickupLng,
        'dropoff_lat': dropoffLat,
        'dropoff_lng': dropoffLng,
        'passenger_departure_time': passengerDepartureTime.toIso8601String(),
        'encoded_polyline': encodedPolyline,
        'ride_departure_time': rideDepartureTime.toIso8601String(),
        'threshold_m': thresholdM,
        'time_window_min': timeWindowMin,
      });
      return RouteEligibilityResult.fromJson(
          resp.data['data'] as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  /// Get full fare breakdown for all passengers on a shared ride.
  Future<RideFaresBreakdown?> getRideFares({
    required List<Map<String, dynamic>> passengers,
    required double totalRouteKm,
  }) async {
    try {
      final resp = await _api.post('$_base/ride-fares', data: {
        'passengers': passengers,
        'total_route_km': totalRouteKm,
      });
      return RideFaresBreakdown.fromJson(
          resp.data['data'] as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  /// Get per-booking fare + estimated pickup time details.
  Future<BookingFareDetails?> getBookingFareDetails(String bookingId) async {
    try {
      final resp = await _api.get('$_base/booking/$bookingId/details');
      return BookingFareDetails.fromJson(
          resp.data['data'] as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }
}
