/// Sylo Shared Fare Calculator — Yango-inspired.
///
/// Computes the total trip cost based on distance, fuel consumption,
/// and petrol price, then divides it among passengers (seats).
///
/// Formula:
///   fuelCost        = (distanceKm / fuelAverageKmPerLitre) × petrolPricePerLitre
///   timeCost        = durationMinutes × timeRatePerMinute
///   platformFee     = fuelCost × platformMarkup   (e.g. 25 %)
///   totalFare       = baseFare + fuelCost + timeCost + platformFee
///   farePerSeat     = totalFare / numberOfSeats
///   farePerSeat rounded UP to nearest 10 PKR
library;

import 'dart:math';

class FareCalculator {
  FareCalculator._();

  // ── Default config (Pakistan, mid-2025) ────────────────
  /// Petrol price per litre (PKR). Update as needed.
  static double petrolPricePerLitre = 268.0;

  /// Average vehicle fuel consumption (km per litre).
  /// Typical city driving for sedan/hatchback: 10-14 km/L
  static double fuelAverageKmPerLitre = 12.0;

  /// Platform markup over raw fuel cost (0.25 = 25%).
  /// Covers driver profit, wear & tear, platform commission.
  static double platformMarkup = 0.30;

  /// Minimum fare per seat (PKR).
  static double minimumFarePerSeat = 80.0;

  /// Base fare (added to every trip, like Yango base charge).
  static double baseFare = 50.0;

  /// Optional time-based component (PKR/min).
  static double timeRatePerMinute = 1.5;

  // ── Calculation ────────────────────────────────────────

  /// Returns a [FareEstimate] for the given parameters.
  static FareEstimate estimate({
    required double distanceKm,
    int totalSeats = 4,
    double durationMinutes = 0,
    double? petrolPrice,
    double? fuelAverage,
    double? markup,
  }) {
    final fuel = petrolPrice ?? petrolPricePerLitre;
    final avg = fuelAverage ?? fuelAverageKmPerLitre;
    final mkp = markup ?? platformMarkup;

    // Raw fuel cost for the trip
    final fuelCost = (distanceKm / avg) * fuel;
    final timeCost = durationMinutes * timeRatePerMinute;

    // Total trip fare
    final totalFare = baseFare + fuelCost + timeCost + (fuelCost * mkp);

    // Per-seat fare (minimum enforced)
    final seats = totalSeats.clamp(1, 8);
    final rawPerSeat = totalFare / seats;
    final perSeat = max(rawPerSeat, minimumFarePerSeat);

    // Round UP to nearest 10
    final perSeatRounded = (perSeat / 10).ceil() * 10.0;

    return FareEstimate(
      distanceKm: distanceKm,
      totalSeats: seats,
      fuelCostRaw: fuelCost,
      timeCost: timeCost,
      durationMinutes: durationMinutes,
      baseFare: baseFare,
      platformFee: fuelCost * mkp,
      totalFare: totalFare,
      farePerSeat: perSeatRounded,
      petrolPriceUsed: fuel,
      fuelAverageUsed: avg,
    );
  }

  /// Quick helper: returns fare-per-seat for a distance.
  static double quickPerSeat(double distanceKm, {int seats = 4}) {
    return estimate(distanceKm: distanceKm, totalSeats: seats).farePerSeat;
  }
}

/// Holds the result of a fare calculation.
class FareEstimate {
  final double distanceKm;
  final int totalSeats;
  final double fuelCostRaw;
  final double timeCost;
  final double durationMinutes;
  final double baseFare;
  final double platformFee;
  final double totalFare;
  final double farePerSeat;
  final double petrolPriceUsed;
  final double fuelAverageUsed;

  const FareEstimate({
    required this.distanceKm,
    required this.totalSeats,
    required this.fuelCostRaw,
    required this.timeCost,
    required this.durationMinutes,
    required this.baseFare,
    required this.platformFee,
    required this.totalFare,
    required this.farePerSeat,
    required this.petrolPriceUsed,
    required this.fuelAverageUsed,
  });

  /// Human-friendly summary.
  String get summary =>
      'Rs ${farePerSeat.toStringAsFixed(0)}/seat × $totalSeats seats '
      '= Rs ${(farePerSeat * totalSeats).toStringAsFixed(0)} total '
      '(${distanceKm.toStringAsFixed(1)} km)';
}
