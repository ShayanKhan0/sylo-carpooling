import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter_polyline_points/flutter_polyline_points.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import 'api_client.dart';

/// Central Google Maps service — Directions, Places, Geocoding, Distance Matrix.
///
/// All requests go through the backend proxy at `/api/v1/maps/*` (JWT via [ApiClient])
/// so the API key stays server-side and Flutter Web avoids CORS.
class MapsService {
  static final MapsService _instance = MapsService._internal();
  factory MapsService() => _instance;
  MapsService._internal();

  static final PolylinePoints _polylineDecoder = PolylinePoints();

  final ApiClient _api = ApiClient();

  static const String _mapsPrefix = '/maps';

  // ═══════════════════════════════════════════════════════════
  //  PLACES AUTOCOMPLETE
  // ═══════════════════════════════════════════════════════════

  Future<List<PlacePrediction>> searchPlaces(
    String query, {
    LatLng? location,
    int radius = 50000,
    String? sessionToken,
  }) async {
    if (query.trim().isEmpty) return [];

    final params = <String, dynamic>{
      'input': query,
      'components': 'country:pk',
    };

    if (location != null) {
      params['location'] = '${location.latitude},${location.longitude}';
      params['radius'] = radius;
    }
    if (sessionToken != null) params['sessiontoken'] = sessionToken;

    try {
      final res = await _api.dio.get(
        '$_mapsPrefix/autocomplete',
        queryParameters: params,
      );

      if (res.data['status'] == 'OK') {
        return (res.data['predictions'] as List)
            .map((p) => PlacePrediction.fromJson(p))
            .toList();
      }
      debugPrint(
          '[MapsService] searchPlaces status: ${res.data['status']} — ${res.data['error_message'] ?? 'no error message'}');
      return [];
    } catch (e) {
      debugPrint('[MapsService] searchPlaces exception: $e');
      return [];
    }
  }

  Future<PlaceDetail?> getPlaceDetails(
    String placeId, {
    String? sessionToken,
  }) async {
    final params = <String, dynamic>{
      'place_id': placeId,
      'fields': 'geometry,formatted_address,name',
    };
    if (sessionToken != null) params['sessiontoken'] = sessionToken;

    try {
      final res = await _api.dio.get(
        '$_mapsPrefix/place-details',
        queryParameters: params,
      );

      if (res.data['status'] == 'OK') {
        return PlaceDetail.fromJson(res.data['result']);
      }
      debugPrint(
          '[MapsService] getPlaceDetails status: ${res.data['status']} — ${res.data['error_message'] ?? 'no error message'}');
      return null;
    } catch (e) {
      debugPrint('[MapsService] getPlaceDetails exception: $e');
      return null;
    }
  }

  // ═══════════════════════════════════════════════════════════
  //  GEOCODING (Address ↔ LatLng)
  // ═══════════════════════════════════════════════════════════

  Future<String?> getAddressFromLatLng(LatLng position) async {
    try {
      final res = await _api.dio.get(
        '$_mapsPrefix/geocode',
        queryParameters: {
          'latlng': '${position.latitude},${position.longitude}',
        },
      );

      if (res.data['status'] == 'OK' &&
          (res.data['results'] as List).isNotEmpty) {
        return res.data['results'][0]['formatted_address'];
      }
      return null;
    } catch (e) {
      return null;
    }
  }

  Future<LatLng?> getLatLngFromAddress(String address) async {
    try {
      final res = await _api.dio.get(
        '$_mapsPrefix/geocode',
        queryParameters: {
          'address': address,
          'components': 'country:PK',
        },
      );

      if (res.data['status'] == 'OK' &&
          (res.data['results'] as List).isNotEmpty) {
        final loc = res.data['results'][0]['geometry']['location'];
        return LatLng(loc['lat'], loc['lng']);
      }
      return null;
    } catch (e) {
      return null;
    }
  }

  Future<LatLng?> snapToNearestRoad(LatLng point) async {
    try {
      final res = await _api.dio.get(
        '$_mapsPrefix/snap-to-road',
        queryParameters: {
          'path': '${point.latitude},${point.longitude}',
          'interpolate': false,
        },
      );

      if (res.data['status'] != 'OK') {
        return null;
      }

      final snapped = res.data['snappedPoints'] as List?;
      if (snapped == null || snapped.isEmpty) {
        return null;
      }

      final first = snapped.first as Map<String, dynamic>;
      final loc = first['location'] as Map<String, dynamic>?;
      if (loc == null) {
        return null;
      }

      final lat = (loc['latitude'] as num?)?.toDouble();
      final lng = (loc['longitude'] as num?)?.toDouble();
      if (lat == null || lng == null) {
        return null;
      }

      return LatLng(lat, lng);
    } catch (_) {
      return null;
    }
  }

  // ═══════════════════════════════════════════════════════════
  //  DIRECTIONS (Route, Polyline, Duration, Distance)
  // ═══════════════════════════════════════════════════════════

  Future<DirectionsResult?> getDirections({
    required LatLng origin,
    required LatLng destination,
    String? originPlaceId,
    String? destinationPlaceId,
    List<LatLng>? waypoints,
    bool alternatives = true,
    String travelMode = 'driving',
    bool avoidTolls = false,
    bool avoidHighways = false,
    String? departureTime,
  }) async {
    final normalizedOriginPlaceId = originPlaceId?.trim();
    final normalizedDestinationPlaceId = destinationPlaceId?.trim();

    final originParam =
        (normalizedOriginPlaceId != null && normalizedOriginPlaceId.isNotEmpty)
            ? 'place_id:$normalizedOriginPlaceId'
            : '${origin.latitude},${origin.longitude}';
    final destinationParam = (normalizedDestinationPlaceId != null &&
            normalizedDestinationPlaceId.isNotEmpty)
        ? 'place_id:$normalizedDestinationPlaceId'
        : '${destination.latitude},${destination.longitude}';

    final params = <String, dynamic>{
      'origin': originParam,
      'destination': destinationParam,
      'mode': travelMode,
      'alternatives': alternatives,
    };

    if (waypoints != null && waypoints.isNotEmpty) {
      params['waypoints'] =
          waypoints.map((w) => '${w.latitude},${w.longitude}').join('|');
    }

    final avoid = <String>[];
    if (avoidTolls) avoid.add('tolls');
    if (avoidHighways) avoid.add('highways');
    if (avoid.isNotEmpty) params['avoid'] = avoid.join('|');

    if (departureTime != null) {
      params['departure_time'] = departureTime;
      params['traffic_model'] = 'best_guess';
    }

    try {
      final res = await _api.dio.get(
        '$_mapsPrefix/directions',
        queryParameters: params,
      );

      debugPrint(
          '[MapsService] getDirections response status: ${res.data['status']}');
      if (res.data['status'] == 'OK') {
        return DirectionsResult.fromJson(res.data);
      }

      // Retry once with a simpler request. Some proxies/providers reject
      // alternatives + departure_time combinations intermittently.
      final retryParams = <String, dynamic>{
        'origin': originParam,
        'destination': destinationParam,
        'mode': travelMode,
        'alternatives': false,
      };
      final retry = await _api.dio.get(
        '$_mapsPrefix/directions',
        queryParameters: retryParams,
      );
      debugPrint(
          '[MapsService] getDirections retry status: ${retry.data['status']}');
      if (retry.data['status'] == 'OK') {
        return DirectionsResult.fromJson(retry.data);
      }

      debugPrint(
          '[MapsService] getDirections FAILED: ${retry.data['status']} — ${retry.data['error_message'] ?? 'no error message'}');
      return null;
    } catch (e) {
      debugPrint('[MapsService] getDirections exception: $e');
      return null;
    }
  }

  // ═══════════════════════════════════════════════════════════
  //  DISTANCE MATRIX
  // ═══════════════════════════════════════════════════════════

  Future<DistanceMatrixResult?> getDistanceMatrix({
    required List<LatLng> origins,
    required List<LatLng> destinations,
    String travelMode = 'driving',
  }) async {
    try {
      final res = await _api.dio.get(
        '$_mapsPrefix/distance-matrix',
        queryParameters: {
          'origins':
              origins.map((o) => '${o.latitude},${o.longitude}').join('|'),
          'destinations':
              destinations.map((d) => '${d.latitude},${d.longitude}').join('|'),
          'mode': travelMode,
        },
      );

      if (res.data['status'] == 'OK') {
        return DistanceMatrixResult.fromJson(res.data);
      }
      return null;
    } catch (e) {
      return null;
    }
  }

  // ═══════════════════════════════════════════════════════════
  //  EXTERNAL NAVIGATION (Google Maps app / browser)
  // ═══════════════════════════════════════════════════════════

  /// Opens Google Maps turn-by-turn directions to [destination].
  /// [origin] optional — user's current location omitted if null (Maps uses device GPS).
  static Future<bool> openGoogleMapsDirections({
    required LatLng destination,
    LatLng? origin,
    String travelMode = 'driving',
  }) async {
    final dest = '${destination.latitude},${destination.longitude}';
    final buf = StringBuffer(
      'https://www.google.com/maps/dir/?api=1&destination=$dest&travelmode=$travelMode',
    );
    if (origin != null) {
      buf.write('&origin=${origin.latitude},${origin.longitude}');
    }
    final uri = Uri.parse(buf.toString());
    if (await canLaunchUrl(uri)) {
      return launchUrl(uri, mode: LaunchMode.externalApplication);
    }
    return false;
  }

  /// Single destination from current location (no origin) — best for "Navigate to pickup".
  static Future<bool> openGoogleMapsToLocation(LatLng target) async {
    final uri = Uri.parse(
      'https://www.google.com/maps/dir/?api=1&destination=${target.latitude},${target.longitude}&travelmode=driving',
    );
    if (await canLaunchUrl(uri)) {
      return launchUrl(uri, mode: LaunchMode.externalApplication);
    }
    return false;
  }

  // ═══════════════════════════════════════════════════════════
  //  POLYLINE DECODER
  // ═══════════════════════════════════════════════════════════

  /// Decode an encoded polyline string into a list of LatLng points.
  static List<LatLng> decodePolyline(String encoded) {
    if (encoded.isEmpty) {
      return const <LatLng>[];
    }

    try {
      final decodedPoints = _polylineDecoder.decodePolyline(encoded);
      return decodedPoints
          .map((point) => LatLng(point.latitude, point.longitude))
          .toList(growable: false);
    } catch (e) {
      debugPrint('[MapsService] decodePolyline failed: $e');
      return const <LatLng>[];
    }
  }
}

// ═════════════════════════════════════════════════════════════
//  DATA MODELS
// ═════════════════════════════════════════════════════════════

/// A place prediction from Places Autocomplete.
class PlacePrediction {
  final String placeId;
  final String description;
  final String mainText;
  final String secondaryText;

  PlacePrediction({
    required this.placeId,
    required this.description,
    required this.mainText,
    required this.secondaryText,
  });

  factory PlacePrediction.fromJson(Map<String, dynamic> json) {
    final structured = json['structured_formatting'] ?? {};
    return PlacePrediction(
      placeId: json['place_id'] ?? '',
      description: json['description'] ?? '',
      mainText: structured['main_text'] ?? '',
      secondaryText: structured['secondary_text'] ?? '',
    );
  }
}

/// Detail info about a place (has lat/lng).
class PlaceDetail {
  final String name;
  final String address;
  final LatLng location;

  PlaceDetail({
    required this.name,
    required this.address,
    required this.location,
  });

  factory PlaceDetail.fromJson(Map<String, dynamic> json) {
    final geo = json['geometry']['location'];
    return PlaceDetail(
      name: json['name'] ?? '',
      address: json['formatted_address'] ?? '',
      location: LatLng(
        (geo['lat'] as num).toDouble(),
        (geo['lng'] as num).toDouble(),
      ),
    );
  }
}

/// Full directions result with potentially multiple routes.
class DirectionsResult {
  final List<DirectionsRoute> routes;

  DirectionsResult({required this.routes});

  factory DirectionsResult.fromJson(Map<String, dynamic> json) {
    return DirectionsResult(
      routes: (json['routes'] as List)
          .map((r) => DirectionsRoute.fromJson(r))
          .toList(),
    );
  }

  /// Convenience — the primary (best) route.
  DirectionsRoute? get bestRoute => routes.isNotEmpty ? routes.first : null;
}

/// A single route option.
class DirectionsRoute {
  static const double _maxStepJoinGapMeters = 150.0;
  static const double _maxStepChunkJoinGapMeters = 220.0;
  static const double _maxContinuityGapMeters = 2500.0;
  static const double _spikeMinSegmentMeters = 700.0;
  static const double _spikeInflationRatio = 3.5;
  static const double _densifyThresholdMeters = 90.0;
  static const double _densifyTargetSpacingMeters = 35.0;
  static const int _maxDensifyPointsPerSegment = 10;
  static const double _routeBoundsPaddingDegrees = 1.2;
  static const double _maxAbsLongitudeBeforeDrop = 1080.0;
  static const double _globalOutlierGapMeters = 50000.0;
  static const double _minDetailedCoverageRatio = 0.55;
  static const double _maxEndpointMissMeters = 1200.0;

  final String summary;
  final List<LatLng> polylinePoints;
  final List<List<LatLng>> polylineChunks;
  final String encodedPolyline;
  final int distanceMeters;
  final String distanceText;
  final int durationSeconds;
  final String durationText;
  final String? durationInTrafficText;
  final int? durationInTrafficSeconds;
  final LatLngBounds bounds;
  final List<RouteStep> steps;
  final List<String> warnings;

  DirectionsRoute({
    required this.summary,
    required this.polylinePoints,
    required this.polylineChunks,
    required this.encodedPolyline,
    required this.distanceMeters,
    required this.distanceText,
    required this.durationSeconds,
    required this.durationText,
    this.durationInTrafficText,
    this.durationInTrafficSeconds,
    required this.bounds,
    required this.steps,
    this.warnings = const [],
  });

  factory DirectionsRoute.fromJson(Map<String, dynamic> json) {
    final legs = json['legs'] as List;
    if (legs.isEmpty) {
      throw const FormatException('Directions route has no legs');
    }

    int totalDistanceM = 0;
    int totalDurationS = 0;
    int? totalTrafficS;
    final allSteps = <RouteStep>[];

    for (final raw in legs) {
      final leg = raw as Map<String, dynamic>;
      totalDistanceM += (leg['distance']?['value'] ?? 0) as int;
      totalDurationS += (leg['duration']?['value'] ?? 0) as int;
      final dit = leg['duration_in_traffic'];
      if (dit is Map) {
        final v = dit['value'];
        if (v is int) {
          totalTrafficS = (totalTrafficS ?? 0) + v;
        }
      }
      final steps = leg['steps'] as List? ?? [];
      for (final s in steps) {
        allSteps.add(RouteStep.fromJson(s as Map<String, dynamic>));
      }
    }

    final boundsNE = json['bounds']['northeast'];
    final boundsSW = json['bounds']['southwest'];
    final routeBounds = LatLngBounds(
      northeast: LatLng(boundsNE['lat'], boundsNE['lng']),
      southwest: LatLng(boundsSW['lat'], boundsSW['lng']),
    );

    final overviewPolyline =
        (json['overview_polyline']?['points'] as String?) ?? '';
    final routePolylinePoints = overviewPolyline.isNotEmpty
        ? _normalizePolylinePoints(MapsService.decodePolyline(overviewPolyline))
        : <LatLng>[];
    final routePolylineChunks = routePolylinePoints.length >= 2
        ? <List<LatLng>>[routePolylinePoints]
        : const <List<LatLng>>[];
    final distanceKm = totalDistanceM / 1000.0;
    final durationMin = (totalDurationS / 60).round();

    return DirectionsRoute(
      summary: json['summary'] ?? '',
      encodedPolyline: overviewPolyline,
      polylinePoints: routePolylinePoints,
      polylineChunks: routePolylineChunks,
      distanceMeters: totalDistanceM,
      distanceText:
          '${distanceKm.toStringAsFixed(1)} km', // clearer for multi-leg
      durationSeconds: totalDurationS,
      durationText: '$durationMin min',
      durationInTrafficText: totalTrafficS != null
          ? '${((totalTrafficS) / 60).round()} min'
          : null,
      durationInTrafficSeconds: totalTrafficS,
      bounds: routeBounds,
      steps: allSteps,
      warnings:
          (json['warnings'] as List?)?.map((w) => w.toString()).toList() ?? [],
    );
  }

  static List<List<LatLng>> _decodeStepPolylineChunks(List legs) {
    final chunks = <List<LatLng>>[];

    for (final rawLeg in legs) {
      if (rawLeg is! Map) continue;
      final rawSteps = rawLeg['steps'];
      if (rawSteps is! List) continue;

      for (final rawStep in rawSteps) {
        if (rawStep is! Map) continue;
        final rawPolyline = rawStep['polyline'];
        if (rawPolyline is! Map) continue;
        final encoded = rawPolyline['points'];
        if (encoded is! String || encoded.isEmpty) continue;

        final decoded = MapsService.decodePolyline(encoded);
        if (decoded.length >= 2) {
          chunks.add(decoded);
        }
      }
    }

    return chunks;
  }

  static List<List<LatLng>> _sanitizeAndDensifyChunks(
      List<List<LatLng>> chunks) {
    final cleaned = <List<LatLng>>[];
    for (final chunk in chunks) {
      final sanitized = _sanitizePolylinePoints(chunk);
      if (sanitized.length < 2) continue;
      final dense = _densifyPolyline(sanitized);
      if (dense.length >= 2) {
        cleaned.add(dense);
      }
    }
    return cleaned;
  }

  static List<LatLng> _normalizePolylinePoints(List<LatLng> points) {
    final normalized = <LatLng>[];
    for (final point in points) {
      final safe = _normalizePoint(point);
      if (safe != null) {
        normalized.add(safe);
      }
    }
    return normalized;
  }

  static List<LatLng> _removeGlobalOutlierJumps(
    List<LatLng> points,
    LatLng? routeStart,
    LatLng? routeEnd,
  ) {
    if (points.length < 2) {
      return points;
    }

    final spikeCleaned = <LatLng>[points.first];
    for (var i = 1; i < points.length - 1; i++) {
      final prev = points[i - 1];
      final curr = points[i];
      final next = points[i + 1];
      final prevToCurr = _distanceMeters(prev, curr);
      final currToNext = _distanceMeters(curr, next);
      final prevToNext = _distanceMeters(prev, next);

      final isGlobalSpike = prevToCurr > _globalOutlierGapMeters &&
          currToNext > _globalOutlierGapMeters &&
          prevToNext <= (_maxContinuityGapMeters * 2);
      if (!isGlobalSpike) {
        spikeCleaned.add(curr);
      }
    }
    spikeCleaned.add(points.last);

    final chunks = <List<LatLng>>[];
    var currentChunk = <LatLng>[spikeCleaned.first];
    for (var i = 1; i < spikeCleaned.length; i++) {
      final prev = spikeCleaned[i - 1];
      final curr = spikeCleaned[i];
      final segMeters = _distanceMeters(prev, curr);
      if (segMeters > _globalOutlierGapMeters) {
        if (currentChunk.length >= 2) {
          chunks.add(currentChunk);
        }
        currentChunk = <LatLng>[curr];
      } else {
        currentChunk.add(curr);
      }
    }
    if (currentChunk.length >= 2) {
      chunks.add(currentChunk);
    }

    if (chunks.isEmpty) {
      return spikeCleaned;
    }
    if (chunks.length == 1 || routeStart == null || routeEnd == null) {
      return _longestChunk(chunks);
    }

    List<LatLng>? bestChunk;
    var bestScore = double.infinity;
    for (final chunk in chunks) {
      final scoreForward = _distanceMeters(chunk.first, routeStart) +
          _distanceMeters(chunk.last, routeEnd);
      final scoreReverse = _distanceMeters(chunk.first, routeEnd) +
          _distanceMeters(chunk.last, routeStart);
      final score = min(scoreForward, scoreReverse);
      if (score < bestScore) {
        bestScore = score;
        bestChunk = chunk;
      }
    }

    if (bestChunk != null) {
      return bestChunk;
    }
    return _longestChunk(chunks);
  }

  static List<LatLng> _ensureRouteEndpoints(
    List<LatLng> points,
    LatLng? routeStart,
    LatLng? routeEnd,
  ) {
    if (points.isEmpty) {
      if (routeStart != null && routeEnd != null) {
        return <LatLng>[routeStart, routeEnd];
      }
      return points;
    }

    final adjusted = <LatLng>[...points];
    if (routeStart != null &&
        _distanceMeters(adjusted.first, routeStart) > _maxEndpointMissMeters) {
      adjusted.insert(0, routeStart);
    }
    if (routeEnd != null &&
        _distanceMeters(adjusted.last, routeEnd) > _maxEndpointMissMeters) {
      adjusted.add(routeEnd);
    }
    return adjusted;
  }

  static List<LatLng> _longestChunk(List<List<LatLng>> chunks) {
    List<LatLng> longest = chunks.first;
    for (final chunk in chunks) {
      if (chunk.length > longest.length) {
        longest = chunk;
      }
    }
    return longest;
  }

  static List<List<LatLng>> _filterUsableChunks(
      List<List<LatLng>> chunks, LatLngBounds bounds) {
    final usable = <List<LatLng>>[];
    for (final chunk in chunks) {
      final bounded = _filterPolylineToBounds(chunk, bounds);
      if (bounded.length < 2) {
        continue;
      }
      if (_hasChunkExtremeGap(bounded)) {
        continue;
      }
      usable.add(bounded);
    }
    return usable;
  }

  static bool _hasChunkExtremeGap(List<LatLng> points) {
    if (points.length < 2) {
      return true;
    }
    for (var i = 1; i < points.length; i++) {
      final segmentMeters = _distanceMeters(points[i - 1], points[i]);
      if (segmentMeters > _maxContinuityGapMeters) {
        return true;
      }
    }
    return false;
  }

  static List<LatLng> _filterPolylineToBounds(
      List<LatLng> points, LatLngBounds bounds) {
    if (points.length < 2) {
      return points;
    }

    final filtered = <LatLng>[];
    for (final point in points) {
      if (_isPointNearBounds(point, bounds)) {
        filtered.add(point);
      }
    }

    if (filtered.length >= 2) {
      return filtered;
    }
    // Keep original if aggressive bounds filtering would empty the route.
    return points;
  }

  static bool _isPointNearBounds(LatLng point, LatLngBounds bounds) {
    final minLat = min(bounds.southwest.latitude, bounds.northeast.latitude) -
        _routeBoundsPaddingDegrees;
    final maxLat = max(bounds.southwest.latitude, bounds.northeast.latitude) +
        _routeBoundsPaddingDegrees;
    final minLng = min(bounds.southwest.longitude, bounds.northeast.longitude) -
        _routeBoundsPaddingDegrees;
    final maxLng = max(bounds.southwest.longitude, bounds.northeast.longitude) +
        _routeBoundsPaddingDegrees;

    return point.latitude >= minLat &&
        point.latitude <= maxLat &&
        point.longitude >= minLng &&
        point.longitude <= maxLng;
  }

  static List<LatLng> _sanitizePolylinePoints(List<LatLng> points) {
    if (points.length < 2) {
      return points;
    }

    final deduped = <LatLng>[];
    for (final point in points) {
      final normalized = _normalizePoint(point);
      if (normalized == null) {
        continue;
      }
      if (deduped.isEmpty || !_samePoint(deduped.last, normalized)) {
        deduped.add(normalized);
      }
    }

    if (deduped.length < 2) {
      return deduped;
    }

    if (deduped.length < 3) {
      return deduped;
    }

    final cleaned = <LatLng>[deduped.first];
    for (var i = 1; i < deduped.length - 1; i++) {
      final prev = deduped[i - 1];
      final curr = deduped[i];
      final next = deduped[i + 1];

      final prevToCurr = _distanceMeters(prev, curr);
      final currToNext = _distanceMeters(curr, next);
      final prevToNext = _distanceMeters(prev, next);

      final isSpike = prevToCurr >= _spikeMinSegmentMeters &&
          currToNext >= _spikeMinSegmentMeters &&
          prevToNext > 0 &&
          (prevToCurr + currToNext) >= prevToNext * _spikeInflationRatio;

      if (!isSpike) {
        cleaned.add(curr);
      }
    }
    cleaned.add(deduped.last);

    if (cleaned.length < 2) {
      return deduped;
    }
    return cleaned;
  }

  static bool _isPolylineSuspicious(List<LatLng> points) {
    if (points.length < 2) {
      return true;
    }

    final segments = <double>[];
    var maxSegmentMeters = 0.0;
    var largeGapCount = 0;

    for (var i = 1; i < points.length; i++) {
      final segmentMeters = _distanceMeters(points[i - 1], points[i]);
      segments.add(segmentMeters);
      if (segmentMeters > maxSegmentMeters) {
        maxSegmentMeters = segmentMeters;
      }
      if (segmentMeters > _maxContinuityGapMeters) {
        largeGapCount++;
      }
    }

    if (largeGapCount > 0) {
      return true;
    }

    if (segments.length >= 4) {
      final sorted = [...segments]..sort();
      final median = sorted[sorted.length ~/ 2];
      if (median > 0 && maxSegmentMeters > median * 12) {
        return true;
      }
    }

    return false;
  }

  static bool _areChunksSuspicious(List<List<LatLng>> chunks) {
    if (chunks.isEmpty) {
      return true;
    }

    var usableChunkCount = 0;
    for (final chunk in chunks) {
      if (chunk.length >= 2) {
        usableChunkCount++;
      }
    }
    return usableChunkCount == 0;
  }

  static List<LatLng> _flattenPolylineChunks(List<List<LatLng>> chunks) {
    if (chunks.isEmpty) {
      return <LatLng>[];
    }

    final flattened = <LatLng>[];
    for (final chunk in chunks) {
      if (chunk.length < 2) continue;
      if (flattened.isEmpty) {
        flattened.addAll(chunk);
        continue;
      }

      final joinGapMeters = _distanceMeters(flattened.last, chunk.first);
      final allowedGap = max(_maxStepJoinGapMeters, _maxStepChunkJoinGapMeters);
      if (joinGapMeters > allowedGap) {
        // Do not bridge disjoint chunks; completeness checks will decide
        // whether to keep detailed geometry or fallback to overview.
        continue;
      }

      if (_samePoint(flattened.last, chunk.first)) {
        flattened.addAll(chunk.skip(1));
      } else {
        flattened.addAll(chunk);
      }
    }

    return flattened;
  }

  static double _maxSegmentMeters(List<LatLng> points) {
    if (points.length < 2) {
      return double.infinity;
    }
    var maxSegment = 0.0;
    for (var i = 1; i < points.length; i++) {
      final segment = _distanceMeters(points[i - 1], points[i]);
      if (segment > maxSegment) {
        maxSegment = segment;
      }
    }
    return maxSegment;
  }

  static double _maxSegmentMetersAcrossChunks(List<List<LatLng>> chunks) {
    if (chunks.isEmpty) {
      return double.infinity;
    }

    var maxSegment = 0.0;
    for (final chunk in chunks) {
      final chunkMax = _maxSegmentMeters(chunk);
      if (chunkMax > maxSegment) {
        maxSegment = chunkMax;
      }
    }
    return maxSegment;
  }

  static LatLng? _extractLegPoint(dynamic raw) {
    if (raw is! Map) {
      return null;
    }
    final lat = (raw['lat'] as num?)?.toDouble();
    final lng = (raw['lng'] as num?)?.toDouble();
    if (lat == null || lng == null) {
      return null;
    }
    return _normalizePoint(LatLng(lat, lng));
  }

  static double _polylineLengthMeters(List<LatLng> points) {
    if (points.length < 2) {
      return 0.0;
    }
    var total = 0.0;
    for (var i = 1; i < points.length; i++) {
      total += _distanceMeters(points[i - 1], points[i]);
    }
    return total;
  }

  static bool _areRouteEndpointsReasonable(
      List<LatLng> points, LatLng routeStart, LatLng routeEnd) {
    if (points.length < 2) {
      return false;
    }

    final startMiss = _distanceMeters(points.first, routeStart);
    final endMiss = _distanceMeters(points.last, routeEnd);
    final reverseStartMiss = _distanceMeters(points.first, routeEnd);
    final reverseEndMiss = _distanceMeters(points.last, routeStart);

    final forwardMatch = startMiss <= _maxEndpointMissMeters &&
        endMiss <= _maxEndpointMissMeters;
    final reverseMatch = reverseStartMiss <= _maxEndpointMissMeters &&
        reverseEndMiss <= _maxEndpointMissMeters;

    return forwardMatch || reverseMatch;
  }

  static List<LatLng> _densifyPolyline(List<LatLng> points) {
    if (points.length < 2) {
      return points;
    }

    final densified = <LatLng>[points.first];
    for (var i = 1; i < points.length; i++) {
      final prev = points[i - 1];
      final curr = points[i];
      final segmentMeters = _distanceMeters(prev, curr);

      if (segmentMeters > _densifyThresholdMeters) {
        final insertCount = min(
          _maxDensifyPointsPerSegment,
          max(0, (segmentMeters / _densifyTargetSpacingMeters).floor() - 1),
        );
        for (var j = 1; j <= insertCount; j++) {
          final t = j / (insertCount + 1);
          densified.add(_interpolatePoint(prev, curr, t));
        }
      }

      densified.add(curr);
    }

    return densified;
  }

  static LatLng? _normalizePoint(LatLng point) {
    final lat = point.latitude;
    var lng = point.longitude;

    if (!lat.isFinite || !lng.isFinite) {
      return null;
    }
    if (lat < -90.0 || lat > 90.0) {
      return null;
    }
    if (lng.abs() > _maxAbsLongitudeBeforeDrop) {
      return null;
    }

    while (lng > 180.0) {
      lng -= 360.0;
    }
    while (lng < -180.0) {
      lng += 360.0;
    }

    return LatLng(lat, lng);
  }

  static LatLng _interpolatePoint(LatLng a, LatLng b, double t) {
    return LatLng(
      a.latitude + (b.latitude - a.latitude) * t,
      a.longitude + (b.longitude - a.longitude) * t,
    );
  }

  static bool _samePoint(LatLng a, LatLng b) {
    return (a.latitude - b.latitude).abs() < 0.000001 &&
        (a.longitude - b.longitude).abs() < 0.000001;
  }

  static double _distanceMeters(LatLng a, LatLng b) {
    const double earthRadiusMeters = 6371000.0;
    final dLat = _degToRad(b.latitude - a.latitude);
    final dLng = _degToRad(b.longitude - a.longitude);
    final lat1 = _degToRad(a.latitude);
    final lat2 = _degToRad(b.latitude);

    final hav = (sin(dLat / 2) * sin(dLat / 2)) +
        cos(lat1) * cos(lat2) * (sin(dLng / 2) * sin(dLng / 2));
    final c = 2 * atan2(sqrt(hav), sqrt(1 - hav));
    return earthRadiusMeters * c;
  }

  static double _degToRad(double deg) => deg * 0.017453292519943295;

  /// Distance in km as a double.
  double get distanceKm => distanceMeters / 1000.0;

  /// Duration in minutes.
  int get durationMinutes => (durationSeconds / 60).round();
}

/// A single step in a route (turn-by-turn).
class RouteStep {
  final String instruction;
  final String distanceText;
  final int distanceMeters;
  final String durationText;
  final int durationSeconds;
  final LatLng startLocation;
  final LatLng endLocation;
  final String travelMode;
  final String? maneuver;

  RouteStep({
    required this.instruction,
    required this.distanceText,
    required this.distanceMeters,
    required this.durationText,
    required this.durationSeconds,
    required this.startLocation,
    required this.endLocation,
    required this.travelMode,
    this.maneuver,
  });

  factory RouteStep.fromJson(Map<String, dynamic> json) {
    return RouteStep(
      instruction: _stripHtml(json['html_instructions'] ?? ''),
      distanceText: json['distance']?['text'] ?? '',
      distanceMeters: json['distance']?['value'] ?? 0,
      durationText: json['duration']?['text'] ?? '',
      durationSeconds: json['duration']?['value'] ?? 0,
      startLocation: LatLng(
        json['start_location']['lat'],
        json['start_location']['lng'],
      ),
      endLocation: LatLng(
        json['end_location']['lat'],
        json['end_location']['lng'],
      ),
      travelMode: json['travel_mode'] ?? 'DRIVING',
      maneuver: json['maneuver'],
    );
  }

  static String _stripHtml(String html) {
    return html.replaceAll(RegExp(r'<[^>]*>'), '');
  }
}

/// Distance Matrix result.
class DistanceMatrixResult {
  final List<String> originAddresses;
  final List<String> destinationAddresses;
  final List<DistanceMatrixElement> elements;

  DistanceMatrixResult({
    required this.originAddresses,
    required this.destinationAddresses,
    required this.elements,
  });

  factory DistanceMatrixResult.fromJson(Map<String, dynamic> json) {
    final elements = <DistanceMatrixElement>[];
    for (final row in json['rows'] as List) {
      for (final el in row['elements'] as List) {
        elements.add(DistanceMatrixElement.fromJson(el));
      }
    }
    return DistanceMatrixResult(
      originAddresses: (json['origin_addresses'] as List).cast<String>(),
      destinationAddresses:
          (json['destination_addresses'] as List).cast<String>(),
      elements: elements,
    );
  }
}

/// A single element in a distance matrix.
class DistanceMatrixElement {
  final String status;
  final String? distanceText;
  final int? distanceMeters;
  final String? durationText;
  final int? durationSeconds;

  DistanceMatrixElement({
    required this.status,
    this.distanceText,
    this.distanceMeters,
    this.durationText,
    this.durationSeconds,
  });

  factory DistanceMatrixElement.fromJson(Map<String, dynamic> json) {
    return DistanceMatrixElement(
      status: json['status'] ?? 'UNKNOWN',
      distanceText: json['distance']?['text'],
      distanceMeters: json['distance']?['value'],
      durationText: json['duration']?['text'],
      durationSeconds: json['duration']?['value'],
    );
  }
}
