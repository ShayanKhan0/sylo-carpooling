import 'dart:async';
import 'dart:math' as math;
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:geolocator/geolocator.dart';
import '../../core/services/api_client.dart';
import '../../core/services/ride_service.dart';
import '../../core/services/rating_service.dart';
import '../../core/services/auth_service.dart';
import '../../core/services/chat_service.dart';
import '../../core/services/chat_sync_service.dart';
import '../../core/services/telemetry_service.dart';
import '../../core/services/trip_service.dart';
import '../../core/models/ride_model.dart';
import '../../core/models/rating_model.dart';
import '../../core/theme/app_colors.dart';
import '../../core/constants/app_constants.dart';
import '../dashboard/home_design_system.dart';
import '../shared/widgets.dart';
import '../maps/route_map_widget.dart';

class RideDetailScreen extends StatefulWidget {
  final String rideId;
  const RideDetailScreen({super.key, required this.rideId});

  @override
  State<RideDetailScreen> createState() => _RideDetailScreenState();
}

class _RideDetailScreenState extends State<RideDetailScreen> {
  static const Color _createRideGreenBackground = Color(0xFFD9FCE8);
  static const Color _rideCardTextPrimary = Colors.white;
  static const Color _rideCardTextSecondary = Color(0xCCFFFFFF);
  static const Color _outsideCardTextColor = Color(0xFF0B3D24);

  final RideService _rideSvc = RideService();
  final RatingService _rateSvc = RatingService();
  final ChatService _chatSvc = ChatService();
  final ChatSyncService _chatSync = ChatSyncService();
  final TelemetryService _telemetrySvc = TelemetryService();
  final TripService _tripSvc = TripService();

  Ride? _ride;
  Rating? _existingRating;
  bool _loading = true;
  String? _error;
  String? _userId;
  bool _updatingRouteSelection = false;
  String? _selectedDriverRouteKey;
  bool _updatingRideStatus = false;
  final Set<String> _bookingProgressBusy = <String>{};
  Map<String, int> _rideThreadUnreadByBookingId = <String, int>{};
  Timer? _progressRefreshTimer;
  Timer? _chatBadgeRefreshTimer;
  bool _isRefreshingRideThreadBadges = false;
  String? _lastTelemetryDiagnosticsShown;
  StreamSubscription<Position>? _driverTelemetryPositionSub;
  Timer? _driverTelemetryHeartbeatTimer;
  String? _activeTelemetryRideId;
  DateTime _lastTelemetrySentAt = DateTime.fromMillisecondsSinceEpoch(0);
  bool _telemetryPermissionHintShown = false;

  bool _isDuplicateRatingError(Object error) {
    if (error is! DioException) return false;
    final message = extractError(error).toLowerCase();
    return message.contains('already rated');
  }

  Future<void> _showAlreadyRatedPopup({String counterpartName = 'this user'}) async {
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Already Rated'),
        content: Text(
          'You have already rated $counterpartName for this ride.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _telemetrySvc.diagnosticsNotifier
        .addListener(_handleTelemetryDiagnosticsChanged);
    _startChatBadgeRefresh();
    _load();
  }

  @override
  void dispose() {
    _telemetrySvc.diagnosticsNotifier
        .removeListener(_handleTelemetryDiagnosticsChanged);
    _progressRefreshTimer?.cancel();
    _chatBadgeRefreshTimer?.cancel();
    _stopDriverTelemetryPublishing(disconnect: false);
    _telemetrySvc.dispose();
    super.dispose();
  }

  void _handleTelemetryDiagnosticsChanged() {
    if (!mounted) return;
    final message = _telemetrySvc.diagnosticsNotifier.value?.trim();
    if (message == null || message.isEmpty) return;
    if (_lastTelemetryDiagnosticsShown == message) return;
    _lastTelemetryDiagnosticsShown = message;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Live tracking: $message'),
        backgroundColor: AppColors.warning,
      ),
    );
  }

  void _startChatBadgeRefresh() {
    _chatBadgeRefreshTimer?.cancel();
    _chatBadgeRefreshTimer = Timer.periodic(
      const Duration(seconds: 2),
      (_) => _refreshRideThreadUnreadBadges(),
    );
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      _userId = await AuthService().getUserId();
      final ride = await _rideSvc.getRideDetail(widget.rideId);
      final ratingTarget = _resolvePreferredRatingTarget(ride);
      Rating? rating;
      try {
        if (ratingTarget != null) {
          rating = await _rateSvc.getRideRating(
            widget.rideId,
            toUserId: ratingTarget.toUserId,
          );
        }
      } catch (_) {}
      setState(() {
        _ride = ride;
        _existingRating = rating;
        _selectedDriverRouteKey = ride.routeSelectedKey;
        _loading = false;
      });
      await _refreshRideThreadUnreadBadges(ride: ride);
      _configureProgressRefresh(ride);
      // Auto-prompt rating for completed rides when user hasn't rated yet
      if (ride.status == 'completed' &&
          rating == null &&
          ratingTarget != null &&
          mounted) {
        // Small delay so the screen renders first
        Future.delayed(const Duration(milliseconds: 500), () {
          if (!mounted) return;
          _showRatingDialog(
            toUserId: ratingTarget.toUserId,
            bookingId: ratingTarget.bookingId,
            counterpartName: ratingTarget.label,
          );
        });
      }
    } catch (e) {
      _configureProgressRefresh(null);
      setState(() {
        _error = e.toString();
        _rideThreadUnreadByBookingId = <String, int>{};
        _loading = false;
      });
    }
  }

  void _configureProgressRefresh(Ride? ride) {
    _progressRefreshTimer?.cancel();
    unawaited(_syncDriverTelemetryForRide(ride));
    if (ride == null || ride.status != 'in_progress') {
      _progressRefreshTimer = null;
      return;
    }

    _progressRefreshTimer = Timer.periodic(
      const Duration(seconds: 15),
      (_) => _refreshRideSilently(),
    );
  }

  Future<void> _syncDriverTelemetryForRide(Ride? ride) async {
    final currentUserId = (_userId ?? '').trim();
    final canPublish = ride != null &&
        currentUserId.isNotEmpty &&
        ride.driverId == currentUserId &&
        ride.status == 'in_progress';

    if (!canPublish) {
      _stopDriverTelemetryPublishing();
      return;
    }

    await _startDriverTelemetryPublishing(ride.id);
  }

  Future<bool> _ensureTelemetryLocationPermission() async {
    if (!await Geolocator.isLocationServiceEnabled()) {
      if (mounted && !_telemetryPermissionHintShown) {
        _telemetryPermissionHintShown = true;
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Enable location services to share live trip tracking with passengers.',
            ),
            backgroundColor: AppColors.warning,
          ),
        );
      }
      return false;
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    final granted = permission == LocationPermission.always ||
        permission == LocationPermission.whileInUse;
    if (!granted && mounted && !_telemetryPermissionHintShown) {
      _telemetryPermissionHintShown = true;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Location permission is required for live driver tracking.',
          ),
          backgroundColor: AppColors.warning,
        ),
      );
    }

    return granted;
  }

  Future<void> _startDriverTelemetryPublishing(String rideId) async {
    if (_activeTelemetryRideId == rideId &&
        _driverTelemetryPositionSub != null &&
        _driverTelemetryHeartbeatTimer != null) {
      return;
    }

    if (_activeTelemetryRideId != null && _activeTelemetryRideId != rideId) {
      _stopDriverTelemetryPublishing();
    }

    final hasPermission = await _ensureTelemetryLocationPermission();
    if (!hasPermission) return;

    await _telemetrySvc.connect(rideId);
    _activeTelemetryRideId = rideId;
    _lastTelemetrySentAt = DateTime.fromMillisecondsSinceEpoch(0);

    unawaited(_sendCurrentDriverTelemetrySample());

    _driverTelemetryHeartbeatTimer?.cancel();
    _driverTelemetryHeartbeatTimer =
        Timer.periodic(const Duration(seconds: 6), (_) {
      unawaited(_sendCurrentDriverTelemetrySample());
    });

    _driverTelemetryPositionSub?.cancel();
    _driverTelemetryPositionSub = Geolocator.getPositionStream(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: 8,
      ),
    ).listen((position) {
      unawaited(_sendDriverTelemetryPoint(position));
    }, onError: (_) {
      // Heartbeat timer continues publishing while stream recoveries happen.
    });
  }

  Future<void> _sendCurrentDriverTelemetrySample() async {
    if (_activeTelemetryRideId == null) return;

    try {
      final current = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 10),
        ),
      );
      await _sendDriverTelemetryPoint(current);
    } catch (_) {
      // Keep retrying on next heartbeat tick.
    }
  }

  Future<void> _sendDriverTelemetryPoint(Position position) async {
    final rideId = _activeTelemetryRideId;
    if (rideId == null || rideId.trim().isEmpty) return;

    final nowUtc = DateTime.now().toUtc();
    if (nowUtc.difference(_lastTelemetrySentAt) < const Duration(seconds: 2)) {
      return;
    }
    _lastTelemetrySentAt = nowUtc;

    final rawSpeed = position.speed;
    final double speedKmh =
        (rawSpeed.isFinite && rawSpeed > 0) ? (rawSpeed * 3.6).toDouble() : 0.0;
    final rawHeading = position.heading;
    final double? bearing =
        (rawHeading.isFinite && rawHeading >= 0 && rawHeading < 360)
            ? rawHeading.toDouble()
            : null;
    final rawAccuracy = position.accuracy;
    final double? accuracy =
        rawAccuracy.isFinite ? rawAccuracy.toDouble() : null;

    await _telemetrySvc.sendLocation(
      TelemetryPoint(
        timestamp: nowUtc,
        lat: position.latitude,
        lng: position.longitude,
        speed: speedKmh,
        bearing: bearing,
        accuracy: accuracy,
      ),
    );
  }

  void _stopDriverTelemetryPublishing({bool disconnect = true}) {
    _driverTelemetryPositionSub?.cancel();
    _driverTelemetryPositionSub = null;
    _driverTelemetryHeartbeatTimer?.cancel();
    _driverTelemetryHeartbeatTimer = null;
    _activeTelemetryRideId = null;
    _lastTelemetrySentAt = DateTime.fromMillisecondsSinceEpoch(0);

    if (disconnect) {
      unawaited(_telemetrySvc.disconnect());
    }
  }

  Future<void> _refreshRideSilently() async {
    if (!mounted || _loading) return;
    try {
      final refreshed = await _rideSvc.getRideDetail(widget.rideId);
      if (!mounted) return;

      setState(() {
        _ride = refreshed;
        if (!_updatingRouteSelection) {
          _selectedDriverRouteKey =
              refreshed.routeSelectedKey ?? _selectedDriverRouteKey;
        }
      });

      await _refreshRideThreadUnreadBadges(ride: refreshed);
      _configureProgressRefresh(refreshed);
    } catch (_) {
      // Ignore background refresh failures.
    }
  }

  Future<void> _refreshRideThreadUnreadBadges({Ride? ride}) async {
    if (_isRefreshingRideThreadBadges) {
      return;
    }
    final targetRide = ride ?? _ride;
    if (targetRide == null) return;

    _isRefreshingRideThreadBadges = true;
    try {
      final result = await _chatSvc.getThreads(state: 'all', limit: 200);
      if (!mounted) return;

      final next = <String, int>{};
      for (final thread in result.threads) {
        if (thread.rideId != targetRide.id) {
          continue;
        }
        final bookingId = thread.bookingId.trim();
        if (bookingId.isEmpty) {
          continue;
        }
        final unread = thread.unreadCount < 0 ? 0 : thread.unreadCount;
        final previous = next[bookingId] ?? 0;
        if (unread > previous) {
          next[bookingId] = unread;
        }
      }

      if (!mounted || mapEquals(_rideThreadUnreadByBookingId, next)) {
        return;
      }
      setState(() {
        _rideThreadUnreadByBookingId = next;
      });
    } catch (_) {
      // Keep last known badge state on transient failures.
    } finally {
      _isRefreshingRideThreadBadges = false;
    }
  }

  int _threadUnreadForBooking(String bookingId) {
    return _rideThreadUnreadByBookingId[bookingId] ?? 0;
  }

  Widget _buildRideChatAction({
    required VoidCallback onTap,
    required int unreadCount,
    required double buttonSize,
    required double iconSize,
  }) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        InkWell(
          borderRadius: BorderRadius.circular(999),
          onTap: onTap,
          child: Container(
            width: buttonSize,
            height: buttonSize,
            decoration: BoxDecoration(
              color: AppColors.primary.withValues(alpha: 0.12),
              shape: BoxShape.circle,
            ),
            child: Icon(
              Icons.chat_rounded,
              size: iconSize,
              color: AppColors.primary,
            ),
          ),
        ),
        if (unreadCount > 0)
          Positioned(
            right: -2,
            top: -2,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
              decoration: const BoxDecoration(
                color: AppColors.error,
                shape: BoxShape.circle,
              ),
              constraints: const BoxConstraints(minWidth: 16, minHeight: 16),
              child: Text(
                unreadCount > 9 ? '9+' : '$unreadCount',
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 9,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ),
      ],
    );
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'open':
        return AppColors.info;
      case 'in_progress':
        return AppColors.accent;
      case 'completed':
        return AppColors.success;
      case 'cancelled':
        return AppColors.error;
      default:
        return AppColors.textSecondary;
    }
  }

  BoxDecoration _rideDetailCardDecoration({
    double radius = AppConstants.radiusMedium,
  }) {
    return HomeDesignSystem.darkTopBarSurface(radius: radius).copyWith(
      border: Border.all(color: Colors.white.withValues(alpha: 0.16), width: 1),
    );
  }

  void _showRatingDialog({
    required String toUserId,
    String? bookingId,
    String counterpartName = 'this user',
  }) {
    int selectedRating = 5;
    final commentCtrl = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setDS) {
            return AlertDialog(
              title: Text('Rate $counterpartName'),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(5, (i) {
                      return IconButton(
                        onPressed: () => setDS(() => selectedRating = i + 1),
                        icon: Icon(
                          i < selectedRating
                              ? Icons.star_rounded
                              : Icons.star_outline_rounded,
                          color: AppColors.accent,
                          size: 36,
                        ),
                      );
                    }),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: commentCtrl,
                    maxLines: 3,
                    decoration: const InputDecoration(
                      labelText: 'Comment (optional)',
                      hintText: 'How was your ride?',
                    ),
                  ),
                ],
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(ctx),
                  child: const Text('Cancel'),
                ),
                ElevatedButton(
                  onPressed: () async {
                    Navigator.pop(ctx);
                    try {
                      final comment = commentCtrl.text.trim();
                      await _rateSvc.createRating(
                        rideId: widget.rideId,
                        rating: selectedRating,
                        toUserId: toUserId,
                        bookingId: bookingId,
                        comment: comment.isNotEmpty ? comment : null,
                      );
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Rating submitted!'),
                            backgroundColor: AppColors.success,
                          ),
                        );
                      }
                      _load();
                    } catch (e) {
                      if (_isDuplicateRatingError(e)) {
                        await _showAlreadyRatedPopup(
                          counterpartName: counterpartName,
                        );
                        return;
                      }
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text('Rating failed: $e')),
                        );
                      }
                    }
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primary,
                    foregroundColor: Colors.white,
                  ),
                  child: const Text('Submit'),
                ),
              ],
            );
          },
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_loading) {
      return Scaffold(
        backgroundColor: _createRideGreenBackground,
        appBar: AppBar(title: const Text('Ride Details')),
        body: const SyloLoader(message: 'Loading ride…'),
      );
    }
    if (_error != null) {
      return Scaffold(
        backgroundColor: _createRideGreenBackground,
        appBar: AppBar(title: const Text('Ride Details')),
        body: SyloError(message: _error!, onRetry: _load),
      );
    }
    if (_ride == null) {
      return Scaffold(
        backgroundColor: _createRideGreenBackground,
        appBar: AppBar(title: const Text('Ride Details')),
        body: const SyloEmpty(
          icon: Icons.directions_car_rounded,
          title: 'Ride not found',
          subtitle: 'This ride may have been deleted.',
        ),
      );
    }

    final ride = _ride!;
    final statusColor = _statusColor(ride.status);
    final isDriver = ride.driverId == _userId;
    final ratingTarget = _resolvePreferredRatingTarget(ride);
    final canRate = ratingTarget != null && _existingRating == null;
    final effectiveBookedSeats = _effectiveBookedSeats(ride);
    final myBooking = _findCurrentUserBooking(ride);
    final canCancelMyBooking = !isDriver && (myBooking?.canCancel ?? false);
    final selectedRoute = _selectedRouteAlternative(ride);
    final selectedPolyline =
        (selectedRoute?.polyline != null && selectedRoute!.polyline!.isNotEmpty)
            ? selectedRoute.polyline
            : ride.polyline;
    final passengerStopColors =
        _buildPassengerStopColorMap(ride, selectedRoute);
    final stopMarkers =
        _buildRouteStopMarkers(ride, selectedRoute, passengerStopColors);
    final routeColorStops =
        _buildRouteColorStops(ride, selectedRoute, passengerStopColors);

    return Scaffold(
      backgroundColor: _createRideGreenBackground,
      appBar: AppBar(
        title: const Text('Ride Details'),
        actions: [
          if (canCancelMyBooking)
            Padding(
              padding: const EdgeInsets.only(right: 4),
              child: InkWell(
                borderRadius: BorderRadius.circular(999),
                onTap: () => _showCancelBookingDialog(myBooking!),
                child: Container(
                  width: 36,
                  height: 36,
                  decoration: const BoxDecoration(
                    color: AppColors.error,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.close_rounded,
                    color: Colors.white,
                    size: 20,
                  ),
                ),
              ),
            ),
          if (canRate)
            IconButton(
              onPressed: () => _showRatingDialog(
                toUserId: ratingTarget.toUserId,
                bookingId: ratingTarget.bookingId,
                counterpartName: ratingTarget.label,
              ),
              icon: const Icon(Icons.star_rounded),
              tooltip: 'Rate Ride',
            ),
        ],
      ),
      body: RefreshIndicator(
        color: AppColors.primary,
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(AppConstants.paddingMedium),
          children: [
            // Status banner
            Container(
              padding: const EdgeInsets.all(16),
              decoration: _rideDetailCardDecoration(),
              child: Row(
                children: [
                  Icon(
                    ride.status == 'completed'
                        ? Icons.check_circle_rounded
                        : ride.status == 'in_progress'
                            ? Icons.play_circle_rounded
                            : ride.status == 'cancelled'
                                ? Icons.cancel_rounded
                                : Icons.schedule_rounded,
                    color: statusColor,
                    size: 28,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          ride.effectiveDisplayStatus,
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            fontSize: 16,
                            color: statusColor,
                          ),
                        ),
                        if (ride.departureDatetime != null)
                          Text(
                            _formatDateTime(ride.departureDatetime!),
                            style: const TextStyle(
                              color: _rideCardTextSecondary,
                              fontSize: 12,
                            ),
                          ),
                      ],
                    ),
                  ),
                  if (isDriver)
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: AppColors.primary.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(_driverRoleChipLabel(ride),
                          style: const TextStyle(
                              color: AppColors.primary,
                              fontSize: 12,
                              fontWeight: FontWeight.w600)),
                    ),
                ],
              ),
            ),

            const SizedBox(height: 20),

            // Route card
            Container(
              padding: const EdgeInsets.all(16),
              decoration: _rideDetailCardDecoration(),
              child: Column(
                children: [
                  _routePoint(
                      Icons.circle, AppColors.primary, 'From', ride.origin),
                  Padding(
                    padding: const EdgeInsets.only(left: 11),
                    child: Container(
                      width: 2,
                      height: 24,
                      color: Colors.white.withValues(alpha: 0.24),
                    ),
                  ),
                  _routePoint(
                      Icons.circle, AppColors.accent, 'To', ride.destination),
                ],
              ),
            ),

            // ── Route Map (shows if ride has geo data) ──
            if (ride.hasGeoData) ...[
              const SizedBox(height: 16),
              ClipRRect(
                borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
                child: RouteMapWidget(
                  origin: LatLng(ride.originLat!, ride.originLng!),
                  destination:
                      LatLng(ride.destinationLat!, ride.destinationLng!),
                  originLabel: ride.origin,
                  destinationLabel: ride.destination,
                  height: 220,
                  showAlternatives: false,
                  interactive: true,
                  encodedPolyline: selectedPolyline,
                  extraMarkers: stopMarkers,
                  routeColorStops: routeColorStops,
                ),
              ),
              if (isDriver &&
                  ride.status == 'open' &&
                  ride.routeAlternatives != null &&
                  ride.routeAlternatives!.length > 1) ...[
                const SizedBox(height: 10),
                SizedBox(
                  height: 40,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: ride.routeAlternatives!.length,
                    separatorBuilder: (_, __) => const SizedBox(width: 8),
                    itemBuilder: (context, index) {
                      final option = ride.routeAlternatives![index];
                      final routeKey = option.key;
                      final isSelected = (_selectedDriverRouteKey ??
                              ride.routeSelectedKey ??
                              '') ==
                          routeKey;

                      return GestureDetector(
                        onTap: _updatingRouteSelection
                            ? null
                            : () => _updateDriverRouteSelection(ride, routeKey),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 180),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 12, vertical: 8),
                          decoration: BoxDecoration(
                            color: isSelected
                                ? AppColors.primary
                                : Colors.white.withValues(alpha: 0.14),
                            borderRadius: BorderRadius.circular(99),
                            border: Border.all(
                              color: isSelected
                                  ? AppColors.primary
                                  : Colors.white.withValues(alpha: 0.24),
                            ),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                '${option.durationMinutes} min • ${option.distanceKm.toStringAsFixed(1)} km',
                                style: TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w700,
                                  color: isSelected
                                      ? Colors.white
                                      : _rideCardTextPrimary,
                                ),
                              ),
                              if (option.isOptimal) ...[
                                const SizedBox(width: 8),
                                Container(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 7,
                                    vertical: 2,
                                  ),
                                  decoration: BoxDecoration(
                                    color: isSelected
                                        ? Colors.white.withValues(alpha: 0.22)
                                        : AppColors.success
                                            .withValues(alpha: 0.14),
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                  child: Text(
                                    'Optimal',
                                    style: TextStyle(
                                      fontSize: 10,
                                      fontWeight: FontWeight.w700,
                                      color: isSelected
                                          ? Colors.white
                                          : AppColors.success,
                                    ),
                                  ),
                                ),
                              ],
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
                if (_updatingRouteSelection)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Row(
                      children: [
                        const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          'Applying selected route...',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: _rideCardTextSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ],

            if (isDriver) ...[
              const SizedBox(height: 16),
              _buildDriverRideActionPanel(theme, ride),
            ],

            const SizedBox(height: 16),

            // Fare & details
            Container(
              padding: const EdgeInsets.all(16),
              decoration: _rideDetailCardDecoration(),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Fare Breakdown',
                      style: theme.textTheme.titleSmall
                          ?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: _rideCardTextPrimary)),
                  const SizedBox(height: 12),
                  _detailRow('Price per Seat',
                      '₨ ${ride.pricePerSeat.toStringAsFixed(0)}'),
                  _detailRow('Available Seats', '${ride.availableSeats}'),
                  _detailRow('Booked Seats', '$effectiveBookedSeats'),
                  _detailRow('Total Earnings',
                      '₨ ${ride.totalEarnings.toStringAsFixed(0)}'),
                  if (ride.isRecurringRide &&
                      (ride.recurringStartDate != null ||
                          ride.recurringEndDate != null))
                    _detailRow('Recurring Date Range',
                        _formatRecurringDateRange(ride)),
                  if (ride.estimatedDuration != null)
                    _detailRow(
                        'Est. Duration', '${ride.estimatedDuration} min'),
                  if (ride.routeDistanceKm != null)
                    _detailRow('Distance',
                        '${ride.routeDistanceKm!.toStringAsFixed(1)} km'),
                ],
              ),
            ),

            const SizedBox(height: 16),

            _buildDriverDetailsCard(theme, ride, isDriver),

            // Bookings list
            if (ride.bookings != null && ride.bookings!.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text(isDriver ? 'Passengers' : 'Riders On This Trip',
                  style: theme.textTheme.titleSmall
                      ?.copyWith(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              ...ride.bookings!.map((b) {
                final passengerName = b.passengerName?.trim();
                final passengerPhone = b.passengerPhone?.trim();
                final isCurrentUserBooking =
                    _userId != null && b.passengerId == _userId;
                final displayName = isDriver
                    ? ((passengerName != null && passengerName.isNotEmpty)
                        ? passengerName
                        : 'Passenger')
                    : ((passengerName != null && passengerName.isNotEmpty)
                        ? (isCurrentUserBooking
                            ? 'You ($passengerName)'
                            : passengerName)
                        : (isCurrentUserBooking ? 'You' : 'Passenger'));

                final subtitleParts = <String>[
                  if (isDriver &&
                      passengerPhone != null &&
                      passengerPhone.isNotEmpty)
                    passengerPhone,
                  '${b.bookedSeats} seat${b.bookedSeats > 1 ? 's' : ''}',
                  '₨ ${b.totalPrice.toStringAsFixed(0)}',
                  _paymentStatusLabel(b.paymentStatus),
                ];
                final stopAccentColor =
                    passengerStopColors[b.id] ?? _fallbackPassengerStopColor;

                return Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(12),
                  decoration: _rideDetailCardDecoration(),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          _bookingPassengerAvatar(b),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(displayName,
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w500,
                                        color: _rideCardTextPrimary)),
                                Text(
                                  subtitleParts.join(' • '),
                                  style: const TextStyle(
                                      color: _rideCardTextSecondary,
                                      fontSize: 12),
                                ),
                              ],
                            ),
                          ),
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 8, vertical: 4),
                                decoration: BoxDecoration(
                                  color: _bookingColor(b.status)
                                      .withValues(alpha: 0.12),
                                  borderRadius: BorderRadius.circular(6),
                                ),
                                child: Text(
                                  b.status.toUpperCase(),
                                  style: TextStyle(
                                    color: _bookingColor(b.status),
                                    fontSize: 10,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                              if (isDriver) ...[
                                const SizedBox(width: 8),
                                _buildRideChatAction(
                                  onTap: () => _openPassengerChat(b, ride),
                                  unreadCount: _threadUnreadForBooking(b.id),
                                  buttonSize: 28,
                                  iconSize: 16,
                                ),
                              ],
                            ],
                          ),
                        ],
                      ),
                      if (_hasStopRouteData(b)) ...[
                        const SizedBox(height: 10),
                        Divider(
                          height: 1,
                          color: Colors.white.withValues(alpha: 0.18),
                        ),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            _stopDetailChip(
                              theme,
                              icon: Icons.login_rounded,
                              label: b.pickupStopOrder != null
                                  ? 'Pickup stop #${b.pickupStopOrder}'
                                  : 'Pickup ${_formatPctAlongRoute(b.pickupPct)} (${_formatKmLabel(b.pickupRouteKm)})',
                              accentColor: stopAccentColor,
                            ),
                            _stopDetailChip(
                              theme,
                              icon: Icons.logout_rounded,
                              label: b.dropoffStopOrder != null
                                  ? 'Dropoff stop #${b.dropoffStopOrder}'
                                  : 'Drop ${_formatPctAlongRoute(b.dropoffPct)} (${_formatKmLabel(b.dropoffRouteKm)})',
                              accentColor: stopAccentColor,
                            ),
                            if (b.segmentKm != null)
                              _stopDetailChip(
                                theme,
                                icon: Icons.route_rounded,
                                label: 'Segment ${_formatKmLabel(b.segmentKm)}',
                                accentColor: stopAccentColor,
                              ),
                            if (b.plannedPickupEta != null ||
                                b.estimatedPickupTime != null)
                              _stopDetailChip(
                                theme,
                                icon: Icons.schedule_rounded,
                                label:
                                    'ETA ${_formatShortTime(b.plannedPickupEta ?? b.estimatedPickupTime!)}',
                                accentColor: stopAccentColor,
                              ),
                            if (b.individualFare != null)
                              _stopDetailChip(
                                theme,
                                icon: Icons.payments_rounded,
                                label:
                                    'Fare ₨ ${b.individualFare!.toStringAsFixed(0)}',
                                accentColor: stopAccentColor,
                              ),
                          ],
                        ),
                        if (b.pickupAddress != null &&
                            b.pickupAddress!.trim().isNotEmpty) ...[
                          const SizedBox(height: 6),
                          Text(
                            'Pickup: ${b.pickupAddress!.trim()}',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: _rideCardTextSecondary,
                            ),
                          ),
                        ],
                        if (b.dropoffAddress != null &&
                            b.dropoffAddress!.trim().isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Text(
                            'Dropoff: ${b.dropoffAddress!.trim()}',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: _rideCardTextSecondary,
                            ),
                          ),
                        ],
                      ],
                      if (isDriver)
                        _buildDriverBookingExecutionActions(theme, ride, b),
                    ],
                  ),
                );
              }),
            ],

            // Existing rating
            if (_existingRating != null) ...[
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: _rideDetailCardDecoration(),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Your Rating',
                        style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: _rideCardTextPrimary)),
                    const SizedBox(height: 8),
                    Row(
                      children: List.generate(5, (i) {
                        return Icon(
                          i < _existingRating!.rating
                              ? Icons.star_rounded
                              : Icons.star_outline_rounded,
                          color: AppColors.accent,
                          size: 24,
                        );
                      }),
                    ),
                    if (_existingRating!.comment != null) ...[
                      const SizedBox(height: 8),
                      Text(
                        _existingRating!.comment!,
                        style: const TextStyle(
                            color: _rideCardTextSecondary, fontSize: 13),
                      ),
                    ],
                  ],
                ),
              ),
            ],

            // Rate button for completed rides
            if (canRate) ...[
              const SizedBox(height: 20),
              SizedBox(
                height: 52,
                child: ElevatedButton.icon(
                  onPressed: () => _showRatingDialog(
                    toUserId: ratingTarget.toUserId,
                    bookingId: ratingTarget.bookingId,
                    counterpartName: ratingTarget.label,
                  ),
                  icon: const Icon(Icons.star_rounded),
                  label: const Text('Rate this Ride'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.accent,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusMedium),
                    ),
                  ),
                ),
              ),
            ],

            // Track Driver button for in-progress rides (passengers only)
            if (ride.status == 'in_progress' && !isDriver) ...[
              const SizedBox(height: 20),
              SizedBox(
                height: 52,
                child: ElevatedButton.icon(
                  onPressed: () => Navigator.pushNamed(
                    context,
                    '/live-tracking',
                    arguments: {
                      'rideId': ride.id,
                      'driverName': null, // Driver name not in Ride model
                      'bookingId': myBooking?.id,
                      'passengerId': myBooking?.passengerId,
                      'pickupLocation':
                          ride.originLat != null && ride.originLng != null
                              ? LatLng(ride.originLat!, ride.originLng!)
                              : null,
                      'dropoffLocation': ride.destinationLat != null &&
                              ride.destinationLng != null
                          ? LatLng(ride.destinationLat!, ride.destinationLng!)
                          : null,
                    },
                  ),
                  icon: const Icon(Icons.location_on_rounded),
                  label: const Text('Track Driver Live'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.info,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusMedium),
                    ),
                  ),
                ),
              ),
            ],
            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }

  Widget _routePoint(IconData icon, Color color, String label, String text) {
    return Row(
      children: [
        Icon(icon, size: 10, color: color),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label,
                  style: const TextStyle(
                      color: _rideCardTextSecondary, fontSize: 11)),
              Text(text,
                  style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 15,
                      color: _rideCardTextPrimary)),
            ],
          ),
        ),
      ],
    );
  }

  Widget _detailRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label,
              style:
                  const TextStyle(color: _rideCardTextSecondary, fontSize: 14)),
          Text(value,
              style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                  color: _rideCardTextPrimary)),
        ],
      ),
    );
  }

  String _formatRecurringDateRange(Ride ride) {
    final start = (ride.recurringStartDate ?? '').trim();
    final end = (ride.recurringEndDate ?? '').trim();
    if (start.isEmpty && end.isEmpty) return 'Series';
    if (start.isNotEmpty && end.isNotEmpty) {
      return '${_formatRecurringDate(start)} - ${_formatRecurringDate(end)}';
    }
    if (start.isNotEmpty) return 'From ${_formatRecurringDate(start)}';
    return 'Until ${_formatRecurringDate(end)}';
  }

  String _formatRecurringDate(String raw) {
    final parsed = DateTime.tryParse(raw);
    if (parsed == null) return raw;
    final local = parsed.isUtc ? parsed.toLocal() : parsed;
    final dd = local.day.toString().padLeft(2, '0');
    final mm = local.month.toString().padLeft(2, '0');
    final yy = local.year.toString();
    return '$dd/$mm/$yy';
  }

  bool _canDriverStartRide(Ride ride) {
    if (ride.status != 'open') return false;
    return ride.canDriverStart ?? true;
  }

  bool _canDriverCompleteRide(Ride ride) {
    if (ride.status != 'in_progress') return false;
    return ride.canDriverComplete ?? true;
  }

  Future<void> _showDriverActionBlockedDialog({
    required String title,
    required String message,
  }) async {
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  Widget _buildDriverRideActionPanel(ThemeData theme, Ride ride) {
    final progress = ride.executionProgress;
    final isOpenRide = ride.status == 'open';
    final isInProgressRide = ride.status == 'in_progress';
    final canStart = _canDriverStartRide(ride);
    final canComplete = _canDriverCompleteRide(ride);
    final canCancel = ride.status == 'open' &&
        (ride.canDriverCancel ?? ride.status == 'open');

    final nextStopLabel = _nextStopLabel(ride, progress);

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: _rideDetailCardDecoration(),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Trip Controls',
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.bold,
              color: _rideCardTextPrimary,
            ),
          ),
          if (progress != null) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _stopDetailChip(
                  theme,
                  icon: Icons.people_alt_rounded,
                  label:
                      '${progress.completedBookings}/${progress.activeBookings} riders done',
                ),
                _stopDetailChip(
                  theme,
                  icon: Icons.alt_route_rounded,
                  label:
                      '${progress.completedStops}/${progress.totalStops} stops (${progress.completionPct.toStringAsFixed(0)}%)',
                ),
              ],
            ),
          ],
          if (nextStopLabel != null && nextStopLabel.isNotEmpty) ...[
            const SizedBox(height: 10),
            Text(
              'Next stop: $nextStopLabel',
              style: theme.textTheme.bodySmall?.copyWith(
                color: _rideCardTextSecondary,
              ),
            ),
          ],
          const SizedBox(height: 12),
          if (_updatingRideStatus)
            Row(
              children: [
                const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                const SizedBox(width: 8),
                Text(
                  'Updating ride status...',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: _rideCardTextSecondary,
                  ),
                ),
              ],
            ),
          if (!_updatingRideStatus)
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                if (isOpenRide)
                  ElevatedButton.icon(
                    onPressed: () {
                      if (canStart) {
                        _updateDriverRideStatus(
                          ride,
                          'in_progress',
                          successMessage: 'Ride started.',
                        );
                      } else {
                        _showDriverActionBlockedDialog(
                          title: 'Cannot Start Ride',
                          message:
                              'You need at least one passenger to start a ride.',
                        );
                      }
                    },
                    icon: const Icon(Icons.play_arrow_rounded),
                    label: const Text('Start Ride'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor:
                          canStart ? AppColors.primary : AppColors.border,
                      foregroundColor:
                          canStart ? Colors.white : AppColors.textHint,
                    ),
                  ),
                if (isInProgressRide)
                  ElevatedButton.icon(
                    onPressed: () {
                      if (canComplete) {
                        _updateDriverRideStatus(
                          ride,
                          'completed',
                          successMessage: 'Ride completed.',
                        );
                      } else {
                        _showDriverActionBlockedDialog(
                          title: 'Cannot Complete Ride',
                          message:
                              'You need to complete all the pickups and drop offs to complete a ride.',
                        );
                      }
                    },
                    icon: const Icon(Icons.check_circle_rounded),
                    label: const Text('Complete Ride'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor:
                          canComplete ? AppColors.success : AppColors.border,
                      foregroundColor:
                          canComplete ? Colors.white : AppColors.textHint,
                    ),
                  ),
                if (canCancel)
                  OutlinedButton.icon(
                    onPressed: () => _updateDriverRideStatus(
                      ride,
                      'cancelled',
                      successMessage: 'Ride cancelled.',
                    ),
                    icon: const Icon(Icons.cancel_outlined),
                    label: const Text('Cancel Ride'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.error,
                      side: const BorderSide(color: AppColors.error),
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }

  Future<void> _updateDriverRideStatus(
    Ride ride,
    String targetStatus, {
    required String successMessage,
  }) async {
    if (_updatingRideStatus) return;

    if (targetStatus == 'in_progress' && !_canDriverStartRide(ride)) {
      await _showDriverActionBlockedDialog(
        title: 'Cannot Start Ride',
        message: 'You need at least one passenger to start a ride.',
      );
      return;
    }

    if (targetStatus == 'completed' && !_canDriverCompleteRide(ride)) {
      await _showDriverActionBlockedDialog(
        title: 'Cannot Complete Ride',
        message:
            'You need to complete all the pickups and drop offs to complete a ride.',
      );
      return;
    }

    setState(() {
      _updatingRideStatus = true;
    });

    try {
      await _rideSvc.updateRideStatus(ride.id, targetStatus);

      if (targetStatus == 'in_progress') {
        try {
          await _tripSvc.startTrip(ride.id);
        } catch (_) {
          // Trip workflow endpoint is optional for backward compatibility.
        }
        await _startDriverTelemetryPublishing(ride.id);
      } else if (targetStatus == 'completed') {
        try {
          await _tripSvc.completeTrip(ride.id, settlePayments: true);
        } catch (_) {
          // Trip workflow endpoint is optional for backward compatibility.
        }
        _stopDriverTelemetryPublishing();
      } else if (targetStatus == 'cancelled') {
        _stopDriverTelemetryPublishing();
      }

      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(successMessage),
          backgroundColor: AppColors.success,
        ),
      );

      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to update ride: $e'),
          backgroundColor: AppColors.error,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _updatingRideStatus = false;
        });
      }
    }
  }

  RideBooking? _findBookingById(Ride ride, String? bookingId) {
    final id = (bookingId ?? '').trim();
    if (id.isEmpty) return null;

    for (final booking in ride.bookings ?? const <RideBooking>[]) {
      if (booking.id == id) return booking;
    }
    return null;
  }

  String? _nextStopLabel(Ride ride, RideExecutionProgress? progress) {
    if (progress == null || progress.nextStopOrder == null) return null;
    final eventType = (progress.nextStopType ?? '').toLowerCase();
    final eventLabel = eventType == 'dropoff' ? 'Dropoff' : 'Pickup';

    final booking = _findBookingById(ride, progress.nextStopBookingId);
    final passengerName = (booking?.passengerName ?? '').trim();
    if (passengerName.isNotEmpty) {
      return '#${progress.nextStopOrder} • $eventLabel • $passengerName';
    }

    return '#${progress.nextStopOrder} • $eventLabel';
  }

  Widget _buildDriverBookingExecutionActions(
    ThemeData theme,
    Ride ride,
    RideBooking booking,
  ) {
    if (ride.status != 'in_progress' || booking.isCancelled) {
      return const SizedBox.shrink();
    }

    final busy = _bookingProgressBusy.contains(booking.id);
    final canPickup = !booking.hasPickedUp && !booking.hasDroppedOff;
    final canDropoff = booking.hasPickedUp && !booking.hasDroppedOff;

    if (!canPickup && !canDropoff && !busy) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 10),
        Divider(
          height: 1,
          color: Colors.white.withValues(alpha: 0.16),
        ),
        const SizedBox(height: 8),
        if (busy)
          Row(
            children: [
              const SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              const SizedBox(width: 8),
              Text(
                'Updating passenger stop...',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: _rideCardTextSecondary,
                ),
              ),
            ],
          ),
        if (!busy)
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (canPickup)
                OutlinedButton.icon(
                  onPressed: () => _markDriverPickupComplete(booking),
                  icon: const Icon(Icons.login_rounded, size: 18),
                  label: const Text('Mark Pickup Done'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: Colors.white,
                  ),
                ),
              if (canDropoff)
                ElevatedButton.icon(
                  onPressed: () => _markDriverDropoffComplete(booking),
                  icon: const Icon(Icons.logout_rounded, size: 18),
                  label: const Text('Mark Dropoff Done'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.success,
                    foregroundColor: Colors.white,
                  ),
                ),
            ],
          ),
      ],
    );
  }

  Future<void> _markDriverPickupComplete(RideBooking booking) async {
    if (_bookingProgressBusy.contains(booking.id)) return;

    setState(() {
      _bookingProgressBusy.add(booking.id);
    });

    try {
      await _rideSvc.markBookingPickupComplete(booking.id);
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Pickup marked complete.'),
          backgroundColor: AppColors.success,
        ),
      );

      await _refreshRideSilently();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to mark pickup: $e'),
          backgroundColor: AppColors.error,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _bookingProgressBusy.remove(booking.id);
        });
      }
    }
  }

  Future<void> _markDriverDropoffComplete(RideBooking booking) async {
    if (_bookingProgressBusy.contains(booking.id)) return;

    setState(() {
      _bookingProgressBusy.add(booking.id);
    });

    try {
      await _rideSvc.markBookingDropoffComplete(booking.id);
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Dropoff marked complete.'),
          backgroundColor: AppColors.success,
        ),
      );

      await _refreshRideSilently();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to mark dropoff: $e'),
          backgroundColor: AppColors.error,
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _bookingProgressBusy.remove(booking.id);
        });
      }
    }
  }

  Widget _buildDriverDetailsCard(ThemeData theme, Ride ride, bool isDriver) {
    final driver = ride.driverSummary;
    final myBooking = !isDriver ? _findCurrentUserBooking(ride) : null;
    final driverName = (driver?.name ?? 'Driver').trim();
    final carName = (driver?.carName ?? '').trim();
    final vehiclePlate = (driver?.vehiclePlate ?? '').trim();
    final ratingLabel = driver?.ratingAvg != null
        ? driver!.ratingAvg!.toStringAsFixed(1)
        : 'N/A';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Driver Details',
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.bold,
            color: _outsideCardTextColor,
          ),
        ),
        const SizedBox(height: 8),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: _rideDetailCardDecoration(),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  _driverAvatar(driver),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          driverName.isEmpty ? 'Driver' : driverName,
                          style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 14,
                            color: _rideCardTextPrimary,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          carName.isNotEmpty
                              ? carName
                              : (vehiclePlate.isNotEmpty
                                  ? vehiclePlate
                                  : 'Vehicle details pending'),
                          style: TextStyle(
                            color: _rideCardTextSecondary,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (!isDriver)
                    _buildRideChatAction(
                      onTap: () => _openDriverChat(ride),
                      unreadCount: myBooking == null
                          ? 0
                          : _threadUnreadForBooking(myBooking.id),
                      buttonSize: 30,
                      iconSize: 17,
                    ),
                ],
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _driverDetailChip(
                    theme,
                    icon: Icons.star_rounded,
                    label: '$ratingLabel average',
                  ),
                  _driverDetailChip(
                    theme,
                    icon: Icons.verified_rounded,
                    label: '${driver?.completedRides ?? 0} completed rides',
                  ),
                  if (vehiclePlate.isNotEmpty)
                    _driverDetailChip(
                      theme,
                      icon: Icons.directions_car_filled_rounded,
                      label: vehiclePlate,
                    ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _driverAvatar(RideDriverSummary? driver) {
    final initials = _passengerInitials(driver?.name);
    final provider = _profileImageProvider(driver?.profilePhoto);

    return SizedBox(
      width: 36,
      height: 36,
      child: Stack(
        children: [
          CircleAvatar(
            radius: 18,
            backgroundColor: AppColors.accent,
            child: Text(
              initials,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          if (provider != null)
            Positioned.fill(
              child: ClipOval(
                child: Image(
                  image: provider,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _driverDetailChip(
    ThemeData theme, {
    required IconData icon,
    required String label,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.primary.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.35)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: AppColors.primary),
          const SizedBox(width: 6),
          Text(
            label,
            style: theme.textTheme.bodySmall?.copyWith(
              color: _rideCardTextPrimary,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  Widget _bookingPassengerAvatar(RideBooking booking) {
    final initials = _passengerInitials(booking.passengerName);
    final provider = _profileImageProvider(booking.passengerProfilePhoto);

    return SizedBox(
      width: 36,
      height: 36,
      child: Stack(
        children: [
          CircleAvatar(
            radius: 18,
            backgroundColor: AppColors.primary,
            child: Text(
              initials,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          if (provider != null)
            Positioned.fill(
              child: ClipOval(
                child: Image(
                  image: provider,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => const SizedBox.shrink(),
                ),
              ),
            ),
        ],
      ),
    );
  }

  String _apiOrigin() {
    final parsed = Uri.tryParse(AppConstants.baseUrl);
    if (parsed == null || !parsed.hasScheme || parsed.host.isEmpty) {
      return '';
    }

    final portPart = parsed.hasPort ? ':${parsed.port}' : '';
    return '${parsed.scheme}://${parsed.host}$portPart';
  }

  String? _resolveProfilePhotoUrl(String? rawPhoto) {
    final value = (rawPhoto ?? '').trim();
    if (value.isEmpty || value.startsWith('data:image/')) {
      return null;
    }

    final normalized = value.replaceAll('\\', '/');
    if (normalized.startsWith('http://') || normalized.startsWith('https://')) {
      return normalized;
    }

    final origin = _apiOrigin();
    if (origin.isEmpty) {
      return null;
    }

    if (normalized.startsWith('/')) {
      return '$origin$normalized';
    }
    if (normalized.startsWith('static/')) {
      return '$origin/$normalized';
    }
    if (normalized.startsWith('uploads/')) {
      return '$origin/static/$normalized';
    }
    return '$origin/$normalized';
  }

  ImageProvider? _profileImageProvider(String? rawPhoto) {
    final value = (rawPhoto ?? '').trim();
    if (value.isEmpty) {
      return null;
    }

    if (value.startsWith('data:image/')) {
      try {
        final parts = value.split(',');
        if (parts.length >= 2) {
          return MemoryImage(base64Decode(parts[1]));
        }
      } catch (_) {
        return null;
      }
      return null;
    }

    final photoUrl = _resolveProfilePhotoUrl(value);
    if (photoUrl == null || photoUrl.isEmpty) {
      return null;
    }

    return NetworkImage(photoUrl);
  }

  String _passengerInitials(String? fullName) {
    final parts = (fullName ?? '')
        .trim()
        .split(RegExp(r'\s+'))
        .where((token) => token.isNotEmpty)
        .toList();

    if (parts.isEmpty) return 'P';
    if (parts.length == 1) {
      return parts.first.substring(0, 1).toUpperCase();
    }

    final first = parts.first.substring(0, 1).toUpperCase();
    final last = parts.last.substring(0, 1).toUpperCase();
    return '$first$last';
  }

  RideBooking? _findCurrentUserBooking(Ride ride) {
    final userId = _userId;
    if (userId == null || userId.isEmpty) return null;

    for (final booking in ride.bookings ?? const <RideBooking>[]) {
      if (booking.passengerId == userId) {
        return booking;
      }
    }
    return null;
  }

  ({String toUserId, String? bookingId, String label})?
      _resolvePreferredRatingTarget(Ride ride) {
    final userId = (_userId ?? '').trim();
    if (userId.isEmpty) return null;

    final isDriver = ride.driverId == userId;

    if (!isDriver) {
      final myBooking = _findCurrentUserBooking(ride);
      if (myBooking == null) return null;

      final eligible = myBooking.hasDroppedOff || ride.status == 'completed';
      if (!eligible) return null;

      final driverName = (ride.driverSummary?.name ?? 'Driver').trim();
      return (
        toUserId: ride.driverId,
        bookingId: myBooking.id,
        label: driverName.isNotEmpty ? driverName : 'Driver',
      );
    }

    final eligiblePassengerBookings =
        (ride.bookings ?? const <RideBooking>[]).where((booking) {
      if (booking.isCancelled) return false;
      if (booking.passengerId.isEmpty || booking.passengerId == userId) {
        return false;
      }
      return booking.hasDroppedOff || ride.status == 'completed';
    }).toList();

    if (eligiblePassengerBookings.length != 1) {
      return null;
    }

    final passengerBooking = eligiblePassengerBookings.first;
    final passengerName =
        (passengerBooking.passengerName ?? 'Passenger').trim();
    return (
      toUserId: passengerBooking.passengerId,
      bookingId: passengerBooking.id,
      label: passengerName.isNotEmpty ? passengerName : 'Passenger',
    );
  }

  void _showCancelBookingDialog(RideBooking booking) {
    if (!booking.canCancel) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('This booking can no longer be cancelled.'),
          backgroundColor: AppColors.warning,
        ),
      );
      return;
    }

    final reasonCtrl = TextEditingController();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Text('Cancel Booking?'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Are you sure you want to cancel this booking?'),
            const SizedBox(height: 16),
            TextField(
              controller: reasonCtrl,
              decoration: InputDecoration(
                labelText: 'Reason (optional)',
                border:
                    OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
              ),
              maxLines: 2,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Keep'),
          ),
          ElevatedButton(
            onPressed: () async {
              Navigator.pop(ctx);
              try {
                await _rideSvc.cancelBooking(
                  booking.id,
                  reason: reasonCtrl.text.isEmpty ? null : reasonCtrl.text,
                );
                await _load();
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('Booking cancelled'),
                      backgroundColor: AppColors.warning,
                    ),
                  );
                }
              } catch (e) {
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Cancellation failed: $e')),
                  );
                }
              }
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.error,
              foregroundColor: Colors.white,
            ),
            child: const Text('Cancel Booking'),
          ),
        ],
      ),
    );
  }

  String _rideChatTitle(Ride ride) {
    final from = ride.origin.trim();
    final to = ride.destination.trim();
    if (from.isEmpty || to.isEmpty) return 'Ride Chat';
    return '$from → $to';
  }

  Future<void> _openPassengerChat(RideBooking booking, Ride ride) async {
    try {
      final thread = await _chatSvc.ensureThread(
        rideId: ride.id,
        bookingId: booking.id,
      );
      if (!mounted) return;

      await Navigator.pushNamed(
        context,
        '/chat',
        arguments: {
          'threadId': thread.id,
          'counterpartName': booking.passengerName ?? 'Passenger',
          'rideTitle': _rideChatTitle(ride),
        },
      );
      if (!mounted) return;
      await _chatSync.refreshUnreadCount(force: true);
      await _refreshRideThreadUnreadBadges(ride: ride);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Unable to open passenger chat: $e')),
      );
    }
  }

  Future<void> _openDriverChat(Ride ride) async {
    final myBooking = _findCurrentUserBooking(ride);
    if (myBooking == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Book this ride first to chat with the driver.'),
        ),
      );
      return;
    }

    try {
      final thread = await _chatSvc.ensureThread(
        rideId: ride.id,
        bookingId: myBooking.id,
      );
      if (!mounted) return;

      await Navigator.pushNamed(
        context,
        '/chat',
        arguments: {
          'threadId': thread.id,
          'counterpartName': ride.driverSummary?.name ?? 'Driver',
          'rideTitle': _rideChatTitle(ride),
        },
      );
      if (!mounted) return;
      await _chatSync.refreshUnreadCount(force: true);
      await _refreshRideThreadUnreadBadges(ride: ride);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Unable to open driver chat: $e')),
      );
    }
  }

  RideRouteAlternative? _selectedRouteAlternative(Ride ride) {
    final options = ride.routeAlternatives;
    if (options == null || options.isEmpty) return null;

    final preferred =
        (_selectedDriverRouteKey ?? ride.routeSelectedKey ?? '').trim();
    if (preferred.isNotEmpty) {
      for (final option in options) {
        if (option.key == preferred) return option;
      }
    }

    for (final option in options) {
      if (option.isOptimal) return option;
    }
    return options.first;
  }

  static const List<Color> _passengerStopPalette = <Color>[
    Color(0xFFFACC15),
    Color(0xFF8B5CF6),
    Color(0xFFF59E0B),
    Color(0xFFEC4899),
    Color(0xFF14B8A6),
    Color(0xFFEF4444),
    Color(0xFF6366F1),
  ];
  static const Color _fallbackPassengerStopColor = AppColors.info;

  int _stableColorHash(String value) {
    var hash = 2166136261;
    for (final code in value.codeUnits) {
      hash ^= code;
      hash = (hash * 16777619) & 0x7fffffff;
    }
    return hash;
  }

  int _bookingOrderHint(RideBooking booking) {
    final candidates = <int>[];
    final pickupOrder = booking.pickupStopOrder;
    final dropoffOrder = booking.dropoffStopOrder;
    if (pickupOrder != null && pickupOrder > 0) {
      candidates.add(pickupOrder);
    }
    if (dropoffOrder != null && dropoffOrder > 0) {
      candidates.add(dropoffOrder);
    }
    if (candidates.isEmpty) {
      return 1000000 + (_stableColorHash(booking.id) % 5000);
    }
    return candidates.reduce(math.min);
  }

  Map<String, Color> _buildPassengerStopColorMap(
    Ride ride,
    RideRouteAlternative? selectedRoute,
  ) {
    final bookingIds = <String>[];

    if (selectedRoute != null && selectedRoute.stopSequence.isNotEmpty) {
      final orderedStops = [...selectedRoute.stopSequence]
        ..sort((a, b) => a.order.compareTo(b.order));
      for (final stop in orderedStops) {
        final id = stop.bookingId.trim();
        if (id.isNotEmpty && !bookingIds.contains(id)) {
          bookingIds.add(id);
        }
      }
    }

    final bookings = [...(ride.bookings ?? const <RideBooking>[])];
    bookings.sort((a, b) {
      final orderCmp = _bookingOrderHint(a).compareTo(_bookingOrderHint(b));
      if (orderCmp != 0) return orderCmp;
      return a.id.compareTo(b.id);
    });
    for (final booking in bookings) {
      if (booking.id.isNotEmpty && !bookingIds.contains(booking.id)) {
        bookingIds.add(booking.id);
      }
    }

    final colorMap = <String, Color>{};
    for (var i = 0; i < bookingIds.length; i++) {
      colorMap[bookingIds[i]] =
          _passengerStopPalette[i % _passengerStopPalette.length];
    }
    return colorMap;
  }

  List<RouteMapStopColorData> _buildRouteColorStops(
    Ride ride,
    RideRouteAlternative? selectedRoute,
    Map<String, Color> passengerStopColors,
  ) {
    final stops = <RouteMapStopColorData>[];

    if (selectedRoute != null && selectedRoute.stopSequence.isNotEmpty) {
      final orderedStops = [...selectedRoute.stopSequence]
        ..sort((a, b) => a.order.compareTo(b.order));
      for (final stop in orderedStops) {
        final lat = stop.lat;
        final lng = stop.lng;
        if (lat == null || lng == null || stop.order <= 0) continue;

        final bookingId = stop.bookingId.trim();
        final stopColor =
            passengerStopColors[bookingId] ?? _fallbackPassengerStopColor;
        stops.add(
          RouteMapStopColorData(
            order: stop.order,
            position: LatLng(lat, lng),
            color: stopColor,
            bookingId: bookingId,
            eventType: stop.eventType,
          ),
        );
      }
      return stops;
    }

    for (final booking in ride.bookings ?? const <RideBooking>[]) {
      final stopColor =
          passengerStopColors[booking.id] ?? _fallbackPassengerStopColor;
      final pickupOrder = booking.pickupStopOrder;
      if (booking.pickupLat != null &&
          booking.pickupLng != null &&
          pickupOrder != null &&
          pickupOrder > 0) {
        stops.add(
          RouteMapStopColorData(
            order: pickupOrder,
            position: LatLng(booking.pickupLat!, booking.pickupLng!),
            color: stopColor,
            bookingId: booking.id,
            eventType: 'pickup',
          ),
        );
      }

      final dropoffOrder = booking.dropoffStopOrder;
      if (booking.dropoffLat != null &&
          booking.dropoffLng != null &&
          dropoffOrder != null &&
          dropoffOrder > 0) {
        stops.add(
          RouteMapStopColorData(
            order: dropoffOrder,
            position: LatLng(booking.dropoffLat!, booking.dropoffLng!),
            color: stopColor,
            bookingId: booking.id,
            eventType: 'dropoff',
          ),
        );
      }
    }

    stops.sort((a, b) => a.order.compareTo(b.order));
    return stops;
  }

  List<RouteMapMarkerData> _buildRouteStopMarkers(
    Ride ride,
    RideRouteAlternative? selectedRoute,
    Map<String, Color> passengerStopColors,
  ) {
    final markers = <RouteMapMarkerData>[];

    if (selectedRoute != null && selectedRoute.stopSequence.isNotEmpty) {
      final orderedStops = [...selectedRoute.stopSequence]
        ..sort((a, b) => a.order.compareTo(b.order));
      for (final stop in orderedStops) {
        final lat = stop.lat;
        final lng = stop.lng;
        if (lat == null || lng == null) continue;
        final isPickup = stop.eventType == 'pickup';
        final bookingId = stop.bookingId.trim();
        final stopColor =
            passengerStopColors[bookingId] ?? _fallbackPassengerStopColor;
        markers.add(
          RouteMapMarkerData(
            id: 'route_stop_${stop.order}_${stop.eventType}_${stop.bookingId}',
            position: LatLng(lat, lng),
            title: 'Stop ${stop.order} • ${isPickup ? 'Pickup' : 'Dropoff'}',
            snippet: stop.address,
            hue: isPickup
                ? BitmapDescriptor.hueAzure
                : BitmapDescriptor.hueOrange,
            markerColor: stopColor,
            stopNumber: stop.order > 0 ? stop.order : null,
            bookingId: bookingId,
            eventType: stop.eventType,
            isPassengerStop: true,
          ),
        );
      }
      return _offsetOverlappingStopMarkers(markers);
    }

    for (final booking in ride.bookings ?? const <RideBooking>[]) {
      final stopColor =
          passengerStopColors[booking.id] ?? _fallbackPassengerStopColor;
      if (booking.pickupLat != null && booking.pickupLng != null) {
        final pickupOrder = booking.pickupStopOrder;
        markers.add(
          RouteMapMarkerData(
            id: 'pickup_${booking.id}',
            position: LatLng(booking.pickupLat!, booking.pickupLng!),
            title:
                pickupOrder != null ? 'Stop $pickupOrder • Pickup' : 'Pickup',
            snippet: booking.pickupAddress,
            hue: BitmapDescriptor.hueAzure,
            markerColor: stopColor,
            stopNumber: pickupOrder,
            bookingId: booking.id,
            eventType: 'pickup',
            isPassengerStop: pickupOrder != null,
          ),
        );
      }
      if (booking.dropoffLat != null && booking.dropoffLng != null) {
        final dropOrder = booking.dropoffStopOrder;
        markers.add(
          RouteMapMarkerData(
            id: 'dropoff_${booking.id}',
            position: LatLng(booking.dropoffLat!, booking.dropoffLng!),
            title: dropOrder != null ? 'Stop $dropOrder • Dropoff' : 'Dropoff',
            snippet: booking.dropoffAddress,
            hue: BitmapDescriptor.hueOrange,
            markerColor: stopColor,
            stopNumber: dropOrder,
            bookingId: booking.id,
            eventType: 'dropoff',
            isPassengerStop: dropOrder != null,
          ),
        );
      }
    }
    return _offsetOverlappingStopMarkers(markers);
  }

  List<RouteMapMarkerData> _offsetOverlappingStopMarkers(
    List<RouteMapMarkerData> markers,
  ) {
    if (markers.length < 2) {
      return markers;
    }

    final groups = <String, List<int>>{};
    for (var i = 0; i < markers.length; i++) {
      final marker = markers[i];
      final key =
          '${marker.position.latitude.toStringAsFixed(6)}:${marker.position.longitude.toStringAsFixed(6)}';
      groups.putIfAbsent(key, () => <int>[]).add(i);
    }

    final adjusted = [...markers];
    for (final indexes in groups.values) {
      if (indexes.length <= 1) continue;

      for (var offsetIndex = 0; offsetIndex < indexes.length; offsetIndex++) {
        final source = markers[indexes[offsetIndex]];
        final ring = offsetIndex ~/ 8;
        final radius = 0.00004 + (ring * 0.00003);
        final angle = (2 * math.pi * offsetIndex) / indexes.length;
        final latOffset = math.cos(angle) * radius;
        final lngOffset = math.sin(angle) * radius;

        adjusted[indexes[offsetIndex]] = RouteMapMarkerData(
          id: source.id,
          position: LatLng(
            source.position.latitude + latOffset,
            source.position.longitude + lngOffset,
          ),
          title: source.title,
          snippet: source.snippet,
          hue: source.hue,
          markerColor: source.markerColor,
          stopNumber: source.stopNumber,
          bookingId: source.bookingId,
          eventType: source.eventType,
          isPassengerStop: source.isPassengerStop,
        );
      }
    }

    return adjusted;
  }

  Future<void> _updateDriverRouteSelection(Ride ride, String routeKey) async {
    final normalized = routeKey.trim();
    if (normalized.isEmpty || _updatingRouteSelection) return;

    final current =
        (_selectedDriverRouteKey ?? ride.routeSelectedKey ?? '').trim();
    if (current == normalized) return;

    setState(() {
      _updatingRouteSelection = true;
      _selectedDriverRouteKey = normalized;
    });

    try {
      final updated = await _rideSvc.updateRideRouteSelection(
        rideId: ride.id,
        routeKey: normalized,
      );
      if (!mounted) return;

      setState(() {
        _ride = updated;
        _selectedDriverRouteKey = updated.routeSelectedKey ?? normalized;
      });

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Route option updated.'),
          backgroundColor: AppColors.success,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Failed to update route: $e'),
          backgroundColor: AppColors.error,
        ),
      );
      setState(() {
        _selectedDriverRouteKey = ride.routeSelectedKey;
      });
    } finally {
      if (mounted) {
        setState(() {
          _updatingRouteSelection = false;
        });
      }
    }
  }

  bool _hasStopRouteData(RideBooking booking) {
    return booking.pickupPct != null ||
        booking.dropoffPct != null ||
        booking.segmentKm != null ||
        booking.pickupRouteKm != null ||
        booking.dropoffRouteKm != null ||
        booking.estimatedPickupTime != null ||
        booking.pickupStopOrder != null ||
        booking.dropoffStopOrder != null ||
        booking.plannedPickupEta != null ||
        booking.plannedDropoffEta != null ||
        (booking.pickupAddress ?? '').trim().isNotEmpty ||
        (booking.dropoffAddress ?? '').trim().isNotEmpty;
  }

  Widget _stopDetailChip(
    ThemeData theme, {
    required IconData icon,
    required String label,
    Color? accentColor,
  }) {
    final chipColor = accentColor ?? AppColors.primary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: chipColor.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: chipColor.withValues(alpha: 0.30)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: chipColor),
          const SizedBox(width: 6),
          Text(
            label,
            style: theme.textTheme.bodySmall?.copyWith(
              color: chipColor,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  String _formatPctAlongRoute(double? pct) {
    if (pct == null) return '--';
    final normalized = pct.clamp(0.0, 1.0) * 100.0;
    return '${normalized.toStringAsFixed(0)}%';
  }

  String _formatKmLabel(double? km) {
    if (km == null) return '-- km';
    return '${km.toStringAsFixed(1)} km';
  }

  String _formatShortTime(DateTime dt) {
    final local = dt.isUtc ? dt.toLocal() : dt;
    final hour = local.hour > 12 ? local.hour - 12 : local.hour;
    final amPm = local.hour >= 12 ? 'PM' : 'AM';
    final minute = local.minute.toString().padLeft(2, '0');
    return '${hour == 0 ? 12 : hour}:$minute $amPm';
  }

  Color _bookingColor(String status) {
    switch (status.toLowerCase()) {
      case 'booked':
      case 'reserved':
      case 'confirmed':
        return AppColors.info;
      case 'completed':
        return AppColors.success;
      case 'cancelled':
        return AppColors.error;
      default:
        return AppColors.textSecondary;
    }
  }

  String _paymentStatusLabel(String rawStatus) {
    final status = rawStatus.trim().toLowerCase();
    switch (status) {
      case 'pending':
        return 'Payment Pending';
      case 'paid':
        return 'Payment Paid';
      case 'refunded':
        return 'Payment Refunded';
      default:
        if (status.isEmpty) return 'Payment Pending';
        final normalized = status.replaceAll('_', ' ');
        final words = normalized
            .split(' ')
            .where((word) => word.isNotEmpty)
            .map((word) =>
                '${word[0].toUpperCase()}${word.substring(1).toLowerCase()}')
            .join(' ');
        return 'Payment $words';
    }
  }

  int _effectiveBookedSeats(Ride ride) {
    final direct = ride.bookedSeatsCount;
    final fromBookings = ride.bookings
        ?.where((booking) => booking.isActive)
        .fold<int>(0, (sum, booking) => sum + booking.bookedSeats);
    final fromTotalSeats = ride.totalSeats != null
        ? math.max(0, ride.totalSeats! - ride.availableSeats)
        : null;

    var best = 0;
    for (final candidate in [direct, fromBookings, fromTotalSeats]) {
      if (candidate != null && candidate > best) {
        best = candidate;
      }
    }
    return best;
  }

  String _driverRoleChipLabel(Ride ride) {
    switch (ride.status) {
      case 'in_progress':
        return 'Ride in progress';
      case 'completed':
        return 'Driver (completed)';
      case 'cancelled':
        return 'Driver (cancelled)';
      default:
        return 'Driver';
    }
  }

  String _formatDateTime(DateTime dt) {
    final months = [
      'Jan',
      'Feb',
      'Mar',
      'Apr',
      'May',
      'Jun',
      'Jul',
      'Aug',
      'Sep',
      'Oct',
      'Nov',
      'Dec'
    ];
    final hour = dt.hour > 12 ? dt.hour - 12 : dt.hour;
    final amPm = dt.hour >= 12 ? 'PM' : 'AM';
    return '${months[dt.month - 1]} ${dt.day}, ${dt.year} at ${hour == 0 ? 12 : hour}:${dt.minute.toString().padLeft(2, '0')} $amPm';
  }
}
