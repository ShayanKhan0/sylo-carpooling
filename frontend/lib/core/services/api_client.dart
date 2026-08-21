import 'package:dio/dio.dart';
import '../constants/app_constants.dart';
import 'auth_service.dart';

/// Singleton Dio API client with JWT interceptor and auto-refresh.
class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  factory ApiClient() => _instance;
  ApiClient._internal() {
    _dio = Dio(BaseOptions(
      baseUrl: AppConstants.baseUrl,
      connectTimeout: AppConstants.connectTimeout,
      receiveTimeout: AppConstants.receiveTimeout,
      headers: {'Content-Type': 'application/json'},
    ));
    _dio.interceptors.add(_AuthInterceptor());
  }

  late final Dio _dio;
  Dio get dio => _dio;

  // ── Convenience helpers ───────────────────────────────
  Future<Response> get(
    String path, {
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) =>
      _dio.get(path, queryParameters: queryParameters, options: options);

  Future<Response> post(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
  }) =>
      _dio.post(path, data: data, queryParameters: queryParameters);

  Future<Response> put(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
  }) =>
      _dio.put(path, data: data, queryParameters: queryParameters);

  Future<Response> delete(
    String path, {
    Map<String, dynamic>? queryParameters,
  }) =>
      _dio.delete(path, queryParameters: queryParameters);
}

/// Attaches Bearer token and auto-refreshes on 401.
class _AuthInterceptor extends Interceptor {
  bool _isRefreshing = false;
  final List<_RetryItem> _queue = [];

  @override
  void onRequest(
      RequestOptions options, RequestInterceptorHandler handler) async {
    try {
      final token = await AuthService().getAccessToken();
      if (token != null) {
        options.headers['Authorization'] = 'Bearer $token';
      }
    } catch (_) {
      // Continue without token; server will respond 401 if needed
    }
    handler.next(options);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) async {
    if (err.response?.statusCode != 401) {
      return handler.next(err);
    }

    // Avoid refreshing for auth endpoints themselves
    final path = err.requestOptions.path;
    if (path.contains('/auth/login') ||
        path.contains('/auth/register') ||
        path.contains('/auth/refresh')) {
      return handler.next(err);
    }

    if (_isRefreshing) {
      // Queue this request to retry after refresh completes
      _queue.add(_RetryItem(err.requestOptions, handler));
      return;
    }

    _isRefreshing = true;

    try {
      final refreshToken = await AuthService().getRefreshToken();
      if (refreshToken == null) {
        _failAll(err);
        return handler.next(err);
      }

      final dio = Dio(BaseOptions(
        baseUrl: AppConstants.baseUrl,
        connectTimeout: AppConstants.connectTimeout,
        receiveTimeout: AppConstants.receiveTimeout,
        sendTimeout: AppConstants.receiveTimeout,
      ));
      final res = await dio.post('/auth/refresh', data: {
        'refresh_token': refreshToken,
      });

      if (res.statusCode == 200) {
        final newToken =
            res.data['data']?['access_token'] ?? res.data['access_token'];
        final newRefreshToken =
            res.data['data']?['refresh_token'] ?? res.data['refresh_token'];
        if (newToken != null) {
          await AuthService().updateAccessToken(newToken);
          if (newRefreshToken != null) {
            await AuthService().updateRefreshToken(newRefreshToken);
          }

          // Retry the original request
          err.requestOptions.headers['Authorization'] = 'Bearer $newToken';
          final retryRes = await ApiClient().dio.fetch(err.requestOptions);
          handler.resolve(retryRes);

          // Retry queued requests
          _retryAll(newToken);
        } else {
          await AuthService().logout();
          _failAll(err);
          handler.next(err);
        }
      } else {
        await AuthService().logout();
        _failAll(err);
        handler.next(err);
      }
    } catch (_) {
      await AuthService().logout();
      _failAll(err);
      handler.next(err);
    } finally {
      _isRefreshing = false;
    }
  }

  void _retryAll(String newToken) {
    for (final item in _queue) {
      item.options.headers['Authorization'] = 'Bearer $newToken';
      ApiClient().dio.fetch(item.options).then(
            (res) => item.handler.resolve(res),
            onError: (e) => item.handler.reject(e as DioException),
          );
    }
    _queue.clear();
  }

  void _failAll(DioException err) {
    for (final item in _queue) {
      item.handler.reject(err);
    }
    _queue.clear();
  }
}

class _RetryItem {
  final RequestOptions options;
  final ErrorInterceptorHandler handler;
  _RetryItem(this.options, this.handler);
}

/// Extracts `data` payload from the standard `{status, data, error}` wrapper.
/// Returns [response.data] as-is if not wrapped.
dynamic unwrap(Response response) {
  final body = response.data;
  if (body is Map && body.containsKey('data')) {
    return body['data'];
  }
  return body;
}

/// Throws a user-friendly message from the standard error wrapper.
String extractError(DioException e) {
  final path = e.requestOptions.path;
  final method = e.requestOptions.method;
  final statusCode = e.response?.statusCode;

  final data = e.response?.data;
  if (data is Map) {
    final validationErrors = data['error']?['errors'];
    if (validationErrors is List && validationErrors.isNotEmpty) {
      final firstError = validationErrors.first;
      if (firstError is Map) {
        final field = firstError['field']?.toString();
        final message = firstError['message']?.toString();
        if (message != null && message.trim().isNotEmpty) {
          final fieldPrefix =
              (field != null && field.trim().isNotEmpty) ? '$field: ' : '';
          return '[$statusCode $method] $path: $fieldPrefix$message';
        }
      }
    }

    final detail = data['detail'] ?? data['error']?['detail'] ?? data['error'];
    if (detail != null) {
      return '[$statusCode $method] $path: ${detail.toString()}';
    }
  }
  return '[$statusCode $method] $path: ${e.message ?? 'Something went wrong'}';
}
