import 'package:dio/dio.dart';

import 'admin_api_client.dart';
import 'admin_session.dart';

class AdminAuthService {
  final AdminApiClient _api = AdminApiClient();

  Future<void> login({
    required String email,
    required String password,
  }) async {
    final response = await _api.post(
      '/api/admin/auth/login',
      data: {
        'email': email,
        'password': password,
      },
    );
    final data = unwrapAdmin(response);
    final token = (data is Map ? data['access_token'] : null)?.toString() ?? '';
    if (token.isEmpty) {
      throw Exception('Admin login failed: token missing');
    }
    AdminSession.setToken(token);
  }

  void logout() {
    AdminSession.clear();
  }
}

String extractAdminError(DioException error) {
  final status = error.response?.statusCode;
  if (status == 401 || status == 403) {
    return 'Incorrect admin email or password.';
  }
  if (status == 404) {
    return 'Admin login service is unavailable right now.';
  }

  final data = error.response?.data;
  if (data is Map) {
    final detail = data['detail'] ?? data['error']?['detail'] ?? data['error'];
    if (detail != null) {
      return detail.toString();
    }
  }
  return 'Unable to sign in right now. Please try again.';
}
