import '../models/notification_model.dart';
import 'api_client.dart';

class NotificationService {
  final ApiClient _api = ApiClient();

  int _asInt(dynamic value, {int fallback = 0}) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    if (value is String) return int.tryParse(value.trim()) ?? fallback;
    return fallback;
  }

  /// GET /notifications/my
  Future<({List<AppNotification> notifications, int total, int unreadCount})>
      getMyNotifications({
    int limit = 50,
    int skip = 0,
    bool unreadOnly = false,
  }) async {
    final res = await _api.get('/notifications/my', queryParameters: {
      'limit': limit,
      'skip': skip,
      'unread_only': unreadOnly,
    });
    final data = unwrap(res);
    final list = (data['notifications'] as List?)
            ?.map((n) => AppNotification.fromJson(n))
            .toList() ??
        [];
    return (
      notifications: list,
      total: _asInt(data['total']),
      unreadCount: _asInt(data['unread_count']),
    );
  }

  /// PUT /notifications/mark-read/{id}
  Future<void> markAsRead(String notificationId) async {
    await _api.put('/notifications/mark-read/$notificationId');
  }

  /// GET /notifications/unread-count
  Future<int> getUnreadCount() async {
    final res = await _api.get('/notifications/unread-count');
    final data = unwrap(res);
    return _asInt(data['unread_count']);
  }

  /// POST /notifications/register-token
  Future<void> registerDeviceToken({
    required String deviceToken,
    String platform = 'android',
  }) async {
    await _api.post('/notifications/register-token', data: {
      'device_token': deviceToken,
      'platform': platform,
    });
  }
}
