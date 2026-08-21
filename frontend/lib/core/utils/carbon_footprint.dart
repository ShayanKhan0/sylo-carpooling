import 'dart:math' as math;

/// Carbon footprint helpers for carpooling (display + stats).
///
/// **Model used (FYP documentation):** approximate **CO₂ avoided** by sharing a ride
/// versus the same distance driven alone in a typical petrol car. We use a single
/// tunable factor **kg CO₂ per passenger-trip-km** for UI consistency with backend stats.
///
/// Factor default **0.12 kg/km** is in line with order-of-magnitude car emissions
/// (~120 g CO₂/km per vehicle) allocated per passenger when occupancy > 1; adjust
/// in one place if your report uses a different methodology.
class CarbonFootprint {
  CarbonFootprint._();

  /// kg CO₂ (approx.) attributed as "saved" per km of passenger travel for display.
  static const double kgCo2PerPassengerKm = 0.12;

  /// CO₂ avoided for one completed trip segment of [routeKm] km.
  static double avoidedKgForDistanceKm(double? routeKm) {
    if (routeKm == null || routeKm <= 0) return 0.0;
    return routeKm * kgCo2PerPassengerKm;
  }

  /// Sum of avoided CO₂ for a list of trip distances (e.g. completed bookings).
  static double totalAvoidedKg(Iterable<double?> distancesKm) {
    double s = 0;
    for (final d in distancesKm) {
      s += avoidedKgForDistanceKm(d);
    }
    return (s * 100).roundToDouble() / 100;
  }

  /// Format for UI: "X.X kg CO₂"
  static String formatKg(double kg) => '${kg.toStringAsFixed(1)} kg';
}

/// Haversine distance in km (accurate for carpooling city / regional distances).
double haversineKm(double lat1, double lng1, double lat2, double lng2) {
  const r = 6371.0;
  final dLat = _rad(lat2 - lat1);
  final dLng = _rad(lng2 - lng1);
  final a = math.sin(dLat / 2) * math.sin(dLat / 2) +
      math.cos(_rad(lat1)) *
          math.cos(_rad(lat2)) *
          math.sin(dLng / 2) *
          math.sin(dLng / 2);
  final c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a));
  return r * c;
}

double _rad(double d) => d * math.pi / 180;
