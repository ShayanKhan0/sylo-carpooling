/// RideStopSequenceWidget — shows drivers the ordered list of passenger pickups
/// along their route, with per-stop ETAs and per-passenger fares.
///
/// Used in:
///   - Driver dashboard "Active Ride" panel (after accepting)
///   - Driver ride details screen
library;

import 'package:flutter/material.dart';
import '../../core/theme/app_colors.dart';
import '../../core/services/dynamic_pricing_service.dart';

// ── Data model for one stop ───────────────────────────────────────────────────

class RideStop {
  final String passengerId;
  final String bookingId;
  final String passengerName;
  final String pickupAddress;
  final String dropoffAddress;
  final double pickupPct;          // 0.0 – 1.0 along route
  final double dropoffPct;
  final double segmentKm;
  final double farePkr;
  final DateTime? estimatedPickupTime;
  final int seatsBooked;
  final bool isPickup;             // true = pickup stop, false = dropoff stop

  const RideStop({
    required this.passengerId,
    required this.bookingId,
    required this.passengerName,
    required this.pickupAddress,
    required this.dropoffAddress,
    required this.pickupPct,
    required this.dropoffPct,
    required this.segmentKm,
    required this.farePkr,
    this.estimatedPickupTime,
    this.seatsBooked = 1,
    this.isPickup = true,
  });

  factory RideStop.fromBookingDetails(
    BookingFareDetails d, {
    String passengerName = 'Passenger',
    String pickupAddress = '',
    String dropoffAddress = '',
  }) =>
      RideStop(
        passengerId: d.passengerId,
        bookingId: d.bookingId,
        passengerName: passengerName,
        pickupAddress: pickupAddress,
        dropoffAddress: dropoffAddress,
        pickupPct: d.pickupPct ?? 0.0,
        dropoffPct: d.dropoffPct ?? 1.0,
        segmentKm: d.segmentKm ?? 0.0,
        farePkr: d.individualFare ?? d.fare,
        estimatedPickupTime: d.estimatedPickupTime,
        seatsBooked: d.seatsReserved,
      );

  String get etaDisplay {
    if (estimatedPickupTime == null) return 'TBD';
    final h = estimatedPickupTime!.hour;
    final m = estimatedPickupTime!.minute.toString().padLeft(2, '0');
    final period = h >= 12 ? 'PM' : 'AM';
    final h12 = h > 12 ? h - 12 : (h == 0 ? 12 : h);
    final diff = estimatedPickupTime!.difference(DateTime.now());
    if (diff.isNegative) return '$h12:$m $period';
    return '$h12:$m $period (+${diff.inMinutes} min)';
  }

  String get fareDisplay => 'Rs ${farePkr.toStringAsFixed(0)}';
  String get distanceDisplay => '${segmentKm.toStringAsFixed(1)} km';
}


// ── Widget ───────────────────────────────────────────────────────────────────

class RideStopSequenceWidget extends StatelessWidget {
  final List<RideStop> stops;
  final double totalRouteKm;
  final double totalEarningsPkr;
  final int totalPassengers;
  final DateTime? departureTime;

  const RideStopSequenceWidget({
    super.key,
    required this.stops,
    required this.totalRouteKm,
    required this.totalEarningsPkr,
    required this.totalPassengers,
    this.departureTime,
  });

  // Sort stops by pickup percentage along route
  List<RideStop> get _sortedStops =>
      [...stops]..sort((a, b) => a.pickupPct.compareTo(b.pickupPct));

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final sorted = _sortedStops;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // ── Earnings summary banner ──────────────────────────────────────
        _EarningsBanner(
          totalEarnings: totalEarningsPkr,
          totalPassengers: totalPassengers,
          totalRouteKm: totalRouteKm,
        ),

        const SizedBox(height: 16),

        Text(
          'Stop Sequence',
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w600,
            color: Colors.grey[700],
          ),
        ),
        const SizedBox(height: 8),

        // ── Route start dot ───────────────────────────────────────────────
        _RouteStartRow(departureTime: departureTime),

        // ── Passenger stops ────────────────────────────────────────────────
        ...sorted.asMap().entries.map(
          (entry) => _PassengerStopRow(
            stop: entry.value,
            index: entry.key,
            isLast: entry.key == sorted.length - 1,
          ),
        ),

        // ── Route end dot ──────────────────────────────────────────────────
        _RouteEndRow(totalRouteKm: totalRouteKm),
      ],
    );
  }
}


// ── Earnings Banner ───────────────────────────────────────────────────────────

class _EarningsBanner extends StatelessWidget {
  final double totalEarnings;
  final int totalPassengers;
  final double totalRouteKm;

  const _EarningsBanner({
    required this.totalEarnings,
    required this.totalPassengers,
    required this.totalRouteKm,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [AppColors.primary, AppColors.primary.withOpacity(0.7)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          const Icon(Icons.payments_rounded, color: Colors.white, size: 28),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Total Earnings',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.85),
                    fontSize: 12,
                  ),
                ),
                Text(
                  'Rs ${totalEarnings.toStringAsFixed(0)}',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              _StatChip(
                icon: Icons.people_outline,
                label: '$totalPassengers passengers',
              ),
              const SizedBox(height: 4),
              _StatChip(
                icon: Icons.route_outlined,
                label: '${totalRouteKm.toStringAsFixed(1)} km',
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatChip extends StatelessWidget {
  final IconData icon;
  final String label;
  const _StatChip({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.2),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: Colors.white),
          const SizedBox(width: 4),
          Text(label,
              style: const TextStyle(color: Colors.white, fontSize: 11)),
        ],
      ),
    );
  }
}


// ── Route start row ───────────────────────────────────────────────────────────

class _RouteStartRow extends StatelessWidget {
  final DateTime? departureTime;
  const _RouteStartRow({this.departureTime});

  String get _timeDisplay {
    if (departureTime == null) return '';
    final h = departureTime!.hour;
    final m = departureTime!.minute.toString().padLeft(2, '0');
    final period = h >= 12 ? 'PM' : 'AM';
    final h12 = h > 12 ? h - 12 : (h == 0 ? 12 : h);
    return '$h12:$m $period';
  }

  @override
  Widget build(BuildContext context) {
    return _StopRow(
      dotColor: Colors.green,
      dotSize: 14,
      isFirst: true,
      isLast: false,
      child: Row(
        children: [
          Text(
            'Departure',
            style: TextStyle(
              fontWeight: FontWeight.w600,
              color: Colors.green[700],
              fontSize: 13,
            ),
          ),
          if (departureTime != null) ...[
            const SizedBox(width: 8),
            Text(
              _timeDisplay,
              style: TextStyle(color: Colors.grey[600], fontSize: 12),
            ),
          ],
        ],
      ),
    );
  }
}


// ── Passenger stop row ────────────────────────────────────────────────────────

class _PassengerStopRow extends StatelessWidget {
  final RideStop stop;
  final int index;
  final bool isLast;

  const _PassengerStopRow({
    required this.stop,
    required this.index,
    required this.isLast,
  });

  @override
  Widget build(BuildContext context) {
    return _StopRow(
      dotColor: AppColors.primary,
      dotSize: 12,
      isFirst: false,
      isLast: false,
      child: Card(
        margin: EdgeInsets.zero,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: AppColors.primary.withOpacity(0.12)),
        ),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Name + fare chip
              Row(
                children: [
                  CircleAvatar(
                    radius: 14,
                    backgroundColor: AppColors.primary.withOpacity(0.1),
                    child: Text(
                      stop.passengerName.isNotEmpty
                          ? stop.passengerName[0].toUpperCase()
                          : '?',
                      style: const TextStyle(
                        color: AppColors.primary,
                        fontWeight: FontWeight.bold,
                        fontSize: 13,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      stop.passengerName,
                      style: const TextStyle(
                        fontWeight: FontWeight.w600,
                        fontSize: 14,
                      ),
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: Colors.green.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                          color: Colors.green.withOpacity(0.3)),
                    ),
                    child: Text(
                      stop.fareDisplay,
                      style: const TextStyle(
                        color: Colors.green,
                        fontWeight: FontWeight.bold,
                        fontSize: 13,
                      ),
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 8),

              // ETA
              Row(
                children: [
                  const Icon(Icons.schedule_rounded,
                      size: 13, color: AppColors.primary),
                  const SizedBox(width: 4),
                  Text(
                    'Pickup: ${stop.etaDisplay}',
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppColors.primary,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 4),

              // Pickup address
              if (stop.pickupAddress.isNotEmpty)
                Row(
                  children: [
                    Icon(Icons.location_on_rounded,
                        size: 13, color: Colors.grey[500]),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        stop.pickupAddress,
                        style:
                            TextStyle(fontSize: 11, color: Colors.grey[600]),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),

              const SizedBox(height: 4),

              // Dropoff address + distance
              Row(
                children: [
                  Icon(Icons.flag_rounded,
                      size: 13, color: Colors.orange[700]),
                  const SizedBox(width: 4),
                  Expanded(
                    child: Text(
                      stop.dropoffAddress.isNotEmpty
                          ? stop.dropoffAddress
                          : 'Dropoff',
                      style:
                          TextStyle(fontSize: 11, color: Colors.grey[600]),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Text(
                    stop.distanceDisplay,
                    style:
                        TextStyle(fontSize: 11, color: Colors.grey[500]),
                  ),
                ],
              ),

              // Seats
              if (stop.seatsBooked > 1) ...[
                const SizedBox(height: 4),
                Row(
                  children: [
                    Icon(Icons.people_alt_rounded,
                        size: 13, color: Colors.grey[500]),
                    const SizedBox(width: 4),
                    Text(
                      '${stop.seatsBooked} seats',
                      style:
                          TextStyle(fontSize: 11, color: Colors.grey[600]),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}


// ── Route end row ─────────────────────────────────────────────────────────────

class _RouteEndRow extends StatelessWidget {
  final double totalRouteKm;
  const _RouteEndRow({required this.totalRouteKm});

  @override
  Widget build(BuildContext context) {
    return _StopRow(
      dotColor: Colors.red[400]!,
      dotSize: 14,
      isFirst: false,
      isLast: true,
      child: Text(
        'Destination  •  ${totalRouteKm.toStringAsFixed(1)} km',
        style: TextStyle(
          fontWeight: FontWeight.w600,
          color: Colors.red[700],
          fontSize: 13,
        ),
      ),
    );
  }
}


// ── Base stop row (dot + vertical line) ───────────────────────────────────────

class _StopRow extends StatelessWidget {
  final Color dotColor;
  final double dotSize;
  final bool isFirst;
  final bool isLast;
  final Widget child;

  const _StopRow({
    required this.dotColor,
    required this.dotSize,
    required this.isFirst,
    required this.isLast,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // ── Timeline column ──────────────────────────────────────────────
          SizedBox(
            width: 24,
            child: Column(
              children: [
                if (!isFirst)
                  Expanded(
                    child: Container(
                      width: 2,
                      color: Colors.grey[300],
                    ),
                  )
                else
                  const SizedBox(height: 6),
                Container(
                  width: dotSize,
                  height: dotSize,
                  decoration: BoxDecoration(
                    color: dotColor,
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 2),
                    boxShadow: [
                      BoxShadow(
                        color: dotColor.withOpacity(0.3),
                        blurRadius: 4,
                      ),
                    ],
                  ),
                ),
                if (!isLast)
                  Expanded(
                    child: Container(
                      width: 2,
                      color: Colors.grey[300],
                    ),
                  )
                else
                  const SizedBox(height: 6),
              ],
            ),
          ),

          const SizedBox(width: 12),

          // ── Content ────────────────────────────────────────────────────
          Expanded(
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: child,
            ),
          ),
        ],
      ),
    );
  }
}
