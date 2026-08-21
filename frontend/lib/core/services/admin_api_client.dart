import 'package:dio/dio.dart';

import '../constants/app_constants.dart';
import 'admin_session.dart';

class AdminApiClient {
  static final AdminApiClient _instance = AdminApiClient._internal();
  factory AdminApiClient() => _instance;

  late final Dio _dio;

  AdminApiClient._internal() {
    final userApiBase = AppConstants.baseUrl;
    final adminBase = userApiBase.contains('/api/')
        ? userApiBase.split('/api/').first
        : userApiBase;
    _dio = Dio(
      BaseOptions(
        baseUrl: adminBase,
        connectTimeout: AppConstants.connectTimeout,
        receiveTimeout: AppConstants.receiveTimeout,
        headers: const {'Content-Type': 'application/json'},
      ),
    );
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          final token = AdminSession.token;
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
      ),
    );
  }

  Future<Response<dynamic>> get(
    String path, {
    Map<String, dynamic>? queryParameters,
  }) =>
      _dio.get(path, queryParameters: queryParameters);

  Future<Response<dynamic>> post(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
  }) =>
      _dio.post(path, data: data, queryParameters: queryParameters);
}

dynamic unwrapAdmin(Response<dynamic> response) {
  final body = response.data;
  if (body is Map && body.containsKey('data')) {
    return body['data'];
  }
  return body;
}
