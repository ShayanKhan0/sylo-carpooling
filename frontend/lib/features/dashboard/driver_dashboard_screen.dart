import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/gestures.dart';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:geolocator/geolocator.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme/app_colors.dart';
import '../../core/constants/app_constants.dart';
import '../../core/services/auth_service.dart';
import '../../core/services/firebase_auth_service.dart';
import '../../core/services/driver_service.dart';
import '../../core/services/ride_service.dart';
import '../../core/services/wallet_service.dart';
import '../../core/services/earnings_service.dart';
import '../../core/services/chat_sync_service.dart';
import '../../core/services/notification_service.dart';
import '../../core/services/notification_sync_service.dart';
import '../../core/services/user_service.dart';
import '../../core/services/api_client.dart';
import '../../core/services/schedule_service.dart';
import '../../core/services/maps_service.dart';
import '../../core/services/telemetry_service.dart';
import '../../core/services/trip_service.dart';
import '../../core/services/verification_service.dart';
import '../../core/services/rating_service.dart';
import '../../core/models/user_model.dart';
import '../../core/models/ride_model.dart';
import '../../core/models/vehicle_model.dart';
import '../../core/models/wallet_model.dart';
import '../../core/models/earnings_model.dart';
import '../auth/auth_design_tokens.dart';
import '../shared/widgets.dart';
import '../maps/location_picker_screen.dart';
import '../maps/route_map_widget.dart';
import '../maps/place_search_field.dart';
import '../maps/dual_location_picker_screen.dart';
import 'home_design_system.dart';
import '../../core/utils/fare_calculator.dart';
import '../matching/ride_stop_sequence_widget.dart';
import '../../core/services/dynamic_pricing_service.dart';
import '../../core/utils/carbon_footprint.dart';
import '../schedule/recurring_schedule_screen.dart';

class DriverDashboardScreen extends StatefulWidget {
  const DriverDashboardScreen({super.key});

  @override
  State<DriverDashboardScreen> createState() => _DriverDashboardScreenState();
}

class _DriverDashboardScreenState extends State<DriverDashboardScreen>
    with SingleTickerProviderStateMixin {
  static const double _driverCo2FallbackSpeedKmh = 40.0;

  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;

  int _selectedNavIndex = 0;

  // Data
  User? _user;
  DriverProfile? _driverProfile;
  DriverStats? _driverStats;
  RideStatistics? _driverRideStats;
  List<Ride> _rides = [];
  List<Ride> _homeScheduledRides = [];
  List<Map<String, dynamic>> _homeRecurringSchedules = [];
  List<Ride> _homeHistoryRides = [];
  List<Vehicle> _vehicles = [];
  LifetimeEarnings? _lifetimeEarnings;
  MonthlyEarnings? _monthlyEarnings;
  EarningsChart? _monthlyChart;
  WalletBalance? _walletBalance;
  int _unreadNotifications = 0;
  int _historyChatBadgeCount = 0;
  bool _notificationsEnabled = true;
  bool _locationSharing = true;
  double? _homeAvgRating;
  PickedLocation? _scheduleOrigin;
  PickedLocation? _scheduleDestination;
  bool _isScheduleDetailsStep = false;
  Widget? _scheduleDetailsView;
  PickedLocation? _recurringOrigin;
  PickedLocation? _recurringDestination;
  bool _isRecurringDetailsStep = false;
  Widget? _recurringDetailsView;

  // States
  bool _isLoadingHome = true;
  bool _isLoadingRides = true;
  bool _isLoadingEarnings = true;
  String? _homeError;
  String? _ridesError;
  String? _earningsError;
  bool _isKycVerified = false;
  bool _isKycStatusLoaded = false;
  bool _isOnline = false;
  String? _ridesFilter;

  // Active driver telemetry publish state.
  StreamSubscription<Position>? _driverTelemetryPositionSub;
  Timer? _driverTelemetryHeartbeatTimer;
  Timer? _homeAutoRefreshTimer;
  String? _activeTelemetryRideId;
  DateTime _lastTelemetrySentAt = DateTime.fromMillisecondsSinceEpoch(0);
  bool _homeAutoRefreshInFlight = false;
  bool _telemetryPermissionHintShown = false;
  String? _lastTelemetryDiagnosticsShown;

  // Services
  final _userService = UserService();
  final _driverService = DriverService();
  final _rideService = RideService();
  final _walletService = WalletService();
  final _earningsService = EarningsService();
  final _chatSync = ChatSyncService();
  final _notificationService = NotificationService();
  final _notificationSync = NotificationSyncService();
  final _verificationService = VerificationService();
  final _ratingService = RatingService();
  final _telemetryService = TelemetryService();
  final _scheduleService = ScheduleService();

  bool get _isDriverVerifiedForRide {
    if (_isKycStatusLoaded) {
      return _isKycVerified;
    }
    return _driverProfile?.isVerified == true;
  }

  Future<void> _refreshVerificationGateState() async {
    final userId = await AuthService().getUserId();

    DriverProfile? latestDriverProfile;
    User? latestUser;
    try {
      latestDriverProfile = await _driverService.getMyProfile();
    } catch (_) {}

    bool latestKycVerified = _isKycVerified;
    bool latestKycLoaded = _isKycStatusLoaded;
    if (userId != null) {
      try {
        final status = await _verificationService.getStatus(userId);
        latestKycVerified = status['overall_verified'] == true;
        latestKycLoaded = true;
        latestUser = await _userService.getMyProfile();
      } catch (_) {}
    }

    if (!mounted) return;
    setState(() {
      if (latestUser != null) {
        _user = latestUser;
      }
      if (latestDriverProfile != null) {
        _driverProfile = latestDriverProfile;
      }
      _isKycVerified = latestKycVerified;
      _isKycStatusLoaded = latestKycLoaded;
    });
  }

  static const Set<PointerDeviceKind> _refreshDragDevices = {
    PointerDeviceKind.touch,
    PointerDeviceKind.mouse,
    PointerDeviceKind.stylus,
    PointerDeviceKind.unknown,
  };

  @override
  void initState() {
    super.initState();
    _initAnimations();
    _telemetryService.diagnosticsNotifier
        .addListener(_handleTelemetryDiagnosticsChanged);
    _chatSync.historyNewCountNotifier
        .addListener(_handleChatHistoryBadgeChanged);
    _chatSync.startPolling(interval: const Duration(seconds: 2));
    _notificationSync.unreadCountNotifier
        .addListener(_handleUnreadCountChanged);
    _notificationSync.startPolling(interval: const Duration(seconds: 2));
    _startHomeAutoRefresh();
    _loadDashboardData();
  }

  void _startHomeAutoRefresh() {
    _homeAutoRefreshTimer?.cancel();
    _homeAutoRefreshTimer =
        Timer.periodic(const Duration(seconds: 5), (_) {
      unawaited(_autoRefreshHomeCards());
    });
  }

  Future<void> _autoRefreshHomeCards() async {
    if (!mounted || _selectedNavIndex != 0 || _homeAutoRefreshInFlight) {
      return;
    }
    _homeAutoRefreshInFlight = true;
    try {
      await Future.wait<void>([
        _loadDashboardData(loadRelatedTabs: false, showLoader: false),
        _loadHomeRideSections(),
        _loadHomeRecurringSchedules(),
      ]);
    } catch (_) {
      // Keep silent on periodic sync failures.
    } finally {
      _homeAutoRefreshInFlight = false;
    }
  }

  void _handleChatHistoryBadgeChanged() {
    if (!mounted) return;
    final historyNew = _chatSync.historyNewCount;
    if (_historyChatBadgeCount == historyNew) return;
    setState(() {
      _historyChatBadgeCount = historyNew;
    });
  }

  void _handleUnreadCountChanged() {
    if (!mounted) return;
    final unread = _notificationSync.unreadCount;
    if (_unreadNotifications == unread) return;
    setState(() {
      _unreadNotifications = unread;
    });
  }

  void _handleTelemetryDiagnosticsChanged() {
    if (!mounted) return;
    final message = _telemetryService.diagnosticsNotifier.value?.trim();
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

  Future<void> _openNotificationsAndRefresh() async {
    await Navigator.pushNamed(context, '/notifications');
    if (!mounted) return;
    await _notificationSync.refreshUnreadCount(force: true);
  }

  Future<void> _openChatHistoryAndRefresh() async {
    await Navigator.pushNamed(context, '/chat-history');
    if (!mounted) return;
    await _chatSync.refreshHistoryBadgeCount(force: true);
  }

  void _initAnimations() {
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _animationController, curve: Curves.easeIn),
    );
    _animationController.forward();
  }

  Future<void> _loadDashboardData({
    bool loadRelatedTabs = true,
    bool showLoader = true,
  }) async {
    if (showLoader) {
      setState(() {
        _isLoadingHome = true;
        _homeError = null;
      });
    } else {
      if (mounted) {
        setState(() => _homeError = null);
      }
    }

    try {
      final userId = await AuthService().getUserId();

      // Load user profile
      User? user;
      try {
        user = await _userService.getMyProfile();
      } catch (_) {}

      // Load driver profile
      DriverProfile? driverProfile;
      try {
        driverProfile = await _driverService.getMyProfile();
      } catch (_) {}

      // Load driver stats
      DriverStats? driverStats;
      try {
        driverStats = await _driverService.getStats();
      } catch (_) {}

      double? homeAvgRating;
      final ratingUserId = userId ?? user?.id;
      if (ratingUserId != null && ratingUserId.isNotEmpty) {
        try {
          final ratingStats = await _ratingService.getStats(ratingUserId);
          homeAvgRating = ratingStats.weightedAverage;
        } catch (_) {}
      }

      // Load ride lifecycle stats for Home semantic counters.
      RideStatistics? driverRideStats;
      try {
        driverRideStats = await _rideService.getDriverStats();
      } catch (_) {}

      bool isKycVerified = false;
      bool isKycStatusLoaded = false;
      if (userId != null) {
        try {
          final status = await _verificationService.getStatus(userId);
          isKycVerified = status['overall_verified'] == true;
          isKycStatusLoaded = true;

          // Verification status call may sync driver selfie as profile photo.
          user = await _userService.getMyProfile();
        } catch (_) {}
      }

      // Load vehicles
      List<Vehicle> vehicles = [];
      try {
        vehicles = await _driverService.getVehicles();
      } catch (_) {}

      // Load wallet balance
      WalletBalance? walletBal;
      if (userId != null) {
        try {
          walletBal = await _walletService.getBalance(userId);
        } catch (_) {}
      }

      // Load unread notifications count
      int unread = _notificationSync.unreadCount;
      try {
        unread = await _notificationService.getUnreadCount();
        _notificationSync.setUnreadCount(unread);
      } catch (_) {}
      try {
        await _chatSync.refreshHistoryBadgeCount(force: true);
      } catch (_) {}

      if (mounted) {
        setState(() {
          _user = user;
          _driverProfile = driverProfile;
          _driverStats = driverStats;
          _driverRideStats = driverRideStats;
          _vehicles = vehicles;
          _walletBalance = walletBal;
          _unreadNotifications = unread;
          _historyChatBadgeCount = _chatSync.historyNewCount;
          _notificationsEnabled =
              user?.profile?.pushNotificationsEnabled ?? true;
          _locationSharing = user?.profile?.shareLocationEnabled ?? true;
          _homeAvgRating = homeAvgRating;
          _isKycVerified = isKycVerified;
          _isKycStatusLoaded = isKycStatusLoaded;
          _isOnline = driverProfile?.status == 'active';
          if (showLoader) _isLoadingHome = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _homeError = e is DioException ? extractError(e) : e.toString();
          if (showLoader) _isLoadingHome = false;
        });
      }
    }

    if (loadRelatedTabs) {
      // Load related sections in parallel for initial dashboard boot.
      await _refreshSupplementaryDashboardData(showEarningsLoader: true);
    }
  }

  int get _driverHomeTotalRides =>
      _driverRideStats?.totalRidesAllExcludingDraft ??
      _driverStats?.totalRides ??
      0;

  int get _driverHomeScheduledRides =>
      _homeScheduledRides.length + _homeRecurringSchedules.length;

  int get _driverHomeCompletedRides =>
      _driverRideStats?.totalRidesCompleted ?? 0;

  double get _driverHomeCarbonSavedKg =>
      _driverRideStats?.carbonFootprintSavedKg ?? 0;

  double get _driverHomeTotalEarned =>
      _lifetimeEarnings?.lifetimeGross ?? _driverStats?.totalEarnings ?? 0;

  String _formatWholeNumberWithCommas(num value) {
    final raw = value.round().toString();
    return raw.replaceAllMapped(
      RegExp(r'\B(?=(\d{3})+(?!\d))'),
      (match) => ',',
    );
  }

  BoxDecoration _driverHomeGlass({
    double radius = 22,
    bool elevated = true,
    double borderAlpha = 0.62,
    double borderWidth = 1.35,
  }) {
    return BoxDecoration(
      borderRadius: BorderRadius.circular(radius),
      color: const Color(0xA2123E2A),
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          Color(0xD255E0A0),
          Color(0xB53ABF7C),
          Color(0xA13A7051),
        ],
        stops: [0.0, 0.5, 1.0],
      ),
      border: Border.all(
        color: const Color(0xFFD7FFE8).withValues(alpha: borderAlpha),
        width: borderWidth,
      ),
      boxShadow: [
        if (elevated)
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.24),
            blurRadius: 32,
            offset: const Offset(0, 12),
          ),
        BoxShadow(
          color: const Color(0xFF1ED760).withValues(alpha: 0.34),
          blurRadius: 46,
          spreadRadius: -8,
          offset: const Offset(-8, -6),
        ),
      ],
    );
  }

  static const Color _homeTextPrimary = Color(0xFF121915);
  static const Color _homeTextSecondary = Color(0xFF25352D);
  static const Color _createRideBlue = Color(0xFF18408E);
  static const Color _homeGraphLineGreen = Color(0xFF1D6F38);
  static const Color _homeRideIconBlue = Color(0xFF1F4E93);
  static const Color _homeCompletedRideIcon = Color(0xFF1F673A);

  Color _profileSymbolShade(Color base) {
    return Color.alphaBlend(Colors.black.withValues(alpha: 0.34), base);
  }

  Future<void> _loadRides() async {
    setState(() {
      _isLoadingRides = true;
      _ridesError = null;
    });
    try {
      final rides =
          await _rideService.getMyDriverRides(statusFilter: _ridesFilter);
      if (mounted) {
        setState(() {
          _rides = rides;
          _isLoadingRides = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _ridesError = e is DioException ? extractError(e) : e.toString();
          _isLoadingRides = false;
        });
      }
    }
  }

  Future<void> _loadHomeRideSections() async {
    try {
      final activeFuture =
          _rideService.getMyDriverRides(statusFilter: 'active');
      final historyFuture =
          _rideService.getMyDriverRides(statusFilter: 'history');

      final active = await activeFuture;
      final history = await historyFuture;
      final scheduled = _prioritizeHomeScheduledRides(active);

      if (!mounted) return;
      setState(() {
        _homeScheduledRides = scheduled;
        _homeHistoryRides = history;
      });
      unawaited(_syncDriverTelemetryWithRides(candidates: scheduled));
    } catch (_) {
      // Keep existing home lists on transient failures to avoid blanking UI.
    }
  }

  Future<void> _loadHomeRecurringSchedules() async {
    try {
      final recurring = await _scheduleService.getDriverRecurringHome();
      if (!mounted) return;
      setState(() {
        _homeRecurringSchedules = recurring;
      });
    } catch (_) {
      // Keep existing recurring list on transient failures.
    }
  }

  List<Ride> _prioritizeHomeScheduledRides(List<Ride> rides) {
    final scheduled = rides.where((ride) {
      if (ride.isRecurringRide) return false;
      final status = ride.status.toLowerCase();
      return status == 'open' ||
          status == 'scheduled' ||
          status == 'in_progress' ||
          status == 'ongoing';
    }).toList();

    int statusPriority(String rawStatus) {
      final status = rawStatus.toLowerCase();
      if (status == 'in_progress' || status == 'ongoing') return 0;
      if (status == 'open' || status == 'scheduled') return 1;
      return 2;
    }

    scheduled.sort((a, b) {
      final priorityCompare =
          statusPriority(a.status).compareTo(statusPriority(b.status));
      if (priorityCompare != 0) return priorityCompare;

      final aTime = a.departureDatetime;
      final bTime = b.departureDatetime;
      if (aTime == null && bTime == null) return 0;
      if (aTime == null) return 1;
      if (bTime == null) return -1;
      return bTime.compareTo(aTime);
    });

    return scheduled;
  }

  double? _driverRideDistanceKm(Ride ride) {
    final routeKm = ride.routeDistanceKm;
    if (routeKm != null && routeKm > 0) {
      return routeKm;
    }

    if (ride.originLat != null &&
        ride.originLng != null &&
        ride.destinationLat != null &&
        ride.destinationLng != null) {
      final meters = Geolocator.distanceBetween(
        ride.originLat!,
        ride.originLng!,
        ride.destinationLat!,
        ride.destinationLng!,
      );
      if (meters > 0) {
        return meters / 1000;
      }
    }

    final durationMinutes = ride.estimatedDuration;
    if (durationMinutes != null && durationMinutes > 0) {
      return (durationMinutes / 60.0) * _driverCo2FallbackSpeedKmh;
    }

    return null;
  }

  double? _driverRideCarbonSavedKg(Ride ride) {
    if (ride.status != 'completed') {
      return null;
    }

    final distanceKm = _driverRideDistanceKm(ride);
    if (distanceKm == null || distanceKm <= 0) {
      return null;
    }

    return CarbonFootprint.avoidedKgForDistanceKm(distanceKm);
  }

  bool _isDriverProfileMissingError(String? message) {
    if (message == null) return false;
    final error = message.toLowerCase();
    return error.contains('/rides/my/driver') &&
        (error.contains('driver profile not found') ||
            error.contains('register as a driver'));
  }

  String _friendlyDriverRegisterError(Object error) {
    if (error is DioException) {
      final details = extractError(error).toLowerCase();
      if (details.contains('already exists')) {
        return 'Driver profile already exists for this account.';
      }
      if (details.contains('cnic')) {
        return 'Please check CNIC format and try again.';
      }
      if (details.contains('failed to create driver profile')) {
        return 'Unable to create your driver profile right now. Please try again.';
      }
    }
    return 'Unable to create your driver profile right now. Please try again.';
  }

  String _friendlyAddVehicleError(Object error) {
    if (error is DioException) {
      final details = extractError(error).toLowerCase();
      if (details.contains('already exists') || details.contains('plate')) {
        return 'A vehicle with this plate number already exists.';
      }
      if (details.contains('driver profile not found')) {
        return 'Please create your driver profile first.';
      }
      if (details.contains('failed to add vehicle')) {
        return 'Unable to add vehicle right now. Please try again.';
      }
    }
    return 'Unable to add vehicle right now. Please try again.';
  }

  Widget _driverBottomSheetFieldCaption(String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 2),
      child: Text(
        text,
        style: GoogleFonts.inter(
          color: Colors.white.withValues(alpha: 0.62),
          fontWeight: FontWeight.w700,
          fontSize: 12,
          letterSpacing: 0.85,
          height: 1.45,
        ),
      ),
    );
  }

  InputDecoration _driverBottomSheetInputDecoration({
    required IconData icon,
    String? hintText,
  }) {
    return InputDecoration(
      hintText: hintText,
      hintStyle: GoogleFonts.inter(
        color: Colors.white.withValues(alpha: 0.38),
        fontWeight: FontWeight.w500,
        fontSize: 16,
      ),
      prefixIcon: Icon(icon, color: const Color(0xFF43E892)),
      filled: true,
      fillColor: Colors.white.withValues(alpha: 0.08),
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 18),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.12)),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(color: Colors.white.withValues(alpha: 0.12)),
      ),
      focusedBorder: const OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(14)),
        borderSide: BorderSide(color: Color(0xFF43E892)),
      ),
    );
  }

  Widget _driverBottomSheetLabeledField({
    required String label,
    required TextEditingController controller,
    required IconData icon,
    String? hintText,
    TextInputType? keyboardType,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _driverBottomSheetFieldCaption(label),
        const SizedBox(height: 8),
        TextField(
          controller: controller,
          keyboardType: keyboardType ?? TextInputType.text,
          style: GoogleFonts.inter(
            color: Colors.white.withValues(alpha: 0.95),
            fontWeight: FontWeight.w600,
            fontSize: 16,
          ),
          decoration: _driverBottomSheetInputDecoration(
            icon: icon,
            hintText: hintText,
          ),
        ),
      ],
    );
  }

  String _friendlyUpdateVehicleError(Object error) {
    if (error is DioException) {
      final details = extractError(error).toLowerCase();
      if (details.contains('already exists') || details.contains('plate')) {
        return 'A vehicle with this plate number already exists.';
      }
      if (details.contains('available seats cannot exceed total seats')) {
        return 'Available seats cannot be greater than total seats.';
      }
      if (details.contains('failed to update vehicle')) {
        return 'Unable to update vehicle right now. Please try again.';
      }
    }
    return 'Unable to update vehicle right now. Please try again.';
  }

  String _friendlyDeleteVehicleError(Object error) {
    if (error is DioException) {
      final details = extractError(error).toLowerCase();
      if (details.contains('vehicle not found')) {
        return 'Vehicle was not found or already removed.';
      }
      if (details.contains('failed to delete vehicle')) {
        return 'Unable to delete vehicle right now. Please try again.';
      }
    }
    return 'Unable to delete vehicle right now. Please try again.';
  }

  Future<void> _loadEarnings({bool showLoader = true}) async {
    if (showLoader) {
      setState(() {
        _isLoadingEarnings = true;
        _earningsError = null;
      });
    } else {
      if (mounted) {
        setState(() => _earningsError = null);
      }
    }
    try {
      LifetimeEarnings? lifetime;
      MonthlyEarnings? monthly;
      EarningsChart? chart;
      try {
        lifetime = await _earningsService.getLifetime();
      } catch (_) {}
      try {
        // Use user's local clock for the current-month earnings bucket.
        final now = DateTime.now();
        monthly =
            await _earningsService.getMonthly(year: now.year, month: now.month);
      } catch (_) {}
      try {
        // 30 daily buckets gives the Monthly Summary chart enough resolution
        // to show a real day-to-day trend for the current month.
        chart = await _earningsService.getChart(days: 30);
      } catch (_) {}

      if (mounted) {
        setState(() {
          _lifetimeEarnings = lifetime;
          _monthlyEarnings = monthly;
          _monthlyChart = chart;
          if (showLoader) _isLoadingEarnings = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _earningsError = e is DioException ? extractError(e) : e.toString();
          if (showLoader) _isLoadingEarnings = false;
        });
      }
    }
  }

  Future<void> _refreshSupplementaryDashboardData({
    bool showEarningsLoader = false,
  }) async {
    await Future.wait([
      _loadRides(),
      _loadHomeRideSections(),
      _loadHomeRecurringSchedules(),
      _loadEarnings(showLoader: showEarningsLoader),
    ]);
  }

  Future<void> _refreshAllDashboardData({
    bool showHomeLoader = false,
    bool showEarningsLoader = false,
  }) async {
    await Future.wait([
      _loadDashboardData(loadRelatedTabs: false, showLoader: showHomeLoader),
      _refreshSupplementaryDashboardData(
          showEarningsLoader: showEarningsLoader),
    ]);
  }

  Future<void> _syncDriverTelemetryWithRides({
    List<Ride>? candidates,
  }) async {
    if (!_locationSharing) {
      _stopDriverTelemetryPublishing();
      return;
    }

    final rides = candidates ?? _homeScheduledRides;
    Ride? inProgressRide;
    for (final ride in rides) {
      final status = ride.status.toLowerCase();
      if (status == 'in_progress' || status == 'ongoing') {
        inProgressRide = ride;
        break;
      }
    }

    if (inProgressRide == null) {
      _stopDriverTelemetryPublishing();
      return;
    }

    await _startDriverTelemetryPublishing(inProgressRide.id);
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
    if (!hasPermission) {
      return;
    }

    await _telemetryService.connect(rideId);
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

    await _telemetryService.sendLocation(
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
      unawaited(_telemetryService.disconnect());
    }
  }

  Future<void> _refreshHomeAndEarnings() async {
    await _refreshAllDashboardData(
      showHomeLoader: false,
      showEarningsLoader: false,
    );
  }

  void _schedulePostSettlementEarningsSync() {
    // Payment settlement can complete a moment after ride completion.
    // Re-sync shortly after to keep Home/Earnings charts current.
    unawaited(Future<void>.delayed(const Duration(seconds: 2), () async {
      if (!mounted) return;
      await _loadEarnings(showLoader: false);
    }));
    unawaited(Future<void>.delayed(const Duration(seconds: 6), () async {
      if (!mounted) return;
      await _loadEarnings(showLoader: false);
    }));
  }

  Future<void> _openWalletAndRefresh() async {
    await Navigator.pushNamed(context, '/wallet');
    if (!mounted) return;
    await _refreshHomeAndEarnings();
  }

  Future<void> _openVerificationAndRefresh() async {
    await Navigator.pushNamed(context, '/verification');
    if (!mounted) return;
    await _refreshVerificationGateState();
  }

  Widget _desktopRefreshScrollable(Widget child) {
    return ScrollConfiguration(
      behavior: const MaterialScrollBehavior().copyWith(
        dragDevices: _refreshDragDevices,
      ),
      child: child,
    );
  }

  Widget _homeReveal({required double begin, required Widget child}) {
    final raw = (_animationController.value - begin) / (1 - begin);
    final t = raw.clamp(0.0, 1.0).toDouble();
    final eased = Curves.easeOutCubic.transform(t);
    return Opacity(
      opacity: eased,
      child: Transform.translate(
        offset: Offset(0, 20 * (1 - eased)),
        child: child,
      ),
    );
  }

  Future<void> _updatePushNotificationsPreference(bool enabled) async {
    final previous = _notificationsEnabled;
    setState(() => _notificationsEnabled = enabled);

    try {
      await _userService.updateProfile(pushNotificationsEnabled: enabled);
    } catch (_) {
      if (!mounted) return;
      setState(() => _notificationsEnabled = previous);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Could not update notification preference.'),
        ),
      );
    }
  }

  Future<void> _updateShareLocationPreference(bool enabled) async {
    final previous = _locationSharing;
    setState(() => _locationSharing = enabled);

    try {
      await _userService.updateProfile(shareLocationEnabled: enabled);
      if (!enabled) {
        _stopDriverTelemetryPublishing();
      } else {
        unawaited(_syncDriverTelemetryWithRides());
      }
    } catch (_) {
      if (!mounted) return;
      setState(() => _locationSharing = previous);
      if (previous) {
        unawaited(_syncDriverTelemetryWithRides());
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Could not update location sharing preference.'),
        ),
      );
    }
  }

  Future<void> _toggleOnlineStatus() async {
    // Ensure driver profile exists before attempting toggle
    if (_driverProfile == null) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
                'Driver profile not found. Please register as a driver first.'),
            backgroundColor: AppColors.error,
            behavior: SnackBarBehavior.floating,
            duration: Duration(seconds: 4),
          ),
        );
      }
      return;
    }

    final newStatus = _isOnline ? 'inactive' : 'active';
    final wasOnline = _isOnline;
    setState(() => _isOnline = !_isOnline);
    try {
      await _driverService.updateStatus(newStatus);
      // Update local state directly — no need to re-fetch
      if (mounted) {
        setState(() {
          _isOnline = newStatus == 'active';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => _isOnline = wasOnline); // revert on failure
        String errorMsg = e is DioException ? extractError(e) : e.toString();
        // Provide helpful message for common cases
        if (errorMsg.contains('not verified') || errorMsg.contains('pending')) {
          errorMsg =
              'Your driver account is not verified yet. Please complete verification first.';
        } else if (errorMsg.contains('not found') || errorMsg.contains('404')) {
          errorMsg =
              'Driver profile not found. Please register as a driver first.';
        }
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(errorMsg),
            backgroundColor: AppColors.error,
            behavior: SnackBarBehavior.floating,
            duration: const Duration(seconds: 4),
          ),
        );
      }
    }
  }

  Future<void> _handleLogout() async {
    try {
      await FirebaseAuthService().signOut();
      if (mounted) {
        Navigator.of(context).pushReplacementNamed('/signin');
      }
    } catch (_) {
      if (mounted) {
        Navigator.of(context).pushReplacementNamed('/signin');
      }
    }
  }

  Future<void> _deleteAccount() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Account'),
        content: const Text(
            'This will permanently delete your account and all associated data. This action cannot be undone.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Delete Account',
                  style: TextStyle(color: AppColors.error))),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    // TODO: Implement account deletion API call
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
          content: Text(
              'Account deletion requested. You will receive a confirmation email.')),
    );
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

  bool _isDepartureTimeFutureValidationError(DioException error) {
    if (error.response?.statusCode != 422) {
      return false;
    }

    final details = extractError(error).toLowerCase();
    return details.contains('departure time must be in the future') ||
        (details.contains('departure_time') && details.contains('future'));
  }

  Future<void> _showDepartureTimeFutureDialog({
    required String actionLabel,
  }) async {
    if (!mounted) return;

    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Invalid Departure Time'),
        content: Text(
          'To $actionLabel, the departure time should be after the current time. '
          'Please pick a future time and try again.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  Future<void> _showStartRideBlockedDialog() {
    return _showDriverActionBlockedDialog(
      title: 'Cannot Start Ride',
      message: 'You need at least one passenger to start a ride.',
    );
  }

  Future<void> _showCompleteRideBlockedDialog() {
    return _showDriverActionBlockedDialog(
      title: 'Cannot Complete Ride',
      message:
          'You need to complete all the pickups and drop offs to complete a ride.',
    );
  }

  Future<void> _startRide(Ride ride) async {
    if (!_canDriverStartRide(ride)) {
      await _showStartRideBlockedDialog();
      return;
    }

    try {
      // Update ride status AND start trip tracking
      await _rideService.updateRideStatus(ride.id, 'in_progress');
      try {
        await TripService().startTrip(ride.id);
      } catch (_) {
        // Trip service is optional — ride status is the primary action
      }
      await _startDriverTelemetryPublishing(ride.id);
      await _refreshAllDashboardData(
        showHomeLoader: false,
        showEarningsLoader: false,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Ride started! Drive safely.'),
            backgroundColor: AppColors.success,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content:
                  Text('Error: ${e is DioException ? extractError(e) : e}')),
        );
      }
    }
  }

  Future<void> _completeRide(Ride ride) async {
    if (!_canDriverCompleteRide(ride)) {
      await _showCompleteRideBlockedDialog();
      return;
    }

    // Confirm before completing
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Complete Ride'),
        content: const Text(
            'Mark this ride as completed? Payments will be settled automatically.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Not Yet')),
          ElevatedButton(
              onPressed: () => Navigator.pop(ctx, true),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.success,
                foregroundColor: Colors.white,
              ),
              child: const Text('Complete')),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      await _rideService.updateRideStatus(ride.id, 'completed');
      try {
        await TripService().completeTrip(ride.id, settlePayments: true);
      } catch (_) {
        // Trip service is optional
      }
      _stopDriverTelemetryPublishing();
      await _refreshAllDashboardData(
        showHomeLoader: false,
        showEarningsLoader: false,
      );
      _schedulePostSettlementEarningsSync();
      if (mounted) {
        // Show trip summary dialog
        _showTripSummary(ride);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content:
                  Text('Error: ${e is DioException ? extractError(e) : e}')),
        );
      }
    }
  }

  Future<void> _showTripSummary(Ride ride) async {
    try {
      final summary = await TripService().getTripSummary(ride.id);
      if (!mounted) return;
      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Trip Summary'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _summaryRow(Icons.route_rounded, 'Distance',
                  '${summary['distance_km']?.toStringAsFixed(1) ?? '—'} km'),
              _summaryRow(Icons.timer_rounded, 'Duration',
                  '${summary['duration_minutes']?.toStringAsFixed(0) ?? '—'} min'),
              _summaryRow(Icons.people_rounded, 'Passengers',
                  '${summary['passenger_count'] ?? '—'}'),
              _summaryRow(Icons.payments_rounded, 'Total Earned',
                  'PKR ${summary['total_earned']?.toStringAsFixed(0) ?? '—'}'),
            ],
          ),
          actions: [
            ElevatedButton(
              onPressed: () => Navigator.pop(ctx),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: Colors.white,
              ),
              child: const Text('Done'),
            ),
          ],
        ),
      );
    } catch (_) {
      // Summary unavailable — just show success
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Ride completed successfully!'),
            backgroundColor: AppColors.success,
          ),
        );
      }
    }
  }

  Widget _summaryRow(IconData icon, String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(icon, size: 20, color: AppColors.primary),
          const SizedBox(width: 10),
          Text(label, style: TextStyle(color: AppColors.textSecondary)),
          const Spacer(),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  Future<void> _cancelRide(Ride ride) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel Ride'),
        content: const Text('Are you sure you want to cancel this ride?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('No')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child:
                  const Text('Yes', style: TextStyle(color: AppColors.error))),
        ],
      ),
    );
    if (confirmed != true) return;

    try {
      await _rideService.updateRideStatus(ride.id, 'cancelled');
      if (_activeTelemetryRideId == ride.id) {
        _stopDriverTelemetryPublishing();
      }
      await _refreshAllDashboardData(
        showHomeLoader: false,
        showEarningsLoader: false,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Ride cancelled')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content:
                  Text('Error: ${e is DioException ? extractError(e) : e}')),
        );
      }
    }
  }

  @override
  void dispose() {
    _homeAutoRefreshTimer?.cancel();
    _stopDriverTelemetryPublishing(disconnect: false);
    _telemetryService.diagnosticsNotifier
        .removeListener(_handleTelemetryDiagnosticsChanged);
    _telemetryService.dispose();
    _chatSync.historyNewCountNotifier
        .removeListener(_handleChatHistoryBadgeChanged);
    _chatSync.stopPolling();
    _notificationSync.unreadCountNotifier
        .removeListener(_handleUnreadCountChanged);
    _notificationSync.stopPolling();
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.light,
      ),
    );

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: FadeTransition(
        opacity: _fadeAnimation,
        child: IndexedStack(
          index: _selectedNavIndex,
          children: [
            _buildHomeTab(),
            _buildScheduleRidesTab(),
            _buildRecurringRidesTab(),
            _buildMyRidesTab(),
            _buildEarningsTab(),
            _buildProfileTab(),
          ],
        ),
      ),
      bottomNavigationBar: _buildBottomNav(),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
      floatingActionButton:
          _selectedNavIndex == 3 ? _buildCreateRideFloatingButton() : null,
    );
  }

  Widget _buildCreateRideFloatingButton() {
    final width = MediaQuery.of(context).size.width;
    final buttonWidth = (width - 32).clamp(220.0, 330.0).toDouble();
    return Container(
      width: buttonWidth,
      height: 56,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF4BF0A1).withValues(alpha: 0.42),
            blurRadius: 20,
            spreadRadius: 1.2,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: FilledButton(
              onPressed: _openScheduleRidesTab,
        style: FilledButton.styleFrom(
          backgroundColor: const Color(0xFF43E892),
          foregroundColor: const Color(0xFF052E1E),
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(999),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 22,
              height: 22,
              decoration: BoxDecoration(
                color: const Color(0xFF052E1E),
                borderRadius: BorderRadius.circular(999),
              ),
              child: const Icon(Icons.add, size: 16, color: Color(0xFF43E892)),
            ),
            const SizedBox(width: 12),
            Text(
              'CREATE RIDE',
              style: GoogleFonts.inter(
                fontWeight: FontWeight.w800,
                fontSize: 16,
                letterSpacing: 1.4,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // ─────────────────────────────────────────────────────────
  //  Bottom Navigation
  // ─────────────────────────────────────────────────────────
  static const List<({IconData icon, IconData selectedIcon, String label})>
      _driverNavDestinations = [
    (
      icon: Icons.home_outlined,
      selectedIcon: Icons.home,
      label: 'Home',
    ),
    (
      icon: Icons.schedule_outlined,
      selectedIcon: Icons.schedule,
      label: 'Schedule Rides',
    ),
    (
      icon: Icons.repeat_outlined,
      selectedIcon: Icons.repeat,
      label: 'Recurring Rides',
    ),
    (
      icon: Icons.directions_car_outlined,
      selectedIcon: Icons.directions_car,
      label: 'My Rides',
    ),
    (
      icon: Icons.account_balance_wallet_outlined,
      selectedIcon: Icons.account_balance_wallet,
      label: 'Earnings',
    ),
    (
      icon: Icons.person_outline,
      selectedIcon: Icons.person,
      label: 'Profile',
    ),
  ];

  /// Two-line nav label: last word on second line, both centered under the icon.
  Widget _driverNavLabelWidget(String label, bool selected, Color color) {
    final style = GoogleFonts.inter(
                  fontSize: 11,
                  fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
      color: color,
      height: 1.05,
    );
    final lastSpace = label.lastIndexOf(' ');
    if (lastSpace <= 0) {
      return Text(
        label,
        maxLines: 2,
        textAlign: TextAlign.center,
        style: style,
      );
    }
    final line1 = label.substring(0, lastSpace);
    final line2 = label.substring(lastSpace + 1);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          line1,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          textAlign: TextAlign.center,
          style: style,
        ),
        Text(
          line2,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          textAlign: TextAlign.center,
          style: style,
        ),
      ],
    );
  }

  Widget _buildDriverNavTile(int index) {
    final spec = _driverNavDestinations[index];
    final selected = _selectedNavIndex == index;
    final labelColor = selected
        ? AuthDesignTokens.white
        : AuthDesignTokens.white.withValues(alpha: 0.76);
    final iconColor = selected
        ? AuthDesignTokens.white
        : _homeTextPrimary.withValues(alpha: 0.78);

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () {
          if (index == 2) {
                  _openRecurringRidesTab();
                  return;
                }
          setState(() => _selectedNavIndex = index);
        },
        splashColor: AuthDesignTokens.sky400.withValues(alpha: 0.18),
        highlightColor: AuthDesignTokens.sky400.withValues(alpha: 0.08),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                height: 32,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    if (selected)
                      Container(
                        width: 44,
                        height: 30,
                        decoration: BoxDecoration(
                          color:
                              AuthDesignTokens.sky400.withValues(alpha: 0.22),
                          borderRadius: BorderRadius.circular(16),
                        ),
                      ),
                    Icon(
                      selected ? spec.selectedIcon : spec.icon,
                      size: 22,
                      color: iconColor,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 4),
              SizedBox(
                width: double.infinity,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 2),
                  child:
                      _driverNavLabelWidget(spec.label, selected, labelColor),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildBottomNav() {
    return SafeArea(
      minimum: const EdgeInsets.fromLTRB(0, 0, 0, 12),
      child: HomeDesignSystem.frostLayer(
        blur: 8,
        child: Container(
          decoration: HomeDesignSystem.darkTopBarSurface(radius: 24),
          child: SizedBox(
            height: 82,
            child: Row(
              children: List.generate(
                _driverNavDestinations.length,
                (i) => Expanded(child: _buildDriverNavTile(i)),
              ),
            ),
          ),
        ),
      ),
    );
  }

  // ═════════════════════════════════════════════════════════
  //  TAB 1 — HOME
  // ═════════════════════════════════════════════════════════
  Widget _buildDriverHomeBackground() {
    return HomeDesignSystem.driverHomeSoftWhiteBackground();
  }

  Widget _buildDriverDashboardBackground() {
    return HomeDesignSystem.driverHomeSoftWhiteBackground();
  }

  Widget _buildHomeTab() {
    if (_isLoadingHome) return const SyloLoader(message: 'Loading dashboard…');
    if (_homeError != null) {
      return SyloError(message: _homeError!, onRetry: _loadDashboardData);
    }

    return Stack(
      children: [
        _buildDriverHomeBackground(),
        RefreshIndicator(
          onRefresh: _refreshHomeAndEarnings,
          color: AuthDesignTokens.brandAction,
          triggerMode: RefreshIndicatorTriggerMode.anywhere,
          child: _desktopRefreshScrollable(
            ListView(
              physics: const AlwaysScrollableScrollPhysics(
                parent: BouncingScrollPhysics(),
              ),
              padding: const EdgeInsets.only(bottom: 12),
              children: [
                _homeReveal(begin: 0.0, child: _buildHomeHeader()),
                if (_driverProfile == null ||
                    (_driverProfile != null &&
                        (!_isDriverVerifiedForRide || _vehicles.isEmpty))) ...[
                  const SizedBox(height: 20),
                  _homeReveal(
                    begin: 0.08,
                    child: HomeDesignSystem.contentWidth(
                      child: _buildDriverOnboardingCard(),
                    ),
                  ),
                ],
                const SizedBox(height: 20),
                _homeReveal(
                  begin: 0.16,
                  child: HomeDesignSystem.contentWidth(
                      child: _buildQuickActions()),
                ),
                const SizedBox(height: 20),
                _homeReveal(
                  begin: 0.24,
                  child: HomeDesignSystem.contentWidth(
                      child: _buildScheduledRides()),
                ),
                const SizedBox(height: 20),
                _homeReveal(
                  begin: 0.32,
                  child: HomeDesignSystem.contentWidth(
                    child: _buildRecurringHomeSchedules(),
                  ),
                ),
                const SizedBox(height: 20),
                _homeReveal(
                  begin: 0.4,
                  child: HomeDesignSystem.contentWidth(
                      child: _buildRidesHistory()),
                ),
                const SizedBox(height: 24),
              ],
            ),
          ),
        ),
      ],
    );
  }

  // ═════════════════════════════════════════════════════════
  //  TAB 2 — SCHEDULE RIDES
  // ═════════════════════════════════════════════════════════
  Widget _buildScheduleRidesTab() {
    if (_isScheduleDetailsStep && _scheduleDetailsView != null) {
      return _scheduleDetailsView!;
    }

    return DualLocationPickerScreen(
      initialOrigin: _scheduleOrigin,
      initialDestination: _scheduleDestination,
      showBackButton: false,
      onLocationsConfirmed: (result) {
        setState(() {
          _scheduleOrigin = result.origin;
          _scheduleDestination = result.destination;
        });
        _showCreateRideDialog(
          initialOrigin: result.origin,
          initialDestination: result.destination,
        );
      },
    );
  }

  Widget _buildRecurringRidesTab() {
    if (_isRecurringDetailsStep && _recurringDetailsView != null) {
      return _recurringDetailsView!;
    }

    return DualLocationPickerScreen(
      initialOrigin: _recurringOrigin,
      initialDestination: _recurringDestination,
      showBackButton: false,
      onLocationsConfirmed: (result) {
        setState(() {
          _recurringOrigin = result.origin;
          _recurringDestination = result.destination;
        });
        _showDriverRecurringDetails(
          RecurringScheduleScreen(
            initialOrigin: result.origin,
            initialDestination: result.destination,
            onBackToMap: _returnToDriverRecurringMap,
          ),
        );
      },
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

  Widget _buildProfileAvatar({
    required double radius,
    required double fontSize,
    required String fallbackInitials,
  }) {
    final provider = _profileImageProvider(_user?.profile?.profilePhoto);
    return Container(
      padding: const EdgeInsets.all(2),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: const Color(0xFF1ED760).withValues(alpha: 0.85),
          width: 1.8,
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF1ED760).withValues(alpha: 0.26),
            blurRadius: 12,
            spreadRadius: 1,
          ),
        ],
      ),
      child: CircleAvatar(
        radius: radius,
        backgroundColor: AuthDesignTokens.brandAction,
        backgroundImage: provider,
        child: provider == null
            ? Text(
                fallbackInitials,
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: fontSize,
                ),
              )
            : null,
      ),
    );
  }

  Future<void> _handleDriverProfilePhotoAction() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Change Driver Photo'),
        content: const Text(
          'Changing your driver photo requires selfie re-verification. '
          'You will become Unverified until you upload and verify a new selfie in Verification.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primary,
              foregroundColor: Colors.white,
            ),
            child: const Text('Continue'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    try {
      await _verificationService.startDriverSelfieReverification();

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Selfie re-verification started. Upload a new selfie in Verification.',
          ),
          backgroundColor: AppColors.accent,
        ),
      );

      await Navigator.pushNamed(context, '/verification');
      if (!mounted) return;

      await _loadDashboardData(loadRelatedTabs: false, showLoader: false);
      await _refreshVerificationGateState();
    } catch (e) {
      if (!mounted) return;
      final message = e is DioException
          ? extractError(e)
          : 'Unable to start selfie re-verification. Please try again.';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message), backgroundColor: AppColors.error),
      );
    }
  }

  Widget _buildHomeHeader() {
    final name = _user?.firstName ?? 'Driver';
    final rating = (_homeAvgRating ?? _driverStats?.rating ?? 0)
        .clamp(0, 5)
        .toStringAsFixed(1);

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
      child: HomeDesignSystem.contentWidth(
        child: Column(
          children: [
            HomeDesignSystem.frostLayer(
              blur: 10,
              child: Container(
                padding: EdgeInsets.fromLTRB(
                  14,
                  MediaQuery.of(context).padding.top + 6,
                  14,
                  10,
                ),
                decoration: _driverHomeGlass(
                  radius: 24,
                  elevated: false,
                  borderAlpha: 0.32,
                  borderWidth: 1.05,
                ),
                child: Row(
                  children: [
                    _buildProfileAvatar(
                      radius: 22,
                      fontSize: 16,
                      fallbackInitials: _user?.initials ?? 'D',
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Welcome,',
                            style: HomeDesignSystem.heroTitleOnDark().copyWith(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                              color: _homeTextSecondary.withValues(alpha: 0.95),
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            name,
                            style:
                                HomeDesignSystem.heroSubtitleOnDark().copyWith(
                              color: _homeTextPrimary,
                              fontSize: 30,
                              fontWeight: FontWeight.w800,
                              height: 1.0,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                    _buildHeaderIcon(
                      icon: Icons.chat_bubble_outline_rounded,
                      badgeCount: _historyChatBadgeCount,
                      onPressed: _openChatHistoryAndRefresh,
                    ),
                    const SizedBox(width: 8),
                    _buildHeaderIcon(
                      icon: Icons.notifications_outlined,
                      badgeCount: _unreadNotifications,
                      onPressed: _openNotificationsAndRefresh,
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: HomeDesignSystem.frostLayer(
                    blur: 10,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 12),
                      decoration: _driverHomeGlass(radius: 20),
                      child: Row(
                        children: [
                          Transform.scale(
                            scale: 1.15,
                            child: Switch.adaptive(
                              value: _isOnline,
                              onChanged: (_) => _toggleOnlineStatus(),
                              activeColor: Colors.white,
                              activeTrackColor: AppColors.success,
                              inactiveThumbColor: const Color(0xFF6B7280),
                              inactiveTrackColor: const Color(0xFFE5E7EB),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  _isOnline
                                      ? 'You are Online'
                                      : 'You are Offline',
                                  style: GoogleFonts.inter(
                                    color: _homeTextPrimary,
                                    fontSize: 16,
                                    fontWeight: FontWeight.w800,
                                  ),
                                ),
                                Row(
                                  children: [
                                    Container(
                                      width: 10,
                                      height: 10,
                                      decoration: BoxDecoration(
                                        color: _isOnline
                                            ? AppColors.success
                                            : _homeTextSecondary.withValues(
                                                alpha: 0.48),
                                        shape: BoxShape.circle,
                                      ),
                                    ),
                                    const SizedBox(width: 6),
                                    Text(
                                      _isOnline
                                          ? 'Ready for requests'
                                          : 'Not accepting requests',
                                      style: HomeDesignSystem.cardBody(
                                        color: _homeTextSecondary.withValues(
                                            alpha: 0.9),
                                        size: 12,
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                SizedBox(
                  width: 118,
                  child: GestureDetector(
                    onTap: () =>
                        Navigator.pushNamed(context, '/ratings-reviews'),
                    child: HomeDesignSystem.frostLayer(
                      blur: 10,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 12),
                        decoration: _driverHomeGlass(radius: 20),
                        child: Column(
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(Icons.star_rounded,
                                    color: const Color(0xFFFACC15),
                                    size: 18),
                                const SizedBox(width: 2),
                                Text(
                                  rating,
                                  style: GoogleFonts.inter(
                                    color: _homeTextPrimary,
                                    fontSize: 30,
                                    fontWeight: FontWeight.w800,
                                    height: 1.0,
                                  ),
                                ),
                              ],
                            ),
                            Text(
                              '$_driverHomeTotalRides rides',
                              style: HomeDesignSystem.cardBody(
                                color:
                                    _homeTextSecondary.withValues(alpha: 0.84),
                                size: 11,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _buildDriverEarningsHeroCard(),
            const SizedBox(height: 12),
            _buildDriverPerformanceCards(),
          ],
        ),
      ),
    );
  }

  Widget _buildDriverEarningsHeroCard() {
    // Same cumulative gross-earnings series used on the Earnings screen so
    // the Home chart always matches what the driver sees in full detail.
    final dailyPoints = _buildDailyEarningsSeries();
    final normalizedPoints = _normalizeSeries(dailyPoints);
    final hasChartPoints = dailyPoints.length >= 2;
    final axisLabels = _dailyAxisLabels(dailyPoints);

    return HomeDesignSystem.frostLayer(
      blur: 10,
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(24),
        child: InkWell(
          borderRadius: BorderRadius.circular(24),
          onTap: () {
            setState(() => _selectedNavIndex = 4);
          },
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
        decoration: _driverHomeGlass(radius: 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
              'Total Earnings',
              style: GoogleFonts.inter(
                color: _homeTextSecondary.withValues(alpha: 0.92),
                fontSize: 15,
                fontWeight: FontWeight.w500,
              ),
                      ),
                    ),
                    Icon(
                      Icons.chevron_right_rounded,
                      size: 22,
                      color: _homeTextSecondary.withValues(alpha: 0.85),
                    ),
                  ],
            ),
            const SizedBox(height: 2),
            SizedBox(
              width: double.infinity,
              child: FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.centerLeft,
                child: Text(
                  'PKR ${_formatWholeNumberWithCommas(_driverHomeTotalEarned)}',
                  style: GoogleFonts.inter(
                    color: _homeTextPrimary,
                    fontSize: 56,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0.2,
                    height: 1.0,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              height: 108,
                  child: hasChartPoints
                      ? CustomPaint(
                painter: _EarningsCurvePainter(
                            points: normalizedPoints,
                  strokeColor: _homeGraphLineGreen,
                            fillColor:
                                _homeGraphLineGreen.withValues(alpha: 0.22),
                ),
                child: const SizedBox.expand(),
                        )
                      : const SizedBox.expand(),
            ),
            const SizedBox(height: 6),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: axisLabels
                  .map(
                    (d) => Text(
                      d,
                      style: GoogleFonts.inter(
                        color: _homeTextSecondary.withValues(alpha: 0.78),
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  )
                  .toList(),
            ),
          ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildDriverMiniStatCard({
    required String title,
    required String value,
    required IconData icon,
    required Color color,
    VoidCallback? onTap,
  }) {
    final radius = BorderRadius.circular(20);
    final card = Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: _driverHomeGlass(radius: 20),
        child: SizedBox(
          height: 86,
          child: Stack(
            children: [
              Positioned.fill(
                child: Padding(
                  padding: const EdgeInsets.only(right: 52),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: HomeDesignSystem.cardBody(
                          color: _homeTextSecondary.withValues(alpha: 0.94),
                          size: 16,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const Spacer(),
                      SizedBox(
                        width: double.infinity,
                        child: FittedBox(
                          fit: BoxFit.scaleDown,
                          alignment: Alignment.centerLeft,
                          child: Text(
                            value,
                            style: GoogleFonts.inter(
                              color: _homeTextPrimary,
                              fontSize: 45,
                              fontWeight: FontWeight.w800,
                              height: 1.0,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              Positioned(
                right: 0,
                bottom: 0,
                child: Container(
                  width: 36,
                  height: 36,
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.16),
                    shape: BoxShape.circle,
                    border: Border.all(color: color.withValues(alpha: 0.62)),
                  ),
                  child: Icon(icon, color: color, size: 21),
              ),
            ),
            if (onTap != null)
              Positioned(
                top: 0,
                right: 0,
                width: 36,
                height: 22,
                child: Center(
                  child: Icon(
                    Icons.chevron_right_rounded,
                    size: 22,
                    color: _homeTextSecondary.withValues(alpha: 0.85),
                  ),
                ),
              ),
            ],
          ),
      ),
    );

    return HomeDesignSystem.frostLayer(
      blur: 10,
      child: onTap == null
          ? card
          : Material(
              color: Colors.transparent,
              borderRadius: radius,
              child: InkWell(
                borderRadius: radius,
                onTap: onTap,
                child: card,
        ),
      ),
    );
  }

  Widget _buildDriverPerformanceCards() {
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: _buildDriverMiniStatCard(
                title: 'Completed Rides',
                value: '$_driverHomeCompletedRides',
                icon: Icons.check_circle_rounded,
                color: _homeCompletedRideIcon,
                onTap: () {
                  setState(() {
                    _selectedNavIndex = 3;
                    _ridesFilter = 'completed';
                  });
                  unawaited(_loadRides());
                },
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _buildDriverMiniStatCard(
                title: 'Scheduled',
                value: '$_driverHomeScheduledRides',
                icon: Icons.schedule_rounded,
                color: _homeTextSecondary.withValues(alpha: 0.88),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: _buildDriverMiniStatCard(
                title: 'Total Rides',
                value: '$_driverHomeTotalRides',
                icon: Icons.directions_car_filled,
                color: _homeRideIconBlue,
                onTap: () {
                  setState(() {
                    _selectedNavIndex = 3;
                    _ridesFilter = null;
                  });
                  unawaited(_loadRides());
                },
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _buildDriverMiniStatCard(
                title: 'Active Vehicles',
                value: '${_driverStats?.activeVehicles ?? 0}',
                icon: Icons.garage_rounded,
                color: AuthDesignTokens.brandAction,
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: _buildDriverMiniStatCard(
                title: 'Wallet',
                value:
                    'PKR ${_formatWholeNumberWithCommas(_walletBalance?.balance ?? 0)}',
                icon: Icons.payments_rounded,
                color: AppColors.accent,
                onTap: () {
                  unawaited(Navigator.pushNamed(context, '/wallet'));
                },
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _buildDriverMiniStatCard(
                title: 'CO₂ Saved',
                value: '${_driverHomeCarbonSavedKg.toStringAsFixed(1)} kg',
                icon: Icons.eco_rounded,
                color: _homeCompletedRideIcon,
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildHeaderIcon({
    required IconData icon,
    required int badgeCount,
    required VoidCallback onPressed,
  }) {
    return Stack(
      children: [
        Container(
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                Color(0x33FFFFFF),
                Color(0x1A20283B),
              ],
            ),
            border: Border.all(
              color: Colors.white.withValues(alpha: 0.34),
              width: 1.05,
            ),
            shape: BoxShape.circle,
          ),
          child: IconButton(
            onPressed: onPressed,
            icon: Icon(icon, color: _homeTextPrimary, size: 22),
            padding: const EdgeInsets.all(10),
            constraints: const BoxConstraints(minWidth: 42, minHeight: 42),
          ),
        ),
        if (badgeCount > 0)
          Positioned(
            right: 2,
            top: 2,
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 220),
              transitionBuilder: (child, animation) => ScaleTransition(
                scale: animation,
                child: child,
              ),
              child: Container(
                key: ValueKey<int>(badgeCount),
                padding: const EdgeInsets.all(4),
                decoration: const BoxDecoration(
                  color: AppColors.error,
                  shape: BoxShape.circle,
                ),
                constraints: const BoxConstraints(minWidth: 18, minHeight: 18),
                child: Text(
                  badgeCount > 9 ? '9+' : '$badgeCount',
                  style: GoogleFonts.inter(
                    color: Colors.white,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildDriverOnboardingCard() {
    final hasProfile = _driverProfile != null;
    final hasVehicle = _vehicles.isNotEmpty;
    final isVerified = _isDriverVerifiedForRide;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: HomeDesignSystem.frostLayer(
        blur: 10,
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: _driverHomeGlass(radius: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.assignment_turned_in_rounded,
                      color: AuthDesignTokens.sky400, size: 18),
                  const SizedBox(width: 8),
                  Text(
                    'Driver Onboarding',
                    style: HomeDesignSystem.cardTitle(
                      color: _homeTextPrimary,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              _onboardingStep('Create driver profile', hasProfile),
              _onboardingStep('Add at least one vehicle', hasVehicle),
              _onboardingStep('Complete verification', isVerified),
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _startDriverOnboarding,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AuthDesignTokens.brandAction,
                    foregroundColor: _homeTextPrimary,
                    padding: const EdgeInsets.symmetric(vertical: 10),
                    textStyle: GoogleFonts.inter(fontWeight: FontWeight.w700),
                  ),
                  icon: const Icon(Icons.play_arrow_rounded),
                  label: const Text('Continue Setup'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _onboardingStep(String label, bool done) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Icon(
            done ? Icons.check_circle_rounded : Icons.radio_button_unchecked,
            size: 16,
            color: done
                ? AppColors.success
                : AuthDesignTokens.white.withValues(alpha: 0.6),
          ),
          const SizedBox(width: 8),
          Text(label,
              style: HomeDesignSystem.cardBody(
                size: 12,
                color: done
                    ? _homeTextSecondary.withValues(alpha: 0.88)
                    : _homeTextPrimary.withValues(alpha: 0.96),
              )),
        ],
      ),
    );
  }

  void _startDriverOnboarding() {
    if (_driverProfile == null) {
      _showRegisterDriverDialog();
      return;
    }
    if (_vehicles.isEmpty) {
      _showAddVehicleDialog();
      return;
    }
    if (!_isDriverVerifiedForRide) {
      _openVerificationAndRefresh();
      return;
    }
  }

  void _handleAddVehicleAction() {
    if (_driverProfile == null) {
      _showRegisterDriverDialog();
      return;
    }
    _showAddVehicleDialog();
  }

  void _openScheduleRidesTab() {
    setState(() {
      _selectedNavIndex = 1;
      _isScheduleDetailsStep = false;
      _scheduleDetailsView = null;
    });
  }

  void _showDriverScheduleDetails(Widget detailsView) {
    setState(() {
      _isScheduleDetailsStep = true;
      _scheduleDetailsView = detailsView;
    });
  }

  void _returnToDriverScheduleMap() {
    if (!mounted) return;
    setState(() {
      _isScheduleDetailsStep = false;
      _scheduleDetailsView = null;
    });
  }

  void _openRecurringRidesTab() {
    setState(() {
      _selectedNavIndex = 2;
      _isRecurringDetailsStep = false;
      _recurringDetailsView = null;
    });
  }

  void _showDriverRecurringDetails(Widget detailsView) {
    setState(() {
      _isRecurringDetailsStep = true;
      _recurringDetailsView = detailsView;
    });
  }

  void _returnToDriverRecurringMap() {
    if (!mounted) return;
    setState(() {
      _isRecurringDetailsStep = false;
      _recurringDetailsView = null;
    });
  }

  Widget _buildQuickActions() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: HomeDesignSystem.frostLayer(
        blur: 10,
        child: Container(
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 12),
          decoration: _driverHomeGlass(radius: 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Quick Actions',
                style: HomeDesignSystem.sectionTitle(color: _homeTextPrimary),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  _actionCard(
                    Icons.add_rounded,
                    'Create Ride',
                    _createRideBlue,
                    _openScheduleRidesTab,
                  ),
                  const SizedBox(width: 8),
                  _actionCard(
                    Icons.directions_car_rounded,
                    'Add Vehicle',
                    AuthDesignTokens.brandAction,
                    _handleAddVehicleAction,
                  ),
                  const SizedBox(width: 8),
                  _actionCard(
                    Icons.account_balance_wallet_rounded,
                    'Payout',
                    AppColors.accent,
                    _showPayoutDialog,
                  ),
                  const SizedBox(width: 8),
                  _actionCard(
                    Icons.history_rounded,
                    'History',
                    AuthDesignTokens.sky400,
                    () => setState(() => _selectedNavIndex = 3),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _actionCard(
      IconData icon, String label, Color color, VoidCallback onTap) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Column(
          children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 220),
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    Colors.white.withValues(alpha: 0.1),
                    color.withValues(alpha: 0.16),
                    color.withValues(alpha: 0.08),
                  ],
                ),
                border: Border.all(
                  color: color.withValues(alpha: 0.82),
                  width: 1.8,
                ),
                boxShadow: [
                  BoxShadow(
                    color: color.withValues(alpha: 0.3),
                    blurRadius: 18,
                    spreadRadius: 0.8,
                  ),
                ],
              ),
              child: Center(
                child: Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: color.withValues(alpha: 0.36),
                      width: 1.2,
                    ),
                  ),
                  child: Icon(icon, color: color, size: 30),
                ),
              ),
            ),
            const SizedBox(height: 10),
            Text(
              label,
              textAlign: TextAlign.center,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: GoogleFonts.inter(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: _homeTextPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildScheduledRides() {
    return _buildHomeRideSection(
      title: 'Scheduled Rides',
      rides: _homeScheduledRides,
      emptyText: 'No scheduled rides',
    );
  }

  String _recurringAddress(
      Map<String, dynamic> schedule, String pointKey, String fallback) {
    final point = schedule[pointKey];
    if (point is Map) {
      final address = point['address']?.toString().trim() ?? '';
      if (address.isNotEmpty) return address;
    }
    return fallback;
  }

  String _formatRecurringClock(String raw, {DateTime? referenceLocalDate}) {
    final value = raw.trim();
    if (value.isEmpty) return '--';
    final parsedFull = DateTime.tryParse(value);
    if (parsedFull != null) {
      final local = parsedFull.toLocal();
      final h = local.hour;
      final period = h >= 12 ? 'PM' : 'AM';
      final h12 = h > 12 ? h - 12 : (h == 0 ? 12 : h);
      return '$h12:${local.minute.toString().padLeft(2, '0')} $period';
    }

    final parts = value.split(':');
    if (parts.length < 2) return value;
    final hour = int.tryParse(parts[0]) ?? 0;
    final minute = int.tryParse(parts[1]) ?? 0;

    // Recurring clock fields are treated as UTC time-of-day from backend.
    // Convert using a local reference date so Home always shows user local time.
    final ref = referenceLocalDate ?? DateTime.now();
    final utc = DateTime.utc(ref.year, ref.month, ref.day, hour, minute);
    final local = utc.toLocal();
    final localHour = local.hour;
    final period = localHour >= 12 ? 'PM' : 'AM';
    final h12 = localHour > 12 ? localHour - 12 : (localHour == 0 ? 12 : localHour);
    return '$h12:${local.minute.toString().padLeft(2, '0')} $period';
  }

  String _formatRecurringDeparture(dynamic value) {
    final raw = value?.toString() ?? '';
    if (raw.isEmpty) return 'No upcoming instance yet';
    final parsed = DateTime.tryParse(raw);
    if (parsed == null) return raw;
    final local = parsed.toLocal();
    final h = local.hour;
    final period = h >= 12 ? 'PM' : 'AM';
    final h12 = h > 12 ? h - 12 : (h == 0 ? 12 : h);
    final minute = local.minute.toString().padLeft(2, '0');
    return '${local.day}/${local.month}/${local.year} $h12:$minute $period';
  }

  Future<void> _openDriverRecurringNearestRide(
      Map<String, dynamic> schedule) async {
    final scheduleId =
        (schedule['schedule_id'] ?? schedule['id'] ?? '').toString();
    if (scheduleId.isEmpty) return;

    try {
      final resolved = await _scheduleService.resolveDriverScheduleNextRide(
        scheduleId,
      );
      final rideId = (resolved['ride_id'] ?? '').toString();
      if (!mounted) return;

      if (rideId.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('No active or upcoming ride instance found.'),
          ),
        );
        return;
      }

      Navigator.pushNamed(context, '/ride-detail', arguments: rideId);
    } catch (e) {
      if (!mounted) return;
      final message = e is DioException
          ? extractError(e)
          : 'Failed to open recurring ride instance.';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message), backgroundColor: AppColors.error),
      );
    }
  }

  Future<void> _cancelDriverRecurringSeries(
      Map<String, dynamic> schedule) async {
    final scheduleId =
        (schedule['schedule_id'] ?? schedule['id'] ?? '').toString();
    if (scheduleId.isEmpty) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel Full Recurring Series'),
        content: const Text(
          'This will deactivate your recurring schedule and remove future open instances. Continue?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('No'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Yes', style: TextStyle(color: AppColors.error)),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    try {
      await _scheduleService.deleteSchedule(
        scheduleId,
        purgeFutureRides: true,
      );
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Recurring series cancelled.'),
          backgroundColor: AppColors.success,
        ),
      );
      _loadHomeRecurringSchedules();
      _loadHomeRideSections();
    } catch (e) {
      if (!mounted) return;
      final message = e is DioException
          ? extractError(e)
          : 'Failed to cancel recurring series.';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message), backgroundColor: AppColors.error),
      );
    }
  }

  Widget _buildRecurringHomeSchedules() {
    final items = _homeRecurringSchedules.take(3).toList();
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: HomeDesignSystem.frostLayer(
        blur: 10,
        child: Container(
          padding: const EdgeInsets.fromLTRB(14, 14, 14, 10),
          decoration: _driverHomeGlass(radius: 22),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text('Recurring Rides',
                        style: HomeDesignSystem.sectionTitle(
                            color: _homeTextPrimary)),
                  ),
                  TextButton(
                    onPressed: _openRecurringRidesTab,
                    child: Text(
                      'View All',
                      style: GoogleFonts.inter(
                        color: _homeTextPrimary,
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              if (_isLoadingHome && _homeRecurringSchedules.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(20),
                  child: Center(
                      child:
                          CircularProgressIndicator(color: AppColors.primary)),
                )
              else if (items.isEmpty)
                Container(
                  padding: const EdgeInsets.all(24),
                  decoration: _driverHomeGlass(radius: 16),
                  child: Center(
                    child: Text(
                      'No recurring rides',
                      style:
                          HomeDesignSystem.cardBody(color: _homeTextSecondary),
                    ),
                  ),
                )
              else
                ...items.map((schedule) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: _buildDriverRecurringHomeCard(schedule),
                    )),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildDriverRecurringHomeCard(Map<String, dynamic> schedule) {
    final scheduleId =
        (schedule['schedule_id'] ?? schedule['id'] ?? '').toString();
    final origin = _recurringAddress(schedule, 'start_point', 'Unknown start');
    final destination =
        _recurringAddress(schedule, 'end_point', 'Unknown destination');
    final nextDepartureRaw = schedule['next_departure_time']?.toString() ?? '';
    final nextDepartureParsed = DateTime.tryParse(nextDepartureRaw)?.toLocal();
    final rideTime = _formatRecurringClock(
      (schedule['ride_time'] ?? '').toString(),
      referenceLocalDate: nextDepartureParsed,
    );
    final seats = (schedule['seats_offered'] ?? '').toString();
    final basePriceRaw = schedule['base_price'];
    final price = basePriceRaw is num
        ? basePriceRaw.toDouble()
        : double.tryParse(basePriceRaw?.toString() ?? '') ?? 0;
    final nextDeparture =
        _formatRecurringDeparture(schedule['next_departure_time']);

    return InkWell(
      onTap: () => _openDriverRecurringNearestRide(schedule),
      borderRadius: BorderRadius.circular(16),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: _driverHomeGlass(radius: 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.repeat_rounded,
                    size: 18, color: _homeRideIconBlue),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Daily • $rideTime',
                    style: HomeDesignSystem.cardTitle(color: _homeTextPrimary),
                  ),
                ),
                Text(
                  'Rs ${price.toStringAsFixed(0)}/seat',
                  style: GoogleFonts.inter(
                    fontWeight: FontWeight.w700,
                    fontSize: 12,
                    color: const Color(0xFF0B3D24),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text('$origin → $destination',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: HomeDesignSystem.cardBody(
                  color: _homeTextPrimary,
                  size: 13,
                )),
            const SizedBox(height: 4),
            Text('$seats seats • Next: $nextDeparture',
                style: HomeDesignSystem.cardBody(
                  size: 12,
                  color: _homeTextSecondary,
                )),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: scheduleId.isEmpty
                        ? null
                        : () => _openDriverRecurringNearestRide(schedule),
                    icon: const Icon(Icons.open_in_new_rounded, size: 16),
                    label: const Text('Open Next Ride'),
                    style:
                        HomeDesignSystem.subtleOutlineButton(_homeTextPrimary),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: scheduleId.isEmpty
                        ? null
                        : () => _cancelDriverRecurringSeries(schedule),
                    icon: const Icon(Icons.delete_outline_rounded, size: 16),
                    label: const Text('Cancel Full'),
                    style: HomeDesignSystem.subtleOutlineButton(
                      _homeTextPrimary,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRidesHistory() {
    return _buildHomeRideSection(
      title: 'Rides History',
      rides: _homeHistoryRides,
      emptyText: 'No ride history yet',
    );
  }

  Widget _buildHomeRideSection({
    required String title,
    required List<Ride> rides,
    required String emptyText,
  }) {
    final visibleRides = rides.take(3).toList();
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: HomeDesignSystem.frostLayer(
        blur: 10,
        child: Container(
          padding: const EdgeInsets.fromLTRB(14, 14, 14, 10),
          decoration: _driverHomeGlass(radius: 22),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      title,
                      style: HomeDesignSystem.sectionTitle(
                          color: _homeTextPrimary),
                    ),
                  ),
                  TextButton(
                    onPressed: () => setState(() => _selectedNavIndex = 3),
                    child: Text(
                      'View All',
                      style: GoogleFonts.inter(
                        color: _homeTextPrimary,
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              if (_isLoadingRides)
                const Padding(
                  padding: EdgeInsets.all(20),
                  child: Center(
                      child:
                          CircularProgressIndicator(color: AppColors.primary)),
                )
              else if (visibleRides.isEmpty)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(20),
                  decoration: _driverHomeGlass(radius: 16),
                  child: Center(
                    child: Text(
                      emptyText,
                      style: HomeDesignSystem.cardBody(
                        color: _homeTextSecondary.withValues(alpha: 0.9),
                      ),
                    ),
                  ),
                )
              else
                ...visibleRides.map((ride) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: _buildDriverRideCard(ride, useHomeTextBlack: true),
                    )),
            ],
          ),
        ),
      ),
    );
  }

  // ═════════════════════════════════════════════════════════
  //  TAB 2 — MY RIDES
  // ═════════════════════════════════════════════════════════
  Widget _buildMyRidesTab() {
    return Stack(
      children: [
        _buildDriverDashboardBackground(),
        SafeArea(
          child: HomeDesignSystem.contentWidth(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'My Rides',
                        style: GoogleFonts.inter(
                          fontSize: 48,
                          fontWeight: FontWeight.w900,
                          color: _homeTextPrimary,
                          height: 0.95,
                        ),
                      ),
                      const SizedBox(height: 6),
                          Text(
                        'TRACKING YOUR VOYAGES',
                        style: GoogleFonts.inter(
                          fontSize: 22,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 0.8,
                          color: _homeTextSecondary.withValues(alpha: 0.75),
                            ),
                          ),
                          const SizedBox(height: 14),
                      Row(
                              children: [
                          Expanded(
                            child: _driverMyRidesActionButton(
                              icon: Icons.tune_rounded,
                              label: 'Filters',
                              onTap: _showDriverRideFiltersSheet,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: _isLoadingRides
                        ? const SyloLoader(message: 'Loading rides…')
                        : _ridesError != null
                            ? (_isDriverProfileMissingError(_ridesError)
                                ? SyloEmpty(
                                    icon: Icons.assignment_turned_in_outlined,
                                    title: 'Complete Driver Setup',
                                    subtitle:
                                        'Create your driver profile first, then your rides will appear here.',
                                    actionLabel: 'Continue Setup',
                                    onAction: _startDriverOnboarding,
                                  )
                                : SyloError(
                                    message:
                                        'Unable to load rides right now. Please try again.',
                                    onRetry: _loadRides,
                                  ))
                            : _rides.isEmpty
                                ? SyloEmpty(
                                    icon: Icons.directions_car_outlined,
                                    title: 'No rides found',
                                    subtitle: 'Create a ride to get started',
                                    actionLabel: 'Create Ride',
                                    onAction: _openScheduleRidesTab,
                                  )
                                : RefreshIndicator(
                                    onRefresh: _refreshHomeAndEarnings,
                                    color: AuthDesignTokens.brandAction,
                                    triggerMode:
                                        RefreshIndicatorTriggerMode.anywhere,
                                    child: _desktopRefreshScrollable(
                                      ListView.separated(
                                        physics:
                                            const AlwaysScrollableScrollPhysics(
                                          parent: BouncingScrollPhysics(),
                                        ),
                                        padding:
                                            const EdgeInsets.only(bottom: 18),
                                        itemCount: _rides.length,
                                        separatorBuilder: (_, __) =>
                                            const SizedBox(height: 10),
                                        itemBuilder: (_, i) =>
                                            _buildDriverMyRideCard(
                                          _rides[i],
                                          index: i,
                                          totalRides: _driverHomeTotalRides,
                                          highlight: i == 0,
                                        ),
                                      ),
                                    ),
                                  ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildDriverMyRideCard(
    Ride ride, {
    required int index,
    required int totalRides,
    bool highlight = false,
  }) {
    final isOpenRide = ride.status == 'open';
    final isInProgressRide = ride.status == 'in_progress';
    final canComplete = _canDriverCompleteRide(ride);
    final canCancel = ride.canDriverCancel ?? (ride.status == 'open');
    Color statusColor;
    switch (ride.status) {
      case 'in_progress':
        statusColor = AppColors.info;
        break;
      case 'open':
        statusColor = AppColors.accent;
        break;
      case 'completed':
        statusColor = AppColors.success;
        break;
      case 'cancelled':
        statusColor = AppColors.error;
        break;
      default:
        statusColor = AppColors.accent;
    }

    final localDt = ride.departureDatetime?.toLocal();
    final timeStr = localDt == null
        ? '—'
        : '${localDt.day}/${localDt.month} ${localDt.hour.toString().padLeft(2, '0')}:${localDt.minute.toString().padLeft(2, '0')}';
    final durationText = ride.estimatedDuration == null
        ? '—'
        : '${ride.estimatedDuration!.round()} mins';
    final distanceText = ride.routeDistanceKm == null
        ? '—'
        : '${ride.routeDistanceKm!.toStringAsFixed(1)} mi';

    final showOpenHeroStyle = isOpenRide;
    final enableCardTap = !isOpenRide;
    final rideNumber = (totalRides > 0)
        ? (totalRides - index).clamp(1, totalRides)
        : (index + 1);

    return GestureDetector(
      onTap: enableCardTap
          ? () =>
              Navigator.pushNamed(context, '/ride-detail', arguments: ride.id)
          : null,
      child: Container(
        constraints: BoxConstraints(minHeight: isOpenRide ? 304 : 0),
        padding: EdgeInsets.zero,
        clipBehavior: Clip.antiAlias,
          decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(18),
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            colors: [
              const Color(0xFF0D2C1F).withValues(alpha: 0.84),
              const Color(0xFF0A2319).withValues(alpha: 0.78),
            ],
          ),
          border: isOpenRide
              ? Border(
                  top: BorderSide(
                    color: Colors.white.withValues(alpha: 0.18),
                    width: 1.0,
                  ),
                  right: BorderSide(
                    color: Colors.white.withValues(alpha: 0.18),
                    width: 1.0,
                  ),
                  bottom: BorderSide(
                    color: Colors.white.withValues(alpha: 0.18),
                    width: 1.0,
                  ),
                )
              : Border.all(
                  color: Colors.white.withValues(alpha: 0.18),
                  width: 1.0,
            ),
            boxShadow: [
                BoxShadow(
              color: Colors.black.withValues(alpha: 0.2),
              blurRadius: 16,
              offset: const Offset(0, 8),
            ),
            BoxShadow(
              color: Colors.white.withValues(alpha: 0.06),
              blurRadius: 8,
              offset: const Offset(0, -2),
                ),
            ],
          ),
        child: Stack(
          children: [
            if (isOpenRide)
              Positioned(
                left: 0,
                top: 0,
                bottom: 0,
                child: Container(
                  width: 11,
                  decoration: const BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [Color(0xFF62FFB0), Color(0xFF43E88E)],
                    ),
                    borderRadius: BorderRadius.only(
                      topLeft: Radius.circular(18),
                      bottomLeft: Radius.circular(18),
                    ),
                  ),
                ),
              ),
            Padding(
              padding: EdgeInsets.fromLTRB(
                isOpenRide ? 24 : 14,
                isOpenRide ? 18 : 14,
                14,
                isOpenRide ? 18 : 14,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.08),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: const Icon(
                          Icons.directions_car_filled_rounded,
                          color: Color(0xFF65F4A5),
                          size: 20,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
          child: Text(
                          'Ride #$rideNumber',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: GoogleFonts.inter(
                            color: Colors.white.withValues(alpha: 0.97),
                            fontWeight: FontWeight.w800,
                            fontSize: 18,
                          ),
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: statusColor.withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(
                          ride.effectiveDisplayStatus.toUpperCase(),
                          style: GoogleFonts.inter(
                            color: statusColor,
                            fontSize: 10.5,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 1.1,
                          ),
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: isOpenRide ? 14 : 10),
                  Row(
                    children: [
                      const Icon(Icons.circle,
                          size: 7, color: Color(0xFF65F4A5)),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          ride.origin,
                          style: GoogleFonts.inter(
                            color: Colors.white.withValues(alpha: 0.9),
                            fontWeight: FontWeight.w700,
                            fontSize: 15,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: isOpenRide ? 9 : 5),
                  Row(
                    children: [
                      Icon(Icons.circle_outlined,
                          size: 8, color: Colors.white.withValues(alpha: 0.72)),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          ride.destination,
                          style: GoogleFonts.inter(
                            color: Colors.white.withValues(alpha: 0.88),
                            fontWeight: FontWeight.w700,
                            fontSize: 15,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: isOpenRide ? 18 : 12),
                  if (!showOpenHeroStyle)
                    Row(
                      children: [
                        Icon(Icons.schedule_rounded,
                            size: 14,
                            color: Colors.white.withValues(alpha: 0.58)),
                        const SizedBox(width: 6),
                        Text(
                          durationText,
                          style: GoogleFonts.inter(
                            color: Colors.white.withValues(alpha: 0.74),
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(width: 16),
                        Icon(Icons.route_rounded,
                            size: 14,
                            color: Colors.white.withValues(alpha: 0.58)),
                        const SizedBox(width: 6),
                        Text(
                          distanceText,
                          style: GoogleFonts.inter(
                            color: Colors.white.withValues(alpha: 0.74),
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const Spacer(),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Text(
                              'Rs ${ride.pricePerSeat.toStringAsFixed(0)}',
                              style: GoogleFonts.inter(
                                color: Colors.white.withValues(alpha: 0.95),
                                fontWeight: FontWeight.w800,
                                fontSize: 20,
                              ),
                            ),
                            Text(
                              'Per Seat',
                              style: GoogleFonts.inter(
                                color: Colors.white.withValues(alpha: 0.6),
                                fontWeight: FontWeight.w700,
                                fontSize: 11,
                                letterSpacing: 0.4,
                              ),
                            ),
                          ],
                        ),
                      ],
                    )
                  else
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'FARE EST.',
                                style: GoogleFonts.inter(
                                  color: Colors.white.withValues(alpha: 0.56),
                                  fontWeight: FontWeight.w700,
                                  fontSize: 11,
                                  letterSpacing: 0.8,
                                ),
                              ),
                              Text(
                                'Rs ${ride.pricePerSeat.toStringAsFixed(2)}',
                                style: GoogleFonts.inter(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w900,
                                  fontSize: 37,
                                ),
                              ),
                              Text(
                                'Per Seat',
                                style: GoogleFonts.inter(
                                  color: Colors.white.withValues(alpha: 0.6),
                                  fontWeight: FontWeight.w700,
                                  fontSize: 11,
                                  letterSpacing: 0.6,
                                ),
                              ),
                            ],
                          ),
                        ),
                        Padding(
                          padding: const EdgeInsets.only(bottom: 6),
                          child: FilledButton(
                            onPressed: () => Navigator.pushNamed(
                              context,
                              '/ride-detail',
                              arguments: ride.id,
                            ),
                            style: FilledButton.styleFrom(
                              backgroundColor: const Color(0xFF50F09B),
                              foregroundColor: const Color(0xFF052F1E),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(999),
                              ),
                              textStyle: GoogleFonts.inter(
                                fontWeight: FontWeight.w800,
                                fontSize: 15,
                              ),
                            ),
                            child: const Text('View Details'),
                          ),
                        ),
                      ],
                    ),
                  SizedBox(height: isOpenRide ? 12 : 8),
                  Text(
                    timeStr,
                    style: GoogleFonts.inter(
                      color: Colors.white.withValues(alpha: 0.62),
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (ride.isActive && (isInProgressRide || canCancel)) ...[
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        if (isInProgressRide)
                          Expanded(
                            child: ElevatedButton(
                              onPressed: () {
                                if (canComplete) {
                                  _completeRide(ride);
                                } else {
                                  _showCompleteRideBlockedDialog();
                                }
                              },
                              child: const Text('Complete'),
                            ),
                          ),
                        if (canCancel && !isOpenRide) ...[
                          const SizedBox(width: 8),
                          Expanded(
                            child: OutlinedButton(
                              onPressed: () => _cancelRide(ride),
                              child: const Text('Cancel'),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _driverMyRidesActionButton({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Container(
          height: 48,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                const Color(0xFF0E2E20).withValues(alpha: 0.82),
                const Color(0xFF0A261A).withValues(alpha: 0.76),
              ],
            ),
            border: Border.all(
              color: const Color(0xFF1ED760).withValues(alpha: 0.28),
            ),
          ),
          child: Row(
            children: [
              Icon(icon, size: 18, color: const Color(0xFF1ED760)),
              const SizedBox(width: 8),
              Text(
            label,
            style: GoogleFonts.inter(
                  fontSize: 14,
                  fontWeight: FontWeight.w700,
                  color: Colors.white.withValues(alpha: 0.94),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showDriverRideFiltersSheet() async {
    final options = <Map<String, String?>>[
      {'label': 'All', 'value': null},
      {'label': 'Scheduled', 'value': 'open'},
      {'label': 'In Progress', 'value': 'in_progress'},
      {'label': 'Completed', 'value': 'completed'},
      {'label': 'Cancelled', 'value': 'cancelled'},
    ];

    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Container(
        decoration: BoxDecoration(
          color: const Color(0xFF0D241A),
          borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
          border: Border.all(
            color: const Color(0xFF1ED760).withValues(alpha: 0.28),
          ),
        ),
        child: SafeArea(
          top: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: options.map((entry) {
              final isSelected = _ridesFilter == entry['value'];
              return ListTile(
                leading: Icon(
                  isSelected
                      ? Icons.radio_button_checked_rounded
                      : Icons.radio_button_off_rounded,
                  color: isSelected
                      ? const Color(0xFF1ED760)
                      : Colors.white.withValues(alpha: 0.55),
                ),
                title: Text(
                  entry['label']!,
                  style: GoogleFonts.inter(
                    color: Colors.white.withValues(alpha: 0.94),
                    fontWeight: FontWeight.w700,
                  ),
                ),
                onTap: () {
                  Navigator.pop(ctx);
                  setState(() => _ridesFilter = entry['value']);
                  _loadRides();
                },
              );
            }).toList(),
          ),
        ),
      ),
    );
  }

  Widget _buildDriverRideCard(Ride ride, {bool useHomeTextBlack = false}) {
    final isOpenRide = ride.status == 'open';
    final isInProgressRide = ride.status == 'in_progress';
    final canStart = _canDriverStartRide(ride);
    final canComplete = _canDriverCompleteRide(ride);
    final canCancel = ride.canDriverCancel ?? (ride.status == 'open');
    final driverCarbonSavedKg = _driverRideCarbonSavedKg(ride);

    Color statusColor;
    switch (ride.status) {
      case 'in_progress':
        statusColor = AppColors.info;
        break;
      case 'open':
        statusColor = AppColors.accent;
        break;
      case 'completed':
        statusColor = AppColors.success;
        break;
      case 'cancelled':
        statusColor = AppColors.error;
        break;
      default:
        statusColor = AppColors.accent;
    }

    if (useHomeTextBlack && ride.status == 'completed') {
      statusColor = _homeCompletedRideIcon;
    }

    final dt = ride.departureDatetime;
    final localDt = dt?.toLocal();
    final timeStr = localDt != null
        ? '${localDt.day}/${localDt.month} ${localDt.hour.toString().padLeft(2, '0')}:${localDt.minute.toString().padLeft(2, '0')}'
        : '';
    final primaryTextColor = useHomeTextBlack ? _homeTextPrimary : Colors.white;
    final secondaryTextColor = useHomeTextBlack
        ? _homeTextSecondary.withValues(alpha: 0.9)
        : Colors.white.withValues(alpha: 0.76);
    final tertiaryTextColor = useHomeTextBlack
        ? _homeTextSecondary.withValues(alpha: 0.82)
        : Colors.white.withValues(alpha: 0.7);

    final emphasize = !useHomeTextBlack && (isOpenRide || isInProgressRide);

    return GestureDetector(
      onTap: () =>
          Navigator.pushNamed(context, '/ride-detail', arguments: ride.id),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: useHomeTextBlack
                ? [
                    const Color(0xA255E0A0),
                    const Color(0x943ABF7C),
                  ]
                : [
                    const Color(0xFF0D2C1F).withValues(alpha: 0.92),
                    const Color(0xFF0A2319).withValues(alpha: 0.88),
                  ],
          ),
          border: Border.all(
            color: emphasize
                ? const Color(0xFF1ED760).withValues(alpha: 0.86)
                : Colors.white
                    .withValues(alpha: useHomeTextBlack ? 0.22 : 0.12),
            width: emphasize ? 1.6 : 1.0,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.2),
              blurRadius: 16,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Route info
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AuthDesignTokens.routeBlue.withValues(alpha: 0.18),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(
                    Icons.directions_car_rounded,
                    color: useHomeTextBlack
                        ? _homeRideIconBlue
                        : AuthDesignTokens.routeBlue,
                    size: 22,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Icon(Icons.circle,
                              size: 6, color: AppColors.primary),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(ride.origin,
                                overflow: TextOverflow.ellipsis,
                                style: GoogleFonts.inter(
                                  color: primaryTextColor,
                                  fontWeight: FontWeight.w600,
                                  fontSize: 13,
                                )),
                          ),
                        ],
                      ),
                      const SizedBox(height: 3),
                      Row(
                        children: [
                          const Icon(Icons.circle,
                              size: 6, color: AppColors.accent),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(ride.destination,
                                overflow: TextOverflow.ellipsis,
                                style: GoogleFonts.inter(
                                  color: primaryTextColor,
                                  fontWeight: FontWeight.w600,
                                  fontSize: 13,
                                )),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: statusColor.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    ride.effectiveDisplayStatus,
                    style: TextStyle(
                        color: statusColor,
                        fontWeight: FontWeight.w700,
                        fontSize: 11),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            // Metadata row
            Row(
              children: [
                Icon(Icons.access_time,
                    size: 13,
                    color: useHomeTextBlack
                        ? _homeTextSecondary.withValues(alpha: 0.78)
                        : AppColors.textHint),
                const SizedBox(width: 4),
                Text(timeStr,
                    style: GoogleFonts.inter(
                      color: secondaryTextColor,
                      fontSize: 12,
                    )),
                const SizedBox(width: 14),
                Icon(Icons.airline_seat_recline_normal,
                    size: 13, color: tertiaryTextColor),
                const SizedBox(width: 4),
                Text('${ride.availableSeats} seats',
                    style: GoogleFonts.inter(
                      color: secondaryTextColor,
                      fontSize: 12,
                    )),
                const Spacer(),
                Text('PKR ${ride.pricePerSeat.toStringAsFixed(0)}/seat',
                    style: GoogleFonts.inter(
                        fontWeight: FontWeight.w800,
                        fontSize: 13,
                        color: const Color(0xFF0B3D24))),
              ],
            ),
            if (driverCarbonSavedKg != null && driverCarbonSavedKg > 0) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(Icons.eco_rounded,
                      size: 13,
                      color: useHomeTextBlack
                          ? _homeCompletedRideIcon
                          : AppColors.success),
                  const SizedBox(width: 4),
                  Text(
                    '${driverCarbonSavedKg.toStringAsFixed(1)} kg CO₂ saved',
                    style: TextStyle(
                      color: useHomeTextBlack
                          ? _homeCompletedRideIcon
                          : AppColors.success,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ],
            // Action buttons for active rides
            if (ride.isActive) ...[
              const SizedBox(height: 10),
              const Divider(height: 1),
              const SizedBox(height: 8),
              // View stop sequence + earnings button
              if (ride.bookings != null && ride.bookings!.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: () => _showRideStopSequence(ride),
                      icon: const Icon(Icons.route_rounded, size: 16),
                      label: Text(
                          'Passenger Stops & Earnings (${ride.bookings!.length} pax)'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.primary,
                        side: BorderSide(
                            color: AppColors.primary.withValues(alpha: 0.5)),
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        textStyle: const TextStyle(
                            fontSize: 12, fontWeight: FontWeight.w600),
                      ),
                    ),
                  ),
                ),
              Row(
                children: [
                  if (isOpenRide)
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () {
                          if (canStart) {
                            _startRide(ride);
                          } else {
                            _showStartRideBlockedDialog();
                          }
                        },
                        icon: const Icon(Icons.play_arrow, size: 18),
                        label: const Text('Start'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor:
                              canStart ? AppColors.info : AppColors.textHint,
                          side: BorderSide(
                              color:
                                  canStart ? AppColors.info : AppColors.border),
                          backgroundColor: canStart
                              ? Colors.transparent
                              : AppColors.backgroundLight,
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          textStyle: const TextStyle(
                              fontSize: 13, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ),
                  if (isInProgressRide) ...[
                    Expanded(
                      child: ElevatedButton.icon(
                        onPressed: () {
                          if (canComplete) {
                            _completeRide(ride);
                          } else {
                            _showCompleteRideBlockedDialog();
                          }
                        },
                        icon: const Icon(Icons.check_circle, size: 18),
                        label: const Text('Complete'),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: canComplete
                              ? AppColors.success
                              : AppColors.border,
                          foregroundColor:
                              canComplete ? Colors.white : AppColors.textHint,
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          textStyle: const TextStyle(
                              fontSize: 13, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ),
                  ],
                  if (canCancel) ...[
                    const SizedBox(width: 8),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () => _cancelRide(ride),
                        icon: const Icon(Icons.cancel, size: 18),
                        label: const Text('Cancel'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppColors.error,
                          side: const BorderSide(color: AppColors.error),
                          padding: const EdgeInsets.symmetric(vertical: 8),
                          textStyle: const TextStyle(
                              fontSize: 13, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  // ── Show ride stop sequence bottom sheet (Module 4 UI) ───────────────────
  Future<void> _showRideStopSequence(Ride ride) async {
    final pricingService = DynamicPricingService();
    final bookings = ride.bookings ?? [];

    // Load booking fare details for each booking
    final List<BookingFareDetails> fareDetails = [];
    for (final booking in bookings) {
      final d = await pricingService.getBookingFareDetails(booking.id);
      if (d != null) fareDetails.add(d);
    }

    if (!mounted) return;

    final stops = fareDetails
        .map((d) => RideStop.fromBookingDetails(d, passengerName: 'Passenger'))
        .toList();

    final totalEarnings =
        fareDetails.fold<double>(0, (s, d) => s + (d.individualFare ?? d.fare));
    final totalRouteKm = ride.routeDistanceKm ?? 0.0;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.7,
        maxChildSize: 0.95,
        builder: (_, ctrl) => SingleChildScrollView(
          controller: ctrl,
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.grey[300],
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              if (stops.isEmpty)
                const Center(child: Text('No passenger data yet.'))
              else
                RideStopSequenceWidget(
                  stops: stops,
                  totalRouteKm: totalRouteKm,
                  totalEarningsPkr: totalEarnings,
                  totalPassengers: stops.length,
                  departureTime: ride.departureDatetime,
                ),
            ],
          ),
        ),
      ),
    );
  }

  // ═════════════════════════════════════════════════════════
  //  TAB 3 — EARNINGS
  // ═════════════════════════════════════════════════════════
  // Reuses the same black-on-green glass palette as the Home screen.
  Color get _earningsCardTextPrimary => _homeTextPrimary;
  Color get _earningsCardTextMuted =>
      _homeTextSecondary.withValues(alpha: 0.88);
  Color get _earningsAccentGreen => _profileSymbolShade(
        const Color(0xFF1ED760),
      );

  Widget _earningsGlassShell({
    required Widget child,
    double radius = 22,
  }) {
    return HomeDesignSystem.frostLayer(
      blur: 10,
      radius: radius,
      child: Container(
        decoration: _driverHomeGlass(
          radius: radius,
          elevated: true,
          borderAlpha: 0.42,
          borderWidth: 1.1,
        ),
        child: child,
      ),
    );
  }

  Widget _buildEarningsTab() {
    return Stack(
            children: [
        _buildDriverHomeBackground(),
        SafeArea(
          child: HomeDesignSystem.contentWidth(
          child: _isLoadingEarnings
              ? const SyloLoader(message: 'Loading earnings…')
              : _earningsError != null
                    ? SyloError(
                        message: _earningsError!, onRetry: _loadEarnings)
                  : RefreshIndicator(
                      onRefresh: _refreshHomeAndEarnings,
                        color: _earningsAccentGreen,
                      triggerMode: RefreshIndicatorTriggerMode.anywhere,
                      child: _desktopRefreshScrollable(
                        ListView(
                          physics: const AlwaysScrollableScrollPhysics(
                            parent: BouncingScrollPhysics(),
                          ),
                            padding: const EdgeInsets.fromLTRB(18, 12, 18, 32),
                          children: [
                              _buildEarningsHeroHeader(),
                              const SizedBox(height: 20),
                              _buildEarningsBreakdownCard(
                                label: 'Gross Earnings',
                                displayValue:
                                    'PKR ${_formatWholeNumberWithCommas(_lifetimeEarnings?.lifetimeGross ?? 0)}',
                                icon: Icons.trending_up_rounded,
                              ),
                            const SizedBox(height: 12),
                              _buildEarningsBreakdownCard(
                                label: 'Total Rides Completed',
                                displayValue: _formatWholeNumberWithCommas(
                                    _lifetimeEarnings?.totalRides ?? 0),
                                icon: Icons.route_rounded,
                              ),
                              const SizedBox(height: 12),
                              _buildEarningsBreakdownCard(
                                label: 'Total Withdrawn',
                                displayValue:
                                    'PKR ${_formatWholeNumberWithCommas(_lifetimeEarnings?.totalWithdrawn ?? 0)}',
                                icon: Icons.account_balance_rounded,
                              ),
                              const SizedBox(height: 22),
                              _buildMonthlySummaryCard(),
                              const SizedBox(height: 20),
                              _buildWalletsPayoutsCard(),
                            ],
                          ),
                        ),
                      ),
                    ),
        ),
      ],
    );
  }

  Widget _buildEarningsHeroHeader() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 6, 4, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
      children: [
          Text(
            'PERFORMANCE OVERVIEW',
            style: GoogleFonts.inter(
              fontSize: 13,
              fontWeight: FontWeight.w800,
              letterSpacing: 2.4,
              color: _homeTextSecondary,
            ),
          ),
        const SizedBox(height: 6),
          Text(
            'Lifetime\nEarnings',
            style: GoogleFonts.playfairDisplay(
              fontSize: 52,
              height: 1.02,
              fontWeight: FontWeight.w900,
              letterSpacing: 0.2,
              color: _homeTextPrimary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEarningsBreakdownCard({
    required String label,
    required String displayValue,
    required IconData icon,
  }) {
    return _earningsGlassShell(
      radius: 20,
      child: Container(
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 16),
        child: Row(
          children: [
            Container(
              width: 42,
              height: 42,
              alignment: Alignment.center,
        decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFF1ED760).withValues(alpha: 0.22),
          border: Border.all(
                  color: _earningsAccentGreen.withValues(alpha: 0.55),
                  width: 1.1,
                ),
              ),
              child: Icon(
                icon,
                size: 19,
                color: _earningsAccentGreen,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    label,
                    style: GoogleFonts.inter(
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.3,
                      color: _homeTextSecondary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    displayValue,
                    style: GoogleFonts.inter(
                      fontSize: 28,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 0.2,
                      color: _earningsCardTextPrimary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        ),
      );
    }

  Widget _buildMonthlySummaryCard() {
    final months = [
      '',
      'January',
      'February',
      'March',
      'April',
      'May',
      'June',
      'July',
      'August',
      'September',
      'October',
      'November',
      'December',
    ];
    final m = _monthlyEarnings;
    final now = DateTime.now();
    final monthIndex = m?.month ?? now.month;
    final year = m?.year ?? now.year;
    final monthLabel =
        monthIndex >= 1 && monthIndex <= 12 ? months[monthIndex] : '';

    final dailyPoints = _buildDailyEarningsSeries();
    final normalizedPoints = _normalizeSeries(dailyPoints);
    final hasChartPoints = dailyPoints.length >= 2;

    return _earningsGlassShell(
      radius: 24,
      child: Container(
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
            Text(
              'Monthly Summary',
              style: GoogleFonts.inter(
                fontSize: 22,
                fontWeight: FontWeight.w900,
                letterSpacing: 0.2,
                color: _earningsCardTextPrimary,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              '$monthLabel $year',
              style: GoogleFonts.inter(
                fontSize: 14,
                fontWeight: FontWeight.w700,
                color: _homeTextSecondary,
                letterSpacing: 0.2,
              ),
            ),
            const SizedBox(height: 18),
            SizedBox(
              height: 148,
              child: hasChartPoints
                  ? CustomPaint(
                      painter: _EarningsCurvePainter(
                        points: normalizedPoints,
                        strokeColor: _earningsAccentGreen,
                        fillColor: _earningsAccentGreen,
                      ),
                      child: const SizedBox.expand(),
                    )
                  : Center(
                      child: Text(
                        'Not enough data yet — complete rides to see your monthly trend.',
                        textAlign: TextAlign.center,
                        style: GoogleFonts.inter(
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                          color: _earningsCardTextMuted,
                        ),
                      ),
                    ),
            ),
            const SizedBox(height: 10),
            if (hasChartPoints)
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: _dailyAxisLabels(dailyPoints)
                    .map(
                      (label) => Text(
                        label,
                        style: GoogleFonts.inter(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: _homeTextSecondary,
                        ),
                      ),
                    )
                    .toList(),
              ),
            const SizedBox(height: 16),
              Container(
              height: 1,
              color: _homeTextPrimary.withValues(alpha: 0.12),
            ),
            const SizedBox(height: 14),
            Row(
              children: [
                Expanded(
                  child: _monthlyStatCell(
                    label: 'Rides',
                    value: '${m?.totalRides ?? 0}',
                  ),
                ),
                _monthlyDivider(),
                Expanded(
                  child: _monthlyStatCell(
                    label: 'Gross',
                    value:
                        'PKR ${_formatWholeNumberWithCommas(m?.grossEarnings ?? 0)}',
                    highlight: true,
                ),
              ),
            ],
          ),
          ],
        ),
      ),
    );
  }

  Widget _monthlyDivider() {
    return Container(
      width: 1,
      height: 32,
      margin: const EdgeInsets.symmetric(horizontal: 6),
      color: _homeTextPrimary.withValues(alpha: 0.14),
    );
  }

  Widget _monthlyStatCell({
    required String label,
    required String value,
    bool highlight = false,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.center,
        children: [
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Text(
            value,
            style: GoogleFonts.inter(
              fontSize: 20,
              fontWeight: FontWeight.w900,
              letterSpacing: 0.2,
              color:
                  highlight ? _earningsAccentGreen : _earningsCardTextPrimary,
            ),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          label,
          style: GoogleFonts.inter(
            fontSize: 12,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.1,
            color: _homeTextSecondary,
          ),
        ),
      ],
    );
  }

  /// Builds a day-by-day **cumulative** gross-earnings series for the last
  /// 30 days using the driver's real data. The line is a running total so
  /// it can only stay flat or climb — it never decreases, reflecting the
  /// fact that monthly earnings are additive.
  ///
  /// Uses the raw `earnings` field from the daily chart (gross earnings),
  /// so no platform fees or other deductions are applied here.
  List<DailyEarningsData> _buildDailyEarningsSeries() {
    const windowDays = 30;
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);

    final earningsByDay = <String, double>{};
    for (final entry
        in _monthlyChart?.dailyData ?? const <DailyEarningsData>[]) {
      final parsed = DateTime.tryParse(entry.date);
      if (parsed == null) continue;
      final key =
          '${parsed.year}-${parsed.month.toString().padLeft(2, '0')}-${parsed.day.toString().padLeft(2, '0')}';
      earningsByDay.update(
        key,
        (v) => v + entry.earnings,
        ifAbsent: () => entry.earnings,
      );
    }

    final series = <DailyEarningsData>[];
    double runningTotal = 0;
    for (int i = windowDays - 1; i >= 0; i--) {
      final d = today.subtract(Duration(days: i));
      final key =
          '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
      runningTotal += earningsByDay[key] ?? 0;
      series.add(DailyEarningsData(
        date: d.toIso8601String().substring(0, 10),
        rides: 0,
        earnings: runningTotal,
      ));
    }
    return series;
  }

  List<double> _normalizeSeries(List<DailyEarningsData> data) {
    if (data.isEmpty) return const <double>[];
    final values = data.map((d) => d.earnings).toList();
    final maxValue = values.fold<double>(0, (a, b) => b > a ? b : a);
    if (maxValue <= 0) {
      // Driver has no gross earnings in the last 30 days — render a gentle
      // flat baseline so the chart is still visible.
      return List<double>.filled(values.length, 0.12);
    }
    // Small baseline so the curve starts a bit above the bottom edge; the
    // final cumulative total pushes the line near the top of the chart.
    return values
        .map((v) => 0.08 + (v / maxValue).clamp(0.0, 1.0) * 0.9)
        .toList();
  }

  List<String> _dailyAxisLabels(List<DailyEarningsData> data) {
    if (data.length < 2) return const <String>[];
    const short = [
      '',
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
      'Dec',
    ];
    String fmt(String raw) {
      final parsed = DateTime.tryParse(raw);
      if (parsed == null) return raw;
      return '${short[parsed.month]} ${parsed.day}';
    }

    final picks = <int>{
      0,
      (data.length * 0.33).floor(),
      (data.length * 0.66).floor(),
      data.length - 1,
    }.toList()
      ..sort();
    return picks.map((i) => fmt(data[i].date)).toList();
  }

  Widget _buildWalletsPayoutsCard() {
    final balance = _lifetimeEarnings?.currentWalletBalance ?? 0;
    final withdrawn = _lifetimeEarnings?.totalWithdrawn ?? 0;

    return _earningsGlassShell(
      radius: 26,
      child: Container(
        padding: const EdgeInsets.fromLTRB(20, 22, 20, 22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                  width: 40,
                  height: 40,
                  alignment: Alignment.center,
                decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: const Color(0xFF1ED760).withValues(alpha: 0.22),
                    border: Border.all(
                      color: _earningsAccentGreen.withValues(alpha: 0.55),
                      width: 1.1,
                    ),
                  ),
                  child: Icon(
                    Icons.account_balance_wallet_rounded,
                    size: 19,
                    color: _earningsAccentGreen,
                  ),
              ),
              const SizedBox(width: 12),
                Text(
                  'Wallets & Payouts',
                  style: GoogleFonts.inter(
                    fontSize: 22,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 0.2,
                    color: _earningsCardTextPrimary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 18),
            Text(
              'Available for Withdrawal',
              style: GoogleFonts.inter(
                fontSize: 14,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.3,
                color: _homeTextSecondary,
              ),
            ),
            const SizedBox(height: 6),
            FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(
                'PKR ${_formatWholeNumberWithCommas(balance)}',
                style: GoogleFonts.inter(
                  fontSize: 48,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0.2,
                  color: _earningsCardTextPrimary,
                  height: 1.0,
                ),
              ),
            ),
            const SizedBox(height: 6),
            Text(
              'Total withdrawn: PKR ${_formatWholeNumberWithCommas(withdrawn)}',
              style: GoogleFonts.inter(
                fontSize: 13.5,
                fontWeight: FontWeight.w600,
                color: _homeTextSecondary,
              ),
            ),
            const SizedBox(height: 22),
            _buildPayoutButton(),
            const SizedBox(height: 10),
            _buildExportCsvButton(),
          ],
        ),
      ),
    );
  }

  Widget _buildPayoutButton() {
    return SizedBox(
      width: double.infinity,
      height: 54,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(999),
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              Color(0xFF2BE088),
              Color(0xFF16A35B),
            ],
          ),
          boxShadow: [
            BoxShadow(
              color: _earningsAccentGreen.withValues(alpha: 0.35),
              blurRadius: 18,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: _showPayoutDialog,
            borderRadius: BorderRadius.circular(999),
            child: Center(
              child: Text(
                'Request Payout',
                style: GoogleFonts.inter(
                  fontSize: 17,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0.4,
                  color: Colors.white,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  bool _isExportingCsv = false;

  Widget _buildExportCsvButton() {
    return SizedBox(
      width: double.infinity,
      height: 46,
      child: TextButton(
        onPressed: _isExportingCsv ? null : _exportEarningsCsv,
        style: TextButton.styleFrom(
          foregroundColor: _earningsCardTextPrimary,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(999),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (_isExportingCsv)
              SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor:
                      AlwaysStoppedAnimation<Color>(_earningsAccentGreen),
                ),
              )
            else
              const Icon(
                Icons.download_rounded,
                size: 16,
                color: _homeTextSecondary,
              ),
            const SizedBox(width: 8),
            Text(
              _isExportingCsv ? 'Exporting…' : 'Export CSV',
              style: GoogleFonts.inter(
                fontSize: 15,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.1,
                color: _homeTextPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _exportEarningsCsv() async {
    setState(() => _isExportingCsv = true);
    try {
      await _earningsService.exportCsv();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('CSV exported successfully'),
            backgroundColor: Colors.green,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Export failed: ${e.toString()}'),
            backgroundColor: AppColors.error,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isExportingCsv = false);
    }
  }

  // ═════════════════════════════════════════════════════════
  //  TAB 4 — PROFILE
  // ═════════════════════════════════════════════════════════
  Widget _buildProfileTab() {
    final averageRating =
        (_homeAvgRating ?? _driverStats?.rating ?? 0).clamp(0, 5);
    return Stack(
      children: [
        _buildDriverHomeBackground(),
        SafeArea(
          child: HomeDesignSystem.contentWidth(
            child: _desktopRefreshScrollable(
              ListView(
                physics: const AlwaysScrollableScrollPhysics(
                  parent: BouncingScrollPhysics(),
                ),
                padding: const EdgeInsets.fromLTRB(14, 10, 14, 30),
                children: [
                  HomeDesignSystem.frostLayer(
                    blur: 10,
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.fromLTRB(16, 10, 10, 10),
                      decoration: _driverHomeGlass(
                        radius: 20,
                        elevated: false,
                        borderAlpha: 0.32,
                        borderWidth: 1.05,
                      ),
                      child: Row(
                        children: [
                          Container(
                            width: 30,
                            height: 30,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: const Color(0xFF1ED760)
                                  .withValues(alpha: 0.18),
                              border: Border.all(
                                color: const Color(0xFF22E082)
                                    .withValues(alpha: 0.8),
                                width: 1.2,
                              ),
                            ),
                            child: const Icon(
                              Icons.person_rounded,
                              size: 16,
                              color: Color(0xFF0B3D24),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Text(
                            'Driver Profile',
                            style: GoogleFonts.inter(
                              fontSize: 22,
                              fontWeight: FontWeight.w900,
                              letterSpacing: 0.2,
                              color: _homeTextPrimary,
                            ),
                          ),
                          const Spacer(),
                          Material(
                            color: Colors.transparent,
                            child: InkWell(
                              onTap: () => Navigator.pushNamed(
                                context,
                                '/profile-edit',
                              ),
                              borderRadius: BorderRadius.circular(999),
                              child: Container(
                                width: 34,
                                height: 34,
                                alignment: Alignment.center,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: Colors.white.withValues(alpha: 0.12),
                                  border: Border.all(
                                    color: Colors.white.withValues(alpha: 0.28),
                                  ),
                                ),
                                child: const Icon(
                                  Icons.settings_rounded,
                                  size: 18,
                                  color: Color(0xFF0B3D24),
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(0, 8, 0, 4),
                      child: Column(
                        children: [
                          Stack(
                            clipBehavior: Clip.none,
                          alignment: Alignment.center,
                            children: [
                            Container(
                              width: 116,
                              height: 116,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                boxShadow: [
                                  BoxShadow(
                                    color: const Color(0xFF1ED760)
                                        .withValues(alpha: 0.55),
                                    blurRadius: 28,
                                    spreadRadius: 1,
                                  ),
                                  BoxShadow(
                                    color: const Color(0xFF1ED760)
                                        .withValues(alpha: 0.22),
                                    blurRadius: 48,
                                    spreadRadius: 6,
                                  ),
                                ],
                              ),
                              child: Container(
                                padding: const EdgeInsets.all(4),
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                    color: const Color(0xFF22E082),
                                    width: 2.4,
                                  ),
                                ),
                                child: _buildProfileAvatar(
                                  radius: 50,
                                  fontSize: 34,
                                fallbackInitials: _user?.initials ?? 'D',
                                ),
                              ),
                              ),
                              Positioned(
                              right: 0,
                              bottom: 2,
                                child: Material(
                                  color: Colors.transparent,
                                  child: InkWell(
                                    onTap: _handleDriverProfilePhotoAction,
                                    borderRadius: BorderRadius.circular(16),
                                    child: Container(
                                      width: 30,
                                      height: 30,
                                      decoration: BoxDecoration(
                                      color: const Color(0xFF22C56D),
                                        shape: BoxShape.circle,
                                        border: Border.all(
                                        color:
                                            Colors.white.withValues(alpha: 0.9),
                                          width: 1.4,
                                        ),
                                      ),
                                      child: const Icon(
                                        Icons.camera_alt_rounded,
                                        color: Colors.white,
                                        size: 16,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        const SizedBox(height: 16),
                          Text(
                            _user?.fullName ?? 'Driver',
                          style: GoogleFonts.inter(
                            fontSize: 36,
                            height: 1.02,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 0.1,
                              color: _homeTextPrimary,
                            ),
                          textAlign: TextAlign.center,
                          ),
                          if ((_user?.email ?? '').isNotEmpty) ...[
                          const SizedBox(height: 8),
                            Text(
                              _user!.email,
                            style: GoogleFonts.inter(
                              fontSize: 14,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 0.2,
                              color: _homeTextSecondary,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                  Row(
                    children: [
                      Expanded(
                        child: _buildProfileStatCard(
                          label: 'RATING',
                          value: '${averageRating.toStringAsFixed(1)} ★',
                          icon: Icons.star_rounded,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _buildProfileStatCard(
                          label: 'TRIPS',
                          value: _formatWholeNumberWithCommas(
                              _driverHomeTotalRides),
                          icon: Icons.route_rounded,
                        ),
                      ),
                    ],
                  ),
                  _profileSectionHeader('MY VEHICLES'),
                  _buildVehicleSection(),
                  _profileSectionHeader('SETTINGS & ACCOUNT'),
                  _profileMenuItem(Icons.person, 'Personal Info', () async {
                    await Navigator.pushNamed(context, '/profile-edit');
                    if (mounted) {
                      await _loadDashboardData(
                        loadRelatedTabs: false,
                        showLoader: false,
                      );
                    }
                  }),
                  _profileMenuItem(
                    Icons.security,
                    'Verification Status',
                    _openVerificationAndRefresh,
                    trailing: Container(
                                  padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 3,
                                  ),
                                  decoration: BoxDecoration(
                                    color: (_isDriverVerifiedForRide
                                ? const Color(0xFF1ED760)
                                : Colors.orangeAccent)
                            .withValues(alpha: 0.2),
                                    borderRadius: BorderRadius.circular(999),
                                    border: Border.all(
                                      color: (_isDriverVerifiedForRide
                                  ? const Color(0xFF1ED760)
                                  : Colors.orangeAccent)
                              .withValues(alpha: 0.55),
                                    ),
                                  ),
                                  child: Text(
                        _isDriverVerifiedForRide ? 'VERIFIED' : 'UNVERIFIED',
                                    style: GoogleFonts.inter(
                          fontSize: 11,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 1.2,
                          color: _isDriverVerifiedForRide
                              ? const Color(0xFF0B6B39)
                              : const Color(0xFF7A4400),
                                    ),
                                  ),
                                ),
                  ),
                  _profileMenuItem(Icons.account_balance_wallet_rounded,
                      'Wallet', () => _openWalletAndRefresh()),
                  _profileMenuItem(Icons.notifications_outlined,
                      'Notifications', _openNotificationsAndRefresh),
                  _profileMenuItem(Icons.history_rounded, 'Ride History', () {
                    setState(() => _selectedNavIndex = 3);
                    _loadRides();
                  }),
                  _profileMenuItem(Icons.star_rounded, 'Ratings & Reviews',
                      () => Navigator.pushNamed(context, '/ratings-reviews')),
                  _profileMenuItem(Icons.sos_rounded, 'Emergency & Safety',
                      () => Navigator.pushNamed(context, '/sos')),
                  _profileSectionHeader('PREFERENCES'),
                  _profileSwitchTile(
                    icon: Icons.notifications_rounded,
                    title: 'Push Notifications',
                    subtitle: 'Ride updates, messages & alerts',
                    value: _notificationsEnabled,
                    onChanged: _updatePushNotificationsPreference,
                  ),
                  _profileSwitchTile(
                    icon: Icons.location_on_rounded,
                    title: 'Share Location',
                    subtitle:
                        'Allow ride partners to see your location during trips',
                    value: _locationSharing,
                    onChanged: _updateShareLocationPreference,
                  ),
                  _profileSectionHeader('Support'),
                  _profileMenuItem(Icons.help_outline_rounded, 'Help & FAQ',
                      () => Navigator.pushNamed(context, '/help-faq')),
                  _profileMenuItem(
                      Icons.description_rounded,
                      'Terms of Service',
                      () => Navigator.pushNamed(context, '/terms-of-service')),
                  _profileMenuItem(Icons.privacy_tip_rounded, 'Privacy Policy',
                      () => Navigator.pushNamed(context, '/privacy-policy')),
                  _profileSectionHeader('About'),
                  HomeDesignSystem.frostLayer(
                    blur: 8,
                    radius: 16,
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 4,
                      ),
                      decoration: _driverHomeGlass(
                        radius: 16,
                        elevated: false,
                        borderAlpha: 0.24,
                      ),
                      child: ListTile(
                        contentPadding: EdgeInsets.zero,
                        leading: Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: AuthDesignTokens.routeBlue
                                .withValues(alpha: 0.2),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Icon(
                            Icons.info_outline_rounded,
                            color:
                                _profileSymbolShade(AuthDesignTokens.routeBlue),
                            size: 22,
                          ),
                        ),
                        title: Text(
                          'App Version',
                          style: GoogleFonts.inter(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.1,
                            color: _homeTextPrimary,
                          ),
                        ),
                        subtitle: Text(
                          'Sylo v1.0.0',
                          style: GoogleFonts.inter(
                            fontSize: 13,
                            fontWeight: FontWeight.w500,
                            color: _homeTextSecondary.withValues(alpha: 0.9),
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 18),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 6),
                    child: OutlinedButton(
                      onPressed: _handleLogout,
                      style: OutlinedButton.styleFrom(
                        minimumSize: const Size(double.infinity, 54),
                        side: BorderSide(
                          color: _homeTextPrimary.withValues(alpha: 0.32),
                          width: 1.1,
                        ),
                        foregroundColor: _homeTextPrimary,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(999),
                        ),
                        textStyle: GoogleFonts.inter(
                          fontSize: 15,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 2.6,
                        ),
                      ),
                      child: const Text('SIGN OUT'),
                    ),
                  ),
                  const SizedBox(height: 6),
                  Center(
                    child: TextButton(
                      onPressed: _deleteAccount,
                      child: Text(
                        'Delete Account',
                        style: GoogleFonts.inter(
                          color: _homeTextSecondary.withValues(alpha: 0.85),
                          fontSize: 13.5,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildProfileStatCard({
    required String label,
    required String value,
    required IconData icon,
  }) {
    return HomeDesignSystem.frostLayer(
      blur: 8,
      radius: 18,
      child: Container(
        height: 104,
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
        decoration: _driverHomeGlass(
          radius: 18,
          elevated: false,
          borderAlpha: 0.28,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              children: [
                Text(
                  label,
                  style: GoogleFonts.inter(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 2.0,
                    color: _homeTextSecondary,
                  ),
                ),
                const Spacer(),
                Icon(
                  icon,
                  size: 18,
                  color: _profileSymbolShade(const Color(0xFF1ED760)),
                ),
              ],
            ),
            Text(
              value,
              style: GoogleFonts.inter(
                color: _homeTextPrimary,
                fontSize: 34,
                height: 1,
                fontWeight: FontWeight.w900,
                letterSpacing: 0.1,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildVehicleSection() {
    return HomeDesignSystem.frostLayer(
      blur: 10,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
        decoration: _driverHomeGlass(
          radius: 22,
          borderAlpha: 0.3,
          borderWidth: 1.05,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.directions_car_rounded,
                    color: _profileSymbolShade(AuthDesignTokens.routeBlue),
                    size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'My Vehicles',
                    style: GoogleFonts.inter(
                      color: _homeTextPrimary,
                      fontSize: 20,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 0.2,
                    ),
                  ),
                ),
                TextButton.icon(
                  onPressed: _handleAddVehicleAction,
                  icon: Icon(
                    Icons.add_rounded,
                    size: 20,
                    color: _profileSymbolShade(AuthDesignTokens.routeBlue),
                  ),
                  label: const Text('Add'),
                  style: TextButton.styleFrom(
                    foregroundColor: _homeTextPrimary,
                    textStyle: GoogleFonts.inter(
                      fontWeight: FontWeight.w800,
                      fontSize: 14,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (_vehicles.isEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(16),
                decoration: _driverHomeGlass(
                  radius: 16,
                  elevated: false,
                  borderAlpha: 0.24,
                ),
                child: Text(
                  'No vehicles added yet',
                  style: HomeDesignSystem.cardBody(
                    color: Colors.white.withValues(alpha: 0.84),
                  ),
                ),
              )
            else
              ..._vehicles.map((v) => _buildVehicleCard(v)),
          ],
        ),
      ),
    );
  }

  Widget _buildVehicleCard(Vehicle vehicle) {
    return Dismissible(
      key: ValueKey('vehicle-${vehicle.id}'),
      direction: DismissDirection.horizontal,
      background: _buildVehicleSwipeBackground(
        color: AppColors.primary,
        icon: Icons.edit_rounded,
        label: 'Edit',
        alignment: MainAxisAlignment.start,
      ),
      secondaryBackground: _buildVehicleSwipeBackground(
        color: AppColors.error,
        icon: Icons.delete_outline_rounded,
        label: 'Delete',
        alignment: MainAxisAlignment.end,
      ),
      confirmDismiss: (direction) async {
        if (direction == DismissDirection.startToEnd) {
          _showEditVehicleDialog(vehicle);
          return false;
        }
        await _confirmDeleteVehicle(vehicle);
        return false;
      },
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: () => _showVehicleActionsMenu(vehicle),
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.all(14),
          decoration: _driverHomeGlass(
            radius: 16,
            elevated: false,
            borderAlpha: 0.24,
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AuthDesignTokens.routeBlue.withValues(alpha: 0.18),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(Icons.directions_car_rounded,
                    color: _profileSymbolShade(AuthDesignTokens.routeBlue),
                    size: 24),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      vehicle.displayName,
                      style: GoogleFonts.inter(
                        color: _homeTextPrimary,
                        fontWeight: FontWeight.w800,
                        fontSize: 16,
                        letterSpacing: 0.1,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      vehicle.plateNumber,
                      style: GoogleFonts.inter(
                        color: _homeTextSecondary,
                        fontWeight: FontWeight.w600,
                        fontSize: 13,
                      ),
                    ),
                    Text(
                      '${vehicle.seatsAvailable}/${vehicle.seatsTotal} seats',
                      style: GoogleFonts.inter(
                        color: _homeTextSecondary.withValues(alpha: 0.88),
                        fontWeight: FontWeight.w500,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(Icons.more_horiz_rounded,
                  size: 20, color: _homeTextSecondary.withValues(alpha: 0.72)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildVehicleSwipeBackground({
    required Color color,
    required IconData icon,
    required String label,
    required MainAxisAlignment alignment,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.28)),
      ),
      child: Row(
        mainAxisAlignment: alignment,
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(width: 8),
          Text(label,
              style: TextStyle(
                  color: color, fontWeight: FontWeight.w600, fontSize: 13)),
        ],
      ),
    );
  }

  Future<void> _showVehicleActionsMenu(Vehicle vehicle) async {
    if (!mounted) return;

    await showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Container(
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        ),
        child: SafeArea(
          top: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(height: 10),
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.border,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(height: 12),
              ListTile(
                leading:
                    const Icon(Icons.more_horiz_rounded, color: AppColors.info),
                title: Text(vehicle.displayName,
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                subtitle: Text(vehicle.plateNumber),
              ),
              ListTile(
                leading:
                    const Icon(Icons.edit_rounded, color: AppColors.primary),
                title: const Text('Edit Vehicle'),
                onTap: () {
                  Navigator.pop(ctx);
                  _showEditVehicleDialog(vehicle);
                },
              ),
              ListTile(
                leading: const Icon(Icons.delete_outline_rounded,
                    color: AppColors.error),
                title: const Text('Delete Vehicle'),
                onTap: () async {
                  Navigator.pop(ctx);
                  await _confirmDeleteVehicle(vehicle);
                },
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }

  void _showEditVehicleDialog(Vehicle vehicle) {
    final makeCtrl = TextEditingController(text: vehicle.make);
    final modelCtrl = TextEditingController(text: vehicle.model);
    final plateCtrl = TextEditingController(text: vehicle.plateNumber);
    final seatsTotalCtrl = TextEditingController(text: '${vehicle.seatsTotal}');
    final seatsAvailCtrl =
        TextEditingController(text: '${vehicle.seatsAvailable}');

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Container(
        padding: EdgeInsets.only(
          top: 20,
          left: 20,
          right: 20,
          bottom: MediaQuery.of(ctx).viewInsets.bottom + 20,
        ),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: AppColors.border,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              const Text('Edit Vehicle',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
              const SizedBox(height: 20),
              Row(
                children: [
                  Expanded(
                    child: _dialogField(makeCtrl, 'Make', Icons.directions_car),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child:
                        _dialogField(modelCtrl, 'Model', Icons.directions_car),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              _dialogField(plateCtrl, 'Plate Number', Icons.badge),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: _dialogField(
                        seatsTotalCtrl, 'Total Seats', Icons.event_seat,
                        keyboard: TextInputType.number),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _dialogField(
                        seatsAvailCtrl, 'Available Seats', Icons.event_seat,
                        keyboard: TextInputType.number),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () async {
                    final make = makeCtrl.text.trim();
                    final model = modelCtrl.text.trim();
                    final plate = plateCtrl.text.trim();
                    final seatsTotal = int.tryParse(seatsTotalCtrl.text.trim());
                    final seatsAvailable =
                        int.tryParse(seatsAvailCtrl.text.trim());

                    if (make.isEmpty || model.isEmpty || plate.isEmpty) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                            content: Text('Please fill all required fields')),
                      );
                      return;
                    }

                    if (seatsTotal == null || seatsAvailable == null) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                            content: Text('Please enter valid seat counts')),
                      );
                      return;
                    }

                    if (seatsAvailable > seatsTotal) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                            content: Text(
                                'Available seats cannot exceed total seats')),
                      );
                      return;
                    }

                    Navigator.pop(ctx);

                    try {
                      await _driverService.updateVehicle(
                        vehicle.id,
                        make: make,
                        model: model,
                        plateNumber: plate,
                        seatsTotal: seatsTotal,
                        seatsAvailable: seatsAvailable,
                      );
                      await _loadDashboardData();
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Vehicle updated!')),
                        );
                      }
                    } catch (e) {
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                              content: Text(_friendlyUpdateVehicleError(e))),
                        );
                      }
                    }
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primary,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                  ),
                  child: const Text('Save Changes',
                      style:
                          TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _confirmDeleteVehicle(Vehicle vehicle) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Vehicle'),
        content: Text(
            'Delete ${vehicle.displayName} (${vehicle.plateNumber}) from your profile?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child:
                const Text('Delete', style: TextStyle(color: AppColors.error)),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    try {
      await _driverService.deleteVehicle(vehicle.id);
      await _loadDashboardData();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Vehicle deleted!')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(_friendlyDeleteVehicleError(e))),
        );
      }
    }
  }

  Widget _profileMenuItem(IconData icon, String label, VoidCallback onTap,
      {Color? color, Widget? trailing}) {
    final effectiveColor = color ?? AuthDesignTokens.routeBlue;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: HomeDesignSystem.frostLayer(
        blur: 8,
        radius: 16,
        child: Container(
          decoration: _driverHomeGlass(
            radius: 16,
            elevated: false,
            borderAlpha: 0.24,
          ),
          child: Material(
            color: Colors.transparent,
            child: InkWell(
            onTap: onTap,
              borderRadius: BorderRadius.circular(16),
              child: Container(
                height: 58,
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                child: Row(
                  children: [
                    Container(
                      width: 34,
                      height: 34,
                      alignment: Alignment.center,
              decoration: BoxDecoration(
                        color: effectiveColor.withValues(alpha: 0.14),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(
                icon,
                color: _profileSymbolShade(effectiveColor),
                        size: 18,
              ),
            ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Text(
              label,
              style: GoogleFonts.inter(
                          fontWeight: FontWeight.w700,
                          fontSize: 16,
                          letterSpacing: 0.1,
                          color:
                              color == null ? _homeTextPrimary : effectiveColor,
                        ),
                      ),
                    ),
                    if (trailing != null) ...[
                      trailing,
                      const SizedBox(width: 8),
                    ],
                    Icon(
              Icons.chevron_right_rounded,
              color: color == null
                          ? _homeTextSecondary.withValues(alpha: 0.7)
                  : effectiveColor,
                      size: 20,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _profileSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 22, 4, 12),
      child: Align(
        alignment: Alignment.centerLeft,
        child: Text(
          title,
          style: GoogleFonts.inter(
            fontSize: 13,
            fontWeight: FontWeight.w800,
            letterSpacing: 2.2,
            color: _homeTextSecondary,
          ),
        ),
      ),
    );
  }

  Widget _profileSwitchTile({
    required IconData icon,
    required String title,
    required String subtitle,
    required bool value,
    required ValueChanged<bool> onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: HomeDesignSystem.frostLayer(
        blur: 8,
        radius: 16,
        child: Container(
          decoration: _driverHomeGlass(
            radius: 16,
            elevated: false,
            borderAlpha: 0.24,
          ),
          child: SwitchListTile(
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
            secondary: Container(
              width: 34,
              height: 34,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: AuthDesignTokens.routeBlue.withValues(alpha: 0.14),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(
                icon,
                color: _profileSymbolShade(AuthDesignTokens.routeBlue),
                size: 18,
              ),
            ),
            title: Text(
              title,
              style: GoogleFonts.inter(
                fontWeight: FontWeight.w700,
                fontSize: 16,
                letterSpacing: 0.1,
                color: _homeTextPrimary,
              ),
            ),
            subtitle: Text(
              subtitle,
              style: GoogleFonts.inter(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: _homeTextSecondary.withValues(alpha: 0.9),
                height: 1.3,
              ),
            ),
            value: value,
            activeColor: AuthDesignTokens.brandAction,
            inactiveThumbColor: _homeTextPrimary.withValues(alpha: 0.88),
            inactiveTrackColor: _homeTextSecondary.withValues(alpha: 0.26),
            onChanged: onChanged,
          ),
        ),
      ),
    );
  }

  // ═════════════════════════════════════════════════════════
  //  DIALOGS
  // ═════════════════════════════════════════════════════════

  void _showRegisterDriverDialog() {
    final licenseCtrl = TextEditingController();
    final cnicCtrl = TextEditingController();
    final addressCtrl = TextEditingController();

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Container(
        padding: EdgeInsets.only(
          top: 20,
          left: 20,
          right: 20,
          bottom: MediaQuery.of(ctx).viewInsets.bottom + 20,
        ),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: AppColors.border,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              const Text('Complete Driver Profile',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
              const SizedBox(height: 12),
              _dialogField(licenseCtrl, 'License Number', Icons.badge_outlined),
              const SizedBox(height: 12),
              _dialogField(
                  cnicCtrl, 'CNIC (12345-1234567-1)', Icons.credit_card,
                  keyboard: TextInputType.text),
              const SizedBox(height: 12),
              _dialogField(addressCtrl, 'Address (optional)', Icons.location_on,
                  keyboard: TextInputType.streetAddress),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () async {
                    final cnicPattern = RegExp(r'^\d{5}-\d{7}-\d{1}$');
                    if (licenseCtrl.text.trim().isEmpty ||
                        cnicCtrl.text.trim().isEmpty) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                            content:
                                Text('License and CNIC are required fields')),
                      );
                      return;
                    }
                    if (!cnicPattern.hasMatch(cnicCtrl.text.trim())) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                            content:
                                Text('CNIC must be in 12345-1234567-1 format')),
                      );
                      return;
                    }

                    Navigator.pop(ctx);

                    try {
                      await _driverService.register(
                        licenseNumber: licenseCtrl.text.trim(),
                        cnicNumber: cnicCtrl.text.trim(),
                        address: addressCtrl.text.trim().isEmpty
                            ? null
                            : addressCtrl.text.trim(),
                      );

                      // Keep generic profile docs in sync with driver onboarding docs.
                      try {
                        await _userService.updateProfile(
                          cnic: cnicCtrl.text.trim(),
                          drivingLicense: licenseCtrl.text.trim(),
                        );
                      } catch (_) {}

                      await _loadDashboardData();
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                              content:
                                  Text('Driver profile created successfully')),
                        );
                      }
                    } catch (e) {
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                              content: Text(_friendlyDriverRegisterError(e))),
                        );
                      }
                    }
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primary,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14)),
                  ),
                  child: const Text('Save Driver Profile',
                      style:
                          TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showCreateRideDialog({
    PickedLocation? initialOrigin,
    PickedLocation? initialDestination,
  }) {
    final priceCtrl = TextEditingController();
    final seatsCtrl = TextEditingController(text: '3');
    DateTime selectedDate = DateTime.now().add(const Duration(hours: 1));
    String? selectedVehicleId =
        _vehicles.isNotEmpty ? _vehicles.first.id : null;

    // Map-picked locations
    PickedLocation? pickedOrigin = initialOrigin;
    PickedLocation? pickedDestination = initialDestination;
    DirectionsRoute? selectedRoute;
    bool routeLoading = false;
    int routeRequestVersion = 0;
    Map<String, dynamic>? fareEstimate;
    bool fareLoading = false;
    bool showOriginError = false;
    bool showDestinationError = false;
    bool showFareError = false;
    bool showVehicleError = false;
    bool showSeatsError = false;
    String? seatsErrorText;
    bool showSlotConflictError = false;
    bool didTriggerInitialRoute = false;
    bool didTriggerInitialSlots = false;
    bool loadingOccupiedSlots = false;
    List<Map<String, dynamic>> occupiedSlots = [];
    int slotsRequestVersion = 0;

    final mapsService = MapsService();

    String dateKeyUtc(DateTime dt) {
      final utc = dt.toUtc();
      final m = utc.month.toString().padLeft(2, '0');
      final d = utc.day.toString().padLeft(2, '0');
      return '${utc.year}-$m-$d';
    }

    String dateKeyLocal(DateTime dt) {
      final m = dt.month.toString().padLeft(2, '0');
      final d = dt.day.toString().padLeft(2, '0');
      return '${dt.year}-$m-$d';
    }

    List<Map<String, dynamic>> mergeSlotsByWindow(
      List<Map<String, dynamic>> first,
      List<Map<String, dynamic>> second,
    ) {
      final merged = <Map<String, dynamic>>[];
      final seen = <String>{};
      for (final slot in [...first, ...second]) {
        final key =
            '${slot['source'] ?? ''}|${slot['entity_id'] ?? ''}|${slot['start_time'] ?? ''}|${slot['end_time'] ?? ''}';
        if (seen.add(key)) {
          merged.add(slot);
        }
      }
      return merged;
    }

    List<Map<String, dynamic>> slotsForSelectedLocalDay(
      List<Map<String, dynamic>> slots,
    ) {
      final dayStartLocal =
          DateTime(selectedDate.year, selectedDate.month, selectedDate.day);
      final dayEndLocal = dayStartLocal.add(const Duration(days: 1));

      return slots.where((slot) {
        final startRaw = slot['start_time']?.toString();
        final endRaw = slot['end_time']?.toString();
        final slotStartUtc =
            startRaw != null ? DateTime.tryParse(startRaw) : null;
        final slotEndUtc = endRaw != null ? DateTime.tryParse(endRaw) : null;
        if (slotStartUtc == null || slotEndUtc == null) return false;

        final slotStartLocal = slotStartUtc.toLocal();
        final slotEndLocal = slotEndUtc.toLocal();
        return slotStartLocal.isBefore(dayEndLocal) &&
            slotEndLocal.isAfter(dayStartLocal);
      }).toList();
    }

    int selectedDurationMinutes() {
      final routeMinutes = selectedRoute?.durationMinutes.round();
      if (routeMinutes != null && routeMinutes > 0) {
        return routeMinutes;
      }
      return 45;
    }

    bool slotConflictsWithSelection(Map<String, dynamic> slot) {
      final startRaw = slot['start_time']?.toString();
      final endRaw = slot['end_time']?.toString();
      final slotStart = startRaw != null ? DateTime.tryParse(startRaw) : null;
      final slotEnd = endRaw != null ? DateTime.tryParse(endRaw) : null;
      if (slotStart == null || slotEnd == null) return false;

      final selectedStartUtc = selectedDate.toUtc();
      final selectedEndUtc =
          selectedStartUtc.add(Duration(minutes: selectedDurationMinutes()));
      return selectedStartUtc.isBefore(slotEnd) &&
          selectedEndUtc.isAfter(slotStart);
    }

    String formatSlotTime(DateTime dt) {
      final local = dt.toLocal();
      final h = local.hour;
      final m = local.minute.toString().padLeft(2, '0');
      final period = h >= 12 ? 'PM' : 'AM';
      final h12 = h > 12 ? h - 12 : (h == 0 ? 12 : h);
      return '$h12:$m $period';
    }

    Vehicle? selectedVehicle() {
      final id = selectedVehicleId;
      if (id == null) return null;
      for (final vehicle in _vehicles) {
        if (vehicle.id == id) return vehicle;
      }
      return null;
    }

    String? validateSeatsField() {
      final seats = int.tryParse(seatsCtrl.text.trim());
      if (seats == null) return 'Enter a valid seat count.';
      if (seats < 1 || seats > 8) return 'Seats must be between 1 and 8.';

      final vehicle = selectedVehicle();
      if (vehicle != null && seats > vehicle.seatsAvailable) {
        return 'Seats cannot exceed vehicle capacity (${vehicle.seatsAvailable}).';
      }
      return null;
    }

    bool applySeatsValidation(StateSetter setSheetState) {
      final error = validateSeatsField();
      setSheetState(() {
        showSeatsError = error != null;
        seatsErrorText = error;
      });
      return error == null;
    }

    Future<List<Map<String, dynamic>>>
        fallbackDriverSlotsForSelectedDate() async {
      final dayStartLocal =
          DateTime(selectedDate.year, selectedDate.month, selectedDate.day);
      final dayEndLocal = dayStartLocal.add(const Duration(days: 1));
      final dayStartUtc = dayStartLocal.toUtc();
      final dayEndUtc = dayEndLocal.toUtc();

      final rides = await _rideService.getMyDriverRides();
      final slots = <Map<String, dynamic>>[];

      for (final ride in rides) {
        final status = ride.status.toLowerCase();
        if (status != 'open' && status != 'in_progress') continue;

        final departure = ride.departureDatetime;
        if (departure == null) continue;

        final startUtc = departure.toUtc();
        final durationMinutes =
            (ride.estimatedDuration != null && ride.estimatedDuration! > 0)
                ? ride.estimatedDuration!
                : 45;
        final endUtc = startUtc.add(Duration(minutes: durationMinutes));

        if (startUtc.isBefore(dayEndUtc) && endUtc.isAfter(dayStartUtc)) {
          slots.add({
            'source': 'ride',
            'entity_id': ride.id,
            'status': ride.status,
            'start_time': startUtc.toIso8601String(),
            'end_time': endUtc.toIso8601String(),
          });
        }
      }

      return slots;
    }

    Future<void> loadOccupiedSlots(StateSetter setSheetState) async {
      final requestVersion = ++slotsRequestVersion;
      setSheetState(() {
        loadingOccupiedSlots = true;
        showSlotConflictError = false;
      });
      try {
        final localDateKey = dateKeyLocal(selectedDate);
        final utcDateKey = dateKeyUtc(selectedDate);
        final timezoneOffsetMinutes = selectedDate.timeZoneOffset.inMinutes;

        var slots = await _rideService.getMyOccupiedSlots(
          targetDate: localDateKey,
          mode: 'driver',
          timezoneOffsetMinutes: timezoneOffsetMinutes,
        );
        slots = slotsForSelectedLocalDay(slots);

        if (slots.isEmpty && localDateKey != utcDateKey) {
          final utcSlots = await _rideService.getMyOccupiedSlots(
            targetDate: utcDateKey,
            mode: 'driver',
          );
          slots = slotsForSelectedLocalDay(mergeSlotsByWindow(slots, utcSlots));
        }

        if (slots.isEmpty) {
          slots = await fallbackDriverSlotsForSelectedDate();
        }

        if (requestVersion != slotsRequestVersion) return;
        setSheetState(() {
          occupiedSlots = slots;
          loadingOccupiedSlots = false;
        });
      } catch (e) {
        if (requestVersion != slotsRequestVersion) return;

        try {
          final fallbackSlots = await fallbackDriverSlotsForSelectedDate();
          if (requestVersion != slotsRequestVersion) return;
          setSheetState(() {
            occupiedSlots = fallbackSlots;
            loadingOccupiedSlots = false;
          });
        } catch (_) {
          if (requestVersion != slotsRequestVersion) return;
          setSheetState(() {
            occupiedSlots = [];
            loadingOccupiedSlots = false;
          });
        }

        debugPrint('Failed to load occupied slots: $e');
      }
    }

    void clearRouteAndFare(StateSetter setSheetState) {
      routeRequestVersion++;
      setSheetState(() {
        routeLoading = false;
        fareLoading = false;
        selectedRoute = null;
        fareEstimate = null;
        priceCtrl.clear();
        showFareError = false;
      });
    }

    Future<void> recalcFare(StateSetter setSheetState) async {
      if (selectedRoute == null) return;
      final distKm = selectedRoute!.distanceMeters / 1000.0;
      final seats = int.tryParse(seatsCtrl.text) ?? 3;
      setSheetState(() => fareLoading = true);
      try {
        final result = await _rideService.getFareEstimate(
          distanceKm: distKm,
          durationMinutes: selectedRoute!.durationMinutes.toDouble(),
          totalSeats: seats,
        );
        setSheetState(() {
          fareEstimate = result;
          fareLoading = false;
          showFareError = false;
          final perSeat = result['fare_per_seat'];
          if (perSeat != null) {
            priceCtrl.text = (perSeat is double)
                ? perSeat.toStringAsFixed(0)
                : perSeat.toString();
          }
        });
      } catch (e) {
        // Fallback to local calculator if backend fails
        final est = FareCalculator.estimate(
            distanceKm: distKm,
            durationMinutes: selectedRoute!.durationMinutes.toDouble(),
            totalSeats: seats);
        setSheetState(() {
          fareEstimate = {
            'distance_km': est.distanceKm,
            'total_seats': est.totalSeats,
            'fuel_cost_raw': est.fuelCostRaw,
            'time_cost': est.timeCost,
            'duration_minutes': est.durationMinutes,
            'base_fare': est.baseFare,
            'platform_fee': est.platformFee,
            'total_fare': est.totalFare,
            'fare_per_seat': est.farePerSeat,
            'markup_percent': FareCalculator.platformMarkup * 100,
            'summary': est.summary,
          };
          fareLoading = false;
          showFareError = false;
          priceCtrl.text = est.farePerSeat.toStringAsFixed(0);
        });
      }
    }

    Future<void> fetchRoutePreview(StateSetter setSheetState) async {
      if (pickedOrigin == null || pickedDestination == null) {
        clearRouteAndFare(setSheetState);
        return;
      }
      final requestVersion = ++routeRequestVersion;
      setSheetState(() {
        routeLoading = true;
        fareLoading = false;
        selectedRoute = null;
        fareEstimate = null;
        priceCtrl.clear();
        showFareError = false;
      });
      try {
        final result = await mapsService.getDirections(
          origin: pickedOrigin!.latLng,
          destination: pickedDestination!.latLng,
          originPlaceId: pickedOrigin!.placeId,
          destinationPlaceId: pickedDestination!.placeId,
          departureTime: 'now',
        );
        if (requestVersion != routeRequestVersion) {
          return;
        }
        if (result != null && result.routes.isNotEmpty) {
          setSheetState(() => selectedRoute = result.routes.first);
          recalcFare(setSheetState);
        }
      } catch (_) {}
      if (requestVersion == routeRequestVersion) {
        setSheetState(() => routeLoading = false);
      }
    }

    _showDriverScheduleDetails(
      Theme(
        data: Theme.of(context).copyWith(
          textTheme: GoogleFonts.interTextTheme(Theme.of(context).textTheme)
              .apply(
            bodyColor: const Color(0xFF0B3D24),
            displayColor: const Color(0xFF0B3D24),
          ),
          inputDecorationTheme: InputDecorationTheme(
            filled: true,
            fillColor: const Color(0xFFE9FFF2),
            labelStyle: GoogleFonts.inter(
              color: const Color(0xFF114B2D),
              fontWeight: FontWeight.w700,
            ),
            hintStyle: GoogleFonts.inter(
              color: const Color(0xFF114B2D).withValues(alpha: 0.72),
              fontWeight: FontWeight.w600,
            ),
            helperStyle: GoogleFonts.inter(
              color: const Color(0xFF114B2D).withValues(alpha: 0.72),
              fontWeight: FontWeight.w600,
              fontSize: 12,
            ),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(14),
              borderSide: const BorderSide(color: Color(0xFF5DAA7E)),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(14),
              borderSide: const BorderSide(color: Color(0xFF5DAA7E)),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(14),
              borderSide: const BorderSide(color: Color(0xFF1D6F38), width: 1.4),
            ),
          ),
          appBarTheme: Theme.of(context).appBarTheme.copyWith(
                foregroundColor: const Color(0xFF0B3D24),
                titleTextStyle: GoogleFonts.inter(
                  fontSize: 24,
                  fontWeight: FontWeight.w900,
                  color: const Color(0xFF0B3D24),
                ),
              ),
        ),
        child: Scaffold(
        backgroundColor: Colors.transparent,
        appBar: AppBar(
          automaticallyImplyLeading: false,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_rounded),
            onPressed: _returnToDriverScheduleMap,
          ),
          backgroundColor: Colors.transparent,
          surfaceTintColor: Colors.transparent,
          elevation: 0,
          title: const Text('Create Ride'),
        ),
        body: Stack(
          children: [
            HomeDesignSystem.driverHomeSoftWhiteBackground(),
            StatefulBuilder(
          builder: (ctx, setSheetState) {
            if (!didTriggerInitialRoute &&
                pickedOrigin != null &&
                pickedDestination != null) {
              didTriggerInitialRoute = true;
              WidgetsBinding.instance.addPostFrameCallback((_) {
                if (!mounted) return;
                fetchRoutePreview(setSheetState);
              });
            }
            if (!didTriggerInitialSlots) {
              didTriggerInitialSlots = true;
              WidgetsBinding.instance.addPostFrameCallback((_) {
                if (!mounted) return;
                loadOccupiedSlots(setSheetState);
              });
            }
            return Theme(
              data: Theme.of(ctx).copyWith(
                inputDecorationTheme: InputDecorationTheme(
                  filled: true,
                  fillColor: const Color(0xFFE9FFF2),
                  labelStyle: const TextStyle(
                    color: Color(0xFF114B2D),
                    fontWeight: FontWeight.w700,
                  ),
                  hintStyle: TextStyle(
                    color: const Color(0xFF114B2D).withValues(alpha: 0.72),
                    fontWeight: FontWeight.w600,
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(color: Color(0xFF5DAA7E)),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(color: Color(0xFF5DAA7E)),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(14),
                    borderSide: const BorderSide(
                      color: Color(0xFF1D6F38),
                      width: 1.4,
                    ),
                  ),
                ),
              ),
              child: Container(
              padding: EdgeInsets.only(
                top: 20,
                left: 20,
                right: 20,
                bottom: MediaQuery.of(ctx).viewInsets.bottom + 20,
              ),
              constraints: BoxConstraints(
                maxHeight: MediaQuery.of(ctx).size.height * 0.9,
              ),
              decoration: BoxDecoration(
                color: const Color(0xFFD9FCE8),
                borderRadius:
                    const BorderRadius.vertical(top: Radius.circular(24)),
              ),
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const SizedBox(height: 8),
                    // ── Route preview ──
                    if (routeLoading)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 12),
                        child: Center(
                          child: SizedBox(
                            width: 24,
                            height: 24,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: AppColors.primary),
                          ),
                        ),
                      ),
                    if (pickedOrigin != null &&
                        pickedDestination != null &&
                        !routeLoading)
                      RouteMapWidget(
                        origin: pickedOrigin!.latLng,
                        destination: pickedDestination!.latLng,
                        originPlaceId: pickedOrigin!.placeId,
                        destinationPlaceId: pickedDestination!.placeId,
                        originLabel: pickedOrigin!.address,
                        destinationLabel: pickedDestination!.address,
                        height: 300,
                        showAlternatives: true,
                        interactive: true,
                        onRouteSelected: (route) {
                          setSheetState(() => selectedRoute = route);
                          recalcFare(setSheetState);
                        },
                      ),
                    if (pickedOrigin != null &&
                        pickedDestination != null &&
                        !routeLoading)
                      const SizedBox(height: 12),
                    // ── Pickup location ──
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 150),
                      decoration: BoxDecoration(
                        borderRadius:
                            BorderRadius.circular(AppConstants.radiusMedium),
                        border: Border.all(
                          color: showOriginError
                              ? AppColors.error
                              : Colors.transparent,
                          width: showOriginError ? 1.5 : 0,
                        ),
                      ),
                      child: PlaceSearchField(
                        hint: 'Start Point – type to search or tap map',
                        dotColor: AppColors.primary,
                        textColor: const Color(0xFF0B3D24),
                        hintColor: const Color(0xFF114B2D).withValues(alpha: 0.7),
                        mapIconColor: const Color(0xFF0B3D24),
                        backgroundColor: const Color(0xFFE9FFF2),
                        borderColor: const Color(0xFF5DAA7E),
                        value: pickedOrigin,
                        onTextChanged: (value) {
                          final query = value.trim();
                          final currentAddress =
                              pickedOrigin?.address.trim() ?? '';
                          if (query.isEmpty ||
                              (pickedOrigin != null &&
                                  query != currentAddress)) {
                            setSheetState(() {
                              pickedOrigin = null;
                              showOriginError = false;
                            });
                            fetchRoutePreview(setSheetState);
                          }
                        },
                        onPlaceSelected: (place) {
                          setSheetState(() {
                            pickedOrigin = place;
                            showOriginError = false;
                            showFareError = false;
                          });
                          fetchRoutePreview(setSheetState);
                        },
                      ),
                    ),
                    if (showOriginError)
                      const Padding(
                        padding: EdgeInsets.only(left: 12, top: 6),
                        child: Text(
                          'Start point is required',
                          style:
                              TextStyle(color: AppColors.error, fontSize: 12),
                        ),
                      ),
                    const SizedBox(height: 12),
                    // ── Destination ──
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 150),
                      decoration: BoxDecoration(
                        borderRadius:
                            BorderRadius.circular(AppConstants.radiusMedium),
                        border: Border.all(
                          color: showDestinationError
                              ? AppColors.error
                              : Colors.transparent,
                          width: showDestinationError ? 1.5 : 0,
                        ),
                      ),
                      child: PlaceSearchField(
                        hint: 'Destination – type to search or tap map',
                        dotColor: AppColors.error,
                        textColor: const Color(0xFF0B3D24),
                        hintColor: const Color(0xFF114B2D).withValues(alpha: 0.7),
                        mapIconColor: const Color(0xFF0B3D24),
                        backgroundColor: const Color(0xFFE9FFF2),
                        borderColor: const Color(0xFF5DAA7E),
                        value: pickedDestination,
                        onTextChanged: (value) {
                          final query = value.trim();
                          final currentAddress =
                              pickedDestination?.address.trim() ?? '';
                          if (query.isEmpty ||
                              (pickedDestination != null &&
                                  query != currentAddress)) {
                            setSheetState(() {
                              pickedDestination = null;
                              showDestinationError = false;
                            });
                            fetchRoutePreview(setSheetState);
                          }
                        },
                        onPlaceSelected: (place) {
                          setSheetState(() {
                            pickedDestination = place;
                            showDestinationError = false;
                            showFareError = false;
                          });
                          fetchRoutePreview(setSheetState);
                        },
                      ),
                    ),
                    if (showDestinationError)
                      const Padding(
                        padding: EdgeInsets.only(left: 12, top: 6),
                        child: Text(
                          'Destination is required',
                          style:
                              TextStyle(color: AppColors.error, fontSize: 12),
                        ),
                      ),
                    const SizedBox(height: 10),
                    // ── Map-pin picker (both locations) ──
                    OutlinedButton.icon(
                      onPressed: () async {
                        final result = await Navigator.push<DualPickResult>(
                          context,
                          MaterialPageRoute(
                            builder: (_) => DualLocationPickerScreen(
                              initialOrigin: pickedOrigin,
                              initialDestination: pickedDestination,
                            ),
                          ),
                        );
                        if (result != null) {
                          setSheetState(() {
                            if (result.origin != null) {
                              pickedOrigin = result.origin;
                              showOriginError = false;
                            }
                            if (result.destination != null) {
                              pickedDestination = result.destination;
                              showDestinationError = false;
                            }
                            showFareError = false;
                          });
                          fetchRoutePreview(setSheetState);
                        }
                      },
                      icon: const Icon(Icons.map_rounded, size: 18),
                      label: const Text('Pick Both on Map'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.primary,
                        side: BorderSide(
                            color: AppColors.primary.withValues(alpha: 0.5)),
                        minimumSize: const Size(double.infinity, 44),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12)),
                      ),
                    ),
                    const SizedBox(height: 12),
                    if (selectedRoute != null && !routeLoading) ...[
                      const SizedBox(height: 10),
                      Builder(builder: (_) {
                        final durationMin =
                            selectedRoute!.durationMinutes.round();
                        final arrival =
                            selectedDate.add(Duration(minutes: durationMin));
                        final h = arrival.hour;
                        final m = arrival.minute.toString().padLeft(2, '0');
                        final period = h >= 12 ? 'PM' : 'AM';
                        final h12 = h > 12 ? h - 12 : (h == 0 ? 12 : h);
                        return Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 16, vertical: 12),
                          decoration: HomeDesignSystem.darkTopBarSurface(
                            radius: 14,
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceAround,
                            children: [
                              _driverRouteChip(
                                Icons.straighten_rounded,
                                AppColors.primary,
                                selectedRoute!.distanceText,
                                'Distance',
                              ),
                              Container(
                                  width: 1,
                                  height: 36,
                                  color: const Color(0xFF5DAA7E)),
                              _driverRouteChip(
                                Icons.timer_rounded,
                                AppColors.secondary,
                                selectedRoute!.durationText,
                                'Average Duration',
                              ),
                              Container(
                                  width: 1,
                                  height: 36,
                                  color: const Color(0xFF5DAA7E)),
                              _driverRouteChip(
                                Icons.access_time_rounded,
                                AppColors.success,
                                '$h12:$m $period',
                                'Arrives',
                              ),
                            ],
                          ),
                        );
                      }),
                    ],
                    const SizedBox(height: 12),
                    // Date picker
                    GestureDetector(
                      onTap: () async {
                        final picked = await showDatePicker(
                          context: ctx,
                          initialDate: selectedDate,
                          firstDate: DateTime.now(),
                          lastDate:
                              DateTime.now().add(const Duration(days: 90)),
                        );
                        if (picked != null) {
                          final time = await showTimePicker(
                            context: ctx,
                            initialTime: TimeOfDay.fromDateTime(selectedDate),
                          );
                          if (time != null) {
                            setSheetState(() {
                              selectedDate = DateTime(picked.year, picked.month,
                                  picked.day, time.hour, time.minute);
                              showSlotConflictError = false;
                            });
                            loadOccupiedSlots(setSheetState);
                          }
                        }
                      },
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 16),
                        decoration: BoxDecoration(
                          color: const Color(0xFFE9FFF2),
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: const Color(0xFF5DAA7E)),
                        ),
                        child: Row(
                          children: [
                            Icon(Icons.schedule,
                                color: AppColors.textHint, size: 20),
                            const SizedBox(width: 12),
                            Text(
                              '${selectedDate.day}/${selectedDate.month}/${selectedDate.year}  ${selectedDate.hour.toString().padLeft(2, '0')}:${selectedDate.minute.toString().padLeft(2, '0')}',
                              style: const TextStyle(fontSize: 15),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFFE9FFF2),
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: const Color(0xFF5DAA7E)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(Icons.event_busy_rounded,
                                  size: 16, color: AppColors.textHint),
                              const SizedBox(width: 8),
                              Text(
                                'Slots Taken',
                                style: TextStyle(
                                  color: AppColors.textPrimary,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 13,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          if (loadingOccupiedSlots)
                            const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          else if (occupiedSlots.isEmpty)
                            Text(
                              'No occupied slots on selected day.',
                              style: TextStyle(
                                color: AppColors.textSecondary,
                                fontSize: 12,
                              ),
                            )
                          else
                            Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: occupiedSlots.map((slot) {
                                final start = DateTime.tryParse(
                                    slot['start_time']?.toString() ?? '');
                                final end = DateTime.tryParse(
                                    slot['end_time']?.toString() ?? '');
                                final isConflict =
                                    slotConflictsWithSelection(slot);
                                final label = (start != null && end != null)
                                    ? '${formatSlotTime(start)} - ${formatSlotTime(end)}'
                                    : 'Occupied';
                                return Container(
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 10, vertical: 6),
                                  decoration: BoxDecoration(
                                    color: isConflict
                                        ? AppColors.error
                                            .withValues(alpha: 0.12)
                                        : const Color(0xFFE9FFF2),
                                    borderRadius: BorderRadius.circular(10),
                                    border: Border.all(
                                      color: isConflict
                                          ? AppColors.error
                                          : const Color(0xFF5DAA7E),
                                    ),
                                  ),
                                  child: Text(
                                    label,
                                    style: TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w600,
                                      color: isConflict
                                          ? AppColors.error
                                          : AppColors.textPrimary,
                                    ),
                                  ),
                                );
                              }).toList(),
                            ),
                        ],
                      ),
                    ),
                    if (showSlotConflictError)
                      const Padding(
                        padding: EdgeInsets.only(left: 12, top: 6),
                        child: Text(
                          'Selected time overlaps with an occupied slot.',
                          style:
                              TextStyle(color: AppColors.error, fontSize: 12),
                        ),
                      ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                            child: TextField(
                          controller: priceCtrl,
                          readOnly: true,
                          decoration: InputDecoration(
                            labelText: 'Price/seat (PKR) - Auto',
                            helperText: 'Calculated from backend fare service',
                            prefixIcon: const Icon(Icons.payments),
                            filled: true,
                            fillColor: const Color(0xFFE9FFF2),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(14),
                              borderSide: const BorderSide(
                                color: Color(0xFF5DAA7E),
                              ),
                            ),
                          ),
                        )),
                        const SizedBox(width: 10),
                        Expanded(
                            child: TextField(
                          controller: seatsCtrl,
                          keyboardType: TextInputType.number,
                          decoration: InputDecoration(
                            labelText: 'Seats',
                            prefixIcon:
                                const Icon(Icons.airline_seat_recline_normal),
                            errorText: showSeatsError
                                ? (seatsErrorText ?? 'Invalid seat count')
                                : null,
                            filled: true,
                            fillColor: const Color(0xFFE9FFF2),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(14),
                              borderSide: const BorderSide(
                                color: Color(0xFF5DAA7E),
                              ),
                            ),
                          ),
                          onChanged: (_) {
                            final isSeatsValid =
                                applySeatsValidation(setSheetState);
                            if (isSeatsValid) {
                              recalcFare(setSheetState);
                            }
                          },
                        )),
                      ],
                    ),
                    if (showFareError)
                      const Padding(
                        padding: EdgeInsets.only(left: 12, top: 6),
                        child: Text(
                          'Route fare is required. Select both points and wait for fare.',
                          style:
                              TextStyle(color: AppColors.error, fontSize: 12),
                        ),
                      ),
                    // Fare breakdown
                    if (fareLoading)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 12),
                        child: Center(
                            child: SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )),
                      ),
                    if (fareEstimate != null && !fareLoading) ...[
                      const SizedBox(height: 10),
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: HomeDesignSystem.darkTopBarSurface(
                          radius: 12,
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Row(
                              children: [
                                Icon(Icons.calculate_outlined,
                                    size: 18, color: AppColors.primary),
                                SizedBox(width: 6),
                                Text('Fare Breakdown (Server)',
                                    style: TextStyle(
                                        fontWeight: FontWeight.w700,
                                        fontSize: 13,
                                        color: AppColors.primary)),
                              ],
                            ),
                            const SizedBox(height: 8),
                            _fareRow('Distance',
                                '${_fmtNum(fareEstimate!['distance_km'], decimals: 1)} km'),
                            _fareRow('Fuel cost',
                                'Rs ${_fmtNum(fareEstimate!['fuel_cost_raw'])}'),
                            _fareRow('Base fare',
                                'Rs ${_fmtNum(fareEstimate!['base_fare'])}'),
                            _fareRow(
                                'Platform fee (${_fmtNum(fareEstimate!['markup_percent'])}%)',
                                'Rs ${_fmtNum(fareEstimate!['platform_fee'])}'),
                            Divider(
                                color: AppColors.primary.withValues(alpha: 0.3),
                                height: 12),
                            _fareRow('Total trip cost',
                                'Rs ${_fmtNum(fareEstimate!['total_fare'])}',
                                bold: true),
                            _fareRow(
                                'Per seat (${fareEstimate!['total_seats']} seats)',
                                'Rs ${_fmtNum(fareEstimate!['fare_per_seat'])}',
                                bold: true,
                                highlight: true),
                          ],
                        ),
                      ),
                    ],
                    const SizedBox(height: 12),
                    // Vehicle dropdown
                    if (_vehicles.isNotEmpty)
                      DropdownButtonFormField<String>(
                        value: selectedVehicleId,
                        decoration: InputDecoration(
                          labelText: 'Vehicle',
                          prefixIcon: const Icon(Icons.directions_car),
                          errorText: showVehicleError
                              ? 'Vehicle selection is required'
                              : null,
                          filled: true,
                          fillColor: const Color(0xFFE9FFF2),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(14),
                            borderSide:
                                const BorderSide(color: Color(0xFF5DAA7E)),
                          ),
                        ),
                        items: _vehicles
                            .map((v) => DropdownMenuItem(
                                  value: v.id,
                                  child: Text(v.shortName),
                                ))
                            .toList(),
                        onChanged: (val) {
                          setSheetState(() {
                            selectedVehicleId = val;
                            if (val != null) {
                              showVehicleError = false;
                            }
                          });
                          final isSeatsValid =
                              applySeatsValidation(setSheetState);
                          if (isSeatsValid) {
                            recalcFare(setSheetState);
                          }
                        },
                      ),
                    const SizedBox(height: 20),
                    Container(
                      width: double.infinity,
                      decoration: HomeDesignSystem.darkTopBarSurface(radius: 14),
                      child: ElevatedButton(
                        onPressed: () async {
                          await _refreshVerificationGateState();
                          if (_driverProfile == null) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                  content: Text(
                                      'Complete driver profile first before creating rides.')),
                            );
                            _showRegisterDriverDialog();
                            return;
                          }
                          if (_vehicles.isEmpty) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                  content: Text(
                                      'Add a vehicle first before creating rides.')),
                            );
                            _showAddVehicleDialog();
                            return;
                          }
                          if (!_isDriverVerifiedForRide) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text(
                                    'Your driver account is not verified yet. Please complete verification first.'),
                              ),
                            );
                            await _openVerificationAndRefresh();
                            return;
                          }

                          if (fareEstimate == null && selectedRoute != null) {
                            await recalcFare(setSheetState);
                          }

                          final farePerSeatRaw = fareEstimate?['fare_per_seat'];
                          final backendFarePerSeat = farePerSeatRaw is num
                              ? farePerSeatRaw.toDouble()
                              : double.tryParse(
                                  farePerSeatRaw?.toString() ?? '');
                          final seatsValidationMessage = validateSeatsField();
                          final hasValidSeats = seatsValidationMessage == null;

                          final hasOrigin = pickedOrigin != null;
                          final hasDestination = pickedDestination != null;
                          final hasFare = backendFarePerSeat != null;
                          final hasVehicle = selectedVehicleId != null;

                          if (!hasOrigin ||
                              !hasDestination ||
                              !hasFare ||
                              !hasVehicle ||
                              !hasValidSeats) {
                            setSheetState(() {
                              showOriginError = !hasOrigin;
                              showDestinationError = !hasDestination;
                              showFareError = !hasFare;
                              showVehicleError = !hasVehicle;
                              showSeatsError = !hasValidSeats;
                              seatsErrorText =
                                  hasValidSeats ? null : seatsValidationMessage;
                            });
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                  content:
                                      Text('Please fix highlighted fields')),
                            );
                            return;
                          }

                          final hasSlotConflict =
                              occupiedSlots.any(slotConflictsWithSelection);
                          if (hasSlotConflict) {
                            setSheetState(() => showSlotConflictError = true);
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text(
                                    'Selected time overlaps with an occupied slot.'),
                                backgroundColor: AppColors.error,
                              ),
                            );
                            return;
                          }

                          final seatsToCreate =
                              int.parse(seatsCtrl.text.trim());

                          try {
                            await _rideService.createRide(
                              origin: pickedOrigin!.address,
                              destination: pickedDestination!.address,
                              originLat: pickedOrigin!.latLng.latitude,
                              originLng: pickedOrigin!.latLng.longitude,
                              destinationLat:
                                  pickedDestination!.latLng.latitude,
                              destinationLng:
                                  pickedDestination!.latLng.longitude,
                              departureTime:
                                  selectedDate.toUtc().toIso8601String(),
                              availableSeats: seatsToCreate,
                              pricePerSeat: backendFarePerSeat,
                              vehicleId: selectedVehicleId!,
                              estimatedDuration:
                                  selectedRoute?.durationMinutes.round(),
                              routeDistanceKm: selectedRoute?.distanceKm,
                              polyline: (selectedRoute?.encodedPolyline ?? '')
                                      .isNotEmpty
                                  ? selectedRoute!.encodedPolyline
                                  : null,
                            );
                            _returnToDriverScheduleMap();
                            await _refreshAllDashboardData(
                              showHomeLoader: false,
                              showEarningsLoader: false,
                            );
                            if (mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('Ride created!')),
                              );
                            }
                          } catch (e) {
                            if (e is DioException &&
                                _isDepartureTimeFutureValidationError(e)) {
                              await _showDepartureTimeFutureDialog(
                                actionLabel: 'create a ride',
                              );
                              return;
                            }

                            if (e is DioException) {
                              final details = extractError(e).toLowerCase();
                              if (details.contains(
                                  'available seats cannot exceed vehicle capacity')) {
                                final capacity =
                                    selectedVehicle()?.seatsAvailable;
                                setSheetState(() {
                                  showSeatsError = true;
                                  seatsErrorText = capacity != null
                                      ? 'Seats cannot exceed vehicle capacity ($capacity).'
                                      : 'Seats cannot exceed selected vehicle capacity.';
                                });
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text(
                                        'Please correct the highlighted seats field.'),
                                    backgroundColor: AppColors.error,
                                  ),
                                );
                                return;
                              }
                            }
                            if (mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                    content: Text(
                                        'Failed: ${e is DioException ? extractError(e) : e}')),
                              );
                            }
                          }
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.transparent,
                          foregroundColor: const Color(0xFF43E892),
                          shadowColor: Colors.transparent,
                          elevation: 0,
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14)),
                        ),
                        child: const Text('Create Ride',
                            style: TextStyle(
                                fontWeight: FontWeight.w700, fontSize: 16)),
                      ),
                    ),
                  ],
                ),
                ),
              ),
            );
          },
        ),
          ],
      ),
      )),
    );
  }

  void _showAddVehicleDialog() {
    if (_driverProfile == null) {
      _showRegisterDriverDialog();
      return;
    }

    final makeCtrl = TextEditingController();
    final modelCtrl = TextEditingController();
    final plateCtrl = TextEditingController();
    final seatsTotalCtrl = TextEditingController(text: '5');
    final seatsAvailCtrl = TextEditingController(text: '4');

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Container(
        padding: EdgeInsets.only(
          top: 14,
          left: 18,
          right: 18,
          bottom: MediaQuery.of(ctx).viewInsets.bottom + 18,
        ),
        decoration: BoxDecoration(
          color: const Color(0xFF06150F),
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
          border: Border.all(
            color: const Color(0xFF43E892).withValues(alpha: 0.16),
          ),
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              Text(
                'Add Vehicle',
                style: GoogleFonts.inter(
                  fontSize: 34,
                  fontWeight: FontWeight.w900,
                  color: Colors.white.withValues(alpha: 0.97),
                ),
              ),
              const SizedBox(height: 4),
              Text(
                'Enter your vehicle details to offer rides.',
                style: GoogleFonts.inter(
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                  color: Colors.white.withValues(alpha: 0.62),
                ),
              ),
              const SizedBox(height: 16),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: _driverBottomSheetLabeledField(
                      label: 'MAKE',
                      controller: makeCtrl,
                      icon: Icons.directions_car_filled_rounded,
                      hintText: 'Make',
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _driverBottomSheetLabeledField(
                      label: 'MODEL',
                      controller: modelCtrl,
                      icon: Icons.directions_car_filled_rounded,
                      hintText: 'Model',
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              _driverBottomSheetLabeledField(
                label: 'PLATE NUMBER',
                controller: plateCtrl,
                icon: Icons.badge_rounded,
                hintText: 'Plate Number',
              ),
              const SizedBox(height: 12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: _driverBottomSheetLabeledField(
                      label: 'TOTAL SEATS',
                      controller: seatsTotalCtrl,
                      icon: Icons.event_seat_rounded,
                      hintText: '5',
                      keyboardType: TextInputType.number,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _driverBottomSheetLabeledField(
                      label: 'AVAILABLE SEATS',
                      controller: seatsAvailCtrl,
                      icon: Icons.event_seat_rounded,
                      hintText: '4',
                      keyboardType: TextInputType.number,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: Container(
                  height: 56,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(999),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF4BF0A1).withValues(alpha: 0.42),
                        blurRadius: 20,
                        spreadRadius: 1.2,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: FilledButton(
                  onPressed: () async {
                    if (makeCtrl.text.isEmpty ||
                        modelCtrl.text.isEmpty ||
                        plateCtrl.text.isEmpty) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                            content: Text('Please fill all required fields')),
                      );
                      return;
                    }

                    Navigator.pop(ctx);

                    try {
                      await _driverService.addVehicle(
                        make: makeCtrl.text.trim(),
                        model: modelCtrl.text.trim(),
                        plateNumber: plateCtrl.text.trim(),
                        seatsTotal: int.tryParse(seatsTotalCtrl.text) ?? 5,
                          seatsAvailable:
                              int.tryParse(seatsAvailCtrl.text) ?? 4,
                      );
                      _loadDashboardData();
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Vehicle added!')),
                        );
                      }
                    } catch (e) {
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                                content: Text(_friendlyAddVehicleError(e))),
                        );
                      }
                    }
                  },
                    style: FilledButton.styleFrom(
                      backgroundColor: const Color(0xFF43E892),
                      foregroundColor: const Color(0xFF052E1E),
                      elevation: 0,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(999),
                      ),
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Container(
                          width: 22,
                          height: 22,
                          decoration: BoxDecoration(
                            color: const Color(0xFF052E1E),
                            borderRadius: BorderRadius.circular(999),
                          ),
                          child: const Icon(
                            Icons.check_rounded,
                            size: 15,
                            color: Color(0xFF43E892),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Text(
                          'ADD VEHICLE',
                          style: GoogleFonts.inter(
                            fontWeight: FontWeight.w800,
                            fontSize: 15,
                            letterSpacing: 1.1,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showPayoutDialog() {
    final amountCtrl = TextEditingController();
    final accountCtrl = TextEditingController();
    final availableBalance = _walletBalance?.balance ?? 0.0;
    String selectedMethod = 'prop_money';

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSheetState) {
          return Container(
            padding: EdgeInsets.only(
              top: 14,
              left: 18,
              right: 18,
              bottom: MediaQuery.of(ctx).viewInsets.bottom + 18,
            ),
            decoration: BoxDecoration(
              color: const Color(0xFF06150F),
              borderRadius:
                  const BorderRadius.vertical(top: Radius.circular(24)),
              border: Border.all(
                color: const Color(0xFF43E892).withValues(alpha: 0.16),
              ),
            ),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Center(
                    child: Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    'Request Payout',
                    style: GoogleFonts.inter(
                      fontSize: 34,
                      fontWeight: FontWeight.w900,
                      color: Colors.white.withValues(alpha: 0.97),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Transfer your earnings to your linked account.',
                    style: GoogleFonts.inter(
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: Colors.white.withValues(alpha: 0.62),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(
                      horizontal: 14,
                      vertical: 12,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.09),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(
                        color: Colors.white.withValues(alpha: 0.12),
                      ),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 42,
                          height: 42,
                          decoration: BoxDecoration(
                            color:
                                const Color(0xFF43E892).withValues(alpha: 0.2),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(
                            Icons.account_balance_wallet_rounded,
                            color: Color(0xFF43E892),
                            size: 22,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                  Text(
                              'AVAILABLE BALANCE',
                              style: GoogleFonts.inter(
                                color: Colors.white.withValues(alpha: 0.62),
                                fontWeight: FontWeight.w700,
                                fontSize: 11,
                                letterSpacing: 0.9,
                              ),
                            ),
                            Text(
                              'PKR ${_walletBalance?.balance.toStringAsFixed(0) ?? '0'}',
                              style: GoogleFonts.inter(
                                color: Colors.white,
                                fontWeight: FontWeight.w900,
                                fontSize: 40,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  Padding(
                    padding: const EdgeInsets.only(bottom: 2),
                    child: Text(
                      'AMOUNT (MIN PKR 500)',
                      style: GoogleFonts.inter(
                        color: Colors.white.withValues(alpha: 0.62),
                        fontWeight: FontWeight.w700,
                        fontSize: 12,
                        letterSpacing: 0.85,
                        height: 1.45,
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: amountCtrl,
                    keyboardType: TextInputType.number,
                    style: GoogleFonts.inter(
                      color: Colors.white.withValues(alpha: 0.95),
                      fontWeight: FontWeight.w700,
                      fontSize: 26,
                    ),
                    decoration: InputDecoration(
                      hintText: 'PKR 500',
                      hintStyle: GoogleFonts.inter(
                        color: Colors.white.withValues(alpha: 0.32),
                        fontWeight: FontWeight.w700,
                        fontSize: 26,
                      ),
                      prefixIcon: Padding(
                        padding: const EdgeInsets.only(left: 12, right: 6),
                        child: Center(
                          widthFactor: 1,
                          child: Text(
                            'PKR',
                            style: GoogleFonts.inter(
                              color: const Color(0xFF43E892),
                              fontWeight: FontWeight.w900,
                              fontSize: 26,
                            ),
                          ),
                        ),
                      ),
                      prefixIconConstraints:
                          const BoxConstraints(minWidth: 68, minHeight: 0),
                      filled: true,
                      fillColor: Colors.white.withValues(alpha: 0.08),
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 18,
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: BorderSide(
                          color: Colors.white.withValues(alpha: 0.12),
                        ),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: BorderSide(
                          color: Colors.white.withValues(alpha: 0.12),
                        ),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(color: Color(0xFF43E892)),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Padding(
                    padding: const EdgeInsets.only(bottom: 2),
                    child: Text(
                      'PAYOUT METHOD',
                      style: GoogleFonts.inter(
                        color: Colors.white.withValues(alpha: 0.62),
                        fontWeight: FontWeight.w700,
                        fontSize: 12,
                        letterSpacing: 0.85,
                        height: 1.45,
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),
                  DropdownButtonFormField<String>(
                    value: selectedMethod,
                    isExpanded: true,
                    itemHeight: 56,
                    alignment: AlignmentDirectional.centerStart,
                    decoration: InputDecoration(
                      prefixIcon: const Padding(
                        padding: EdgeInsets.only(left: 8, right: 4),
                        child: Icon(
                          Icons.account_balance_wallet_rounded,
                          color: Color(0xFF43E892),
                          size: 22,
                        ),
                      ),
                      prefixIconConstraints: const BoxConstraints(
                        minWidth: 44,
                        minHeight: 0,
                      ),
                      filled: true,
                      fillColor: Colors.white.withValues(alpha: 0.08),
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 22,
                      ),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: BorderSide(
                          color: Colors.white.withValues(alpha: 0.12),
                        ),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: BorderSide(
                          color: Colors.white.withValues(alpha: 0.12),
                        ),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(color: Color(0xFF43E892)),
                      ),
                    ),
                    dropdownColor: const Color(0xFF10251B),
                    style: GoogleFonts.inter(
                      color: Colors.white.withValues(alpha: 0.95),
                      fontWeight: FontWeight.w700,
                      fontSize: 18,
                    ),
                    iconEnabledColor: Colors.white.withValues(alpha: 0.74),
                    items: [
                      DropdownMenuItem(
                        value: 'jazzcash',
                        child: Text(
                          'JazzCash',
                          style: GoogleFonts.inter(
                            color: Colors.white.withValues(alpha: 0.95),
                            fontWeight: FontWeight.w700,
                            fontSize: 18,
                          ),
                        ),
                      ),
                      DropdownMenuItem(
                        value: 'easypaisa',
                        child: Text(
                          'Easypaisa',
                          style: GoogleFonts.inter(
                            color: Colors.white.withValues(alpha: 0.95),
                            fontWeight: FontWeight.w700,
                            fontSize: 18,
                          ),
                        ),
                      ),
                      DropdownMenuItem(
                        value: 'bank_transfer',
                        child: Text(
                          'Bank Transfer',
                          style: GoogleFonts.inter(
                            color: Colors.white.withValues(alpha: 0.95),
                            fontWeight: FontWeight.w700,
                            fontSize: 18,
                          ),
                        ),
                      ),
                      DropdownMenuItem(
                        value: 'prop_money',
                        child: Text(
                          'Prop Money',
                          style: GoogleFonts.inter(
                            color: Colors.white.withValues(alpha: 0.95),
                            fontWeight: FontWeight.w700,
                            fontSize: 18,
                          ),
                        ),
                      ),
                    ],
                    onChanged: (val) {
                      setSheetState(() => selectedMethod = val ?? 'prop_money');
                    },
                  ),
                  if (!_isDriverPayoutMethodSupported(selectedMethod)) ...[
                    const SizedBox(height: 8),
                    _buildDriverPayoutComingSoonHint(selectedMethod),
                  ],
                  const SizedBox(height: 12),
                  if (selectedMethod == 'prop_money')
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFF43E892).withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: const Color(0xFF43E892).withValues(alpha: 0.2),
                      ),
                      ),
                      child: Text(
                        'Prop Money is internal and deducts your wallet instantly.',
                        style: GoogleFonts.inter(
                          color: Colors.white.withValues(alpha: 0.82),
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    )
                  else ...[
                    Padding(
                      padding: const EdgeInsets.only(bottom: 2),
                      child: Text(
                        'ACCOUNT NUMBER / IBAN',
                        style: GoogleFonts.inter(
                          color: Colors.white.withValues(alpha: 0.62),
                          fontWeight: FontWeight.w700,
                          fontSize: 12,
                          letterSpacing: 0.85,
                          height: 1.45,
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: accountCtrl,
                      keyboardType: TextInputType.text,
                      style: GoogleFonts.inter(
                        color: Colors.white.withValues(alpha: 0.95),
                        fontWeight: FontWeight.w600,
                        fontSize: 16,
                      ),
                      decoration: InputDecoration(
                        hintText: 'Account Number / IBAN',
                        hintStyle: GoogleFonts.inter(
                          color: Colors.white.withValues(alpha: 0.38),
                          fontWeight: FontWeight.w500,
                          fontSize: 16,
                        ),
                        prefixIcon: const Icon(
                          Icons.credit_card_rounded,
                          color: Color(0xFF43E892),
                        ),
                        filled: true,
                        fillColor: Colors.white.withValues(alpha: 0.08),
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 18,
                        ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide(
                            color: Colors.white.withValues(alpha: 0.12),
                          ),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide(
                            color: Colors.white.withValues(alpha: 0.12),
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide:
                              const BorderSide(color: Color(0xFF43E892)),
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: 20),
                  SizedBox(
                    width: double.infinity,
                    child: Container(
                      height: 56,
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(999),
                        boxShadow: [
                          BoxShadow(
                            color:
                                const Color(0xFF4BF0A1).withValues(alpha: 0.42),
                            blurRadius: 20,
                            spreadRadius: 1.2,
                            offset: const Offset(0, 8),
                          ),
                        ],
                      ),
                      child: FilledButton(
                      onPressed: () async {
                        final amount =
                            double.tryParse(amountCtrl.text.trim()) ?? 0;
                        final accountDetails = accountCtrl.text.trim();

                        if (amount < 500) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                                content:
                                    Text('Amount must be at least PKR 500')),
                          );
                          return;
                        }

                        if (!_isDriverPayoutMethodSupported(selectedMethod)) {
                          _showDriverPayoutComingSoonDialog(
                              ctx, selectedMethod);
                          return;
                        }

                        if (selectedMethod != 'prop_money' &&
                            accountDetails.isEmpty) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                                  content:
                                      Text('Please enter account details')),
                          );
                          return;
                        }

                        if (amount > availableBalance) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                                content: Text(
                                    'Requested amount exceeds available balance (PKR ${availableBalance.toStringAsFixed(0)}).')),
                          );
                          return;
                        }

                        Navigator.pop(ctx);

                        try {
                          if (selectedMethod == 'prop_money') {
                            await _walletService.propPayout(
                              amount: amount,
                                description: 'Prop Money Payout',
                            );
                          } else {
                            await _walletService.requestPayout(
                              amount: amount,
                              method: selectedMethod,
                              accountDetails: accountDetails,
                            );
                          }

                          _loadEarnings();
                          _loadDashboardData();
                          if (mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                  content: Text(selectedMethod == 'prop_money'
                                      ? 'Prop Money payout completed instantly.'
                                      : 'Payout requested!')),
                            );
                          }
                        } catch (e) {
                          if (mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                  content: Text(
                                      'Failed: ${e is DioException ? extractError(e) : e}')),
                            );
                          }
                        }
                      },
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFF43E892),
                          foregroundColor: const Color(0xFF052E1E),
                          elevation: 0,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(999)),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Container(
                              width: 22,
                              height: 22,
                              decoration: BoxDecoration(
                                color: const Color(0xFF052E1E),
                                borderRadius: BorderRadius.circular(999),
                              ),
                              child: const Icon(Icons.check_rounded,
                                  size: 15, color: Color(0xFF43E892)),
                            ),
                            const SizedBox(width: 10),
                            Text(
                              'SUBMIT REQUEST',
                              style: GoogleFonts.inter(
                                fontWeight: FontWeight.w800,
                                fontSize: 15,
                                letterSpacing: 1.1,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  bool _isDriverPayoutMethodSupported(String method) {
    return method == 'prop_money';
  }

  String _driverPayoutMethodDisplayName(String value) {
    switch (value) {
      case 'jazzcash':
        return 'JazzCash';
      case 'easypaisa':
        return 'Easypaisa';
      case 'bank_transfer':
        return 'Bank Transfer';
      case 'prop_money':
        return 'Prop Money';
      default:
        return value.replaceAll('_', ' ');
    }
  }

  String _driverPayoutComingSoonMessage(String value) {
    return '${_driverPayoutMethodDisplayName(value)} integration is coming soon. Please use Prop Money for now.';
  }

  void _showDriverPayoutComingSoonDialog(
      BuildContext sheetContext, String value) {
    showDialog<void>(
      context: sheetContext,
      useRootNavigator: true,
      builder: (dialogCtx) => AlertDialog(
        title: const Text('Feature Coming Soon'),
        content: Text(_driverPayoutComingSoonMessage(value)),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogCtx).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  Widget _buildDriverPayoutComingSoonHint(String value) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF43E892).withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: const Color(0xFF43E892).withValues(alpha: 0.2),
        ),
      ),
            child: Text(
              '${_driverPayoutMethodDisplayName(value)} will be implemented in a future update.',
        style: GoogleFonts.inter(
          color: Colors.white.withValues(alpha: 0.82),
          fontWeight: FontWeight.w600,
            ),
      ),
    );
  }

  /// Format a numeric value from API response (could be int, double, or null).
  String _fmtNum(dynamic val, {int decimals = 0}) {
    if (val == null) return '0';
    final d =
        (val is num) ? val.toDouble() : double.tryParse(val.toString()) ?? 0.0;
    return decimals > 0 ? d.toStringAsFixed(decimals) : d.toStringAsFixed(0);
  }

  /// Small column chip used in the driver route summary bar.
  Widget _driverRouteChip(
      IconData icon, Color color, String value, String label) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(height: 4),
        Text(value,
            style: TextStyle(
                fontWeight: FontWeight.w700,
                fontSize: 13,
                color: Colors.white)),
        Text(label,
            style: TextStyle(
              fontSize: 11,
              color: Colors.white.withValues(alpha: 0.84),
            )),
      ],
    );
  }

  Widget _fareRow(String label, String value,
      {bool bold = false, bool highlight = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label,
              style: TextStyle(
                fontSize: 12,
                color: highlight
                    ? AppColors.primary
                    : Colors.white.withValues(alpha: 0.86),
                fontWeight: bold ? FontWeight.w600 : FontWeight.normal,
              )),
          Text(value,
              style: TextStyle(
                fontSize: 12,
                color: highlight ? AppColors.primary : Colors.white,
                fontWeight: bold ? FontWeight.w700 : FontWeight.w500,
              )),
        ],
      ),
    );
  }

  Widget _dialogField(
      TextEditingController controller, String label, IconData icon,
      {TextInputType? keyboard}) {
    return TextField(
      controller: controller,
      keyboardType: keyboard,
      decoration: InputDecoration(
        labelText: label,
        prefixIcon: Icon(icon, size: 20),
        filled: true,
        fillColor: AppColors.backgroundLight,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: AppColors.border),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 16),
      ),
    );
  }
}

class _EarningsCurvePainter extends CustomPainter {
  final List<double> points;
  final Color strokeColor;
  final Color fillColor;

  _EarningsCurvePainter({
    required this.points,
    required this.strokeColor,
    required this.fillColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (points.length < 2) return;

    final dxStep = size.width / (points.length - 1);
    final chartPoints = List<Offset>.generate(points.length, (index) {
      final x = index * dxStep;
      final y = size.height - (points[index].clamp(0.0, 1.0) * size.height);
      return Offset(x, y);
    });

    final linePath = Path()..moveTo(chartPoints.first.dx, chartPoints.first.dy);
    for (int i = 0; i < chartPoints.length - 1; i++) {
      final p0 = chartPoints[i];
      final p1 = chartPoints[i + 1];
      final c1 = Offset(p0.dx + (dxStep * 0.5), p0.dy);
      final c2 = Offset(p1.dx - (dxStep * 0.5), p1.dy);
      linePath.cubicTo(c1.dx, c1.dy, c2.dx, c2.dy, p1.dx, p1.dy);
    }

    final fillPath = Path.from(linePath)
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();

    final fillPaint = Paint()
      ..style = PaintingStyle.fill
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [
          fillColor.withValues(alpha: 0.5),
          fillColor.withValues(alpha: 0.04),
        ],
      ).createShader(Offset.zero & size);

    final glowPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 8
      ..strokeCap = StrokeCap.round
      ..color = strokeColor.withValues(alpha: 0.24)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8);

    final linePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round
      ..color = strokeColor;

    canvas.drawPath(fillPath, fillPaint);
    canvas.drawPath(linePath, glowPaint);
    canvas.drawPath(linePath, linePaint);
  }

  @override
  bool shouldRepaint(covariant _EarningsCurvePainter oldDelegate) {
    return oldDelegate.points != points ||
        oldDelegate.strokeColor != strokeColor ||
        oldDelegate.fillColor != fillColor;
  }
}
