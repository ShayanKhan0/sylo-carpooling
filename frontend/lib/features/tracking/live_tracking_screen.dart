import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:geolocator/geolocator.dart';
import 'package:pointer_interceptor/pointer_interceptor.dart';
import '../../core/services/telemetry_service.dart';
import '../../core/services/ride_service.dart';
import '../../core/services/maps_service.dart';
import '../../core/services/auth_service.dart';
import '../../core/models/ride_model.dart';
import '../../core/theme/app_colors.dart';
import '../../core/utils/carbon_footprint.dart';
import '../../core/utils/live_location_marker_icon.dart';
import '../shared/widgets.dart';

/// Live tracking screen showing driver's real-time location on map
class LiveTrackingScreen extends StatefulWidget {
  final String rideId;
  final String? driverName;
  final String? bookingId;
  final String? passengerId;
  final LatLng? pickupLocation;
  final LatLng? dropoffLocation;

  const LiveTrackingScreen({
    super.key,
    required this.rideId,
    this.driverName,
    this.bookingId,
    this.passengerId,
    this.pickupLocation,
    this.dropoffLocation,
  });

  @override
  State<LiveTrackingScreen> createState() => _LiveTrackingScreenState();
}

class _LiveTrackingScreenState extends State<LiveTrackingScreen> {
  final TelemetryService _telemetryService = TelemetryService();
  final RideService _rideService = RideService();
  final MapsService _mapsService = MapsService();

  static const double _mapMatchMaxDistanceMeters = 120.0;
  static const double _offRouteThresholdMeters = 80.0;
  static const Duration _minRerouteInterval = Duration(seconds: 20);
  static const Duration _periodicRerouteInterval = Duration(seconds: 75);

  GoogleMapController? _mapController;
  StreamSubscription<TelemetryPoint>? _telemetrySub;
  StreamSubscription<Position>? _riderLocationSub;
  Timer? _latestLocationFallbackTimer;

  LatLng? _driverLocation;
  LatLng? _riderLocation;
  double _driverSpeed = 0;
  double _driverBearing = 0;
  String? _error;
  bool _isLoading = true;
  BitmapDescriptor? _webLiveLocationIcon;

  // ETA calculation
  String _etaText = 'Calculating...';
  DateTime? _lastUpdate;
  String? _telemetryDiagnostics;

  // Polyline from ride data
  Set<Polyline> _polylines = {};
  List<LatLng> _activeRoutePoints = <LatLng>[];
  int? _latestRoutePlanVersion;
  DateTime _lastRoutePlanSyncAt = DateTime.fromMillisecondsSinceEpoch(0);
  int _rerouteRequestVersion = 0;
  DateTime _lastRerouteAt = DateTime.fromMillisecondsSinceEpoch(0);
  final Set<Marker> _markers = {};

  /// Resolved from ride if [pickupLocation] / [dropoffLocation] args omitted.
  LatLng? _resolvedPickup;
  LatLng? _resolvedDropoff;

  @override
  void initState() {
    super.initState();
    _telemetryService.diagnosticsNotifier
        .addListener(_handleTelemetryDiagnosticsChanged);
    _telemetryService.transportNotifier
        .addListener(_handleTelemetryDiagnosticsChanged);
    _initializeWebCurrentLocationLayer();
    _initTracking();
  }

  @override
  void dispose() {
    _telemetryService.diagnosticsNotifier
        .removeListener(_handleTelemetryDiagnosticsChanged);
    _telemetryService.transportNotifier
        .removeListener(_handleTelemetryDiagnosticsChanged);
    _telemetrySub?.cancel();
    _riderLocationSub?.cancel();
    _latestLocationFallbackTimer?.cancel();
    _telemetryService.dispose();
    _mapController?.dispose();
    super.dispose();
  }

  void _handleTelemetryDiagnosticsChanged() {
    if (!mounted) return;
    setState(() {
      _telemetryDiagnostics = _telemetryService.diagnosticsNotifier.value;
      if (_driverLocation == null &&
          (_error == null || _error == 'Waiting for driver location...') &&
          _telemetryDiagnostics != null &&
          _telemetryDiagnostics!.trim().isNotEmpty) {
        _error = _telemetryDiagnostics;
      }
    });
  }

  Future<void> _initializeWebCurrentLocationLayer() async {
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
        _riderLocation = LatLng(pos.latitude, pos.longitude);
        _upsertRiderMarker();
      });

      _riderLocationSub = Geolocator.getPositionStream(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          distanceFilter: 12,
        ),
      ).listen((position) {
        if (!mounted) return;
        setState(() {
          _riderLocation = LatLng(position.latitude, position.longitude);
          _upsertRiderMarker();
        });
      });
    } catch (_) {
      // Keep tracking usable even if user location is unavailable on web.
    }
  }

  Future<void> _initTracking() async {
    // Load ride details for polyline
    try {
      final ride = await _rideService.getRideDetail(widget.rideId);
      _buildRoutePolyline(ride);
      _latestRoutePlanVersion = ride.routePlanVersion;
    } catch (_) {
      // Continue without polyline
    }

    // Connect to telemetry stream
    await _telemetryService.connect(widget.rideId);

    _telemetrySub = _telemetryService.pointStream.listen((point) {
      if (mounted) {
        final rawLocation = LatLng(point.lat, point.lng);
        final mapMatchedLocation = _mapMatchToRoute(rawLocation);

        setState(() {
          _driverLocation = mapMatchedLocation;
          _driverSpeed = point.speed;
          _driverBearing = point.bearing ?? 0;
          _lastUpdate = point.timestamp;
          _isLoading = false;
          _error = null;
          _updateMarkers();
          _calculateETA();
        });

        unawaited(_syncAuthoritativeRoutePlanIfNeeded());
        _maybeTriggerReroute(rawLocation);

        // Animate camera to driver location
        _mapController?.animateCamera(
          CameraUpdate.newLatLngZoom(_driverLocation!, 15),
        );
      }
    });

    _startLatestLocationFallbackPolling();

    // Initial fetch if WebSocket takes time
    _fetchInitialLocation();
  }

  Future<void> _fetchInitialLocation() async {
    await Future.delayed(const Duration(seconds: 2));
    if (_driverLocation == null && mounted) {
      final point = await _telemetryService.getLatestLocation(widget.rideId);
      if (point != null && mounted) {
        setState(() {
          _driverLocation = LatLng(point.lat, point.lng);
          _driverSpeed = point.speed;
          _lastUpdate = point.timestamp;
          _isLoading = false;
          _error = null;
          _updateMarkers();
        });
      } else if (mounted) {
        setState(() {
          _isLoading = false;
          _error = 'Waiting for driver location...';
        });
      }
    }
  }

  void _startLatestLocationFallbackPolling() {
    _latestLocationFallbackTimer?.cancel();
    _latestLocationFallbackTimer = Timer.periodic(
      const Duration(seconds: 4),
      (_) async {
        if (!mounted) return;

        final shouldRefresh = _driverLocation == null ||
            _lastUpdate == null ||
            DateTime.now().toUtc().difference(_lastUpdate!.toUtc()) >=
                const Duration(seconds: 8);
        if (!shouldRefresh) return;

        final latest = await _telemetryService.getLatestLocation(widget.rideId);
        if (latest == null || !mounted) return;

        final rawLocation = LatLng(latest.lat, latest.lng);
        final mapMatchedLocation = _mapMatchToRoute(rawLocation);

        setState(() {
          _driverLocation = mapMatchedLocation;
          _driverSpeed = latest.speed;
          _driverBearing = latest.bearing ?? _driverBearing;
          _lastUpdate = latest.timestamp;
          _isLoading = false;
          _error = null;
          _updateMarkers();
          _calculateETA();
        });
        unawaited(_syncAuthoritativeRoutePlanIfNeeded());
      },
    );
  }

  Future<void> _syncAuthoritativeRoutePlanIfNeeded() async {
    final now = DateTime.now();
    if (now.difference(_lastRoutePlanSyncAt) < const Duration(seconds: 8)) {
      return;
    }
    _lastRoutePlanSyncAt = now;

    try {
      final ride = await _rideService.getRideDetail(widget.rideId);
      if (!mounted) return;
      final hasRouteVersionChange =
          _latestRoutePlanVersion == null ||
          ride.routePlanVersion != _latestRoutePlanVersion;
      final missingRouteLine = _activeRoutePoints.length < 2;
      if (hasRouteVersionChange || missingRouteLine) {
        _buildRoutePolyline(ride);
        _latestRoutePlanVersion = ride.routePlanVersion;
      }
    } catch (_) {
      // Keep current route if refresh fails.
    }
  }

  void _buildRoutePolyline(Ride ride) {
    final polylineStr = _preferredRidePolyline(ride) ?? '';
    final points = polylineStr.isNotEmpty
        ? MapsService.decodePolyline(polylineStr)
        : const <LatLng>[];

    // Set pickup/dropoff markers from ride data
    final startLat = ride.originLat;
    final startLng = ride.originLng;
    final endLat = ride.destinationLat;
    final endLng = ride.destinationLng;

    final pickup = (startLat != null && startLng != null)
        ? LatLng(startLat, startLng)
        : null;
    final dropoff =
        (endLat != null && endLng != null) ? LatLng(endLat, endLng) : null;

    final updatedMarkers = Set<Marker>.from(_markers)
      ..removeWhere(
          (m) => m.markerId.value == 'pickup' || m.markerId.value == 'dropoff');

    if (pickup != null) {
      updatedMarkers.add(
        Marker(
          markerId: const MarkerId('pickup'),
          position: pickup,
          icon:
              BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueGreen),
          infoWindow: const InfoWindow(title: 'Pickup'),
        ),
      );
    }

    if (dropoff != null) {
      updatedMarkers.add(
        Marker(
          markerId: const MarkerId('dropoff'),
          position: dropoff,
          icon: BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueRed),
          infoWindow: const InfoWindow(title: 'Destination'),
        ),
      );
    }

    setState(() {
      _resolvedPickup = pickup;
      _resolvedDropoff = dropoff;
      _latestRoutePlanVersion = ride.routePlanVersion;
      _activeRoutePoints = points;
      _polylines = points.length >= 2
          ? {
              Polyline(
                polylineId: const PolylineId('route'),
                points: points,
                color: AppColors.primary,
                width: 4,
              ),
            }
          : <Polyline>{};
      _markers
        ..clear()
        ..addAll(updatedMarkers);
    });
  }

  String? _preferredRidePolyline(Ride ride) {
    final selectedKey = (ride.routeSelectedKey ?? '').trim();
    if (selectedKey.isNotEmpty) {
      for (final alt
          in ride.routeAlternatives ?? const <RideRouteAlternative>[]) {
        if (alt.key == selectedKey) {
          final encoded = (alt.polyline ?? '').trim();
          if (encoded.isNotEmpty) return encoded;
          break;
        }
      }
    }

    for (final alt
        in ride.routeAlternatives ?? const <RideRouteAlternative>[]) {
      final encoded = (alt.polyline ?? '').trim();
      if (encoded.isNotEmpty) return encoded;
    }

    final fallback = (ride.polyline ?? '').trim();
    return fallback.isNotEmpty ? fallback : null;
  }

  void _updateMarkers() {
    if (_driverLocation == null) return;

    // Remove old driver marker and add new one
    _markers.removeWhere((m) => m.markerId.value == 'driver');
    _markers.add(Marker(
      markerId: const MarkerId('driver'),
      position: _driverLocation!,
      rotation: _driverBearing,
      icon: BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueAzure),
      infoWindow: InfoWindow(
        title: widget.driverName ?? 'Driver',
        snippet: '${_driverSpeed.toStringAsFixed(0)} km/h',
      ),
    ));

    _upsertRiderMarker();
  }

  void _upsertRiderMarker() {
    _markers.removeWhere((m) => m.markerId.value == 'riderCurrentLocation');

    if (!kIsWeb || _riderLocation == null) return;

    _markers.add(
      Marker(
        markerId: const MarkerId('riderCurrentLocation'),
        position: _riderLocation!,
        icon: _webLiveLocationIcon ??
            BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueAzure),
        infoWindow: const InfoWindow(title: 'You'),
        zIndexInt: 0,
      ),
    );
  }

  void _calculateETA() {
    final target = _currentTrackingTarget();
    if (_driverLocation == null || target == null) {
      _etaText = 'Calculating...';
      return;
    }

    final distance = haversineKm(
      _driverLocation!.latitude,
      _driverLocation!.longitude,
      target.latitude,
      target.longitude,
    );

    final avgSpeed = _driverSpeed > 5 ? _driverSpeed : 30.0;
    final etaMinutes = (distance / avgSpeed * 60).round();

    if (etaMinutes < 1) {
      _etaText = 'Arriving now';
    } else if (etaMinutes == 1) {
      _etaText = '1 minute away';
    } else {
      _etaText = '$etaMinutes minutes away';
    }
  }

  LatLng? _currentTrackingTarget() {
    // For in-progress tracking, prioritize destination so passengers can see
    // the forward route to the trip end instead of only heading to pickup.
    return widget.dropoffLocation ??
        _resolvedDropoff ??
        widget.pickupLocation ??
        _resolvedPickup;
  }

  double _distanceMeters(LatLng a, LatLng b) {
    return haversineKm(a.latitude, a.longitude, b.latitude, b.longitude) * 1000;
  }

  double _distanceToActiveRouteMeters(LatLng location) {
    if (_activeRoutePoints.isEmpty) {
      return double.infinity;
    }
    var minDistance = double.infinity;
    for (final point in _activeRoutePoints) {
      final distance = _distanceMeters(location, point);
      if (distance < minDistance) {
        minDistance = distance;
      }
    }
    return minDistance;
  }

  LatLng _mapMatchToRoute(LatLng rawLocation) {
    if (_activeRoutePoints.isEmpty) {
      return rawLocation;
    }

    LatLng nearest = _activeRoutePoints.first;
    var minDistance = _distanceMeters(rawLocation, nearest);

    for (var i = 1; i < _activeRoutePoints.length; i++) {
      final candidate = _activeRoutePoints[i];
      final distance = _distanceMeters(rawLocation, candidate);
      if (distance < minDistance) {
        minDistance = distance;
        nearest = candidate;
      }
    }

    if (minDistance <= _mapMatchMaxDistanceMeters) {
      return nearest;
    }
    return rawLocation;
  }

  void _maybeTriggerReroute(LatLng rawLocation) {
    // If backend has already provided an optimized route plan polyline
    // (the same one shown on Ride Details), preserve that authoritative path.
    if ((_latestRoutePlanVersion ?? 0) > 0 && _activeRoutePoints.length >= 2) {
      return;
    }

    final target = _currentTrackingTarget();
    if (target == null) return;

    final now = DateTime.now();
    final elapsed = now.difference(_lastRerouteAt);
    final missingRouteLine = _activeRoutePoints.length < 2;
    if (!missingRouteLine && elapsed < _minRerouteInterval) return;

    final offRoute = _activeRoutePoints.isNotEmpty &&
        _distanceToActiveRouteMeters(rawLocation) > _offRouteThresholdMeters;
    final duePeriodic = elapsed >= _periodicRerouteInterval;

    if (!missingRouteLine && !offRoute && !duePeriodic) return;

    _lastRerouteAt = now;
    _rerouteFromCurrentLocation(rawLocation, target);
  }

  Future<void> _rerouteFromCurrentLocation(
      LatLng currentLocation, LatLng target) async {
    final requestVersion = ++_rerouteRequestVersion;
    try {
      final directions = await _mapsService.getDirections(
        origin: currentLocation,
        destination: target,
        alternatives: false,
        departureTime: 'now',
      );

      if (!mounted || requestVersion != _rerouteRequestVersion) {
        return;
      }

      final route = directions?.bestRoute;
      if (route == null || route.polylinePoints.length < 2) {
        return;
      }

      setState(() {
        _activeRoutePoints = route.polylinePoints;
        _polylines = {
          Polyline(
            polylineId: const PolylineId('route'),
            points: route.polylinePoints,
            color: AppColors.primary,
            width: 4,
          ),
        };
      });
    } catch (_) {
      // Keep previous route if reroute request fails.
    }
  }

  Widget _interceptPointer(Widget child) {
    return PointerInterceptor(child: child);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      body: Stack(
        children: [
          // Google Map
          GoogleMap(
            initialCameraPosition: CameraPosition(
              target: widget.pickupLocation ??
                  const LatLng(31.5204, 74.3587), // Default: Lahore
              zoom: 14,
            ),
            onMapCreated: (controller) => _mapController = controller,
            markers: _markers,
            polylines: _polylines,
            myLocationEnabled: !kIsWeb,
            myLocationButtonEnabled: false,
            zoomControlsEnabled: false,
            mapToolbarEnabled: false,
          ),

          // Loading overlay
          if (_isLoading)
            Container(
              color: Colors.black45,
              child: const Center(
                child: SyloLoader(message: 'Connecting to driver...'),
              ),
            ),

          // Top Floating AppBar over Map
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: _interceptPointer(
              Container(
                padding: EdgeInsets.only(
                  top: MediaQuery.of(context).padding.top + 8,
                  left: 16,
                  right: 16,
                  bottom: 16,
                ),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Colors.black.withValues(alpha: 0.8),
                      Colors.transparent,
                    ],
                  ),
                ),
                child: Row(
                  children: [
                    InkWell(
                      onTap: () => Navigator.pop(context),
                      child: Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: Theme.of(context).cardColor,
                          shape: BoxShape.circle,
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: 0.1),
                              blurRadius: 8,
                            ),
                          ],
                        ),
                        child: const Icon(Icons.arrow_back),
                      ),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 12),
                        decoration: BoxDecoration(
                          color: Theme.of(context)
                              .cardColor
                              .withValues(alpha: 0.95),
                          borderRadius: BorderRadius.circular(999),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: 0.05),
                              blurRadius: 10,
                            ),
                          ],
                        ),
                        child: Text(
                          widget.driverName ?? 'Track Driver',
                          style: const TextStyle(
                            fontWeight: FontWeight.bold,
                            fontSize: 16,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ),
                    const SizedBox(width: 16),
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: Theme.of(context).cardColor,
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.1),
                            blurRadius: 8,
                          ),
                        ],
                      ),
                      child: Icon(
                        _telemetryService.isConnected
                            ? Icons.wifi
                            : Icons.wifi_off,
                        color: _telemetryService.isConnected
                            ? AppColors.success
                            : AppColors.warning,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),

          // Error message
          if (_error != null && !_isLoading)
            Positioned(
              top: MediaQuery.of(context).padding.top + 80,
              left: 16,
              right: 16,
              child: _interceptPointer(
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppColors.warning.withValues(alpha: 0.9),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.info_outline, color: Colors.white),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _error!,
                          style: const TextStyle(color: Colors.white),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),

          // Bottom info panel (Glassmorphic)
          Positioned(
            bottom: 24,
            left: 16,
            right: 16,
            child: _interceptPointer(
              Container(
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: Theme.of(context).cardColor.withValues(alpha: 0.85),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(
                    color:
                        Theme.of(context).dividerColor.withValues(alpha: 0.1),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.15),
                      blurRadius: 20,
                      offset: const Offset(0, 8),
                    ),
                  ],
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Driver info row
                    Row(
                      children: [
                        CircleAvatar(
                          radius: 24,
                          backgroundColor: AppColors.primary,
                          child: Text(
                            (widget.driverName ?? 'D')[0].toUpperCase(),
                            style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.bold,
                              fontSize: 18,
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                widget.driverName ?? 'Driver',
                                style: const TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 16,
                                ),
                              ),
                              Text(
                                _etaText,
                                style: TextStyle(
                                  color: AppColors.textSecondary,
                                  fontSize: 14,
                                ),
                              ),
                              if (_telemetryDiagnostics != null &&
                                  _telemetryDiagnostics!.trim().isNotEmpty)
                                Text(
                                  _telemetryDiagnostics!,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(
                                    color: AppColors.warning,
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                            ],
                          ),
                        ),
                        // Speed indicator
                        if (_driverSpeed > 0)
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 6,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.info.withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Icon(
                                  Icons.speed,
                                  size: 16,
                                  color: AppColors.info,
                                ),
                                const SizedBox(width: 4),
                                Text(
                                  '${_driverSpeed.toStringAsFixed(0)} km/h',
                                  style: const TextStyle(
                                    color: AppColors.info,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ],
                            ),
                          ),
                      ],
                    ),

                    const SizedBox(height: 16),

                    // Last update time
                    if (_lastUpdate != null)
                      Text(
                        'Last update: ${_formatTime(_lastUpdate!)}',
                        style: TextStyle(
                          color: AppColors.textHint,
                          fontSize: 12,
                        ),
                      ),
                    if (_lastUpdate == null)
                      Text(
                        'Telemetry mode: ${_telemetryService.transportNotifier.value}',
                        style: TextStyle(
                          color: AppColors.textHint,
                          fontSize: 12,
                        ),
                      ),

                    const SizedBox(height: 16),

                    // Action buttons
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: _openChatForTrackedRide,
                        icon: const Icon(Icons.chat_bubble_outline),
                        label: const Text('Message'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppColors.primary,
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                      ),
                    ),
                    const SizedBox(height: 10),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: () => Navigator.pop(context),
                        icon: const Icon(Icons.close),
                        label: const Text('Close'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppColors.textPrimary,
                          padding: const EdgeInsets.symmetric(vertical: 12),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),

          // Center on driver button
          if (_driverLocation != null)
            Positioned(
              right: 16,
              bottom: 220,
              child: _interceptPointer(
                FloatingActionButton.small(
                  onPressed: () {
                    _mapController?.animateCamera(
                      CameraUpdate.newLatLngZoom(_driverLocation!, 16),
                    );
                  },
                  backgroundColor: AppColors.surface,
                  child:
                      const Icon(Icons.my_location, color: AppColors.primary),
                ),
              ),
            ),
        ],
      ),
    );
  }

  String _formatTime(DateTime time) {
    final now = DateTime.now();
    final diff = now.difference(time);

    if (diff.inSeconds < 5) return 'Just now';
    if (diff.inSeconds < 60) return '${diff.inSeconds}s ago';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    return '${diff.inHours}h ago';
  }

  Future<void> _openChatForTrackedRide() async {
    final bookingId = (widget.bookingId ?? '').trim();
    var passengerId = (widget.passengerId ?? '').trim();

    if (passengerId.isEmpty) {
      passengerId = (await AuthService().getUserId())?.trim() ?? '';
    }

    if (bookingId.isEmpty && passengerId.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Unable to open chat: missing booking context.'),
        ),
      );
      return;
    }

    if (!mounted) return;
    await Navigator.pushNamed(
      context,
      '/chat',
      arguments: {
        'rideId': widget.rideId,
        if (bookingId.isNotEmpty) 'bookingId': bookingId,
        if (passengerId.isNotEmpty) 'passengerId': passengerId,
      },
    );
  }
}
