import 'dart:async';

import 'package:flutter/foundation.dart';

import 'notification_service.dart';

class NotificationSyncService {
  NotificationSyncService._internal();

  static final NotificationSyncService _instance =
      NotificationSyncService._internal();

  factory NotificationSyncService() => _instance;

  final NotificationService _notificationService = NotificationService();
  final ValueNotifier<int> unreadCountNotifier = ValueNotifier<int>(0);

  Timer? _pollTimer;
  bool _isRefreshing = false;

  int get unreadCount => unreadCountNotifier.value;

  // Lightweight polling keeps dashboard badges fresh when notifications arrive.
  void startPolling({Duration interval = const Duration(seconds: 5)}) {
    if (_pollTimer != null) {
      return;
    }

    _pollTimer = Timer.periodic(interval, (_) {
      refreshUnreadCount();
    });

    refreshUnreadCount(force: true);
  }

  void stopPolling() {
    _pollTimer?.cancel();
    _pollTimer = null;
  }

  Future<void> refreshUnreadCount({bool force = false}) async {
    if (_isRefreshing && !force) {
      return;
    }

    _isRefreshing = true;
    try {
      final unread = await _notificationService.getUnreadCount();
      setUnreadCount(unread);
    } catch (_) {
      // Ignore transient network/API errors and keep last known badge value.
    } finally {
      _isRefreshing = false;
    }
  }

  void setUnreadCount(int unread) {
    final next = unread < 0 ? 0 : unread;
    if (unreadCountNotifier.value != next) {
      unreadCountNotifier.value = next;
    }
  }
}
