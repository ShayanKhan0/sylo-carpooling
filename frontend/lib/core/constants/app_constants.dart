import 'package:flutter/foundation.dart'
    show kIsWeb, defaultTargetPlatform, TargetPlatform;

class AppConstants {
  AppConstants._();

  // App Info
  static const String appName = 'Sylo';
  static const String appVersion = '1.0.0';

  // API Configuration — auto-detects web vs mobile
  // Physical Android/iOS devices: pass your PC/Mac LAN IP, e.g.
  // --dart-define=BASE_URL=http://192.168.1.10:8000/api/v1
  static const String _baseUrlOverride = String.fromEnvironment('BASE_URL');
  static const String _baseUrlV2Override =
      String.fromEnvironment('BASE_URL_V2');

  /// Default API base when [BASE_URL] is not set.
  static String get _defaultBaseUrlV1 {
    if (kIsWeb) return 'http://localhost:8001/api/v1';
    // iOS Simulator / macOS: host machine is localhost.
    if (defaultTargetPlatform == TargetPlatform.iOS ||
        defaultTargetPlatform == TargetPlatform.macOS) {
      return 'http://localhost:8001/api/v1';
    }
    // Android emulator: 10.0.2.2 is the host PC from the emulator.
    // Real Android phone: you must set BASE_URL to your PC's LAN IP (10.0.2.2 will not work).
    return 'http://10.0.2.2:8000/api/v1';
  }

  static String get _defaultBaseUrlV2 {
    if (kIsWeb) return 'http://localhost:8001/api/v2';
    if (defaultTargetPlatform == TargetPlatform.iOS ||
        defaultTargetPlatform == TargetPlatform.macOS) {
      return 'http://localhost:8001/api/v2';
    }
    return 'http://10.0.2.2:8000/api/v2';
  }

  static String get baseUrl =>
      _baseUrlOverride.isNotEmpty ? _baseUrlOverride : _defaultBaseUrlV1;

  static String get baseUrlV2 =>
      _baseUrlV2Override.isNotEmpty ? _baseUrlV2Override : _defaultBaseUrlV2;

  /// Shown when login/register cannot reach the backend (timeout / connection refused).
  static String get apiConnectionHelp {
    if (kIsWeb) {
      return 'Start the API on this machine: port 8001. '
          'Recommended on Windows: powershell -ExecutionPolicy Bypass -File .\\scripts\\ensure-backend-8001.ps1 -SingleRun. '
          'Open http://localhost:8001/healthz to confirm it is running.';
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return 'Android emulator: the app calls ${baseUrl.split('/api').first} — start the backend on your PC (port 8000). '
            'Real phone: phone and PC must be on the same Wi‑Fi; run with '
            '--dart-define=BASE_URL=http://YOUR_PC_LAN_IP:8000/api/v1 (find IP with ipconfig / ifconfig).';
      case TargetPlatform.iOS:
        return 'Simulator: run the API on your Mac (port 8000). '
            'Physical iPhone: same Wi‑Fi as the Mac and '
            '--dart-define=BASE_URL=http://YOUR_MAC_LAN_IP:8000/api/v1';
      default:
        return 'Ensure the FastAPI backend is running on port 8000 and reachable from this device.';
    }
  }

  // WebSocket URL for real-time telemetry (ws:// or wss://)
  static String get wsBaseUrl {
    final http = baseUrlV2;
    if (http.startsWith('https://')) {
      return http.replaceFirst('https://', 'wss://');
    }
    return http.replaceFirst('http://', 'ws://');
  }

  // Timeouts
  static const Duration connectTimeout = Duration(seconds: 30);
  static const Duration receiveTimeout = Duration(seconds: 30);

  // Storage Keys
  static const String keyAccessToken = 'access_token';
  static const String keyRefreshToken = 'refresh_token';
  static const String keyUserId = 'user_id';
  static const String keyUserEmail = 'user_email';
  static const String keyUserRole = 'user_role';
  static const String keyIsLoggedIn = 'is_logged_in';

  // Animation Durations
  static const Duration splashDuration = Duration(seconds: 3);
  static const Duration animationDuration = Duration(milliseconds: 300);
  static const Duration longAnimationDuration = Duration(milliseconds: 500);

  // Padding
  static const double paddingSmall = 8.0;
  static const double paddingMedium = 16.0;
  static const double paddingLarge = 24.0;
  static const double paddingXLarge = 32.0;

  // Border Radius
  static const double radiusSmall = 8.0;
  static const double radiusMedium = 12.0;
  static const double radiusLarge = 16.0;
  static const double radiusXLarge = 24.0;

  // Icon Sizes
  static const double iconSmall = 16.0;
  static const double iconMedium = 24.0;
  static const double iconLarge = 32.0;
  static const double iconXLarge = 48.0;

  // Google Maps (Android/iOS/Web widget). Prefer --dart-define=GOOGLE_MAPS_API_KEY=...
  // Backend proxy uses .env GOOGLE_MAPS_KEY; this key is only for native map SDK.
  static const String googleMapsApiKey = String.fromEnvironment(
    'GOOGLE_MAPS_API_KEY',
    defaultValue: 'YOUR_GOOGLE_MAPS_API_KEY',
  );
  static const double defaultLat = 31.5204; // Lahore default
  static const double defaultLng = 74.3587;
  static const double defaultZoom = 14.0;
}
