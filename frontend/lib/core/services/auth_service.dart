import 'package:shared_preferences/shared_preferences.dart';
import '../../core/constants/app_constants.dart';

class AuthService {
  static final AuthService _instance = AuthService._internal();
  factory AuthService() => _instance;
  AuthService._internal();

  SharedPreferences? _prefs;

  Future<void> init() async {
    _prefs = await SharedPreferences.getInstance();
  }

  // Check if user is logged in
  Future<bool> isLoggedIn() async {
    if (_prefs == null) await init();
    return _prefs?.getBool(AppConstants.keyIsLoggedIn) ?? false;
  }

  // Get access token
  Future<String?> getAccessToken() async {
    if (_prefs == null) await init();
    return _prefs?.getString(AppConstants.keyAccessToken);
  }

  // Get refresh token
  Future<String?> getRefreshToken() async {
    if (_prefs == null) await init();
    return _prefs?.getString(AppConstants.keyRefreshToken);
  }

  // Get user ID
  Future<String?> getUserId() async {
    if (_prefs == null) await init();
    return _prefs?.getString(AppConstants.keyUserId);
  }

  // Get user email
  Future<String?> getUserEmail() async {
    if (_prefs == null) await init();
    return _prefs?.getString(AppConstants.keyUserEmail);
  }

  // Save login data
  Future<void> saveLoginData({
    required String accessToken,
    required String refreshToken,
    required String userId,
    required String userEmail,
    String? userRole,
  }) async {
    if (_prefs == null) await init();
    await _prefs?.setString(AppConstants.keyAccessToken, accessToken);
    await _prefs?.setString(AppConstants.keyRefreshToken, refreshToken);
    await _prefs?.setString(AppConstants.keyUserId, userId);
    await _prefs?.setString(AppConstants.keyUserEmail, userEmail);
    if (userRole != null) {
      await _prefs?.setString(AppConstants.keyUserRole, userRole);
    }
    await _prefs?.setBool(AppConstants.keyIsLoggedIn, true);
  }

  // Clear login data (logout)
  Future<void> logout() async {
    if (_prefs == null) await init();
    await _prefs?.remove(AppConstants.keyAccessToken);
    await _prefs?.remove(AppConstants.keyRefreshToken);
    await _prefs?.remove(AppConstants.keyUserId);
    await _prefs?.remove(AppConstants.keyUserEmail);
    await _prefs?.remove(AppConstants.keyUserRole);
    await _prefs?.setBool(AppConstants.keyIsLoggedIn, false);
  }

  // Get user role
  Future<String?> getUserRole() async {
    if (_prefs == null) await init();
    return _prefs?.getString(AppConstants.keyUserRole);
  }

  // Get route for current role
  Future<String> getDashboardRoute() async {
    final role = await getUserRole();
    return role == 'driver' ? '/driver-dashboard' : '/passenger-dashboard';
  }

  // Update access token
  Future<void> updateAccessToken(String accessToken) async {
    if (_prefs == null) await init();
    await _prefs?.setString(AppConstants.keyAccessToken, accessToken);
  }

  // Update refresh token
  Future<void> updateRefreshToken(String refreshToken) async {
    if (_prefs == null) await init();
    await _prefs?.setString(AppConstants.keyRefreshToken, refreshToken);
  }
}
