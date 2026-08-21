/// ClusterStatusWidget — Shows AI match status for a pending ride request.
///
/// Usage: Place this widget in the passenger dashboard after a passenger
/// has posted a ride request and is waiting for AI grouping.
///
/// States shown:
///   - pending:  Pulsing spinner + "Searching for travel partners..."
///   - matched:  Green card + group info + "View Your Ride" button
///   - solo:     Blue card + "Private ride assigned"
///   - no_driver:Orange card + "No driver available — try again later"
///   - error:    Red card + error detail
library;

import 'dart:async';
import 'package:flutter/material.dart';
import '../../core/services/matching_service.dart';
import '../../core/theme/app_colors.dart';
import '../../core/constants/app_constants.dart';

class ClusterStatusWidget extends StatefulWidget {
  final String requestId;
  final VoidCallback? onRideMatched;

  const ClusterStatusWidget({
    super.key,
    required this.requestId,
    this.onRideMatched,
  });

  @override
  State<ClusterStatusWidget> createState() => _ClusterStatusWidgetState();
}

class _ClusterStatusWidgetState extends State<ClusterStatusWidget>
    with SingleTickerProviderStateMixin {
  final MatchingService _svc = MatchingService();

  RideRequestClusterStatus? _status;
  bool _loading = true;
  String? _error;
  Timer? _pollTimer;
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);
    _pulseAnimation = Tween<double>(begin: 0.6, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    _pollStatus();
    // Poll every 30 seconds while pending
    _pollTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (_status?.isPending ?? true) _pollStatus();
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _pulseController.dispose();
    super.dispose();
  }

  Future<void> _pollStatus() async {
    if (!mounted) return;
    try {
      final status = await _svc.getRequestClusterStatus(widget.requestId);
      if (!mounted) return;
      setState(() {
        _status = status;
        _loading = false;
        _error = null;
      });
      if (status.isMatched) {
        _pollTimer?.cancel();
        widget.onRideMatched?.call();
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return _buildLoading();
    if (_error != null) return _buildError();
    if (_status == null) return const SizedBox.shrink();
    return _buildStatusCard(_status!);
  }

  // ── Loading state ──────────────────────────────────────────────────────────
  Widget _buildLoading() {
    return _card(
      color: AppColors.backgroundLight,
      child: Row(
        children: [
          const SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(
                strokeWidth: 2, color: AppColors.primary),
          ),
          const SizedBox(width: 12),
          Text('Checking match status...',
              style: TextStyle(color: AppColors.textSecondary)),
        ],
      ),
    );
  }

  // ── Error state ────────────────────────────────────────────────────────────
  Widget _buildError() {
    return _card(
      color: AppColors.error.withValues(alpha: 0.08),
      borderColor: AppColors.error.withValues(alpha: 0.3),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: AppColors.error, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(_error ?? 'Unknown error',
                style: const TextStyle(color: AppColors.error, fontSize: 13)),
          ),
          IconButton(
            icon: const Icon(Icons.refresh, size: 18),
            color: AppColors.error,
            onPressed: () {
              setState(() {
                _loading = true;
                _error = null;
              });
              _pollStatus();
            },
          ),
        ],
      ),
    );
  }

  // ── Status card ────────────────────────────────────────────────────────────
  Widget _buildStatusCard(RideRequestClusterStatus status) {
    switch (status.status) {
      case 'pending':
        return _buildPendingCard(status);
      case 'matched':
        return _buildMatchedCard(status);
      case 'cancelled':
      case 'expired':
        return _buildInactiveCard(status);
      default:
        return _buildPendingCard(status);
    }
  }

  Widget _buildPendingCard(RideRequestClusterStatus status) {
    return _card(
      color: AppColors.primary.withValues(alpha: 0.07),
      borderColor: AppColors.primary.withValues(alpha: 0.25),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            FadeTransition(
              opacity: _pulseAnimation,
              child: Container(
                width: 10,
                height: 10,
                decoration: const BoxDecoration(
                    shape: BoxShape.circle, color: AppColors.primary),
              ),
            ),
            const SizedBox(width: 10),
            const Text(
              'AI Matching in Progress',
              style: TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                  color: AppColors.primaryDark),
            ),
          ]),
          const SizedBox(height: 6),
          Text(
            'Our AI (DBSCAN) is searching for passengers near you '
            'with a similar route and departure time. '
            'Clustering runs every 5 minutes.',
            style: TextStyle(
                fontSize: 12, color: AppColors.textSecondary, height: 1.4),
          ),
          const SizedBox(height: 10),
          // Visual: "How it works" mini-info
          _clusterInfoRow(
              Icons.pin_drop_rounded, AppColors.primary, 'Pickup radius: 2 km'),
          const SizedBox(height: 4),
          _clusterInfoRow(Icons.directions_rounded, AppColors.secondary,
              'Same direction: within 8 km'),
          const SizedBox(height: 4),
          _clusterInfoRow(Icons.schedule_rounded, AppColors.accent,
              'Time window: ±20 minutes'),
        ],
      ),
    );
  }

  Widget _buildMatchedCard(RideRequestClusterStatus status) {
    final groupSize = status.clusterSize ?? 1;
    final isSolo = groupSize <= 1;
    final color = isSolo ? AppColors.info : AppColors.success;

    return _card(
      color: color.withValues(alpha: 0.08),
      borderColor: color.withValues(alpha: 0.30),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              child: Icon(
                isSolo ? Icons.person_rounded : Icons.group_rounded,
                color: Colors.white,
                size: 16,
              ),
            ),
            const SizedBox(width: 10),
            Text(
              isSolo ? 'Private Ride Confirmed!' : 'Carpooling Group Matched!',
              style: TextStyle(
                  fontWeight: FontWeight.bold, fontSize: 14, color: color),
            ),
          ]),
          const SizedBox(height: 8),
          if (!isSolo) ...[
            Text(
              'You are sharing with ${groupSize - 1} other passenger(s). '
              'Your fare has been split automatically.',
              style: TextStyle(
                  fontSize: 12, color: AppColors.textSecondary, height: 1.4),
            ),
            const SizedBox(height: 8),
            Row(children: [
              _clusterStatChip('${groupSize}x', Icons.people_rounded, color),
              const SizedBox(width: 8),
              if (status.estimatedFare != null)
                _clusterStatChip(
                    'Rs ${status.estimatedFare!.toStringAsFixed(0)}',
                    Icons.payments_rounded,
                    color),
            ]),
          ] else ...[
            Text(
              status.message,
              style: TextStyle(
                  fontSize: 12, color: AppColors.textSecondary, height: 1.4),
            ),
          ],
          if (status.matchedRideId != null) ...[
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: () {
                  final id = status.matchedRideId;
                  if (id == null || id.isEmpty) return;
                  Navigator.of(context).pushNamed(
                    '/ride-detail',
                    arguments: id,
                  );
                },
                icon: const Icon(Icons.arrow_forward_rounded, size: 16),
                label: const Text('View Your Ride'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: color,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildInactiveCard(RideRequestClusterStatus status) {
    return _card(
      color: AppColors.textSecondary.withValues(alpha: 0.08),
      borderColor: AppColors.border,
      child: Row(
        children: [
          Icon(Icons.cancel_outlined, color: AppColors.textSecondary, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              status.message,
              style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
            ),
          ),
        ],
      ),
    );
  }

  // ── Helpers ────────────────────────────────────────────────────────────────
  Widget _card({
    required Widget child,
    required Color color,
    Color? borderColor,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
        border: Border.all(color: borderColor ?? AppColors.border),
      ),
      child: child,
    );
  }

  Widget _clusterInfoRow(IconData icon, Color color, String label) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 13, color: color),
        const SizedBox(width: 5),
        Text(label,
            style: TextStyle(fontSize: 11, color: AppColors.textSecondary)),
      ],
    );
  }

  Widget _clusterStatChip(String value, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 12, color: color),
          const SizedBox(width: 4),
          Text(value,
              style: TextStyle(
                  fontSize: 12, fontWeight: FontWeight.bold, color: color)),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
//  AI Cluster Explanation Bottom Sheet
// ─────────────────────────────────────────────────────────────────────────────

/// Show a bottom sheet explaining how the DBSCAN clustering algorithm works.
void showClusterExplanationSheet(BuildContext context) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: AppColors.surface,
    shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
    builder: (ctx) => Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                  color: AppColors.divider,
                  borderRadius: BorderRadius.circular(2)),
            ),
          ),
          const SizedBox(height: 20),
          Row(children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                  color: AppColors.primary.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(12)),
              child: const Icon(Icons.auto_awesome_rounded,
                  color: AppColors.primary, size: 22),
            ),
            const SizedBox(width: 12),
            const Expanded(
              child: Text(
                'How AI Matching Works',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
            ),
          ]),
          const SizedBox(height: 20),
          _explanationStep(
              '1',
              'You post a ride request',
              'Origin, destination, departure time and seats needed are sent to our server.',
              AppColors.primary),
          _explanationStep(
              '2',
              'DBSCAN Clustering',
              'Our AI groups passengers who are within 2 km of each other, heading in the same direction (within 8 km), and departing within 20 minutes.',
              AppColors.secondary),
          _explanationStep(
              '3',
              'Driver Assignment',
              'The nearest available driver with enough seats is assigned to your group. Higher-rated drivers are preferred.',
              AppColors.accent),
          _explanationStep(
              '4',
              'Fare Split',
              'The total fare is calculated based on route distance and divided equally among all passengers in your group.',
              AppColors.success),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.backgroundLight,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.border),
            ),
            child: Row(
              children: [
                Icon(Icons.info_outline_rounded,
                    size: 16, color: AppColors.textSecondary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Clustering runs every 5 minutes. If no group is found, '
                    'you will be offered a private ride.',
                    style:
                        TextStyle(fontSize: 12, color: AppColors.textSecondary),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
        ],
      ),
    ),
  );
}

Widget _explanationStep(String step, String title, String body, Color color) {
  return Padding(
    padding: const EdgeInsets.only(bottom: 16),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 28,
          height: 28,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          child: Center(
            child: Text(step,
                style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    fontSize: 13)),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title,
                  style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                      color: AppColors.textPrimary)),
              const SizedBox(height: 2),
              Text(body,
                  style: TextStyle(
                      fontSize: 12,
                      color: AppColors.textSecondary,
                      height: 1.4)),
            ],
          ),
        ),
      ],
    ),
  );
}
