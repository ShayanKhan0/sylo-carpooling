/// BookingFareCard — displays per-passenger fare breakdown and pickup ETA.
///
/// Used in:
///   - Booking confirmation screen (after ride is matched)
///   - Passenger dashboard "My Rides" list
///   - Ride details screen
library;

import 'package:flutter/material.dart';
import '../../core/theme/app_colors.dart';
import '../../core/services/dynamic_pricing_service.dart';

class BookingFareCard extends StatelessWidget {
  final BookingFareDetails details;
  final bool showFullBreakdown;

  const BookingFareCard({
    super.key,
    required this.details,
    this.showFullBreakdown = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: AppColors.primary.withOpacity(0.15)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Header ──────────────────────────────────────────────────────
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AppColors.primary.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Icon(Icons.receipt_long_rounded,
                      color: AppColors.primary, size: 20),
                ),
                const SizedBox(width: 10),
                Text(
                  'Your Fare',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const Spacer(),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: AppColors.primary,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    details.fareDisplay,
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.bold,
                      fontSize: 15,
                    ),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 16),

            // ── Pickup ETA ────────────────────────────────────────────────
            _InfoRow(
              icon: Icons.access_time_rounded,
              label: 'Estimated Pickup',
              value: details.pickupTimeDisplay,
              valueColor: AppColors.primary,
              bold: true,
            ),

            const Divider(height: 20),

            // ── Segment distance ───────────────────────────────────────────
            _InfoRow(
              icon: Icons.straighten_rounded,
              label: 'Your travel distance',
              value: details.segmentKm != null
                  ? '${details.segmentKm!.toStringAsFixed(1)} km'
                  : 'N/A',
            ),

            const SizedBox(height: 6),

            // ── Rate per km ────────────────────────────────────────────────
            _InfoRow(
              icon: Icons.local_gas_station_rounded,
              label: 'Rate',
              value: details.ratePerKmUsed != null
                  ? 'Rs ${details.ratePerKmUsed!.toStringAsFixed(1)}/km'
                  : 'N/A',
            ),

            // ── Full breakdown (optional) ─────────────────────────────────
            if (showFullBreakdown && details.segmentKm != null) ...[
              const Divider(height: 20),
              Text(
                'Fare Breakdown',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: Colors.grey[600],
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(height: 8),
              _BreakdownRow(
                label: 'Distance cost',
                value: _distanceCost(details),
              ),
              const _BreakdownRow(
                label: 'Base share',
                value: 'Rs 10',
                subtitle: '(split equally)',
              ),
              const Divider(height: 12),
              _BreakdownRow(
                label: 'Total',
                value: details.fareDisplay,
                bold: true,
              ),
            ],

            const SizedBox(height: 8),

            // ── Route position indicator ───────────────────────────────────
            if (details.pickupPct != null && details.dropoffPct != null)
              _RoutePositionBar(
                pickupPct: details.pickupPct!,
                dropoffPct: details.dropoffPct!,
              ),
          ],
        ),
      ),
    );
  }

  String _distanceCost(BookingFareDetails d) {
    if (d.segmentKm == null || d.ratePerKmUsed == null) return 'N/A';
    final cost = d.segmentKm! * d.ratePerKmUsed!;
    return 'Rs ${cost.toStringAsFixed(0)}';
  }
}


/// Compact version for use in ride list tiles.
class BookingFareTile extends StatelessWidget {
  final BookingFareDetails details;

  const BookingFareTile({super.key, required this.details});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const Icon(Icons.access_time_rounded,
            size: 14, color: AppColors.primary),
        const SizedBox(width: 4),
        Text(
          details.pickupTimeDisplay,
          style: const TextStyle(
            fontSize: 12,
            color: AppColors.primary,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(width: 12),
        Icon(Icons.payments_outlined, size: 14, color: Colors.grey[600]),
        const SizedBox(width: 4),
        Text(
          details.fareDisplay,
          style: TextStyle(
            fontSize: 12,
            color: Colors.grey[700],
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }
}


/// Async card that fetches and shows fare details for a booking ID.
class BookingFareCardAsync extends StatefulWidget {
  final String bookingId;
  final bool showFullBreakdown;

  const BookingFareCardAsync({
    super.key,
    required this.bookingId,
    this.showFullBreakdown = false,
  });

  @override
  State<BookingFareCardAsync> createState() => _BookingFareCardAsyncState();
}

class _BookingFareCardAsyncState extends State<BookingFareCardAsync> {
  final _pricingService = DynamicPricingService();
  BookingFareDetails? _details;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final d = await _pricingService.getBookingFareDetails(widget.bookingId);
    if (mounted) {
      setState(() {
        _details = d;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Card(
        child: Padding(
          padding: EdgeInsets.all(16),
          child: Center(child: CircularProgressIndicator()),
        ),
      );
    }
    if (_details == null) {
      return const SizedBox.shrink();
    }
    return BookingFareCard(
      details: _details!,
      showFullBreakdown: widget.showFullBreakdown,
    );
  }
}


// ── Helper widgets ────────────────────────────────────────────────────────────

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color? valueColor;
  final bool bold;

  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
    this.valueColor,
    this.bold = false,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 16, color: Colors.grey[500]),
        const SizedBox(width: 8),
        Text(
          label,
          style: TextStyle(fontSize: 13, color: Colors.grey[600]),
        ),
        const Spacer(),
        Text(
          value,
          style: TextStyle(
            fontSize: 13,
            fontWeight: bold ? FontWeight.bold : FontWeight.w500,
            color: valueColor,
          ),
        ),
      ],
    );
  }
}


class _BreakdownRow extends StatelessWidget {
  final String label;
  final String value;
  final String? subtitle;
  final bool bold;

  const _BreakdownRow({
    required this.label,
    required this.value,
    this.subtitle,
    this.bold = false,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              color: Colors.grey[600],
              fontWeight: bold ? FontWeight.bold : FontWeight.normal,
            ),
          ),
          if (subtitle != null) ...[
            const SizedBox(width: 4),
            Text(
              subtitle!,
              style: TextStyle(fontSize: 11, color: Colors.grey[400]),
            ),
          ],
          const Spacer(),
          Text(
            value,
            style: TextStyle(
              fontSize: 12,
              fontWeight: bold ? FontWeight.bold : FontWeight.w500,
              color: bold ? AppColors.primary : null,
            ),
          ),
        ],
      ),
    );
  }
}


/// Visual bar showing where on the route this passenger boards and alights.
class _RoutePositionBar extends StatelessWidget {
  final double pickupPct;
  final double dropoffPct;

  const _RoutePositionBar({
    required this.pickupPct,
    required this.dropoffPct,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 4),
        Text(
          'Your position on route',
          style: TextStyle(fontSize: 11, color: Colors.grey[500]),
        ),
        const SizedBox(height: 6),
        LayoutBuilder(
          builder: (context, constraints) {
            final width = constraints.maxWidth;
            final leftPad = pickupPct * width;
            final segWidth = (dropoffPct - pickupPct) * width;
            return Stack(
              children: [
                Container(
                  height: 8,
                  decoration: BoxDecoration(
                    color: Colors.grey[200],
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
                Positioned(
                  left: leftPad,
                  child: Container(
                    height: 8,
                    width: segWidth.clamp(16.0, width - leftPad),
                    decoration: BoxDecoration(
                      color: AppColors.primary,
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                ),
              ],
            );
          },
        ),
        const SizedBox(height: 4),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Start', style: TextStyle(fontSize: 10, color: Colors.grey[500])),
            Text('End', style: TextStyle(fontSize: 10, color: Colors.grey[500])),
          ],
        ),
      ],
    );
  }
}
