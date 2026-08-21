import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'auth_service.dart';
import 'chat_service.dart';

class ChatSyncService {
  ChatSyncService._internal();

  static final ChatSyncService _instance = ChatSyncService._internal();

  factory ChatSyncService() => _instance;

  final ChatService _chatService = ChatService();
  final ValueNotifier<int> unreadCountNotifier = ValueNotifier<int>(0);
  final ValueNotifier<int> historyNewCountNotifier = ValueNotifier<int>(0);

  static const String _historyBaselineReadyKeyPrefix =
      'sylo.chat.history.badge.baseline_ready.v1';
  static const String _historyBaselineIdsKeyPrefix =
      'sylo.chat.history.badge.baseline_ids.v1';
  static const String _historyPendingIdsKeyPrefix =
      'sylo.chat.history.badge.pending_ids.v1';
  static const String _historyOpenedIdsKeyPrefix =
      'sylo.chat.history.badge.opened_ids.v1';

  Timer? _pollTimer;
  bool _isRefreshing = false;
  bool _isHistoryRefreshing = false;

  String? _historyUserId;
  bool _historyStateLoaded = false;
  bool _historyBaselineReady = false;
  Set<String> _historyBaselineThreadIds = <String>{};
  Set<String> _historyPendingThreadIds = <String>{};
  Set<String> _historyOpenedThreadIds = <String>{};

  int get unreadCount => unreadCountNotifier.value;
  int get historyNewCount => historyNewCountNotifier.value;

  void startPolling({Duration interval = const Duration(seconds: 5)}) {
    if (_pollTimer != null) return;

    _pollTimer = Timer.periodic(interval, (_) {
      refreshUnreadCount();
      refreshHistoryBadgeCount();
    });

    refreshUnreadCount(force: true);
    refreshHistoryBadgeCount(force: true);
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
      final unread = await _chatService.getGlobalUnreadCount();
      setUnreadCount(unread);
    } catch (_) {
      // Keep last known count on transient failures.
    } finally {
      _isRefreshing = false;
    }
  }

  Future<void> refreshHistoryBadgeCount({
    bool force = false,
    bool fromHistoryVisit = false,
  }) async {
    if (_isHistoryRefreshing && !force) {
      return;
    }

    _isHistoryRefreshing = true;
    try {
      final result =
          await _chatService.getThreads(state: 'history', limit: 200);
      await applyHistoryThreadsSnapshot(
        result.threads,
        fromHistoryVisit: fromHistoryVisit,
      );
    } catch (_) {
      // Keep last known count on transient failures.
    } finally {
      _isHistoryRefreshing = false;
    }
  }

  Future<void> applyHistoryThreadsSnapshot(
    Iterable<ChatThreadModel> threads, {
    bool fromHistoryVisit = false,
  }) async {
    await _ensureHistoryStateLoaded();
    if (!_historyStateLoaded) {
      setHistoryNewCount(0);
      return;
    }

    final currentThreadIds = <String>{};
    for (final thread in threads) {
      final id = thread.id.trim();
      if (id.isNotEmpty) {
        currentThreadIds.add(id);
      }
    }

    await _applyHistorySnapshot(
      currentThreadIds,
      fromHistoryVisit: fromHistoryVisit,
    );
  }

  Future<void> markHistoryThreadOpened(String threadId) async {
    final normalized = threadId.trim();
    if (normalized.isEmpty) return;

    await _ensureHistoryStateLoaded();
    if (!_historyStateLoaded) {
      setHistoryNewCount(0);
      return;
    }

    var changed = false;
    if (_historyOpenedThreadIds.add(normalized)) {
      changed = true;
    }
    if (_historyPendingThreadIds.remove(normalized)) {
      changed = true;
    }

    _syncHistoryBadgeCount();
    if (changed) {
      await _persistHistoryState();
    }
  }

  void setUnreadCount(int unread) {
    final next = unread < 0 ? 0 : unread;
    if (unreadCountNotifier.value != next) {
      unreadCountNotifier.value = next;
    }
  }

  void setHistoryNewCount(int count) {
    final next = count < 0 ? 0 : count;
    if (historyNewCountNotifier.value != next) {
      historyNewCountNotifier.value = next;
    }
  }

  Future<void> _ensureHistoryStateLoaded() async {
    final userId = (await AuthService().getUserId())?.trim();
    if (userId == null || userId.isEmpty) {
      _resetHistoryState();
      return;
    }

    if (_historyStateLoaded && _historyUserId == userId) {
      return;
    }

    final prefs = await SharedPreferences.getInstance();
    _historyUserId = userId;
    _historyBaselineReady =
        prefs.getBool(_historyBaselineReadyKey(userId)) ?? false;
    _historyBaselineThreadIds = _asIdSet(
      prefs.getStringList(_historyBaselineIdsKey(userId)),
    );
    _historyPendingThreadIds = _asIdSet(
      prefs.getStringList(_historyPendingIdsKey(userId)),
    );
    _historyOpenedThreadIds = _asIdSet(
      prefs.getStringList(_historyOpenedIdsKey(userId)),
    );
    _historyStateLoaded = true;
    _syncHistoryBadgeCount();
  }

  Future<void> _applyHistorySnapshot(
    Set<String> currentThreadIds, {
    required bool fromHistoryVisit,
  }) async {
    if (!_historyBaselineReady) {
      _historyBaselineReady = true;
      _historyBaselineThreadIds = Set<String>.from(currentThreadIds);
      _historyPendingThreadIds.clear();
      _historyOpenedThreadIds.clear();
      _syncHistoryBadgeCount();
      await _persistHistoryState();
      return;
    }

    var changed = false;
    final newlyEnteredHistory =
        currentThreadIds.difference(_historyBaselineThreadIds);
    for (final threadId in newlyEnteredHistory) {
      if (_historyOpenedThreadIds.contains(threadId)) {
        continue;
      }
      if (_historyPendingThreadIds.add(threadId)) {
        changed = true;
      }
    }

    final pendingBefore = _historyPendingThreadIds.length;
    _historyPendingThreadIds.retainAll(currentThreadIds);
    if (pendingBefore != _historyPendingThreadIds.length) {
      changed = true;
    }

    final openedBefore = _historyOpenedThreadIds.length;
    _historyOpenedThreadIds.retainAll(currentThreadIds);
    if (openedBefore != _historyOpenedThreadIds.length) {
      changed = true;
    }

    if (fromHistoryVisit &&
        !setEquals(_historyBaselineThreadIds, currentThreadIds)) {
      _historyBaselineThreadIds = Set<String>.from(currentThreadIds);
      changed = true;
    }

    _syncHistoryBadgeCount();
    if (changed) {
      await _persistHistoryState();
    }
  }

  Future<void> _persistHistoryState() async {
    final userId = _historyUserId;
    if (!_historyStateLoaded || userId == null || userId.isEmpty) {
      return;
    }

    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(
        _historyBaselineReadyKey(userId), _historyBaselineReady);
    await prefs.setStringList(
      _historyBaselineIdsKey(userId),
      _sortedIds(_historyBaselineThreadIds),
    );
    await prefs.setStringList(
      _historyPendingIdsKey(userId),
      _sortedIds(_historyPendingThreadIds),
    );
    await prefs.setStringList(
      _historyOpenedIdsKey(userId),
      _sortedIds(_historyOpenedThreadIds),
    );
  }

  void _syncHistoryBadgeCount() {
    final count = _historyPendingThreadIds
        .where((id) => !_historyOpenedThreadIds.contains(id))
        .length;
    setHistoryNewCount(count);
  }

  void _resetHistoryState() {
    _historyUserId = null;
    _historyStateLoaded = false;
    _historyBaselineReady = false;
    _historyBaselineThreadIds = <String>{};
    _historyPendingThreadIds = <String>{};
    _historyOpenedThreadIds = <String>{};
    setHistoryNewCount(0);
  }

  Set<String> _asIdSet(List<String>? values) {
    if (values == null || values.isEmpty) {
      return <String>{};
    }
    return values.map((id) => id.trim()).where((id) => id.isNotEmpty).toSet();
  }

  List<String> _sortedIds(Set<String> values) {
    final ids = values.toList();
    ids.sort();
    return ids;
  }

  String _historyBaselineReadyKey(String userId) =>
      '$_historyBaselineReadyKeyPrefix.$userId';

  String _historyBaselineIdsKey(String userId) =>
      '$_historyBaselineIdsKeyPrefix.$userId';

  String _historyPendingIdsKey(String userId) =>
      '$_historyPendingIdsKeyPrefix.$userId';

  String _historyOpenedIdsKey(String userId) =>
      '$_historyOpenedIdsKeyPrefix.$userId';
}
