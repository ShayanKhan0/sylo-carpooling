import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:geolocator/geolocator.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';
import 'package:pointer_interceptor/pointer_interceptor.dart';
import '../../core/theme/app_colors.dart';
import '../../core/constants/app_constants.dart';
import '../../core/services/auth_service.dart';
import '../../core/services/firebase_auth_service.dart';
import '../../core/services/user_service.dart';
import '../../core/services/ride_service.dart';
import '../../core/services/wallet_service.dart';
import '../../core/services/chat_sync_service.dart';
import '../../core/services/notification_service.dart';
import '../../core/services/notification_sync_service.dart';
import '../../core/services/api_client.dart';
import '../../core/services/schedule_service.dart';
import '../../core/services/maps_service.dart';
import '../../core/services/verification_service.dart';
import '../../core/utils/fare_calculator.dart';
import '../../core/utils/carbon_footprint.dart';
import '../../core/utils/live_location_marker_icon.dart';
import '../../core/models/user_model.dart';
import '../../core/models/ride_model.dart';
import '../../core/models/wallet_model.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import '../auth/auth_design_tokens.dart';
import '../shared/widgets.dart';
import '../maps/location_picker_screen.dart';
import '../maps/route_map_widget.dart';
import '../maps/place_search_field.dart';
import '../maps/dual_location_picker_screen.dart';
import 'home_design_system.dart';
import '../matching/cluster_status_widget.dart';
import '../schedule/passenger_recurring_discovery_tab.dart';

class PassengerDashboardScreen extends StatefulWidget {
  const PassengerDashboardScreen({super.key});

  @override
  State<PassengerDashboardScreen> createState() =>
      _PassengerDashboardScreenState();
}

class _PassengerDashboardScreenState extends State<PassengerDashboardScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;
  GoogleMapController? _embeddedMapController;

  int _selectedNavIndex = 0;
  Timer? _homeAutoRefreshTimer;
  bool _homeAutoRefreshInFlight = false;

  // Data
  User? _user;
  List<RideBooking> _bookings = [];
  List<RideBooking> _homeScheduledBookings = [];
  List<Map<String, dynamic>> _homeRecurringSubscriptions = [];
  List<RideBooking> _homeHistoryBookings = [];
  PassengerBookingHistory? _stats;
  int _unreadNotifications = 0;
  int _historyChatBadgeCount = 0;
  bool _notificationsEnabled = true;
  bool _locationSharing = true;
  bool _isKycVerified = false;
  bool _isKycStatusLoaded = false;
  LatLng? _embeddedCurrentLocation;
  BitmapDescriptor? _webLiveLocationIcon;
  PickedLocation? _scheduleOrigin;
  PickedLocation? _scheduleDestination;
  bool _isScheduleDetailsStep = false;
  Widget? _scheduleDetailsView;

  // States
  bool _isLoadingHome = true;
  bool _isLoadingRides = true;
  String? _homeError;
  String? _ridesError;
  String? _activeFilter;

  // AI Cluster tracking — set when passenger posts a ride request
  String? _pendingRequestId;

  // Services
  final _userService = UserService();
  final _rideService = RideService();
  final _walletService = WalletService();
  final _chatSync = ChatSyncService();
  final _notificationService = NotificationService();
  final _notificationSync = NotificationSyncService();
  final _scheduleService = ScheduleService();
  final _mapsService = MapsService();
  final _verificationService = VerificationService();
  final ImagePicker _imagePicker = ImagePicker();

  static const Set<PointerDeviceKind> _refreshDragDevices = {
    PointerDeviceKind.touch,
    PointerDeviceKind.mouse,
    PointerDeviceKind.stylus,
    PointerDeviceKind.unknown,
  };

  Widget _interceptMapPointerBleed(Widget child) {
    if (!kIsWeb) return child;
    return PointerInterceptor(child: child);
  }

  static PassengerBookingHistory get _emptyStats => PassengerBookingHistory(
        totalBookings: 0,
        totalSpent: 0,
        activeBookings: 0,
        completedRides: 0,
        cancelledBookings: 0,
        carbonFootprintSavedKg: 0,
      );

  static const Color _profileHomeTextPrimary = Color(0xFF121915);
  static const Color _profileHomeTextSecondary = Color(0xFF25352D);

  Color _profileSymbolShade(Color base) {
    return Color.alphaBlend(Colors.black.withValues(alpha: 0.34), base);
  }

  BoxDecoration _profileHomeGlass({
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

  @override
  void initState() {
    super.initState();
    _initAnimations();
    _initWebEmbeddedMapLocation();
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
      await _loadDashboardData(showLoader: false);
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

  /// Runs [future] and maps failures to null so parallel dashboard loads do not fail the whole screen.
  Future<T?> _silent<T>(Future<T> future) async {
    try {
      return await future;
    } catch (_) {
      return null;
    }
  }

  Future<void> _initWebEmbeddedMapLocation() async {
    if (!kIsWeb) return;

    try {
      final serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) return;

      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }

      final granted = permission == LocationPermission.always ||
          permission == LocationPermission.whileInUse;
      if (!granted) return;

      final icon = await LiveLocationMarkerIcon.forWeb();
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 10),
        ),
      );

      if (!mounted) return;
      setState(() {
        _webLiveLocationIcon = icon;
        _embeddedCurrentLocation = LatLng(pos.latitude, pos.longitude);
      });

      _embeddedMapController?.animateCamera(
        CameraUpdate.newCameraPosition(
          CameraPosition(target: _embeddedCurrentLocation!, zoom: 13),
        ),
      );
    } catch (_) {
      // Ignore location failures for compact dashboard map.
    }
  }

  Future<void> _loadDashboardData({bool showLoader = true}) async {
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

      // Parallelize — worst-case wait is one timeout, not six in sequence
      final fUser = _silent(_userService.getMyProfile());
      final fBookings = _silent(_rideService.getMyBookings());
      final fHomeScheduledBookings =
          _silent(_rideService.getMyBookings(statusFilter: 'active'));
      final fHomeHistoryBookings =
          _silent(_rideService.getMyBookings(statusFilter: 'history'));
      final fRecurringHome =
          _silent(_scheduleService.getPassengerRecurringHome());
      final fRideReq = _silent(_rideService.getMyRideRequests());
      final fStats = _silent(_rideService.getPassengerStats());
      final fVerification = userId != null
          ? _silent(_verificationService.getStatus(userId))
          : Future<Map<String, dynamic>?>.value(null);
      final fUnread = _silent(_notificationService.getUnreadCount());
      final fChatHistoryBadge =
          _silent(_chatSync.refreshHistoryBadgeCount(force: true));

      await Future.wait([
        fUser,
        fBookings,
        fHomeScheduledBookings,
        fHomeHistoryBookings,
        fRecurringHome,
        fRideReq,
        fStats,
        fVerification,
        fUnread,
        fChatHistoryBadge,
      ]);

      final user = await fUser;
      final bookings = (await fBookings) ?? <RideBooking>[];
      final homeScheduledBookings = _homeScheduledIncompleteBookings(
        (await fHomeScheduledBookings) ?? <RideBooking>[],
      );
      final homeHistoryBookings =
          (await fHomeHistoryBookings) ?? <RideBooking>[];
      final recurringHome = (await fRecurringHome) ?? <Map<String, dynamic>>[];
      final stats = await fStats;
      final verificationStatus = await fVerification;
      final verificationMap = (verificationStatus?['verifications'] as Map?)
              ?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final isKycVerified = verificationStatus?['overall_verified'] == true ||
          verificationMap['cnic']?.toString().toLowerCase() == 'verified';
      final isKycStatusLoaded = verificationStatus != null;
      final unread = (await fUnread) ?? _notificationSync.unreadCount;
      _notificationSync.setUnreadCount(unread);

      if (!mounted) return;
      setState(() {
        _user = user;
        _bookings = bookings;
        _homeScheduledBookings = homeScheduledBookings;
        _homeHistoryBookings = homeHistoryBookings;
        _homeRecurringSubscriptions = recurringHome;
        _stats = stats ?? _emptyStats;
        _unreadNotifications = unread;
        _historyChatBadgeCount = _chatSync.historyNewCount;
        _isKycVerified = isKycVerified;
        _isKycStatusLoaded = isKycStatusLoaded;
        _notificationsEnabled = user?.profile?.pushNotificationsEnabled ?? true;
        _locationSharing = user?.profile?.shareLocationEnabled ?? true;
        if (showLoader) _isLoadingHome = false;
        _isLoadingRides = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _homeError = e is DioException ? extractError(e) : e.toString();
        if (showLoader) _isLoadingHome = false;
      });
    }
  }

  List<RideBooking> _homeScheduledIncompleteBookings(
      List<RideBooking> bookings) {
    bool isIncomplete(RideBooking booking) {
      final ride = booking.ride;
      if (ride != null && ride.isRecurringRide) {
        return false;
      }

      final bookingStatus = booking.status.toLowerCase();
      if (bookingStatus == 'completed' || bookingStatus == 'cancelled') {
        return false;
      }

      final rideStatus = booking.ride?.status.toLowerCase();
      if (rideStatus == 'completed' || rideStatus == 'cancelled') {
        return false;
      }

      return true;
    }

    int statusPriority(RideBooking booking) {
      final rideStatus = (booking.ride?.status ?? '').toLowerCase();
      if (rideStatus == 'in_progress' || rideStatus == 'ongoing') return 0;
      if (rideStatus == 'open' || rideStatus == 'scheduled') return 1;
      return 2;
    }

    DateTime? sortTime(RideBooking booking) {
      final departure = booking.ride?.departureDatetime;
      if (departure != null) return departure;
      return DateTime.tryParse(booking.bookingTime);
    }

    final filtered = bookings.where(isIncomplete).toList();
    filtered.sort((a, b) {
      final priorityCompare = statusPriority(a).compareTo(statusPriority(b));
      if (priorityCompare != 0) return priorityCompare;

      final aTime = sortTime(a);
      final bTime = sortTime(b);
      if (aTime == null && bTime == null) return 0;
      if (aTime == null) return 1;
      if (bTime == null) return -1;
      return bTime.compareTo(aTime);
    });
    return filtered;
  }

  double? _bookingSegmentDistanceKm(RideBooking booking) {
    final segmentKm = booking.segmentKm;
    if (segmentKm != null && segmentKm > 0) {
      return segmentKm;
    }

    if (booking.pickupLat != null &&
        booking.pickupLng != null &&
        booking.dropoffLat != null &&
        booking.dropoffLng != null) {
      final distanceMeters = Geolocator.distanceBetween(
        booking.pickupLat!,
        booking.pickupLng!,
        booking.dropoffLat!,
        booking.dropoffLng!,
      );
      if (distanceMeters > 0) {
        return distanceMeters / 1000;
      }
    }

    return null;
  }

  double? _bookingCarbonSavedKg(RideBooking booking) {
    final distanceKm = _bookingSegmentDistanceKm(booking);
    if (distanceKm == null || distanceKm <= 0) {
      return null;
    }
    return CarbonFootprint.avoidedKgForDistanceKm(distanceKm);
  }

  Future<void> _refreshAllDashboardData({bool showHomeLoader = false}) async {
    await _loadDashboardData(showLoader: showHomeLoader);

    // Keep My Rides aligned with the active filter when one is selected.
    if (_activeFilter != null) {
      await _loadBookings(filter: _activeFilter);
    }
  }

  Future<void> _refreshHomeData() async {
    await _refreshAllDashboardData(showHomeLoader: false);
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

  Future<void> _loadBookings({String? filter}) async {
    setState(() {
      _isLoadingRides = true;
      _ridesError = null;
    });
    try {
      final bookings = await _rideService.getMyBookings(statusFilter: filter);
      if (!mounted) return;
      setState(() {
        _bookings = bookings;
        _isLoadingRides = false;
        _ridesError = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _bookings = [];
        _ridesError = e is DioException ? extractError(e) : e.toString();
        _isLoadingRides = false;
      });
    }
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
    } catch (_) {
      if (!mounted) return;
      setState(() => _locationSharing = previous);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Could not update location sharing preference.'),
        ),
      );
    }
  }

  void _openScheduleRidesTab() {
    setState(() {
      _selectedNavIndex = 1;
      _isScheduleDetailsStep = false;
      _scheduleDetailsView = null;
    });
  }

  void _showPassengerScheduleDetails(Widget detailsView) {
    setState(() {
      _isScheduleDetailsStep = true;
      _scheduleDetailsView = detailsView;
    });
  }

  void _returnToScheduleMap() {
    if (!mounted) return;
    setState(() {
      _isScheduleDetailsStep = false;
      _scheduleDetailsView = null;
    });
  }

  @override
  void dispose() {
    _homeAutoRefreshTimer?.cancel();
    _chatSync.historyNewCountNotifier
        .removeListener(_handleChatHistoryBadgeChanged);
    _chatSync.stopPolling();
    _notificationSync.unreadCountNotifier
        .removeListener(_handleUnreadCountChanged);
    _notificationSync.stopPolling();
    _animationController.dispose();
    _embeddedMapController?.dispose();
    super.dispose();
  }

  Future<void> _handleLogout() async {
    try {
      await FirebaseAuthService().signOut();
    } catch (_) {}
    if (mounted) {
      Navigator.of(context).pushReplacementNamed('/signin');
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

  @override
  Widget build(BuildContext context) {
    SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
    ));

    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: FadeTransition(
        opacity: _fadeAnimation,
        child: IndexedStack(
          index: _selectedNavIndex,
          children: [
            _buildHomeTab(),
            _buildScheduleRidesTab(),
            const PassengerRecurringDiscoveryTab(),
            _buildMyRidesTab(),
            _buildProfileTab(),
          ],
        ),
      ),
      bottomNavigationBar: _buildBottomNav(),
    );
  }

  // ───────────────────────────────────────────────────────
  //  Bottom Navigation
  // ───────────────────────────────────────────────────────
  Widget _buildBottomNav() {
    return SafeArea(
      minimum: const EdgeInsets.fromLTRB(0, 0, 0, 12),
      child: HomeDesignSystem.frostLayer(
        blur: 8,
        child: Container(
          decoration: HomeDesignSystem.darkTopBarSurface(radius: 24),
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _navItem(Icons.home_rounded, 'Home', 0),
              _navItem(Icons.schedule_rounded, 'Schedule Rides', 1),
              _navItem(Icons.repeat_rounded, 'Recurring Rides', 2),
              _navItem(Icons.history_rounded, 'My Rides', 3),
              _navItem(Icons.person_rounded, 'Profile', 4),
            ],
          ),
        ),
      ),
    );
  }

  Widget _navItem(IconData icon, String label, int index) {
    final isSelected = _selectedNavIndex == index;
    return GestureDetector(
      onTap: () {
        setState(() => _selectedNavIndex = index);
        if (index == 3) _loadBookings(filter: _activeFilter);
      },
      behavior: HitTestBehavior.opaque,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected
              ? AuthDesignTokens.sky400.withValues(alpha: 0.22)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: isSelected
                ? AuthDesignTokens.routeBlue.withValues(alpha: 0.34)
                : Colors.transparent,
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon,
                color: isSelected
                    ? AuthDesignTokens.white
                    : AuthDesignTokens.white.withValues(alpha: 0.72),
                size: 22),
            const SizedBox(height: 4),
            Text(label,
                style: GoogleFonts.inter(
                    color: isSelected
                        ? AuthDesignTokens.white
                        : AuthDesignTokens.white.withValues(alpha: 0.74),
                    fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                    fontSize: 10.5)),
          ],
        ),
      ),
    );
  }

  // ───────────────────────────────────────────────────────
  //  HOME TAB (IMMERSIVE THEME)
  // ───────────────────────────────────────────────────────
  Widget _buildHomeTab() {
    if (_isLoadingHome) {
      return const SyloLoader(message: 'Loading your dashboard...');
    }
    if (_homeError != null) {
      return SyloError(message: _homeError!, onRetry: _loadDashboardData);
    }

    final width = MediaQuery.of(context).size.width;
    final initialSheetSize = width >= 1100 ? 0.62 : 0.55;
    final minSheetSize = width >= 1100 ? 0.4 : 0.35;
    const defaultCenter = LatLng(31.5204, 74.3587); // Lahore

    return Stack(
      children: [
        // 1. Immersive Full-Screen Map
        Positioned.fill(
          child: ShaderMask(
            shaderCallback: (rect) {
              return const LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.black,
                  Colors.black,
                  Colors.transparent,
                ],
                stops: [0.0, 0.6, 1.0],
              ).createShader(rect);
            },
            blendMode: BlendMode.dstIn,
            child: GoogleMap(
              initialCameraPosition: CameraPosition(
                target: _embeddedCurrentLocation ?? defaultCenter,
                zoom: 14,
              ),
              myLocationEnabled: !kIsWeb,
              myLocationButtonEnabled: false,
              zoomControlsEnabled: false,
              mapToolbarEnabled: false,
              onMapCreated: (controller) {
                _embeddedMapController = controller;
                if (_embeddedCurrentLocation != null) {
                  controller.animateCamera(
                    CameraUpdate.newCameraPosition(
                      CameraPosition(
                          target: _embeddedCurrentLocation!, zoom: 14),
                    ),
                  );
                }
              },
              markers: {
                if (kIsWeb && _embeddedCurrentLocation != null)
                  Marker(
                    markerId: const MarkerId('embeddedCurrentLocation'),
                    position: _embeddedCurrentLocation!,
                    icon: _webLiveLocationIcon ??
                        BitmapDescriptor.defaultMarkerWithHue(
                            BitmapDescriptor.hueAzure),
                  ),
              },
              circles: {
                if (kIsWeb && _embeddedCurrentLocation != null)
                  Circle(
                    circleId: const CircleId('embeddedCurrentLocationAura'),
                    center: _embeddedCurrentLocation!,
                    radius: 18,
                    fillColor:
                        AuthDesignTokens.routeBlue.withValues(alpha: 0.2),
                    strokeColor:
                        AuthDesignTokens.routeBlue.withValues(alpha: 0.55),
                    strokeWidth: 1,
                  ),
              },
            ),
          ),
        ),

        const Positioned.fill(
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: AuthDesignTokens.pageVeilGradient,
              ),
            ),
          ),
        ),

        // 2. Custom App Bar over the Map (Transparent)
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          child: _interceptMapPointerBleed(_buildFloatingAppBar()),
        ),

        // 3. Floating Bottom Sheet
        DraggableScrollableSheet(
          initialChildSize: initialSheetSize,
          minChildSize: minSheetSize,
          maxChildSize: 0.90,
          builder: (context, scrollController) {
            return _interceptMapPointerBleed(
              HomeDesignSystem.contentWidth(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 10),
                  child: HomeDesignSystem.frostLayer(
                    blur: 14,
                    child: Container(
                      decoration: HomeDesignSystem.glassShell(radius: 28),
                      child: RefreshIndicator(
                        onRefresh: _refreshHomeData,
                        color: AuthDesignTokens.brandAction,
                        child: _desktopRefreshScrollable(
                          ListView(
                            controller: scrollController,
                            physics: const AlwaysScrollableScrollPhysics(
                              parent: BouncingScrollPhysics(),
                            ),
                            padding: EdgeInsets.zero,
                            children: [
                              const SizedBox(height: 12),
                              Center(
                                child: Container(
                                  width: 46,
                                  height: 4,
                                  decoration: BoxDecoration(
                                    color: AuthDesignTokens.lineFog,
                                    borderRadius: BorderRadius.circular(2),
                                  ),
                                ),
                              ),
                              const SizedBox(height: 18),
                              _homeReveal(
                                  begin: 0.00, child: _buildSearchBar()),
                              const SizedBox(height: 24),
                              _homeReveal(
                                  begin: 0.08, child: _buildQuickActions()),
                              const SizedBox(height: 24),
                              _homeReveal(
                                  begin: 0.16, child: _buildScheduledRides()),
                              const SizedBox(height: 24),
                              _homeReveal(
                                  begin: 0.24,
                                  child: _buildRecurringHomeSubscriptions()),
                              const SizedBox(height: 24),
                              _homeReveal(
                                  begin: 0.32, child: _buildRidesHistory()),
                              const SizedBox(height: 24),
                              if (_pendingRequestId != null)
                                _homeReveal(
                                    begin: 0.4,
                                    child: _buildClusterStatusSection()),
                              if (_pendingRequestId != null)
                                const SizedBox(height: 24),
                              _homeReveal(
                                  begin: 0.48, child: _buildStatsSection()),
                              const SizedBox(height: 32),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ],
    );
  }

  Widget _buildFloatingAppBar() {
    final name = _user?.firstName ?? 'Passenger';
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        child: HomeDesignSystem.contentWidth(
          child: HomeDesignSystem.frostLayer(
            blur: 8,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: HomeDesignSystem.darkTopBarSurface(radius: 18),
              child: Row(
                children: [
                  _buildProfileAvatar(
                    radius: 22,
                    fontSize: 15,
                    fallbackInitials: _user?.initials ?? 'P',
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Welcome back, $name',
                          style: HomeDesignSystem.heroTitleOnDark().copyWith(
                            fontSize: 22,
                            height: 1.0,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: 3),
                        Text(
                          'Plan your next shared route',
                          style: HomeDesignSystem.heroSubtitleOnDark().copyWith(
                            color:
                                AuthDesignTokens.white.withValues(alpha: 0.85),
                          ),
                        ),
                      ],
                    ),
                  ),
                  _buildActionIcon(
                    Icons.chat_bubble_outline_rounded,
                    _historyChatBadgeCount,
                    _openChatHistoryAndRefresh,
                  ),
                  const SizedBox(width: 10),
                  _buildActionIcon(
                    Icons.notifications_outlined,
                    _unreadNotifications,
                    _openNotificationsAndRefresh,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildActionIcon(IconData icon, int badgeCount, VoidCallback onTap) {
    return Stack(
      children: [
        Container(
          decoration: BoxDecoration(
              color: AuthDesignTokens.white.withValues(alpha: 0.14),
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.14),
                  blurRadius: 10,
                )
              ]),
          child: IconButton(
            icon: Icon(icon, color: AuthDesignTokens.white),
            onPressed: onTap,
          ),
        ),
        if (badgeCount > 0)
          Positioned(
            right: 0,
            top: 0,
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
    return CircleAvatar(
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
    );
  }

  static const Set<String> _supportedProfilePhotoExtensions = {
    'jpg',
    'jpeg',
    'png',
    'gif',
    'webp',
  };

  bool _isSupportedProfilePhotoFile(XFile file) {
    final mime = (file.mimeType ?? '').toLowerCase().trim();
    if (mime.isNotEmpty && !mime.startsWith('image/')) {
      return false;
    }

    final lowerName = file.name.toLowerCase().trim();
    final dotIndex = lowerName.lastIndexOf('.');
    if (dotIndex < 0 || dotIndex == lowerName.length - 1) {
      return mime.startsWith('image/');
    }

    final extension = lowerName.substring(dotIndex + 1);
    return _supportedProfilePhotoExtensions.contains(extension);
  }

  String _imageSubtypeFromFile(XFile file) {
    final mime = (file.mimeType ?? '').toLowerCase().trim();
    if (mime.startsWith('image/')) {
      final subtype = mime.substring('image/'.length);
      if (subtype == 'jpg' || subtype == 'jpeg') return 'jpeg';
      if (subtype == 'png') return 'png';
      if (subtype == 'gif') return 'gif';
      if (subtype == 'webp') return 'webp';
    }

    final lower = file.name.toLowerCase();
    if (lower.endsWith('.png')) return 'png';
    if (lower.endsWith('.gif')) return 'gif';
    if (lower.endsWith('.webp')) return 'webp';
    return 'jpeg';
  }

  Future<void> _showInvalidProfilePhotoFormatDialog() async {
    if (!mounted) return;

    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Invalid Profile Photo Format'),
        content: const Text(
          'Please upload your profile photo in one of these formats:\n'
          '- JPG / JPEG\n'
          '- PNG\n'
          '- GIF\n'
          '- WEBP',
        ),
        actions: [
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primary,
              foregroundColor: Colors.white,
            ),
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

  bool _isProfilePhotoFormatErrorText(String text) {
    final lower = text.toLowerCase();
    return lower.contains('invalid photo format') ||
        lower.contains('unsupported photo format') ||
        lower.contains('invalid base64') ||
        lower.contains('photo must be a valid url or base64 data uri') ||
        lower.contains('invalid file type') ||
        lower.contains('unsupported media type');
  }

  ({String message, bool showFormatDialog}) _profilePhotoUploadFeedback(
    Object error,
  ) {
    const fallback = 'Unable to update profile picture. Please try again.';

    if (error is DioException) {
      final data = error.response?.data;
      final statusCode = error.response?.statusCode;

      if (data is Map) {
        final validationErrors = data['error']?['errors'];
        if (validationErrors is List && validationErrors.isNotEmpty) {
          final firstError = validationErrors.first;
          if (firstError is Map) {
            final validationMessage =
                (firstError['message'] ?? '').toString().toLowerCase();
            if (validationMessage.contains('at most') ||
                validationMessage.contains('too long')) {
              return (
                message:
                    'Profile photo is too large. Please choose a smaller image (up to 4 MB).',
                showFormatDialog: false,
              );
            }
          }
        }

        final detail =
            (data['detail'] ?? data['error']?['detail'] ?? data['error'])
                ?.toString();
        final detailText = (detail ?? '').trim();
        if (detailText.isNotEmpty) {
          if (_isProfilePhotoFormatErrorText(detailText)) {
            return (
              message:
                  'Invalid profile photo format. Please upload JPG, PNG, GIF, or WEBP.',
              showFormatDialog: true,
            );
          }
          final lowerDetail = detailText.toLowerCase();
          if (lowerDetail.contains('size exceeds') ||
              lowerDetail.contains('too large')) {
            return (
              message:
                  'Profile photo is too large. Please choose a smaller image (up to 4 MB).',
              showFormatDialog: false,
            );
          }
        }
      }

      final extracted = extractError(error);
      if (_isProfilePhotoFormatErrorText(extracted) ||
          (statusCode == 422 &&
              extracted.toLowerCase().contains('body.photo'))) {
        return (
          message:
              'Invalid profile photo format. Please upload JPG, PNG, GIF, or WEBP.',
          showFormatDialog: true,
        );
      }
      return (message: extracted, showFormatDialog: false);
    }

    return (message: fallback, showFormatDialog: false);
  }

  Future<void> _pickAndUploadPassengerProfilePhoto(ImageSource source) async {
    try {
      final picked = await _imagePicker.pickImage(
        source: source,
        maxWidth: 1024,
        maxHeight: 1024,
        imageQuality: 85,
      );

      if (picked == null) return;
      if (!_isSupportedProfilePhotoFile(picked)) {
        await _showInvalidProfilePhotoFormatDialog();
        return;
      }

      final bytes = await picked.readAsBytes();
      final subtype = _imageSubtypeFromFile(picked);
      final payload = 'data:image/$subtype;base64,${base64Encode(bytes)}';

      await _userService.uploadPhoto(payload);
      await _loadDashboardData(showLoader: false);

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Profile picture updated.'),
          backgroundColor: AppColors.success,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      final feedback = _profilePhotoUploadFeedback(e);
      if (feedback.showFormatDialog) {
        await _showInvalidProfilePhotoFormatDialog();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(feedback.message),
            backgroundColor: AppColors.error,
          ),
        );
      }
    }
  }

  Future<void> _removePassengerProfilePhoto() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Remove Profile Picture'),
        content:
            const Text('Remove your profile picture and use initials instead?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child:
                const Text('Remove', style: TextStyle(color: AppColors.error)),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    try {
      await _userService.updateProfile(profilePhoto: '');
      await _loadDashboardData(showLoader: false);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Profile picture removed.'),
          backgroundColor: AppColors.info,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      final message = e is DioException
          ? extractError(e)
          : 'Unable to remove profile picture. Please try again.';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message), backgroundColor: AppColors.error),
      );
    }
  }

  Future<void> _handlePassengerProfilePhotoAction() async {
    final hasPhoto = (_user?.profile?.profilePhoto ?? '').trim().isNotEmpty;
    final action = await showModalBottomSheet<String>(
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
              const SizedBox(height: 10),
              if (!kIsWeb)
                ListTile(
                  leading: const Icon(Icons.camera_alt_rounded,
                      color: AppColors.primary),
                  title: const Text('Take Selfie'),
                  onTap: () => Navigator.pop(ctx, 'camera'),
                ),
              ListTile(
                leading: const Icon(Icons.photo_library_rounded,
                    color: AppColors.info),
                title: const Text(
                    kIsWeb ? 'Choose Image File' : 'Choose from Gallery'),
                onTap: () => Navigator.pop(ctx, 'gallery'),
              ),
              if (hasPhoto)
                ListTile(
                  leading: const Icon(Icons.delete_outline_rounded,
                      color: AppColors.error),
                  title: const Text('Remove Picture'),
                  onTap: () => Navigator.pop(ctx, 'remove'),
                ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );

    if (action == null) return;

    if (action == 'remove') {
      await _removePassengerProfilePhoto();
      return;
    }

    final shouldSetPhoto = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Set Profile Picture'),
        content: const Text(
            'Do you want to set a selfie/photo as your profile picture?'),
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
            child: const Text('Set Photo'),
          ),
        ],
      ),
    );

    if (shouldSetPhoto != true) return;

    final source =
        action == 'camera' ? ImageSource.camera : ImageSource.gallery;
    await _pickAndUploadPassengerProfilePhoto(source);
  }

  Widget _buildAppBar() {
    final name = _user?.firstName ?? 'Passenger';
    return SliverAppBar(
      expandedHeight: 180,
      floating: false,
      pinned: true,
      automaticallyImplyLeading: false,
      backgroundColor: AppColors.surface,
      flexibleSpace: FlexibleSpaceBar(
        background: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: AppColors.isDark
                  ? [const Color(0xFF1E1E1E), const Color(0xFF2C2C2C)]
                  : [AppColors.charcoal, AppColors.charcoalMid],
            ),
          ),
          child: SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(AppConstants.paddingLarge),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  Row(
                    children: [
                      _buildProfileAvatar(
                        radius: 22,
                        fontSize: 16,
                        fallbackInitials: _user?.initials ?? 'P',
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Hello, $name 👋',
                              style: const TextStyle(
                                color: AppColors.textOnDark,
                                fontSize: 20,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              'Where are you heading?',
                              style: TextStyle(
                                  color: AppColors.textHint, fontSize: 14),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
      actions: [
        Stack(
          children: [
            IconButton(
              icon: const Icon(Icons.chat_bubble_outline_rounded,
                  color: AppColors.textOnDark),
              onPressed: _openChatHistoryAndRefresh,
              tooltip: 'Chat History',
            ),
            if (_historyChatBadgeCount > 0)
              Positioned(
                right: 8,
                top: 8,
                child: Container(
                  padding: const EdgeInsets.all(4),
                  decoration: const BoxDecoration(
                    color: AppColors.error,
                    shape: BoxShape.circle,
                  ),
                  constraints:
                      const BoxConstraints(minWidth: 18, minHeight: 18),
                  child: Text(
                    _historyChatBadgeCount > 9
                        ? '9+'
                        : '$_historyChatBadgeCount',
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 10,
                        fontWeight: FontWeight.bold),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
          ],
        ),
        Stack(
          children: [
            IconButton(
              icon: const Icon(Icons.notifications_outlined,
                  color: AppColors.textOnDark),
              onPressed: _openNotificationsAndRefresh,
            ),
            if (_unreadNotifications > 0)
              Positioned(
                right: 8,
                top: 8,
                child: Container(
                  padding: const EdgeInsets.all(4),
                  decoration: const BoxDecoration(
                    color: AppColors.error,
                    shape: BoxShape.circle,
                  ),
                  constraints:
                      const BoxConstraints(minWidth: 18, minHeight: 18),
                  child: Text(
                    _unreadNotifications > 9 ? '9+' : '$_unreadNotifications',
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 10,
                        fontWeight: FontWeight.bold),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }

  Widget _buildSearchBar() {
    return Padding(
      padding:
          const EdgeInsets.symmetric(horizontal: AppConstants.paddingLarge),
      child: GestureDetector(
        onTap: _openScheduleRidesTab,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
          decoration: HomeDesignSystem.softPanel(radius: 18, elevated: true),
          child: Row(
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: const BoxDecoration(
                    color: AuthDesignTokens.routeBlue, shape: BoxShape.circle),
                child: const Icon(Icons.search, color: Colors.white, size: 20),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Where to?',
                      style: GoogleFonts.inter(
                        color: AuthDesignTokens.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      'Discover available rides by route and time',
                      style: HomeDesignSystem.cardBody(size: 11.5),
                    ),
                  ],
                ),
              ),
              Icon(
                Icons.arrow_forward_ios_rounded,
                size: 14,
                color: AuthDesignTokens.white.withValues(alpha: 0.84),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildQuickActions() {
    return Padding(
      padding:
          const EdgeInsets.symmetric(horizontal: AppConstants.paddingLarge),
      child: HomeDesignSystem.frostLayer(
        blur: 10,
        child: Container(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 12),
          decoration: HomeDesignSystem.softPanel(radius: 24, elevated: true),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Quick Actions', style: HomeDesignSystem.sectionTitle()),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: _actionCard(
                      Icons.local_taxi_rounded,
                      'Find Ride',
                      AuthDesignTokens.routeBlue,
                      _openScheduleRidesTab,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _actionCard(
                      Icons.account_balance_wallet_rounded,
                      'Wallet',
                      AuthDesignTokens.brandAction,
                      () => Navigator.pushNamed(context, '/wallet'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _actionCard(
                      Icons.sos_rounded,
                      'SOS',
                      AppColors.error,
                      () => Navigator.pushNamed(context, '/sos'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: _actionCard(
                      Icons.history_rounded,
                      'History',
                      AuthDesignTokens.sky400,
                      () => setState(() => _selectedNavIndex = 3),
                    ),
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
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
        splashColor: color.withValues(alpha: 0.12),
        child: Ink(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                color.withValues(alpha: 0.22),
                color.withValues(alpha: 0.08),
              ],
            ),
            borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
            border: Border.all(
              color: Colors.white.withValues(alpha: 0.42),
            ),
          ),
          child: Column(
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.22),
                  shape: BoxShape.circle,
                  border: Border.all(color: color.withValues(alpha: 0.72)),
                  boxShadow: [
                    BoxShadow(
                      color: color.withValues(alpha: 0.34),
                      blurRadius: 12,
                    ),
                  ],
                ),
                child: Icon(icon, color: color, size: 24),
              ),
              const SizedBox(height: 8),
              Text(
                label,
                textAlign: TextAlign.center,
                style: GoogleFonts.inter(
                  fontWeight: FontWeight.w700,
                  fontSize: 12,
                  color: AuthDesignTokens.white,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildScheduledRides() {
    return _buildHomeBookingSection(
      title: 'Scheduled Rides',
      rides: _homeScheduledBookings,
      emptyTitle: 'No scheduled rides',
      emptySubtitle: 'Upcoming and in-progress rides appear here.',
    );
  }

  void _openRecurringRidesTab() {
    setState(() {
      _selectedNavIndex = 2;
    });
  }

  String _recurringAddress(
      Map<String, dynamic> item, String pointKey, String fallback) {
    final point = item[pointKey];
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
    final ref = referenceLocalDate ?? DateTime.now();
    final utc = DateTime.utc(ref.year, ref.month, ref.day, hour, minute);
    final local = utc.toLocal();
    final localHour = local.hour;
    final period = localHour >= 12 ? 'PM' : 'AM';
    final h12 = localHour > 12 ? localHour - 12 : (localHour == 0 ? 12 : localHour);
    return '$h12:${local.minute.toString().padLeft(2, '0')} $period';
  }

  String _formatRecurringWindow(Map<String, dynamic> item) {
    final start = (item['departure_window_start'] ?? '').toString();
    final end = (item['departure_window_end'] ?? '').toString();
    final nextDepartureRaw = (item['next_departure_time'] ?? '').toString();
    final nextDepartureLocal = DateTime.tryParse(nextDepartureRaw)?.toLocal();
    if (start.isEmpty || end.isEmpty) return 'Flexible departure window';
    return '${_formatRecurringClock(start, referenceLocalDate: nextDepartureLocal)} - ${_formatRecurringClock(end, referenceLocalDate: nextDepartureLocal)}';
  }

  Future<void> _openPassengerRecurringNearestRide(
      Map<String, dynamic> item) async {
    final subscriptionId = (item['subscription_id'] ?? '').toString();
    if (subscriptionId.isEmpty) return;

    try {
      final resolved =
          await _scheduleService.resolvePassengerSubscriptionNextRide(
        subscriptionId,
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

  Future<void> _cancelPassengerRecurringSeries(
      Map<String, dynamic> item) async {
    final subscriptionId = (item['subscription_id'] ?? '').toString();
    if (subscriptionId.isEmpty) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel Full Recurring Series'),
        content: const Text(
          'This will cancel all your future rides in this recurring series. Continue?',
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
      await _scheduleService.cancelPassengerRecurringSeries(subscriptionId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Recurring series cancelled.'),
          backgroundColor: AppColors.success,
        ),
      );
      _loadDashboardData(showLoader: false);
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

  Widget _buildRecurringHomeSubscriptions() {
    final items = _homeRecurringSubscriptions.take(3).toList();
    return Padding(
      padding:
          const EdgeInsets.symmetric(horizontal: AppConstants.paddingLarge),
      child: HomeDesignSystem.frostLayer(
        blur: 10,
        child: Container(
          padding: const EdgeInsets.fromLTRB(14, 14, 14, 10),
          decoration: HomeDesignSystem.softPanel(radius: 22, elevated: true),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('Recurring Rides',
                      style: HomeDesignSystem.sectionTitle()),
                  TextButton(
                    onPressed: _openRecurringRidesTab,
                    child: Text(
                      'View All',
                      style: GoogleFonts.inter(
                        color: AuthDesignTokens.brandAction,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              if (items.isEmpty)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(32),
                  decoration: HomeDesignSystem.softPanel(radius: 16),
                  child: Column(
                    children: [
                      Icon(Icons.repeat_rounded,
                          size: 40,
                          color:
                              AuthDesignTokens.white.withValues(alpha: 0.72)),
                      const SizedBox(height: 12),
                      Text(
                        'No recurring rides',
                        style: HomeDesignSystem.cardTitle(
                          color: AuthDesignTokens.white.withValues(alpha: 0.9),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Your booked recurring series appear here.',
                        style: HomeDesignSystem.cardBody(),
                      ),
                    ],
                  ),
                )
              else
                ...items.map(
                  (item) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _buildPassengerRecurringHomeCard(item),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPassengerRecurringHomeCard(Map<String, dynamic> item) {
    final subscriptionId = (item['subscription_id'] ?? '').toString();
    final origin = _recurringAddress(item, 'start_point', 'Unknown start');
    final destination =
        _recurringAddress(item, 'end_point', 'Unknown destination');
    final seats = (item['seats_reserved'] ?? '1').toString();
    final status = (item['status'] ?? 'active').toString();
    final window = _formatRecurringWindow(item);
    final nextDepartureRaw = (item['next_departure_time'] ?? '').toString();
    final nextDeparture = nextDepartureRaw.isEmpty
        ? 'No upcoming instance yet'
        : _formatDateTime(nextDepartureRaw);

    return InkWell(
      onTap: () => _openPassengerRecurringNearestRide(item),
      borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: HomeDesignSystem.softPanel(radius: 16, elevated: true),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.repeat_rounded,
                    size: 18, color: AuthDesignTokens.routeBlue),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Daily recurring',
                    style: HomeDesignSystem.cardTitle(),
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: _statusColor(status).withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    status.toUpperCase(),
                    style: GoogleFonts.inter(
                      color: _statusColor(status),
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text('$origin -> $destination',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: HomeDesignSystem.cardBody(
                  color: AuthDesignTokens.white,
                  size: 13,
                )),
            const SizedBox(height: 4),
            Text('$window • $seats seat(s)',
                style: HomeDesignSystem.cardBody(size: 12)),
            const SizedBox(height: 4),
            Text('Next: $nextDeparture',
                style: HomeDesignSystem.cardBody(size: 12)),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: subscriptionId.isEmpty
                        ? null
                        : () => _openPassengerRecurringNearestRide(item),
                    icon: const Icon(Icons.open_in_new_rounded, size: 16),
                    label: const Text('Open Next Ride'),
                    style: HomeDesignSystem.subtleOutlineButton(
                        AuthDesignTokens.brandAction),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: subscriptionId.isEmpty
                        ? null
                        : () => _cancelPassengerRecurringSeries(item),
                    icon: const Icon(Icons.delete_outline_rounded, size: 16),
                    label: const Text('Cancel Full'),
                    style:
                        HomeDesignSystem.subtleOutlineButton(AppColors.error),
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
    return _buildHomeBookingSection(
      title: 'Rides History',
      rides: _homeHistoryBookings,
      emptyTitle: 'No ride history yet',
      emptySubtitle: 'Completed and cancelled rides appear here.',
    );
  }

  Widget _buildHomeBookingSection({
    required String title,
    required List<RideBooking> rides,
    required String emptyTitle,
    required String emptySubtitle,
  }) {
    final items = rides.take(3).toList();
    return Padding(
      padding:
          const EdgeInsets.symmetric(horizontal: AppConstants.paddingLarge),
      child: HomeDesignSystem.frostLayer(
        blur: 10,
        child: Container(
          padding: const EdgeInsets.fromLTRB(14, 14, 14, 10),
          decoration: HomeDesignSystem.softPanel(radius: 22, elevated: true),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(title, style: HomeDesignSystem.sectionTitle()),
                  if (rides.isNotEmpty)
                    TextButton(
                      onPressed: () => setState(() => _selectedNavIndex = 3),
                      child: Text(
                        'View All',
                        style: GoogleFonts.inter(
                          color: AuthDesignTokens.brandAction,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              if (items.isEmpty)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(32),
                  decoration: HomeDesignSystem.softPanel(radius: 16),
                  child: Column(
                    children: [
                      Icon(Icons.directions_car_outlined,
                          size: 40,
                          color:
                              AuthDesignTokens.white.withValues(alpha: 0.72)),
                      const SizedBox(height: 12),
                      Text(
                        emptyTitle,
                        style: HomeDesignSystem.cardTitle(
                          color: AuthDesignTokens.white.withValues(alpha: 0.9),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        emptySubtitle,
                        style: HomeDesignSystem.cardBody(),
                      ),
                    ],
                  ),
                )
              else
                ...items.map((b) {
                  final ride = b.ride;
                  final co2 = _bookingCarbonSavedKg(b);
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: RideCard(
                      from: ride?.origin ?? 'Unknown',
                      to: ride?.destination ?? 'Unknown',
                      subtitle:
                          _formatDateTime(ride?.departureTime ?? b.bookingTime),
                      status: b.effectiveDisplayStatus,
                      statusColor: _statusColor(b.effectiveDisplayStatus),
                      price: 'Rs ${b.totalPrice.toStringAsFixed(0)}',
                      carbonSavedKg: (b.status == 'completed' ||
                              ride?.status == 'completed')
                          ? co2
                          : null,
                      onTap: () {
                        Navigator.pushNamed(
                          context,
                          '/ride-detail',
                          arguments: b.rideId,
                        );
                      },
                    ),
                  );
                }),
            ],
          ),
        ),
      ),
    );
  }

  // ───────────────────────────────────────────────────────
  //  AI CLUSTER STATUS SECTION
  // ───────────────────────────────────────────────────────
  Widget _buildClusterStatusSection() {
    return Padding(
      padding:
          const EdgeInsets.symmetric(horizontal: AppConstants.paddingLarge),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.auto_awesome_rounded,
                  size: 18, color: AuthDesignTokens.routeBlue),
              const SizedBox(width: 8),
              Text(
                'AI Match Status',
                style: HomeDesignSystem.sectionTitle(),
              ),
              const Spacer(),
              GestureDetector(
                onTap: () => showClusterExplanationSheet(context),
                child: Text(
                  'How it works',
                  style: GoogleFonts.inter(
                      fontSize: 12,
                      color: AuthDesignTokens.brandAction,
                      fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          ClusterStatusWidget(
            requestId: _pendingRequestId!,
            onRideMatched: () async {
              await _refreshAllDashboardData(showHomeLoader: false);
              if (!mounted) return;
              setState(() => _pendingRequestId = null);
            },
          ),
        ],
      ),
    );
  }

  Widget _buildStatsSection() {
    final s = _stats;
    return Padding(
      padding:
          const EdgeInsets.symmetric(horizontal: AppConstants.paddingLarge),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Your Stats', style: HomeDesignSystem.sectionTitle()),
          const SizedBox(height: 16),
          Row(children: [
            Expanded(
              child: StatTile(
                  icon: Icons.route_rounded,
                  value: '${s?.totalBookings ?? 0}',
                  label: 'Total Rides',
                  color: AuthDesignTokens.routeBlue),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: StatTile(
                  icon: Icons.check_circle_rounded,
                  value: '${s?.completedRides ?? 0}',
                  label: 'Completed Rides',
                  color: AppColors.success),
            ),
          ]),
          const SizedBox(height: 12),
          Row(children: [
            Expanded(
              child: StatTile(
                  icon: Icons.pending_actions_rounded,
                  value: '${s?.activeBookings ?? 0}',
                  label: 'Scheduled',
                  color: AuthDesignTokens.brandAction),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: StatTile(
                  icon: Icons.eco_rounded,
                  value:
                      '${(s?.carbonFootprintSavedKg ?? 0).toStringAsFixed(1)} kg',
                  label: 'CO₂ Saved',
                  color: AppColors.success),
            ),
          ]),
        ],
      ),
    );
  }

  // ───────────────────────────────────────────────────────
  //  SCHEDULE RIDES TAB
  // ───────────────────────────────────────────────────────
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
        _showRideSearchSheet(
          initialOrigin: result.origin,
          initialDestination: result.destination,
        );
      },
    );
  }

  // ───────────────────────────────────────────────────────
  //  MY RIDES TAB
  // ───────────────────────────────────────────────────────
  Widget _buildPassengerMyRidesBackground() {
    return HomeDesignSystem.driverHomeSoftWhiteBackground();
  }

  Widget _buildMyRidesTab() {
    return Stack(
      children: [
        _buildPassengerMyRidesBackground(),
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
                          color: _profileHomeTextPrimary,
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
                          color: _profileHomeTextSecondary.withValues(alpha: 0.75),
                        ),
                      ),
                      const SizedBox(height: 14),
                      Row(
                        children: [
                          Expanded(
                            child: _myRidesActionButton(
                              icon: Icons.tune_rounded,
                              label: 'Filters',
                              onTap: _showPassengerRideFiltersSheet,
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
                        ? const SyloLoader()
                        : _ridesError != null
                            ? SyloError(
                                message: _ridesError!,
                                onRetry: () =>
                                    _loadBookings(filter: _activeFilter),
                              )
                            : _bookings.isEmpty
                                ? SyloEmpty(
                                    icon: Icons.directions_car_rounded,
                                    title: 'No rides yet',
                                    subtitle:
                                        'Your ride history will appear here',
                                    actionLabel: 'Find a Ride',
                                    onAction: _openScheduleRidesTab,
                                  )
                                : RefreshIndicator(
                                    onRefresh: _refreshHomeData,
                                    color: AuthDesignTokens.brandAction,
                                    triggerMode:
                                        RefreshIndicatorTriggerMode.anywhere,
                                    child: _desktopRefreshScrollable(
                                      ListView.separated(
                                        physics:
                                            const AlwaysScrollableScrollPhysics(
                                          parent: BouncingScrollPhysics(),
                                        ),
                                        padding: const EdgeInsets.only(
                                          left: 0,
                                          right: 0,
                                          bottom: 18,
                                        ),
                                        itemCount: _bookings.length,
                                        separatorBuilder: (_, __) =>
                                            const SizedBox(height: 10),
                                        itemBuilder: (_, i) {
                                          final b = _bookings[i];
                                          return _buildPassengerMyRideCard(
                                            b,
                                            index: i,
                                            totalBookings: _bookings.length,
                                            highlight: i == 0,
                                          );
                                        },
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

  Widget _myRidesActionButton({
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

  Future<void> _showPassengerRideFiltersSheet() async {
    final options = <Map<String, String?>>[
      {'label': 'All', 'value': null},
      {'label': 'Scheduled', 'value': 'active'},
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
              final isSelected = _activeFilter == entry['value'];
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
                  setState(() => _activeFilter = entry['value']);
                  _loadBookings(filter: entry['value']);
                },
              );
            }).toList(),
          ),
        ),
      ),
    );
  }

  Widget _buildPassengerMyRideCard(
    RideBooking booking, {
    required int index,
    required int totalBookings,
    bool highlight = false,
  }) {
    final ride = booking.ride;
    final status = booking.effectiveDisplayStatus;
    final statusColor = _statusColor(status);
    final departureText = _formatDateTime(ride?.departureTime ?? booking.bookingTime);
    final durationText = ride?.estimatedDuration != null
        ? '${ride!.estimatedDuration!.round()} mins'
        : '—';
    final distanceText = ride?.routeDistanceKm != null
        ? '${ride!.routeDistanceKm!.toStringAsFixed(1)} mi'
        : '—';
    final rideStatus = (ride?.status ?? '').toLowerCase();
    final bookingStatus = booking.status.toLowerCase();
    final isActiveBooking = booking.isActive ||
        bookingStatus == 'booked' ||
        bookingStatus == 'reserved' ||
        bookingStatus == 'confirmed';
    final isOpenRide = rideStatus == 'open' && isActiveBooking;
    final showOpenHeroStyle = isOpenRide;
    final enableCardTap = !isOpenRide;
    final rideNumber = (totalBookings > 0)
        ? (totalBookings - index).clamp(1, totalBookings)
        : (index + 1);
    final perSeatPrice = ride?.pricePerSeat ?? booking.totalPrice;

    return GestureDetector(
      onTap: enableCardTap
          ? () {
              Navigator.pushNamed(
                context,
                '/ride-detail',
                arguments: booking.rideId,
              );
            }
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
                  color: highlight
                      ? const Color(0xFF1ED760).withValues(alpha: 0.86)
                      : Colors.white.withValues(alpha: 0.18),
                  width: highlight ? 1.6 : 1.0,
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
                          horizontal: 10,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: statusColor.withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(
                          status.toUpperCase(),
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
                      const Icon(Icons.circle, size: 7, color: Color(0xFF65F4A5)),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          ride?.origin ?? 'Unknown origin',
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
                      Icon(
                        Icons.circle_outlined,
                        size: 8,
                        color: Colors.white.withValues(alpha: 0.72),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          ride?.destination ?? 'Unknown destination',
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
                        Icon(
                          Icons.schedule_rounded,
                          size: 14,
                          color: Colors.white.withValues(alpha: 0.58),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          durationText,
                          style: GoogleFonts.inter(
                            color: Colors.white.withValues(alpha: 0.74),
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(width: 16),
                        Icon(
                          Icons.route_rounded,
                          size: 14,
                          color: Colors.white.withValues(alpha: 0.58),
                        ),
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
                              'Rs ${perSeatPrice.toStringAsFixed(0)}',
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
                                'Rs ${perSeatPrice.toStringAsFixed(2)}',
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
                            onPressed: () {
                              Navigator.pushNamed(
                                context,
                                '/ride-detail',
                                arguments: booking.rideId,
                              );
                            },
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
                    departureText,
                    style: GoogleFonts.inter(
                      color: Colors.white.withValues(alpha: 0.62),
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
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

  // ───────────────────────────────────────────────────────
  //  PROFILE TAB
  // ───────────────────────────────────────────────────────
  Widget _buildProfileTab() {
    final user = _user;
    final bookingStats = _stats ?? _emptyStats;
    final isPassengerVerified =
        _isKycStatusLoaded ? _isKycVerified : (_user?.isVerified == true);
    return Stack(
      children: [
        HomeDesignSystem.driverHomeSoftWhiteBackground(),
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
                      decoration: _profileHomeGlass(
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
                            'Passenger Profile',
                            style: GoogleFonts.inter(
                              fontSize: 22,
                              fontWeight: FontWeight.w900,
                              letterSpacing: 0.2,
                              color: _profileHomeTextPrimary,
                            ),
                          ),
                          const Spacer(),
                          Material(
                            color: Colors.transparent,
                            child: InkWell(
                              onTap: () =>
                                  Navigator.pushNamed(context, '/profile-edit'),
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
                                  fallbackInitials: user?.initials ?? 'P',
                                ),
                              ),
                            ),
                            Positioned(
                              right: 0,
                              bottom: 2,
                              child: Material(
                                color: Colors.transparent,
                                child: InkWell(
                                  onTap: _handlePassengerProfilePhotoAction,
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
                          user?.fullName ?? 'Passenger',
                          style: GoogleFonts.inter(
                            fontSize: 36,
                            height: 1.02,
                            fontWeight: FontWeight.w900,
                            letterSpacing: 0.1,
                            color: _profileHomeTextPrimary,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        if (user?.email != null) ...[
                          const SizedBox(height: 8),
                          Text(
                            user!.email,
                            style: GoogleFonts.inter(
                              fontSize: 14,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 0.2,
                              color: _profileHomeTextSecondary,
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
                          label: 'BOOKINGS',
                          value: '${bookingStats.totalBookings}',
                          icon: Icons.confirmation_number_rounded,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _buildProfileStatCard(
                          label: 'COMPLETED',
                          value: '${bookingStats.completedRides}',
                          icon: Icons.task_alt_rounded,
                        ),
                      ),
                    ],
                  ),
                  _profileSectionHeader('SETTINGS & ACCOUNT'),
                  _profileMenuItem(Icons.edit_rounded, 'Edit Profile',
                      () => Navigator.pushNamed(context, '/profile-edit')),
                  _profileMenuItem(Icons.account_balance_wallet_rounded,
                      'Wallet', () => Navigator.pushNamed(context, '/wallet')),
                  _profileMenuItem(Icons.history_rounded, 'Ride History', () {
                    setState(() => _selectedNavIndex = 3);
                    _loadBookings(filter: _activeFilter);
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
                  _profileMenuItem(
                    Icons.verified_user_rounded,
                    'Verification Status',
                    () => Navigator.pushNamed(context, '/verification'),
                    trailing: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 3,
                      ),
                      decoration: BoxDecoration(
                        color: (isPassengerVerified
                                ? const Color(0xFF1ED760)
                                : Colors.orangeAccent)
                            .withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(999),
                        border: Border.all(
                          color: (isPassengerVerified
                                  ? const Color(0xFF1ED760)
                                  : Colors.orangeAccent)
                              .withValues(alpha: 0.55),
                        ),
                      ),
                      child: Text(
                        isPassengerVerified ? 'VERIFIED' : 'UNVERIFIED',
                        style: GoogleFonts.inter(
                          fontSize: 11,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 1.2,
                          color: isPassengerVerified
                              ? const Color(0xFF0B6B39)
                              : const Color(0xFF7A4400),
                        ),
                      ),
                    ),
                  ),
                  _profileSectionHeader('SUPPORT'),
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
                      decoration: _profileHomeGlass(
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
                            color: _profileHomeTextPrimary,
                          ),
                        ),
                        subtitle: Text(
                          'Sylo v1.0.0',
                          style: GoogleFonts.inter(
                            fontSize: 13,
                            fontWeight: FontWeight.w500,
                            color: _profileHomeTextSecondary.withValues(
                                alpha: 0.9),
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
                          color:
                              _profileHomeTextPrimary.withValues(alpha: 0.32),
                          width: 1.1,
                        ),
                        foregroundColor: _profileHomeTextPrimary,
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
                          color: _profileHomeTextSecondary.withValues(
                            alpha: 0.85,
                          ),
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
        decoration: _profileHomeGlass(
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
                    color: _profileHomeTextSecondary,
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
                color: _profileHomeTextPrimary,
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

  Widget _profileMenuItemCard({
    required IconData icon,
    required String title,
    required VoidCallback onTap,
    required Color color,
    Widget? trailing,
  }) {
    final isDanger = color == AppColors.error;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: HomeDesignSystem.frostLayer(
        blur: 8,
        radius: 16,
        child: Container(
          decoration: _profileHomeGlass(
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
                        color: color.withValues(alpha: 0.14),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Icon(
                        icon,
                        color: _profileSymbolShade(color),
                        size: 18,
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Text(
                        title,
                        style: GoogleFonts.inter(
                          fontWeight: FontWeight.w700,
                          fontSize: 16,
                          letterSpacing: 0.1,
                          color: isDanger
                              ? AppColors.error
                              : _profileHomeTextPrimary,
                        ),
                      ),
                    ),
                    if (trailing != null) ...[
                      trailing,
                      const SizedBox(width: 8),
                    ],
                    Icon(
                      Icons.chevron_right_rounded,
                      size: 20,
                      color: isDanger
                          ? AppColors.error
                          : _profileHomeTextSecondary.withValues(alpha: 0.7),
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

  Widget _profileMenuItem(IconData icon, String title, VoidCallback onTap,
      {Color? color, Widget? trailing}) {
    return _profileMenuItemCard(
      icon: icon,
      title: title,
      onTap: onTap,
      color: color ?? AuthDesignTokens.routeBlue,
      trailing: trailing,
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
            color: _profileHomeTextSecondary,
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
          decoration: _profileHomeGlass(
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
                color: _profileHomeTextPrimary,
              ),
            ),
            subtitle: Text(
              subtitle,
              style: GoogleFonts.inter(
                fontSize: 13,
                fontWeight: FontWeight.w500,
                color: _profileHomeTextSecondary.withValues(alpha: 0.9),
                height: 1.3,
              ),
            ),
            value: value,
            activeColor: AuthDesignTokens.brandAction,
            inactiveThumbColor: _profileHomeTextPrimary.withValues(alpha: 0.88),
            inactiveTrackColor:
                _profileHomeTextSecondary.withValues(alpha: 0.26),
            onChanged: onChanged,
          ),
        ),
      ),
    );
  }

  // ───────────────────────────────────────────────────────
  //  BOTTOM SHEETS & DIALOGS
  // ───────────────────────────────────────────────────────

  void _showRideSearchSheet({
    PickedLocation? initialOrigin,
    PickedLocation? initialDestination,
  }) {
    PickedLocation? pickedOrigin = initialOrigin;
    PickedLocation? pickedDestination = initialDestination;
    List<Ride> results = [];
    Set<String> alreadyBookedRideIds = <String>{};
    Set<String> previouslyCancelledRideIds = <String>{};
    bool searching = false;
    bool hasSearched = false;
    bool showOriginError = false;
    bool showDestinationError = false;
    bool showDateError = false;
    bool showWindowStartError = false;
    bool showWindowEndError = false;
    bool showTimeWindowError = false;
    String? timeWindowErrorText;

    // Fare estimation state
    FareEstimate? fareEstimate;
    bool fareLoading = false;
    double? routeDistanceKm;
    DirectionsRoute? routeDetails;
    int seatsNeeded = 1;
    int? driverTotalSeats;
    int fareRequestVersion = 0;
    bool didTriggerInitialFare = false;
    bool didTriggerInitialSlots = false;
    DateTime selectedDay = DateTime.now().add(const Duration(hours: 1));
    TimeOfDay? selectedWindowStartTime;
    TimeOfDay? selectedWindowEndTime;
    bool loadingOccupiedSlots = false;
    bool showSlotConflictError = false;
    List<Map<String, dynamic>> occupiedSlots = [];
    int slotsRequestVersion = 0;
    int searchRequestVersion = 0;

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
          DateTime(selectedDay.year, selectedDay.month, selectedDay.day);
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

    DateTime withTime(DateTime day, TimeOfDay time) {
      return DateTime(
        day.year,
        day.month,
        day.day,
        time.hour,
        time.minute,
      );
    }

    DateTime? selectedWindowStartDateTime() {
      final start = selectedWindowStartTime;
      if (start == null) return null;
      return withTime(selectedDay, start);
    }

    DateTime? selectedWindowEndDateTime() {
      final end = selectedWindowEndTime;
      if (end == null) return null;
      return withTime(selectedDay, end);
    }

    String formatDay(DateTime dt) {
      final d = dt.day.toString().padLeft(2, '0');
      final m = dt.month.toString().padLeft(2, '0');
      return '$d/$m/${dt.year}';
    }

    String formatTimeOfDayLabel(TimeOfDay time) {
      final h = time.hour;
      final m = time.minute.toString().padLeft(2, '0');
      final period = h >= 12 ? 'PM' : 'AM';
      final h12 = h > 12 ? h - 12 : (h == 0 ? 12 : h);
      return '$h12:$m $period';
    }

    String? validateSelectedWindow() {
      final start = selectedWindowStartDateTime();
      final end = selectedWindowEndDateTime();
      if (start == null || end == null) return null;
      if (!end.isAfter(start)) {
        return 'End time must be after start time.';
      }
      return null;
    }

    void invalidateSearchResults(StateSetter setSheetState) {
      // Hide stale search results and cancel any in-flight search response.
      searchRequestVersion++;
      setSheetState(() {
        hasSearched = false;
        results = [];
        alreadyBookedRideIds = <String>{};
        previouslyCancelledRideIds = <String>{};
        searching = false;
      });
    }

    bool slotConflictsWithSelection(Map<String, dynamic> slot) {
      final startRaw = slot['start_time']?.toString();
      final endRaw = slot['end_time']?.toString();
      final slotStart = startRaw != null ? DateTime.tryParse(startRaw) : null;
      final slotEnd = endRaw != null ? DateTime.tryParse(endRaw) : null;
      if (slotStart == null || slotEnd == null) return false;

      final selectedStart = selectedWindowStartDateTime();
      final selectedEnd = selectedWindowEndDateTime();
      if (selectedStart == null || selectedEnd == null) return false;
      final selectedStartUtc = selectedStart.toUtc();
      final selectedEndUtc = selectedEnd.toUtc();
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

    String slotSourceLabel(Map<String, dynamic> slot) {
      final source = (slot['source']?.toString() ?? '').trim().toLowerCase();
      if (source == 'ride_request') return 'Ride Request';
      if (source == 'passenger_booking' ||
          source == 'passenger_booking_legacy') {
        return 'Booked Ride';
      }
      return 'Occupied Slot';
    }

    Future<void> loadOccupiedSlots(StateSetter setSheetState) async {
      final requestVersion = ++slotsRequestVersion;
      setSheetState(() {
        loadingOccupiedSlots = true;
        showSlotConflictError = false;
      });
      try {
        final localDateKey = dateKeyLocal(selectedDay);
        final utcDateKey = dateKeyUtc(selectedDay);
        final timezoneOffsetMinutes = selectedDay.timeZoneOffset.inMinutes;

        var slots = await _rideService.getMyOccupiedSlots(
          targetDate: localDateKey,
          mode: 'passenger',
          timezoneOffsetMinutes: timezoneOffsetMinutes,
        );
        slots = slotsForSelectedLocalDay(slots);

        if (slots.isEmpty && localDateKey != utcDateKey) {
          final utcSlots = await _rideService.getMyOccupiedSlots(
            targetDate: utcDateKey,
            mode: 'passenger',
          );
          slots = slotsForSelectedLocalDay(mergeSlotsByWindow(slots, utcSlots));
        }

        if (requestVersion != slotsRequestVersion) return;
        setSheetState(() {
          occupiedSlots = slots;
          loadingOccupiedSlots = false;
        });
      } catch (_) {
        if (requestVersion != slotsRequestVersion) return;
        setSheetState(() {
          occupiedSlots = [];
          loadingOccupiedSlots = false;
        });
      }
    }

    Future<void> calculateFare(StateSetter setSheetState) async {
      if (pickedOrigin == null || pickedDestination == null) {
        fareRequestVersion++;
        setSheetState(() {
          fareEstimate = null;
          fareLoading = false;
          routeDistanceKm = null;
          routeDetails = null;
        });
        return;
      }
      final requestVersion = ++fareRequestVersion;
      setSheetState(() => fareLoading = true);
      try {
        // Get route distance from Google Maps Directions API
        final directions = await _mapsService.getDirections(
          origin: pickedOrigin!.latLng,
          destination: pickedDestination!.latLng,
          originPlaceId: pickedOrigin!.placeId,
          destinationPlaceId: pickedDestination!.placeId,
        );
        if (requestVersion != fareRequestVersion) {
          return;
        }
        if (directions != null && directions.bestRoute != null) {
          routeDetails = directions.bestRoute;
          routeDistanceKm = directions.bestRoute!.distanceKm;
          // Try server-side fare estimate first, fallback to local calculator
          try {
            final serverFare = await _rideService.getFareEstimate(
              distanceKm: routeDistanceKm!,
              durationMinutes: routeDetails!.durationMinutes.toDouble(),
              totalSeats: seatsNeeded.clamp(1, 8),
            );
            fareEstimate = FareEstimate(
              distanceKm: (serverFare['distance_km'] as num).toDouble(),
              totalSeats: (serverFare['total_seats'] as num).toInt(),
              fuelCostRaw: (serverFare['fuel_cost_raw'] as num).toDouble(),
              timeCost: ((serverFare['time_cost'] ?? 0) as num).toDouble(),
              durationMinutes: ((serverFare['duration_minutes'] ??
                      routeDetails!.durationMinutes) as num)
                  .toDouble(),
              baseFare: (serverFare['base_fare'] as num).toDouble(),
              platformFee: (serverFare['platform_fee'] as num).toDouble(),
              totalFare: (serverFare['total_fare'] as num).toDouble(),
              farePerSeat: (serverFare['fare_per_seat'] as num).toDouble(),
              petrolPriceUsed: ((serverFare['petrol_price_used'] ??
                      serverFare['petrol_price']) as num)
                  .toDouble(),
              fuelAverageUsed: ((serverFare['fuel_average_used'] ??
                          serverFare['fuel_average']) as num?)
                      ?.toDouble() ??
                  12.0,
            );
          } catch (_) {
            // Fallback to local calculator
            fareEstimate = FareCalculator.estimate(
              distanceKm: routeDistanceKm!,
              durationMinutes: routeDetails!.durationMinutes.toDouble(),
              totalSeats: seatsNeeded.clamp(1, 8),
            );
          }
        }
      } catch (_) {}
      if (requestVersion == fareRequestVersion) {
        setSheetState(() => fareLoading = false);
      }
    }

    _showPassengerScheduleDetails(
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
            onPressed: _returnToScheduleMap,
          ),
          backgroundColor: Colors.transparent,
          surfaceTintColor: Colors.transparent,
          elevation: 0,
          centerTitle: true,
          title: Text(
            'Find Schedule Rides',
            style: GoogleFonts.inter(
              fontSize: 24,
              fontWeight: FontWeight.w900,
              color: const Color(0xFF0B3D24),
            ),
          ),
        ),
        body: Stack(children: [
          HomeDesignSystem.driverHomeSoftWhiteBackground(),
          StatefulBuilder(builder: (ctx, setSheetState) {
            if (!didTriggerInitialFare &&
              pickedOrigin != null &&
              pickedDestination != null) {
              didTriggerInitialFare = true;
              WidgetsBinding.instance.addPostFrameCallback((_) {
                if (!mounted) return;
                calculateFare(setSheetState);
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
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
                decoration: const BoxDecoration(
                  color: Color(0xFFD9FCE8),
                  borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
                ),
                child: ListView(
              children: [
                const SizedBox(height: 8),
                // ── Route preview ──
                if (pickedOrigin != null && pickedDestination != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 14),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(14),
                      child: SizedBox(
                        height: 280,
                        child: RouteMapWidget(
                          origin: pickedOrigin!.latLng,
                          destination: pickedDestination!.latLng,
                          originPlaceId: pickedOrigin!.placeId,
                          destinationPlaceId: pickedDestination!.placeId,
                          originLabel: pickedOrigin!.address,
                          destinationLabel: pickedDestination!.address,
                          height: 280,
                          showAlternatives: true,
                          interactive: false,
                          showInfoCard: false,
                        ),
                      ),
                    ),
                  ),
                // ── Origin picker ──
                AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: showOriginError
                          ? AppColors.error
                          : Colors.transparent,
                      width: showOriginError ? 1.5 : 0,
                    ),
                  ),
                  child: PlaceSearchField(
                    hint: 'From – type to search or tap map',
                    dotColor: AppColors.primary,
                    textColor: const Color(0xFF0B3D24),
                    hintColor: const Color(0xFF114B2D).withValues(alpha: 0.7),
                    mapIconColor: const Color(0xFF0B3D24),
                    backgroundColor: const Color(0xFFE9FFF2),
                    borderColor: const Color(0xFF5DAA7E),
                    value: pickedOrigin,
                    onTextChanged: (value) {
                      final query = value.trim();
                      final currentAddress = pickedOrigin?.address.trim() ?? '';
                      if (query.isEmpty ||
                          (pickedOrigin != null && query != currentAddress)) {
                        fareRequestVersion++;
                        setSheetState(() {
                          pickedOrigin = null;
                          showOriginError = false;
                          fareEstimate = null;
                          fareLoading = false;
                          routeDistanceKm = null;
                          routeDetails = null;
                        });
                      }
                    },
                    onPlaceSelected: (place) {
                      setSheetState(() {
                        pickedOrigin = place;
                        showOriginError = false;
                      });
                      calculateFare(setSheetState);
                    },
                  ),
                ),
                if (showOriginError)
                  const Padding(
                    padding: EdgeInsets.only(left: 12, top: 6),
                    child: Text(
                      'Start point is required',
                      style: TextStyle(color: AppColors.error, fontSize: 12),
                    ),
                  ),
                const SizedBox(height: 12),
                // ── Destination picker ──
                AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: showDestinationError
                          ? AppColors.error
                          : Colors.transparent,
                      width: showDestinationError ? 1.5 : 0,
                    ),
                  ),
                  child: PlaceSearchField(
                    hint: 'To – type to search or tap map',
                    dotColor: AppColors.accent,
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
                        fareRequestVersion++;
                        setSheetState(() {
                          pickedDestination = null;
                          showDestinationError = false;
                          fareEstimate = null;
                          fareLoading = false;
                          routeDistanceKm = null;
                          routeDetails = null;
                        });
                      }
                    },
                    onPlaceSelected: (place) {
                      setSheetState(() {
                        pickedDestination = place;
                        showDestinationError = false;
                      });
                      calculateFare(setSheetState);
                    },
                  ),
                ),
                if (showDestinationError)
                  const Padding(
                    padding: EdgeInsets.only(left: 12, top: 6),
                    child: Text(
                      'Destination is required',
                      style: TextStyle(color: AppColors.error, fontSize: 12),
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
                      });
                      calculateFare(setSheetState);
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
                // ── Fare Estimate Card ──
                if (routeDetails != null && !fareLoading)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 12),
                      decoration: HomeDesignSystem.darkTopBarSurface(
                        radius: 14,
                      ),
                      child: Builder(builder: (_) {
                        final durationMin =
                            routeDetails!.durationMinutes.round();
                        final departureReference =
                            selectedWindowStartDateTime() ?? selectedDay;
                        final arrival = departureReference
                            .add(Duration(minutes: durationMin));
                        final h = arrival.hour;
                        final m = arrival.minute.toString().padLeft(2, '0');
                        final period = h >= 12 ? 'PM' : 'AM';
                        final h12 = h > 12 ? h - 12 : (h == 0 ? 12 : h);
                        return Row(
                          mainAxisAlignment: MainAxisAlignment.spaceAround,
                          children: [
                            _routeInfoChip(
                              Icons.straighten_rounded,
                              AppColors.primary,
                              '${routeDetails!.distanceKm.toStringAsFixed(1)} km',
                              'Distance',
                            ),
                            Container(
                                width: 1, height: 36, color: AppColors.border),
                            _routeInfoChip(
                              Icons.timer_rounded,
                              AppColors.secondary,
                              '~$durationMin min',
                              'Duration',
                            ),
                            Container(
                                width: 1, height: 36, color: AppColors.border),
                            _routeInfoChip(
                              Icons.access_time_rounded,
                              AppColors.success,
                              '$h12:$m $period',
                              'Arrives',
                            ),
                          ],
                        );
                      }),
                    ),
                  ),
                if (fareLoading)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(16),
                      decoration: HomeDesignSystem.darkTopBarSurface(
                        radius: 14,
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: AppColors.primary)),
                          const SizedBox(width: 10),
                          Text('Calculating fare...',
                              style: TextStyle(
                                  color: AppColors.textSecondary,
                                  fontSize: 13)),
                        ],
                      ),
                    ),
                  ),
                if (fareEstimate != null && !fareLoading)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(16),
                      decoration: HomeDesignSystem.darkTopBarSurface(
                        radius: 14,
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Icon(Icons.calculate_rounded,
                                  color: AppColors.primary, size: 18),
                              const SizedBox(width: 8),
                              Text('Estimated Trip Cost',
                                  style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      fontSize: 15,
                                      color: Colors.white)),
                            ],
                          ),
                          const SizedBox(height: 12),
                          Row(
                            children: [
                              Expanded(
                                child: _fareInfoTile(
                                  Icons.route_rounded,
                                  '${fareEstimate!.distanceKm.toStringAsFixed(1)} km',
                                  'Route Distance',
                                ),
                              ),
                              Expanded(
                                child: _fareInfoTile(
                                  Icons.payments_rounded,
                                  'Rs ${fareEstimate!.farePerSeat.toStringAsFixed(0)}',
                                  'Estimated Rs / Seat',
                                ),
                              ),
                              Expanded(
                                child: _fareInfoTile(
                                  Icons.receipt_long_rounded,
                                  'Rs ${fareEstimate!.totalFare.toStringAsFixed(0)}',
                                  'Estimated Trip Total',
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 14),
                          // Seats selector
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('Seats you want to book:',
                                  style: TextStyle(
                                      fontSize: 13,
                                      color: Colors.white.withValues(alpha: 0.84))),
                              const SizedBox(height: 10),
                              Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: List.generate(8, (i) {
                                  final n = i + 1;
                                  final isSelected = seatsNeeded == n;
                                  return GestureDetector(
                                    onTap: () {
                                      setSheetState(() => seatsNeeded = n);
                                      calculateFare(setSheetState);
                                    },
                                    child: Container(
                                      width: 36,
                                      height: 36,
                                      decoration: BoxDecoration(
                                        color: isSelected
                                            ? AppColors.primary
                                            : Colors.white.withValues(alpha: 0.12),
                                        borderRadius: BorderRadius.circular(10),
                                        border: Border.all(
                                          color: isSelected
                                              ? AppColors.primary
                                              : Colors.white.withValues(alpha: 0.28),
                                        ),
                                      ),
                                      child: Center(
                                        child: Text(
                                          '$n',
                                          style: TextStyle(
                                            fontWeight: FontWeight.bold,
                                            color: isSelected
                                                ? Colors.white
                                                : Colors.white,
                                          ),
                                        ),
                                      ),
                                    ),
                                  );
                                }),
                              ),
                              const SizedBox(height: 14),
                              Divider(
                                  height: 1,
                                  thickness: 1,
                                  color: Colors.white.withValues(alpha: 0.2)),
                              const SizedBox(height: 14),
                              Text('Driver total offered seats:',
                                  style: TextStyle(
                                      fontSize: 13,
                                      color: Colors.white.withValues(alpha: 0.84))),
                              const SizedBox(height: 10),
                              Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                children: [
                                  GestureDetector(
                                    onTap: () {
                                      setSheetState(
                                          () => driverTotalSeats = null);
                                    },
                                    child: Container(
                                      height: 36,
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 12),
                                      decoration: BoxDecoration(
                                        color: driverTotalSeats == null
                                            ? AppColors.primary
                                            : Colors.white.withValues(alpha: 0.12),
                                        borderRadius: BorderRadius.circular(10),
                                        border: Border.all(
                                          color: driverTotalSeats == null
                                              ? AppColors.primary
                                              : Colors.white.withValues(alpha: 0.28),
                                        ),
                                      ),
                                      child: Center(
                                        child: Text(
                                          'Any',
                                          style: TextStyle(
                                            fontWeight: FontWeight.bold,
                                            color: driverTotalSeats == null
                                                ? Colors.white
                                                  : Colors.white,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                  ...List.generate(8, (i) {
                                    final n = i + 1;
                                    final isSelected = driverTotalSeats == n;
                                    return GestureDetector(
                                      onTap: () {
                                        setSheetState(() {
                                          driverTotalSeats = n;
                                        });
                                      },
                                      child: Container(
                                        width: 36,
                                        height: 36,
                                        decoration: BoxDecoration(
                                          color: isSelected
                                              ? AppColors.primary
                                              : Colors.white.withValues(alpha: 0.12),
                                          borderRadius:
                                              BorderRadius.circular(10),
                                          border: Border.all(
                                            color: isSelected
                                                ? AppColors.primary
                                                : Colors.white.withValues(alpha: 0.28),
                                          ),
                                        ),
                                        child: Center(
                                          child: Text(
                                            '$n',
                                            style: TextStyle(
                                              fontWeight: FontWeight.bold,
                                              color: isSelected
                                                  ? Colors.white
                                                  : Colors.white,
                                            ),
                                          ),
                                        ),
                                      ),
                                    );
                                  }),
                                ],
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                const SizedBox(height: 8),
                AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color:
                          showDateError ? AppColors.error : Colors.transparent,
                      width: showDateError ? 1.5 : 0,
                    ),
                  ),
                  child: GestureDetector(
                    onTap: () async {
                      final picked = await showDatePicker(
                        context: ctx,
                        initialDate: selectedDay,
                        firstDate: DateTime.now(),
                        lastDate: DateTime.now().add(const Duration(days: 90)),
                      );
                      if (picked != null) {
                        invalidateSearchResults(setSheetState);
                        setSheetState(() {
                          selectedDay = DateTime(
                            picked.year,
                            picked.month,
                            picked.day,
                          );
                          showDateError = false;
                          showTimeWindowError = false;
                          timeWindowErrorText = null;
                          showSlotConflictError = false;
                        });
                        loadOccupiedSlots(setSheetState);
                      }
                    },
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 16),
                      decoration: BoxDecoration(
                        color: AppColors.backgroundLight,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: AppColors.border),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.calendar_today_rounded,
                              color: AppColors.textHint, size: 20),
                          const SizedBox(width: 12),
                          Text(
                            'Date: ${formatDay(selectedDay)}',
                            style: const TextStyle(fontSize: 15),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                if (showDateError)
                  const Padding(
                    padding: EdgeInsets.only(left: 12, top: 6),
                    child: Text(
                      'Please select a day.',
                      style: TextStyle(color: AppColors.error, fontSize: 12),
                    ),
                  ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 150),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(
                            color: showWindowStartError
                                ? AppColors.error
                                : Colors.transparent,
                            width: showWindowStartError ? 1.5 : 0,
                          ),
                        ),
                        child: GestureDetector(
                          onTap: () async {
                            final picked = await showTimePicker(
                              context: ctx,
                              initialTime: selectedWindowStartTime ??
                                  const TimeOfDay(hour: 8, minute: 0),
                            );
                            if (picked != null) {
                              invalidateSearchResults(setSheetState);
                              setSheetState(() {
                                selectedWindowStartTime = picked;
                                showWindowStartError = false;
                                showTimeWindowError = false;
                                timeWindowErrorText = null;
                                showSlotConflictError = false;
                              });
                            }
                          },
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 14),
                            decoration: BoxDecoration(
                              color: AppColors.backgroundLight,
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(color: AppColors.border),
                            ),
                            child: Row(
                              children: [
                                Icon(Icons.access_time_rounded,
                                    color: AppColors.textHint, size: 18),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    selectedWindowStartTime == null
                                        ? 'From Time'
                                        : formatTimeOfDayLabel(
                                            selectedWindowStartTime!),
                                    style: TextStyle(
                                      fontSize: 14,
                                      color: selectedWindowStartTime == null
                                          ? AppColors.textSecondary
                                          : AppColors.textPrimary,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 150),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(
                            color: showWindowEndError
                                ? AppColors.error
                                : Colors.transparent,
                            width: showWindowEndError ? 1.5 : 0,
                          ),
                        ),
                        child: GestureDetector(
                          onTap: () async {
                            final picked = await showTimePicker(
                              context: ctx,
                              initialTime: selectedWindowEndTime ??
                                  const TimeOfDay(hour: 10, minute: 0),
                            );
                            if (picked != null) {
                              invalidateSearchResults(setSheetState);
                              setSheetState(() {
                                selectedWindowEndTime = picked;
                                showWindowEndError = false;
                                showTimeWindowError = false;
                                timeWindowErrorText = null;
                                showSlotConflictError = false;
                              });
                            }
                          },
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 14),
                            decoration: BoxDecoration(
                              color: AppColors.backgroundLight,
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(color: AppColors.border),
                            ),
                            child: Row(
                              children: [
                                Icon(Icons.access_time_filled_rounded,
                                    color: AppColors.textHint, size: 18),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    selectedWindowEndTime == null
                                        ? 'To Time'
                                        : formatTimeOfDayLabel(
                                            selectedWindowEndTime!),
                                    style: TextStyle(
                                      fontSize: 14,
                                      color: selectedWindowEndTime == null
                                          ? AppColors.textSecondary
                                          : AppColors.textPrimary,
                                    ),
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
                if (showWindowStartError)
                  const Padding(
                    padding: EdgeInsets.only(left: 12, top: 6),
                    child: Text(
                      'Start time is required.',
                      style: TextStyle(color: AppColors.error, fontSize: 12),
                    ),
                  ),
                if (showWindowEndError)
                  const Padding(
                    padding: EdgeInsets.only(left: 12, top: 6),
                    child: Text(
                      'End time is required.',
                      style: TextStyle(color: AppColors.error, fontSize: 12),
                    ),
                  ),
                if (showTimeWindowError)
                  Padding(
                    padding: const EdgeInsets.only(left: 12, top: 6),
                    child: Text(
                      timeWindowErrorText ??
                          'Please select a valid time window.',
                      style:
                          const TextStyle(color: AppColors.error, fontSize: 12),
                    ),
                  ),
                if (selectedWindowStartTime != null &&
                    selectedWindowEndTime != null)
                  Padding(
                    padding: const EdgeInsets.only(left: 2, top: 8),
                    child: Text(
                      'Window: ${formatTimeOfDayLabel(selectedWindowStartTime!)} - ${formatTimeOfDayLabel(selectedWindowEndTime!)}',
                      style: TextStyle(
                        fontSize: 12,
                        color: AppColors.textSecondary,
                        fontWeight: FontWeight.w600,
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
                            final isConflict = slotConflictsWithSelection(slot);
                            final sourceLabel = slotSourceLabel(slot);
                            final timeLabel = (start != null && end != null)
                                ? '${formatSlotTime(start)} - ${formatSlotTime(end)}'
                                : null;
                            final label = timeLabel == null
                                ? sourceLabel
                                : '$sourceLabel: $timeLabel';
                            return Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 10, vertical: 6),
                              decoration: BoxDecoration(
                                color: isConflict
                                    ? AppColors.error.withValues(alpha: 0.12)
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
                      style: TextStyle(color: AppColors.error, fontSize: 12),
                    ),
                  ),
                const SizedBox(height: 4),
                Container(
                  width: double.infinity,
                  decoration: HomeDesignSystem.darkTopBarSurface(radius: 14),
                  child: ElevatedButton.icon(
                    onPressed: searching
                        ? null
                        : () async {
                            final hasOrigin = pickedOrigin != null;
                            final hasDestination = pickedDestination != null;
                            final hasWindowStart =
                                selectedWindowStartTime != null;
                            final hasWindowEnd = selectedWindowEndTime != null;
                            final windowStart = selectedWindowStartDateTime();
                            final windowEnd = selectedWindowEndDateTime();
                            final windowValidationError =
                                validateSelectedWindow();

                            if (!hasOrigin ||
                                !hasDestination ||
                                !hasWindowStart ||
                                !hasWindowEnd ||
                                windowValidationError != null ||
                                windowStart == null ||
                                windowEnd == null) {
                              setSheetState(() {
                                hasSearched = true;
                                showOriginError = !hasOrigin;
                                showDestinationError = !hasDestination;
                                showDateError = false;
                                showWindowStartError = !hasWindowStart;
                                showWindowEndError = !hasWindowEnd;
                                showTimeWindowError =
                                    windowValidationError != null;
                                timeWindowErrorText = windowValidationError;
                              });
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text(
                                      'Please set route and valid time window'),
                                  backgroundColor: AppColors.error,
                                ),
                              );
                              return;
                            }

                            setSheetState(() {
                              searching = true;
                              hasSearched = true;
                            });
                            final requestVersion = ++searchRequestVersion;
                            try {
                              final canProceed =
                                  await _ensureAuthenticatedRideFlow(
                                actionLabel: 'search rides',
                              );
                              if (!canProceed) {
                                return;
                              }

                              final cancelledBookingsFuture = _silent(
                                _rideService.getMyBookings(
                                  statusFilter: 'cancelled',
                                ),
                              );
                              final activeBookingsFuture = _silent(
                                _rideService.getMyBookings(
                                  statusFilter: 'active',
                                ),
                              );

                              final fetched = await _rideService.searchRides(
                                origin: pickedOrigin?.address,
                                destination: pickedDestination?.address,
                                originLat: pickedOrigin?.latLng.latitude,
                                originLng: pickedOrigin?.latLng.longitude,
                                destinationLat:
                                    pickedDestination?.latLng.latitude,
                                destinationLng:
                                    pickedDestination?.latLng.longitude,
                                radiusKm: 5.0,
                                minSeats: seatsNeeded,
                                driverTotalSeats: driverTotalSeats,
                                departureAfter:
                                    windowStart.toUtc().toIso8601String(),
                                departureBefore:
                                    windowEnd.toUtc().toIso8601String(),
                              );
                              final cancelledBookings =
                                  (await cancelledBookingsFuture) ??
                                      <RideBooking>[];
                              final activeBookings =
                                  (await activeBookingsFuture) ??
                                      <RideBooking>[];
                              if (requestVersion != searchRequestVersion) {
                                return;
                              }
                              final bookedRideIds = activeBookings
                                  .map((booking) => booking.rideId.trim())
                                  .where((rideId) => rideId.isNotEmpty)
                                  .toSet();
                              final cancelledRideIds = cancelledBookings
                                  .map((booking) => booking.rideId.trim())
                                  .where((rideId) => rideId.isNotEmpty)
                                  .toSet();

                              final filtered = fetched.where((ride) {
                                final meetsSeatsNeeded =
                                    ride.remainingSeats >= seatsNeeded;
                                final meetsDriverTotal = driverTotalSeats ==
                                        null ||
                                    (ride.totalSeats != null &&
                                        ride.totalSeats == driverTotalSeats);
                                final departureLocal = ride.departureDatetime;
                                final withinSelectedWindow =
                                    departureLocal != null &&
                                        !departureLocal.isBefore(windowStart) &&
                                        !departureLocal.isAfter(windowEnd);
                                return meetsSeatsNeeded &&
                                    meetsDriverTotal &&
                                    withinSelectedWindow;
                              }).toList();

                              filtered.sort((a, b) {
                                final aAlreadyBooked =
                                    bookedRideIds.contains(a.id);
                                final bAlreadyBooked =
                                    bookedRideIds.contains(b.id);
                                if (aAlreadyBooked != bAlreadyBooked) {
                                  return aAlreadyBooked ? -1 : 1;
                                }

                                final aWasCancelled =
                                    cancelledRideIds.contains(a.id);
                                final bWasCancelled =
                                    cancelledRideIds.contains(b.id);
                                if (aWasCancelled != bWasCancelled) {
                                  return aWasCancelled ? -1 : 1;
                                }

                                final aDeparture = a.departureDatetime;
                                final bDeparture = b.departureDatetime;
                                if (aDeparture != null && bDeparture != null) {
                                  return aDeparture.compareTo(bDeparture);
                                }
                                return 0;
                              });

                              results = filtered;
                              alreadyBookedRideIds = bookedRideIds;
                              previouslyCancelledRideIds = cancelledRideIds;
                            } catch (e) {
                              if (requestVersion != searchRequestVersion) {
                                return;
                              }
                              results = [];
                              alreadyBookedRideIds = <String>{};
                              previouslyCancelledRideIds = <String>{};
                              if (e is DioException &&
                                  _isUnauthorizedRideFlowError(e)) {
                                await _handleUnauthorizedRideFlow(
                                  actionLabel: 'search rides',
                                );
                                return;
                              }

                              if (e is DioException &&
                                  _isDepartureTimeFutureValidationError(e)) {
                                await _showDepartureTimeFutureDialog(
                                  actionLabel: 'find rides',
                                );
                                return;
                              }

                              if (mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(
                                    content: Text(
                                      e is DioException
                                          ? extractError(e)
                                          : 'Failed to search rides',
                                    ),
                                    backgroundColor: AppColors.error,
                                  ),
                                );
                              }
                            } finally {
                              if (mounted &&
                                  requestVersion == searchRequestVersion) {
                                setSheetState(() => searching = false);
                              }
                            }
                          },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.transparent,
                      foregroundColor: const Color(0xFF43E892),
                      shadowColor: Colors.transparent,
                      elevation: 0,
                      padding: const EdgeInsets.symmetric(vertical: 15),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    icon: const Icon(Icons.search),
                    label: const Text('Search Rides'),
                  ),
                ),
                const SizedBox(height: 20),
                if (hasSearched) ...[
                  const SizedBox(height: 4),
                  Divider(height: 1, thickness: 1, color: AppColors.border),
                  const SizedBox(height: 18),
                  Center(
                    child: Text('Available Rides',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                            color: AppColors.textPrimary)),
                  ),
                  const SizedBox(height: 12),
                  if (searching)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 12),
                      child: Center(
                        child: SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: AppColors.primary),
                        ),
                      ),
                    ),
                  if (!searching && results.isEmpty)
                    Center(
                        child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.symmetric(
                              horizontal: 16, vertical: 14),
                          decoration: BoxDecoration(
                            color: const Color(0xFFE9FFF2),
                            borderRadius: BorderRadius.circular(14),
                            border:
                                Border.all(color: const Color(0xFF5DAA7E)),
                          ),
                          child: Column(
                            children: [
                              Icon(Icons.event_busy_rounded,
                                  size: 22, color: AppColors.textHint),
                              const SizedBox(height: 8),
                              Text('No scheduled rides available',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                      fontWeight: FontWeight.w700,
                                      fontSize: 16,
                                      color: AppColors.textPrimary)),
                              const SizedBox(height: 4),
                              Text(
                                  'Try changing route, time window, or seat filters.',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                      color: AppColors.textSecondary,
                                      fontSize: 12)),
                            ],
                          ),
                        ),
                      ],
                    )),
                  if (!searching)
                    ...results.map((ride) => Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: _availableRideCard(
                            ride,
                            seatsNeededForBooking: seatsNeeded,
                            isAlreadyBooked:
                                alreadyBookedRideIds.contains(ride.id),
                            wasPreviouslyCancelled:
                                previouslyCancelledRideIds.contains(ride.id),
                          ),
                        )),
                ],
              ],
            ),
              ),
            );
          }),
        ]),
      )),
    );
  }

  Widget _fareInfoTile(IconData icon, String value, String label) {
    return Column(
      children: [
        Icon(icon, color: AppColors.primary, size: 22),
        const SizedBox(height: 6),
        Text(value,
            style: TextStyle(
                fontWeight: FontWeight.bold,
                fontSize: 15,
                color: Colors.white)),
        const SizedBox(height: 2),
        Text(label,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: 12,
              color: Colors.white.withValues(alpha: 0.84),
            )),
      ],
    );
  }

  /// Small stat column used in the route summary bar.
  Widget _routeInfoChip(
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

  bool _isUnauthorizedRideFlowError(Object? error) {
    if (error is DioException) {
      final statusCode = error.response?.statusCode;
      if (statusCode == 401) return true;

      final extracted = extractError(error).toLowerCase();
      return extracted.contains('not authenticated') ||
          extracted.contains('not authorized') ||
          extracted.contains('could not validate credentials') ||
          extracted.contains('unauthorized');
    }

    final text = (error ?? '').toString().toLowerCase();
    return text.contains('401') &&
        (text.contains('not authenticated') || text.contains('unauthorized'));
  }

  bool _isAlreadyBookedRideError(DioException error) {
    final extracted = extractError(error).toLowerCase();
    return extracted.contains('you already booked this ride') ||
        extracted.contains('already have an active booking for this ride') ||
        extracted.contains('already booked this ride');
  }

  Future<void> _showAlreadyBookedDialog() async {
    if (!mounted) return;

    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Text('Already Booked'),
        content: const Text(
          'You have already booked this ride. Please check your Scheduled Rides.',
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

  Future<void> _handleUnauthorizedRideFlow({
    required String actionLabel,
  }) async {
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          'Your session expired while trying to $actionLabel. Please sign in again.',
        ),
        backgroundColor: AppColors.warning,
      ),
    );

    await _handleLogout();
  }

  Future<bool> _ensureAuthenticatedRideFlow({
    required String actionLabel,
  }) async {
    final token = await AuthService().getAccessToken();
    if (token != null && token.trim().isNotEmpty) {
      return true;
    }

    await _handleUnauthorizedRideFlow(actionLabel: actionLabel);
    return false;
  }

  Future<void> _openRideDetailSheetGuarded(
    Ride ride, {
    required int seatsNeededForBooking,
    bool isAlreadyBooked = false,
  }) async {
    final canProceed = await _ensureAuthenticatedRideFlow(
      actionLabel: 'view ride details',
    );
    if (!canProceed) return;

    await _showRideDetailSheet(
      ride,
      seatsNeededForBooking: seatsNeededForBooking,
      isAlreadyBooked: isAlreadyBooked,
    );
  }

  Widget _rideDetailMetaChip({
    required IconData icon,
    required String label,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.backgroundLight,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: AppColors.textHint),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              color: AppColors.textSecondary,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  String _driverInitials(String? fullName) {
    final parts = (fullName ?? '')
        .trim()
        .split(RegExp(r'\s+'))
        .where((token) => token.isNotEmpty)
        .toList();

    if (parts.isEmpty) return 'DR';
    if (parts.length == 1) {
      return parts.first.substring(0, 1).toUpperCase();
    }

    final first = parts.first.substring(0, 1).toUpperCase();
    final last = parts.last.substring(0, 1).toUpperCase();
    return '$first$last';
  }

  Widget _buildRideDriverAvatar(RideDriverSummary? summary) {
    final provider = _profileImageProvider(summary?.profilePhoto);
    return CircleAvatar(
      radius: 24,
      backgroundColor: AppColors.primary.withValues(alpha: 0.16),
      backgroundImage: provider,
      child: provider == null
          ? Text(
              _driverInitials(summary?.name),
              style: const TextStyle(
                color: AppColors.primary,
                fontWeight: FontWeight.w700,
              ),
            )
          : null,
    );
  }

  Future<void> _showRideDetailSheet(
    Ride ride, {
    required int seatsNeededForBooking,
    bool isAlreadyBooked = false,
  }) async {
    if (!mounted) return;

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (sheetCtx) {
        return FractionallySizedBox(
          heightFactor: 0.94,
          child: FutureBuilder<Ride>(
            future: _rideService.getRideDetail(ride.id),
            builder: (ctx, snapshot) {
              if (snapshot.connectionState == ConnectionState.waiting) {
                return Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const CircularProgressIndicator(color: AppColors.primary),
                      const SizedBox(height: 10),
                      Text(
                        'Loading ride details...',
                        style: TextStyle(color: AppColors.textSecondary),
                      ),
                    ],
                  ),
                );
              }

              if (snapshot.hasError &&
                  _isUnauthorizedRideFlowError(snapshot.error)) {
                return Padding(
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(
                        Icons.lock_clock_rounded,
                        color: AppColors.warning,
                        size: 40,
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Session expired',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textPrimary,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Please sign in again to view ride details and continue booking.',
                        textAlign: TextAlign.center,
                        style: TextStyle(color: AppColors.textSecondary),
                      ),
                      const SizedBox(height: 16),
                      SizedBox(
                        width: double.infinity,
                        child: ElevatedButton(
                          onPressed: () async {
                            Navigator.pop(sheetCtx);
                            await _handleUnauthorizedRideFlow(
                              actionLabel: 'view ride details',
                            );
                          },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: AppColors.primary,
                            foregroundColor: Colors.white,
                          ),
                          child: const Text('Sign In Again'),
                        ),
                      ),
                    ],
                  ),
                );
              }

              final detailRide = snapshot.data ?? ride;
              final driver = detailRide.driverSummary;
              final hasEnoughSeats =
                  detailRide.availableSeats >= seatsNeededForBooking;
              final canBook = hasEnoughSeats && !isAlreadyBooked;
              final departure = detailRide.departureDatetime;
              final hasGeoData = detailRide.hasGeoData;
              final carName = (driver?.carName ?? '').trim();
              final vehiclePlate = (driver?.vehiclePlate ?? '').trim();
              final ratingLabel = driver?.ratingAvg != null
                  ? driver!.ratingAvg!.toStringAsFixed(1)
                  : 'N/A';

              return Column(
                children: [
                  const SizedBox(height: 10),
                  Container(
                    width: 44,
                    height: 4,
                    decoration: BoxDecoration(
                      color: AppColors.divider,
                      borderRadius: BorderRadius.circular(99),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'Ride Details',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Driver details are shown here after tapping a ride',
                    style: TextStyle(
                      fontSize: 12,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  if (snapshot.hasError)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                      child: Container(
                        width: double.infinity,
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 10),
                        decoration: BoxDecoration(
                          color: AppColors.warning.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: AppColors.warning.withValues(alpha: 0.35),
                          ),
                        ),
                        child: Text(
                          'Live ride details could not be refreshed. Showing available ride data.',
                          style: TextStyle(
                            color: AppColors.textSecondary,
                            fontSize: 12,
                          ),
                        ),
                      ),
                    ),
                  const SizedBox(height: 10),
                  Expanded(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: AppColors.backgroundLight,
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(color: AppColors.border),
                            ),
                            child: Column(
                              children: [
                                Row(children: [
                                  const Icon(Icons.circle,
                                      size: 8, color: AppColors.primary),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      detailRide.origin,
                                      style: const TextStyle(
                                        fontWeight: FontWeight.w600,
                                        fontSize: 14,
                                      ),
                                    ),
                                  ),
                                ]),
                                const SizedBox(height: 10),
                                Row(children: [
                                  const Icon(Icons.circle,
                                      size: 8, color: AppColors.accent),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      detailRide.destination,
                                      style: const TextStyle(
                                        fontWeight: FontWeight.w600,
                                        fontSize: 14,
                                      ),
                                    ),
                                  ),
                                ]),
                                const SizedBox(height: 14),
                                Row(
                                  children: [
                                    Expanded(
                                      child: _rideDetailMetaChip(
                                        icon: Icons.access_time,
                                        label: departure != null
                                            ? _formatDateTime(
                                                departure.toIso8601String())
                                            : _formatDateTime(
                                                detailRide.departureTime),
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 14),
                          if (hasGeoData)
                            ClipRRect(
                              borderRadius: BorderRadius.circular(14),
                              child: RouteMapWidget(
                                origin: LatLng(detailRide.originLat!,
                                    detailRide.originLng!),
                                destination: LatLng(detailRide.destinationLat!,
                                    detailRide.destinationLng!),
                                originLabel: detailRide.origin,
                                destinationLabel: detailRide.destination,
                                height: 230,
                                showAlternatives: false,
                                interactive: true,
                                encodedPolyline: detailRide.polyline,
                              ),
                            )
                          else
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 14, vertical: 18),
                              decoration: BoxDecoration(
                                color: AppColors.backgroundLight,
                                borderRadius: BorderRadius.circular(14),
                                border: Border.all(color: AppColors.border),
                              ),
                              child: Row(
                                children: [
                                  Icon(Icons.map_outlined,
                                      size: 20, color: AppColors.textHint),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    child: Text(
                                      'Route map is unavailable for this ride because location points are missing.',
                                      style: TextStyle(
                                        color: AppColors.textSecondary,
                                        fontSize: 12,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          const SizedBox(height: 16),
                          Text(
                            'Driver Details',
                            style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              color: AppColors.textPrimary,
                            ),
                          ),
                          const SizedBox(height: 10),
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: AppColors.backgroundLight,
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(color: AppColors.border),
                            ),
                            child: Column(
                              children: [
                                Row(
                                  children: [
                                    _buildRideDriverAvatar(driver),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            (driver?.name ?? 'Driver').trim(),
                                            style: const TextStyle(
                                              fontSize: 15,
                                              fontWeight: FontWeight.w700,
                                            ),
                                          ),
                                          const SizedBox(height: 4),
                                          Text(
                                            carName.isNotEmpty
                                                ? carName
                                                : (vehiclePlate.isNotEmpty
                                                    ? vehiclePlate
                                                    : 'Vehicle details pending'),
                                            style: TextStyle(
                                              fontSize: 12,
                                              color: AppColors.textSecondary,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 12),
                                Wrap(
                                  spacing: 8,
                                  runSpacing: 8,
                                  children: [
                                    _rideDetailMetaChip(
                                      icon: Icons.star_rounded,
                                      label: '$ratingLabel average',
                                    ),
                                    _rideDetailMetaChip(
                                      icon: Icons.verified_rounded,
                                      label:
                                          '${driver?.completedRides ?? 0} completed rides',
                                    ),
                                    if (vehiclePlate.isNotEmpty)
                                      _rideDetailMetaChip(
                                        icon: Icons.directions_car_filled,
                                        label: vehiclePlate,
                                      ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 14),
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: AppColors.backgroundLight,
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(color: AppColors.border),
                            ),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        'Price per seat',
                                        style: TextStyle(
                                          fontSize: 12,
                                          color: AppColors.textSecondary,
                                        ),
                                      ),
                                      const SizedBox(height: 4),
                                      Text(
                                        'Rs ${detailRide.pricePerSeat.toStringAsFixed(0)}',
                                        style: const TextStyle(
                                          fontSize: 18,
                                          fontWeight: FontWeight.w700,
                                          color: AppColors.success,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                Container(
                                  width: 1,
                                  height: 34,
                                  color: AppColors.border,
                                ),
                                Expanded(
                                  child: Padding(
                                    padding: const EdgeInsets.only(left: 12),
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          'Seats left',
                                          style: TextStyle(
                                            fontSize: 12,
                                            color: AppColors.textSecondary,
                                          ),
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          '${detailRide.availableSeats}',
                                          style: const TextStyle(
                                            fontSize: 18,
                                            fontWeight: FontWeight.w700,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                    child: SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: isAlreadyBooked
                            ? () async {
                                Navigator.pop(sheetCtx);
                                await _showAlreadyBookedDialog();
                              }
                            : canBook
                                ? () async {
                                    Navigator.pop(sheetCtx);
                                    await _bookRide(
                                      detailRide,
                                      seatsToBook: seatsNeededForBooking,
                                    );
                                  }
                                : null,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppColors.primary,
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
                          padding: const EdgeInsets.symmetric(vertical: 13),
                        ),
                        child: Text(
                          isAlreadyBooked
                              ? 'Already Booked'
                              : hasEnoughSeats
                                  ? 'Book $seatsNeededForBooking seat${seatsNeededForBooking > 1 ? 's' : ''}'
                                  : 'Not enough seats',
                        ),
                      ),
                    ),
                  ),
                ],
              );
            },
          ),
        );
      },
    );
  }

  Widget _availableRideCard(
    Ride ride, {
    required int seatsNeededForBooking,
    bool isAlreadyBooked = false,
    bool wasPreviouslyCancelled = false,
  }) {
    final hasEnoughSeats = ride.remainingSeats >= seatsNeededForBooking;

    return Material(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () => _openRideDetailSheetGuarded(
          ride,
          seatsNeededForBooking: seatsNeededForBooking,
          isAlreadyBooked: isAlreadyBooked,
        ),
        child: Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: AppColors.border),
            boxShadow: [
              BoxShadow(
                color: AppColors.shadow,
                blurRadius: 6,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Column(
            children: [
              if (isAlreadyBooked) ...[
                Align(
                  alignment: Alignment.centerLeft,
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color: AppColors.primary.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(
                        color: AppColors.primary.withValues(alpha: 0.35),
                      ),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.check_circle_rounded,
                          size: 13,
                          color: AppColors.primary,
                        ),
                        SizedBox(width: 6),
                        Text(
                          'Already Booked',
                          style: TextStyle(
                            color: AppColors.primary,
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 10),
              ] else if (wasPreviouslyCancelled) ...[
                Align(
                  alignment: Alignment.centerLeft,
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color: AppColors.warning.withValues(alpha: 0.14),
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(
                        color: AppColors.warning.withValues(alpha: 0.35),
                      ),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.history_rounded,
                          size: 13,
                          color: AppColors.warning,
                        ),
                        SizedBox(width: 6),
                        Text(
                          'Previously Cancelled',
                          style: TextStyle(
                            color: AppColors.warning,
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 10),
              ],
              Row(children: [
                const Icon(Icons.circle, size: 8, color: AppColors.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    ride.origin,
                    style: const TextStyle(
                        fontWeight: FontWeight.w600, fontSize: 14),
                  ),
                ),
              ]),
              const SizedBox(height: 8),
              Row(children: [
                const Icon(Icons.circle, size: 8, color: AppColors.accent),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    ride.destination,
                    style: const TextStyle(
                        fontWeight: FontWeight.w600, fontSize: 14),
                  ),
                ),
              ]),
              const Divider(height: 24),
              Row(children: [
                Icon(Icons.access_time, size: 14, color: AppColors.textHint),
                const SizedBox(width: 6),
                Text(
                  _formatDateTime(ride.departureTime),
                  style:
                      TextStyle(fontSize: 12, color: AppColors.textSecondary),
                ),
              ]),
              const SizedBox(height: 10),
              Wrap(
                spacing: 14,
                runSpacing: 8,
                children: [
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.event_seat,
                          size: 14, color: AppColors.textHint),
                      const SizedBox(width: 4),
                      Text(
                        '${ride.remainingSeats} seats left',
                        style: TextStyle(
                            fontSize: 12, color: AppColors.textSecondary),
                      ),
                    ],
                  ),
                  if (ride.totalSeats != null) ...[
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.group, size: 14, color: AppColors.textHint),
                        const SizedBox(width: 4),
                        Text(
                          'Total Seats: ${ride.totalSeats}',
                          style: TextStyle(
                              fontSize: 12, color: AppColors.textSecondary),
                        ),
                      ],
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 10),
              Align(
                alignment: Alignment.centerRight,
                child: Text(
                  'Rs ${ride.pricePerSeat.toStringAsFixed(0)} Per Seat',
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                    color: Color(0xFF0B3D24),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: isAlreadyBooked
                      ? _showAlreadyBookedDialog
                      : () => _openRideDetailSheetGuarded(
                            ride,
                            seatsNeededForBooking: seatsNeededForBooking,
                            isAlreadyBooked: isAlreadyBooked,
                          ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primary,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    padding: const EdgeInsets.symmetric(vertical: 12),
                  ),
                  icon: const Icon(Icons.visibility_rounded, size: 18),
                  label: Text(
                    isAlreadyBooked
                        ? 'Already Booked'
                        : hasEnoughSeats
                            ? 'View Details & Book'
                            : 'View Ride Details',
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _bookRide(Ride ride, {required int seatsToBook}) async {
    try {
      final canProceed = await _ensureAuthenticatedRideFlow(
        actionLabel: 'book a ride',
      );
      if (!canProceed) return;

      final pickup = _scheduleOrigin;
      final dropoff = _scheduleDestination;

      final pickupLat = pickup?.latLng.latitude ?? ride.originLat;
      final pickupLng = pickup?.latLng.longitude ?? ride.originLng;
      final dropoffLat = dropoff?.latLng.latitude ?? ride.destinationLat;
      final dropoffLng = dropoff?.latLng.longitude ?? ride.destinationLng;
      final pickupAddress = ((pickup?.address ?? '').trim().isNotEmpty)
          ? pickup!.address.trim()
          : ride.origin;
      final dropoffAddress = ((dropoff?.address ?? '').trim().isNotEmpty)
          ? dropoff!.address.trim()
          : ride.destination;

      await _rideService.bookRide(
        rideId: ride.id,
        bookedSeats: seatsToBook,
        pickupLat: pickupLat,
        pickupLng: pickupLng,
        pickupAddress: pickupAddress,
        pickupPlaceId: pickup?.placeId,
        dropoffLat: dropoffLat,
        dropoffLng: dropoffLng,
        dropoffAddress: dropoffAddress,
        dropoffPlaceId: dropoff?.placeId,
      );
      if (mounted) {
        _returnToScheduleMap();
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(
              'Ride booked successfully for $seatsToBook seat${seatsToBook > 1 ? 's' : ''}!'),
          backgroundColor: AppColors.success,
        ));
        await _refreshAllDashboardData(showHomeLoader: false);
      }
    } catch (e) {
      if (e is DioException && _isUnauthorizedRideFlowError(e)) {
        await _handleUnauthorizedRideFlow(actionLabel: 'book a ride');
        return;
      }

      if (e is DioException && _isAlreadyBookedRideError(e)) {
        await _showAlreadyBookedDialog();
        return;
      }

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(e is DioException ? extractError(e) : 'Booking failed'),
          backgroundColor: AppColors.error,
        ));
      }
    }
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
              onPressed: () => Navigator.pop(ctx), child: const Text('Keep')),
          ElevatedButton(
            onPressed: () async {
              Navigator.pop(ctx);
              try {
                await _rideService.cancelBooking(booking.id,
                    reason: reasonCtrl.text.isEmpty ? null : reasonCtrl.text);
                await _refreshAllDashboardData(showHomeLoader: false);
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                        content: Text('Booking cancelled'),
                        backgroundColor: AppColors.warning),
                  );
                }
              } catch (e) {
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(e is DioException
                        ? extractError(e)
                        : 'Cancellation failed'),
                    backgroundColor: AppColors.error,
                  ));
                }
              }
            },
            style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.error,
                foregroundColor: Colors.white),
            child: const Text('Cancel Booking'),
          ),
        ],
      ),
    );
  }

  // ignore: unused_element
  void _showWalletSheet() {
    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (_) {
        return FutureBuilder<(double?, List<WalletTransaction>)>(
          future: _loadWalletData(),
          builder: (ctx, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const SizedBox(
                  height: 200, child: SyloLoader(message: 'Loading wallet...'));
            }
            final balance = snapshot.data?.$1;
            final txns = snapshot.data?.$2 ?? [];
            return Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Center(
                    child: Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: AppColors.divider,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  const SizedBox(height: 20),
                  const Text('Wallet',
                      style:
                          TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 24),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                          colors: [AppColors.charcoal, AppColors.charcoalMid]),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Column(children: [
                      Text('Balance',
                          style: TextStyle(
                              color: AppColors.textHint, fontSize: 14)),
                      const SizedBox(height: 8),
                      Text('Rs ${balance?.toStringAsFixed(0) ?? '0'}',
                          style: const TextStyle(
                              color: AppColors.primary,
                              fontSize: 36,
                              fontWeight: FontWeight.bold)),
                    ]),
                  ),
                  if (txns.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: Text('Recent Transactions',
                          style: TextStyle(
                              fontWeight: FontWeight.w600, fontSize: 15)),
                    ),
                    const SizedBox(height: 8),
                    ...txns.take(5).map((t) => ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: CircleAvatar(
                            backgroundColor: t.isCredit
                                ? AppColors.success.withValues(alpha: 0.12)
                                : AppColors.error.withValues(alpha: 0.12),
                            child: Icon(
                                t.isCredit
                                    ? Icons.arrow_downward
                                    : Icons.arrow_upward,
                                color: t.isCredit
                                    ? AppColors.success
                                    : AppColors.error,
                                size: 18),
                          ),
                          title: Text(t.description ?? _capitalize(t.type),
                              style: const TextStyle(
                                  fontSize: 13, fontWeight: FontWeight.w500)),
                          trailing: Text(
                            '${t.isCredit ? '+' : '-'} Rs ${t.amount.toStringAsFixed(0)}',
                            style: TextStyle(
                                fontWeight: FontWeight.w700,
                                color: t.isCredit
                                    ? AppColors.success
                                    : AppColors.error),
                          ),
                        )),
                  ],
                  const SizedBox(height: 24),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Future<(double?, List<WalletTransaction>)> _loadWalletData() async {
    final userId = await AuthService().getUserId();
    if (userId == null) return (null, <WalletTransaction>[]);
    try {
      final balance = await _walletService.getBalance(userId);
      final txnResult = await _walletService.getTransactions(limit: 5);
      return (balance.balance, txnResult.transactions);
    } catch (_) {
      return (null, <WalletTransaction>[]);
    }
  }

  // ignore: unused_element
  void _showEditProfileSheet() {
    final genderCtrl =
        TextEditingController(text: _user?.profile?.gender ?? '');
    final orgCtrl =
        TextEditingController(text: _user?.profile?.organizationName ?? '');

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (ctx) {
        return Padding(
          padding: EdgeInsets.only(
            left: 24,
            right: 24,
            top: 24,
            bottom: MediaQuery.of(ctx).viewInsets.bottom + 24,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: AppColors.divider,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 20),
              const Text('Edit Profile',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
              const SizedBox(height: 20),
              DropdownButtonFormField<String>(
                value: genderCtrl.text.isEmpty ? null : genderCtrl.text,
                decoration: InputDecoration(
                  labelText: 'Gender',
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(14)),
                ),
                items: const [
                  DropdownMenuItem(value: 'male', child: Text('Male')),
                  DropdownMenuItem(value: 'female', child: Text('Female')),
                  DropdownMenuItem(value: 'other', child: Text('Other')),
                ],
                onChanged: (v) => genderCtrl.text = v ?? '',
              ),
              const SizedBox(height: 12),
              TextField(
                controller: orgCtrl,
                decoration: InputDecoration(
                  labelText: 'Organization',
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(14)),
                ),
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () async {
                    try {
                      await _userService.updateProfile(
                        gender:
                            genderCtrl.text.isEmpty ? null : genderCtrl.text,
                        organizationName:
                            orgCtrl.text.isEmpty ? null : orgCtrl.text,
                      );
                      if (mounted) {
                        Navigator.pop(ctx);
                        await _refreshAllDashboardData(showHomeLoader: false);
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                              content: Text('Profile updated'),
                              backgroundColor: AppColors.success),
                        );
                      }
                    } catch (e) {
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                              content: Text(e is DioException
                                  ? extractError(e)
                                  : 'Update failed'),
                              backgroundColor: AppColors.error),
                        );
                      }
                    }
                  },
                  child: const Text('Save Changes'),
                ),
              ),
              const SizedBox(height: 16),
            ],
          ),
        );
      },
    );
  }

  // ───────────────────────────────────────────────────────
  //  HELPERS
  // ───────────────────────────────────────────────────────
  String _formatDateTime(String iso) {
    final parsed = DateTime.tryParse(iso);
    if (parsed == null) return iso;
    final dt = parsed.toLocal();
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inDays == 0 && dt.day == now.day) {
      return 'Today, ${_pad(dt.hour)}:${_pad(dt.minute)}';
    } else if (diff.inDays == 1 ||
        (diff.inDays == 0 && dt.day == now.day - 1)) {
      return 'Yesterday, ${_pad(dt.hour)}:${_pad(dt.minute)}';
    } else if (diff.inDays < 7) {
      const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      return '${days[dt.weekday - 1]}, ${_pad(dt.hour)}:${_pad(dt.minute)}';
    }
    return '${dt.day}/${dt.month}/${dt.year}';
  }

  String _pad(int n) => n.toString().padLeft(2, '0');

  String _capitalize(String s) =>
      s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);

  Color _statusColor(String status) {
    final normalized = status.trim().toLowerCase();

    if (normalized.contains('cancelled')) {
      return AppColors.error;
    }
    if (normalized.contains('completed')) {
      return AppColors.success;
    }
    if (normalized.contains('started') || normalized == 'in_progress') {
      return AppColors.info;
    }
    if (normalized.contains('booked') ||
        normalized.contains('open') ||
        normalized.contains('reserved') ||
        normalized.contains('confirmed')) {
      return AppColors.accent;
    }
    return AppColors.textSecondary;
  }
}
