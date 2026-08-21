import 'dart:async';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import '../../core/theme/app_colors.dart';
import '../../core/services/maps_service.dart';

class RouteMapMarkerData {
  final String id;
  final LatLng position;
  final String title;
  final String? snippet;
  final double hue;
  final Color? markerColor;
  final int? stopNumber;
  final String? bookingId;
  final String? eventType;
  final bool isPassengerStop;

  const RouteMapMarkerData({
    required this.id,
    required this.position,
    required this.title,
    this.snippet,
    this.hue = BitmapDescriptor.hueAzure,
    this.markerColor,
    this.stopNumber,
    this.bookingId,
    this.eventType,
    this.isPassengerStop = false,
  });
}

class RouteMapStopColorData {
  final int order;
  final LatLng position;
  final Color color;
  final String? bookingId;
  final String? eventType;

  const RouteMapStopColorData({
    required this.order,
    required this.position,
    required this.color,
    this.bookingId,
    this.eventType,
  });
}

/// Displays a route on Google Maps between origin and destination.
/// Shows polyline, markers, distance, duration, traffic, and alternatives.
class RouteMapWidget extends StatefulWidget {
  final LatLng origin;
  final LatLng destination;
  final String? originPlaceId;
  final String? destinationPlaceId;
  final String originLabel;
  final String destinationLabel;
  final double height;
  final bool showAlternatives;
  final bool interactive; // allow zoom/pan
  final bool showInfoCard; // show distance/duration card below map
  final ValueChanged<DirectionsRoute>? onRouteSelected;
  final List<RouteMapMarkerData> extraMarkers;
  final List<RouteMapStopColorData> routeColorStops;

  /// If provided, display this stored polyline instead of fetching from API.
  final String? encodedPolyline;

  const RouteMapWidget({
    super.key,
    required this.origin,
    required this.destination,
    this.originPlaceId,
    this.destinationPlaceId,
    this.originLabel = 'Pickup',
    this.destinationLabel = 'Drop-off',
    this.height = 300,
    this.showAlternatives = true,
    this.interactive = true,
    this.showInfoCard = true,
    this.onRouteSelected,
    this.encodedPolyline,
    this.extraMarkers = const [],
    this.routeColorStops = const [],
  });

  @override
  State<RouteMapWidget> createState() => _RouteMapWidgetState();
}

class _RouteMapWidgetState extends State<RouteMapWidget> {
  GoogleMapController? _mapController;
  final MapsService _mapsService = MapsService();

  DirectionsResult? _result;
  int _selectedRouteIndex = 0;
  bool _isLoading = true;
  String? _error;

  Set<Polyline> _polylines = {};
  Set<Marker> _markers = {};
  int _routeLoadVersion = 0;
  List<LatLng> _storedPolylinePoints = const <LatLng>[];
  final Map<String, BitmapDescriptor> _customMarkerIconCache =
      <String, BitmapDescriptor>{};

  @override
  void initState() {
    super.initState();
    _loadRoute();
  }

  @override
  void didUpdateWidget(covariant RouteMapWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.origin != widget.origin ||
        oldWidget.destination != widget.destination ||
        oldWidget.originPlaceId != widget.originPlaceId ||
        oldWidget.destinationPlaceId != widget.destinationPlaceId) {
      _loadRoute();
      return;
    }

    if (oldWidget.extraMarkers.length != widget.extraMarkers.length ||
        oldWidget.routeColorStops.length != widget.routeColorStops.length) {
      unawaited(_rebuildMapLayers());
      return;
    }

    final oldSignature = oldWidget.extraMarkers
        .map((m) =>
            '${m.id}:${m.position.latitude}:${m.position.longitude}:${m.title}:${m.snippet}:${m.markerColor?.toARGB32()}:${m.stopNumber}:${m.bookingId}:${m.eventType}:${m.isPassengerStop}')
        .join('|');
    final newSignature = widget.extraMarkers
        .map((m) =>
            '${m.id}:${m.position.latitude}:${m.position.longitude}:${m.title}:${m.snippet}:${m.markerColor?.toARGB32()}:${m.stopNumber}:${m.bookingId}:${m.eventType}:${m.isPassengerStop}')
        .join('|');
    final oldStopColorSignature = oldWidget.routeColorStops
        .map((s) =>
            '${s.order}:${s.position.latitude}:${s.position.longitude}:${s.color.toARGB32()}:${s.bookingId}:${s.eventType}')
        .join('|');
    final newStopColorSignature = widget.routeColorStops
        .map((s) =>
            '${s.order}:${s.position.latitude}:${s.position.longitude}:${s.color.toARGB32()}:${s.bookingId}:${s.eventType}')
        .join('|');
    if (oldSignature != newSignature ||
        oldStopColorSignature != newStopColorSignature) {
      unawaited(_rebuildMapLayers());
    }
  }

  Future<void> _rebuildMapLayers() async {
    await _buildPolylinesAndMarkers();
    if (!mounted) return;
    setState(() {});
  }

  Future<Set<Marker>> _buildExtraMarkers() async {
    final markers = <Marker>{};
    for (final marker in widget.extraMarkers) {
      BitmapDescriptor icon;
      if (marker.isPassengerStop &&
          marker.markerColor != null &&
          marker.stopNumber != null) {
        icon = await _buildPassengerStopIcon(
          color: marker.markerColor!,
          stopNumber: marker.stopNumber!,
        );
      } else {
        icon = BitmapDescriptor.defaultMarkerWithHue(marker.hue);
      }

      markers.add(
        Marker(
          markerId: MarkerId(marker.id),
          position: marker.position,
          icon: icon,
          infoWindow: InfoWindow(
            title: marker.title,
            snippet: marker.snippet,
          ),
        ),
      );
    }
    return markers;
  }

  Future<void> _loadRoute() async {
    final loadVersion = ++_routeLoadVersion;
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      // If an encoded polyline was provided (e.g. from DB), use it directly
      if (widget.encodedPolyline != null &&
          widget.encodedPolyline!.isNotEmpty) {
        final decoded = MapsService.decodePolyline(widget.encodedPolyline!);
        if (decoded.isNotEmpty) {
          _result = null;
          _storedPolylinePoints = decoded;
          _selectedRouteIndex = 0;
          await _buildPolylinesAndMarkers();
          if (!mounted || loadVersion != _routeLoadVersion) {
            return;
          }
          setState(() => _isLoading = false);
          Future.delayed(const Duration(milliseconds: 300), () => _fitBounds());
          return;
        }
      }

      _storedPolylinePoints = const <LatLng>[];

      final result = await _mapsService.getDirections(
        origin: widget.origin,
        destination: widget.destination,
        originPlaceId: widget.originPlaceId,
        destinationPlaceId: widget.destinationPlaceId,
        alternatives: widget.showAlternatives,
        departureTime: 'now',
      );

      if (!mounted || loadVersion != _routeLoadVersion) {
        return;
      }

      if (result == null || result.routes.isEmpty) {
        // Directions API failed — show markers only (no polyline)
        _result = null;
        _storedPolylinePoints = const <LatLng>[];
        _polylines = {};
        _markers = {
          Marker(
            markerId: const MarkerId('origin'),
            position: widget.origin,
            icon: BitmapDescriptor.defaultMarkerWithHue(
                BitmapDescriptor.hueGreen),
            infoWindow: InfoWindow(title: widget.originLabel),
          ),
          Marker(
            markerId: const MarkerId('destination'),
            position: widget.destination,
            icon:
                BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueRed),
            infoWindow: InfoWindow(title: widget.destinationLabel),
          ),
          ...await _buildExtraMarkers(),
        };
        if (loadVersion != _routeLoadVersion) return;
        setState(() => _isLoading = false);
        Future.delayed(const Duration(milliseconds: 300), () => _fitBounds());
        return;
      }

      _result = result;
      _selectedRouteIndex = 0;
      await _buildPolylinesAndMarkers();

      if (!mounted || loadVersion != _routeLoadVersion) {
        return;
      }

      setState(() => _isLoading = false);

      // Fit bounds after a brief delay for map to initialize
      Future.delayed(const Duration(milliseconds: 300), () {
        if (loadVersion != _routeLoadVersion) return;
        _fitBounds();
      });

      widget.onRouteSelected?.call(result.routes[0]);
    } catch (e) {
      if (!mounted || loadVersion != _routeLoadVersion) {
        return;
      }
      setState(() {
        _error = e.toString();
        _isLoading = false;
      });
    }
  }

  Future<void> _buildPolylinesAndMarkers() async {
    final markers = <Marker>{
      Marker(
        markerId: const MarkerId('origin'),
        position: widget.origin,
        icon: BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueGreen),
        infoWindow: InfoWindow(title: widget.originLabel),
      ),
      Marker(
        markerId: const MarkerId('destination'),
        position: widget.destination,
        icon: BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueRed),
        infoWindow: InfoWindow(title: widget.destinationLabel),
      ),
    };
    markers.addAll(await _buildExtraMarkers());

    List<LatLng> routePoints = const <LatLng>[];
    if (_result != null && _result!.routes.isNotEmpty) {
      routePoints = _result!.routes[_selectedRouteIndex].polylinePoints;
    } else if (_storedPolylinePoints.length >= 2) {
      routePoints = _storedPolylinePoints;
    }

    final polylines = _buildSegmentedRoutePolylines(routePoints);
    if (polylines.isEmpty && routePoints.length >= 2) {
      polylines.add(
        Polyline(
          polylineId: _result != null
              ? PolylineId('route_$_selectedRouteIndex')
              : const PolylineId('stored_route'),
          points: routePoints,
          color: AppColors.primary,
          width: 6,
          zIndex: 2,
        ),
      );
    }

    _polylines = polylines;
    _markers = markers;
  }

  Set<Polyline> _buildSegmentedRoutePolylines(List<LatLng> routePoints) {
    final polylines = <Polyline>{};
    if (routePoints.length < 2) {
      return polylines;
    }

    final orderedStops = widget.routeColorStops
        .where((stop) => stop.order > 0)
        .toList(growable: false)
      ..sort((a, b) => a.order.compareTo(b.order));

    if (orderedStops.isEmpty) {
      return polylines;
    }

    var startIndex = 0;
    var segmentIndex = 0;

    for (final stop in orderedStops) {
      final stopIndex =
          _nearestPolylinePointIndex(routePoints, stop.position, startIndex);
      if (stopIndex <= startIndex) {
        continue;
      }

      final segmentPoints = routePoints.sublist(startIndex, stopIndex + 1);
      if (segmentPoints.length >= 2) {
        polylines.add(
          Polyline(
            polylineId: PolylineId('route_color_seg_${segmentIndex++}'),
            points: segmentPoints,
            color: stop.color,
            width: 6,
            zIndex: 2,
          ),
        );
      }
      startIndex = stopIndex;
    }

    if (startIndex < routePoints.length - 1) {
      final finalPoints = routePoints.sublist(startIndex);
      if (finalPoints.length >= 2) {
        polylines.add(
          Polyline(
            polylineId: PolylineId('route_color_seg_${segmentIndex++}'),
            points: finalPoints,
            color: AppColors.primary,
            width: 6,
            zIndex: 2,
          ),
        );
      }
    }

    return polylines;
  }

  int _nearestPolylinePointIndex(
    List<LatLng> points,
    LatLng target,
    int startIndex,
  ) {
    var bestIndex = startIndex.clamp(0, points.length - 1);
    var bestDistance = double.infinity;

    for (var i = bestIndex; i < points.length; i++) {
      final dLat = points[i].latitude - target.latitude;
      final dLng = points[i].longitude - target.longitude;
      final distanceScore = (dLat * dLat) + (dLng * dLng);
      if (distanceScore < bestDistance) {
        bestDistance = distanceScore;
        bestIndex = i;
      }
    }
    return bestIndex;
  }

  Future<BitmapDescriptor> _buildPassengerStopIcon({
    required Color color,
    required int stopNumber,
  }) async {
    final cacheKey = '${color.toARGB32()}:$stopNumber';
    final cached = _customMarkerIconCache[cacheKey];
    if (cached != null) {
      return cached;
    }

    try {
      const canvasSize = 72.0;
      final recorder = ui.PictureRecorder();
      final canvas = Canvas(recorder);

      const center = Offset(canvasSize / 2, canvasSize / 2);
      final shadowPaint = Paint()
        ..color = Colors.black.withValues(alpha: 0.20)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 3);
      canvas.drawCircle(
        Offset(center.dx, center.dy + 3),
        19,
        shadowPaint,
      );

      final fillPaint = Paint()..color = color;
      canvas.drawCircle(center, 18, fillPaint);

      final borderPaint = Paint()
        ..color = Colors.white
        ..style = PaintingStyle.stroke
        ..strokeWidth = 3;
      canvas.drawCircle(center, 18, borderPaint);

      final label = stopNumber.toString();
      final textPainter = TextPainter(
        text: TextSpan(
          text: label,
          style: TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.w800,
            fontSize: label.length >= 3 ? 14 : (label.length == 2 ? 16 : 18),
            height: 1.0,
          ),
        ),
        textAlign: TextAlign.center,
        textDirection: TextDirection.ltr,
      )..layout();

      textPainter.paint(
        canvas,
        Offset(
          center.dx - (textPainter.width / 2),
          center.dy - (textPainter.height / 2),
        ),
      );

      final image = await recorder
          .endRecording()
          .toImage(canvasSize.toInt(), canvasSize.toInt());
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      if (bytes == null) {
        return BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueAzure);
      }

      final descriptor = BitmapDescriptor.bytes(
        Uint8List.view(bytes.buffer),
      );
      _customMarkerIconCache[cacheKey] = descriptor;
      return descriptor;
    } catch (_) {
      return BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueAzure);
    }
  }

  Future<void> _selectRoute(int index) async {
    setState(() => _selectedRouteIndex = index);
    await _buildPolylinesAndMarkers();
    if (!mounted) return;
    setState(() {});
    widget.onRouteSelected?.call(_result!.routes[index]);
  }

  void _fitBounds() {
    if (_mapController == null) return;

    try {
      // If we have a DirectionsResult, use its bounds
      if (_result != null) {
        final bounds = _result!.routes[_selectedRouteIndex].bounds;
        _mapController!.animateCamera(
          CameraUpdate.newLatLngBounds(bounds, 60),
        );
        return;
      }

      // Otherwise compute bounds from origin + destination (stored polyline case)
      final sw = LatLng(
        widget.origin.latitude < widget.destination.latitude
            ? widget.origin.latitude
            : widget.destination.latitude,
        widget.origin.longitude < widget.destination.longitude
            ? widget.origin.longitude
            : widget.destination.longitude,
      );
      final ne = LatLng(
        widget.origin.latitude > widget.destination.latitude
            ? widget.origin.latitude
            : widget.destination.latitude,
        widget.origin.longitude > widget.destination.longitude
            ? widget.origin.longitude
            : widget.destination.longitude,
      );
      _mapController!.animateCamera(
        CameraUpdate.newLatLngBounds(
            LatLngBounds(southwest: sw, northeast: ne), 60),
      );
    } catch (e) {
      debugPrint('Error animating camera: $e');
      // Retry for web maps initialization delay
      if (kIsWeb && e.toString().contains('buildView')) {
        Future.delayed(const Duration(milliseconds: 500), _fitBounds);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return SizedBox(
        height: widget.height,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const CircularProgressIndicator(color: AppColors.primary),
              const SizedBox(height: 12),
              Text('Finding best route…',
                  style:
                      TextStyle(color: AppColors.textSecondary, fontSize: 13)),
            ],
          ),
        ),
      );
    }

    if (_error != null) {
      return SizedBox(
        height: widget.height,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: AppColors.error, size: 32),
              const SizedBox(height: 8),
              Text(_error!, style: const TextStyle(color: AppColors.error)),
              const SizedBox(height: 8),
              TextButton(onPressed: _loadRoute, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }

    final selectedRoute = _result?.routes[_selectedRouteIndex];
    final bool hasDirectionsResult = selectedRoute != null;

    return Column(
      children: [
        // ── Map ─────────────────────────────────────
        ClipRRect(
          borderRadius: BorderRadius.circular(16),
          child: SizedBox(
            height: widget.height,
            child: GoogleMap(
              initialCameraPosition: CameraPosition(
                target: LatLng(
                  (widget.origin.latitude + widget.destination.latitude) / 2,
                  (widget.origin.longitude + widget.destination.longitude) / 2,
                ),
                zoom: 12,
              ),
              onMapCreated: (controller) {
                _mapController = controller;
                Future.delayed(const Duration(milliseconds: 300), _fitBounds);
              },
              polylines: _polylines,
              markers: _markers,
              myLocationEnabled: false,
              zoomControlsEnabled: false,
              mapToolbarEnabled: false,
              scrollGesturesEnabled: widget.interactive,
              zoomGesturesEnabled: widget.interactive,
              rotateGesturesEnabled: widget.interactive,
              tiltGesturesEnabled: false,
            ),
          ),
        ),

        if (widget.showInfoCard && hasDirectionsResult)
          const SizedBox(height: 12),

        // ── Route info card (only when Directions API result available) ──
        if (widget.showInfoCard && hasDirectionsResult)
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(color: AppColors.border),
            ),
            child: Column(
              children: [
                Row(
                  children: [
                    // Distance
                    Expanded(
                      child: _routeInfoTile(
                        icon: Icons.straighten_rounded,
                        value: selectedRoute.distanceText,
                        label: 'Distance',
                        color: AppColors.primary,
                      ),
                    ),
                    Container(width: 1, height: 40, color: AppColors.divider),
                    // Duration
                    Expanded(
                      child: _routeInfoTile(
                        icon: Icons.schedule_rounded,
                        value: selectedRoute.durationInTrafficText ??
                            selectedRoute.durationText,
                        label: selectedRoute.durationInTrafficText != null
                            ? 'Current duration with traffic'
                            : 'Duration',
                        color: AppColors.secondary,
                      ),
                    ),
                  ],
                ),

                // Route via
                if (selectedRoute.summary.isNotEmpty) ...[
                  const Divider(height: 20),
                  Row(
                    children: [
                      Icon(Icons.alt_route,
                          size: 16, color: AppColors.textSecondary),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Via ${selectedRoute.summary}',
                          style: TextStyle(
                              color: AppColors.textSecondary, fontSize: 12),
                        ),
                      ),
                    ],
                  ),
                ],

                // Alternative routes selector
                if (_result!.routes.length > 1) ...[
                  const Divider(height: 20),
                  SizedBox(
                    height: 36,
                    child: ListView.separated(
                      scrollDirection: Axis.horizontal,
                      itemCount: _result!.routes.length,
                      separatorBuilder: (_, __) => const SizedBox(width: 8),
                      itemBuilder: (ctx, i) {
                        final route = _result!.routes[i];
                        final isSelected = i == _selectedRouteIndex;
                        return GestureDetector(
                          onTap: () => _selectRoute(i),
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 14, vertical: 6),
                            decoration: BoxDecoration(
                              color: isSelected
                                  ? AppColors.primary
                                  : AppColors.backgroundLight,
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(
                                color: isSelected
                                    ? AppColors.primary
                                    : AppColors.border,
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  route.durationText,
                                  style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w600,
                                    color: isSelected
                                        ? Colors.white
                                        : AppColors.textPrimary,
                                  ),
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  route.distanceText,
                                  style: TextStyle(
                                    fontSize: 11,
                                    color: isSelected
                                        ? Colors.white.withValues(alpha: 0.8)
                                        : AppColors.textSecondary,
                                  ),
                                ),
                                if (i == 0) ...[
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
                ],
              ],
            ),
          ),
      ],
    );
  }

  Widget _routeInfoTile({
    required IconData icon,
    required String value,
    required String label,
    required Color color,
  }) {
    return Column(
      children: [
        Icon(icon, color: color, size: 22),
        const SizedBox(height: 6),
        Text(value,
            style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
        const SizedBox(height: 2),
        Text(label,
            style: TextStyle(color: AppColors.textSecondary, fontSize: 11)),
      ],
    );
  }
}

/// Standalone full-screen route view (for ride detail pages, etc.)
class RouteMapScreen extends StatelessWidget {
  final LatLng origin;
  final LatLng destination;
  final String originLabel;
  final String destinationLabel;

  const RouteMapScreen({
    super.key,
    required this.origin,
    required this.destination,
    this.originLabel = 'Pickup',
    this.destinationLabel = 'Drop-off',
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Route Map'),
        backgroundColor: AppColors.surface,
        foregroundColor: AppColors.textPrimary,
        elevation: 0,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: RouteMapWidget(
          origin: origin,
          destination: destination,
          originLabel: originLabel,
          destinationLabel: destinationLabel,
          height: MediaQuery.of(context).size.height * 0.55,
          showAlternatives: true,
        ),
      ),
    );
  }
}
