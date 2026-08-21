import 'dart:async';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../constants/app_constants.dart';
import 'api_client.dart';

/// Model for a telemetry point (driver location update)
class TelemetryPoint {
  final DateTime timestamp;
  final double lat;
  final double lng;
  final double speed;
  final double? bearing;
  final double? accuracy;

  TelemetryPoint({
    required this.timestamp,
    required this.lat,
    required this.lng,
    required this.speed,
    this.bearing,
    this.accuracy,
  });

  factory TelemetryPoint.fromJson(Map<String, dynamic> json) {
    return TelemetryPoint(
      timestamp: DateTime.tryParse(json['timestamp']?.toString() ?? '') ??
          DateTime.now(),
      lat: (json['lat'] ?? json['latitude'] ?? 0).toDouble(),
      lng: (json['lng'] ?? json['longitude'] ?? 0).toDouble(),
      speed: (json['speed'] ?? 0).toDouble(),
      bearing: json['bearing']?.toDouble(),
      accuracy: json['accuracy']?.toDouble(),
    );
  }

  Map<String, dynamic> toJson() => {
        'timestamp': timestamp.toIso8601String(),
        'lat': lat,
        'lng': lng,
        'speed': speed,
        if (bearing != null) 'bearing': bearing,
        if (accuracy != null) 'accuracy': accuracy,
      };
}

/// Service for real-time telemetry streaming via WebSocket or REST polling
class TelemetryService {
  final ApiClient _api = ApiClient();

  WebSocketChannel? _channel;
  StreamSubscription? _subscription;
  Timer? _pingTimer;
  Timer? _pollTimer;

  final StreamController<TelemetryPoint> _pointController =
      StreamController<TelemetryPoint>.broadcast();

  /// Stream of telemetry points from the driver
  Stream<TelemetryPoint> get pointStream => _pointController.stream;

  bool _isConnected = false;
  bool get isConnected => _isConnected;
  final ValueNotifier<String?> diagnosticsNotifier = ValueNotifier<String?>(null);
  final ValueNotifier<String> transportNotifier =
      ValueNotifier<String>('disconnected');

  String? _currentRideId;

  /// Connect to WebSocket for real-time telemetry
  Future<void> connect(String rideId) async {
    if (_currentRideId == rideId && _isConnected) return;

    await disconnect(); // Clean up any existing connection
    _currentRideId = rideId;

    try {
      diagnosticsNotifier.value = null;
      transportNotifier.value = 'connecting';
      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString(AppConstants.keyAccessToken);

      if (token == null) {
        // Fall back to polling if no token
        diagnosticsNotifier.value =
            'No auth token for telemetry websocket; using REST fallback polling.';
        _startPolling(rideId);
        return;
      }

      final wsUrl = '${AppConstants.wsBaseUrl}/ws/trip/$rideId?token=$token';
      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));

      _subscription = _channel!.stream.listen(
        (data) {
          // Mark socket ready only after receiving server data (welcome/ping/ack).
          _isConnected = true;
          transportNotifier.value = 'websocket';
          _handleMessage(data);
        },
        onError: (error) {
          _isConnected = false;
          diagnosticsNotifier.value =
              'Telemetry websocket error: $error. Falling back to REST polling.';
          // Fall back to polling on WebSocket error
          _startPolling(rideId);
        },
        onDone: () {
          _isConnected = false;
          transportNotifier.value = 'disconnected';
        },
      );

      // Start ping timer to keep connection alive
      _pingTimer = Timer.periodic(const Duration(seconds: 25), (_) {
        if (_isConnected && _channel != null) {
          _channel!.sink.add(jsonEncode({'type': 'pong'}));
        }
      });
    } catch (e) {
      // Fall back to REST polling if WebSocket fails
      diagnosticsNotifier.value =
          'Telemetry websocket connection failed: $e. Using REST fallback polling.';
      _startPolling(rideId);
    }
  }

  void _handleMessage(dynamic data) {
    try {
      final json = jsonDecode(data);

      // Handle different message types
      final type = json['type']?.toString();

      if (type == 'ping') {
        // Respond to server ping with pong
        _channel?.sink.add(jsonEncode({'type': 'pong'}));
        return;
      }

      if (type == 'ack' || type == 'welcome') {
        // Acks/welcome messages do not carry location coordinates.
        return;
      }

      if (type == 'location_sharing_disabled') {
        final serverMessage = json['message']?.toString();
        diagnosticsNotifier.value = serverMessage == null || serverMessage.isEmpty
            ? 'Location sharing disabled for this account.'
            : serverMessage;
        return;
      }

      if (type == 'location' || type == 'telemetry') {
        // Location update from driver
        final point = TelemetryPoint.fromJson(json);
        diagnosticsNotifier.value = null;
        _pointController.add(point);
        return;
      }

      // Handle raw location data (no type field)
      if (json.containsKey('lat') && json.containsKey('lng')) {
        final point = TelemetryPoint.fromJson(json);
        diagnosticsNotifier.value = null;
        _pointController.add(point);
      }
    } catch (_) {
      // Ignore malformed messages
    }
  }

  /// Fall back to REST polling for latest location
  void _startPolling(String rideId) {
    _pollTimer?.cancel();
    transportNotifier.value = 'rest_polling';
    _pollTimer = Timer.periodic(const Duration(seconds: 3), (_) async {
      try {
        final point = await getLatestLocation(rideId);
        if (point != null) {
          diagnosticsNotifier.value = null;
          _pointController.add(point);
        }
      } catch (_) {
        // Ignore polling errors
      }
    });
  }

  /// GET /api/v2/telemetry/{rideId}/latest — fetch latest location via REST
  Future<TelemetryPoint?> getLatestLocation(String rideId) async {
    try {
      final res = await _getLatestTelemetryResponse(rideId);
      final payload = unwrap(res);

      if (payload is! Map) {
        return null;
      }

      final pointsRaw = payload['points'] ?? payload['samples'];
      if (pointsRaw is! List || pointsRaw.isEmpty) {
        return null;
      }

      TelemetryPoint? latestPoint;
      for (final entry in pointsRaw) {
        if (entry is! Map) continue;
        final point = TelemetryPoint.fromJson(Map<String, dynamic>.from(entry));
        if (latestPoint == null ||
            point.timestamp.isAfter(latestPoint.timestamp)) {
          latestPoint = point;
        }
      }

      return latestPoint;
    } catch (_) {
      return null;
    }
  }

  /// Send driver location update (for drivers only)
  Future<void> sendLocation(TelemetryPoint point) async {
    var wsSent = false;
    if (_isConnected && _channel != null) {
      try {
        _channel!.sink.add(jsonEncode(point.toJson()));
        wsSent = true;
      } catch (_) {
        diagnosticsNotifier.value =
            'Realtime telemetry socket publish failed; using REST upload fallback.';
      }
    }

    final rideId = _currentRideId;
    if (rideId == null || rideId.trim().isEmpty) return;

    // Persist every point through REST as a reliability layer so passengers
    // can still fetch latest telemetry even when websocket delivery degrades.
    try {
      await _postTelemetryBatch(rideId, point);
      if (!wsSent) {
        diagnosticsNotifier.value = null;
      }
    } on DioException catch (e) {
      final message = extractError(e);
      diagnosticsNotifier.value =
          'Unable to publish driver location to backend (batch upload failed): $message';
    } catch (_) {
      diagnosticsNotifier.value =
          'Unable to publish driver location to backend (batch upload failed): unknown error.';
      // Keep non-blocking behavior; diagnostics surface the issue to users.
    }
  }

  Future<Response<dynamic>> _getLatestTelemetryResponse(String rideId) async {
    final absoluteUrl = '${AppConstants.baseUrlV2}/telemetry/$rideId/latest';
    try {
      return await _api.dio.getUri(Uri.parse(absoluteUrl));
    } on DioException catch (e) {
      if (e.response?.statusCode != 404) rethrow;
      // Legacy fallback for environments still routing absolute v2 paths differently.
      return _api.get('/api/v2/telemetry/$rideId/latest');
    }
  }

  Future<void> _postTelemetryBatch(String rideId, TelemetryPoint point) async {
    final body = <String, dynamic>{
      'ride_id': rideId,
      'points': [point.toJson()],
    };
    final absoluteUrl = '${AppConstants.baseUrlV2}/telemetry/batch';
    try {
      await _api.dio.postUri(Uri.parse(absoluteUrl), data: body);
      return;
    } on DioException catch (e) {
      if (e.response?.statusCode != 404) rethrow;
      // Legacy fallback for environments still routing absolute v2 paths differently.
      await _api.post('/api/v2/telemetry/batch', data: body);
    }
  }

  /// Disconnect from WebSocket and stop polling
  Future<void> disconnect() async {
    _pingTimer?.cancel();
    _pingTimer = null;

    _pollTimer?.cancel();
    _pollTimer = null;

    await _subscription?.cancel();
    _subscription = null;

    await _channel?.sink.close();
    _channel = null;

    _isConnected = false;
    _currentRideId = null;
    transportNotifier.value = 'disconnected';
  }

  /// Dispose resources
  void dispose() {
    disconnect();
    diagnosticsNotifier.dispose();
    transportNotifier.dispose();
    _pointController.close();
  }
}
