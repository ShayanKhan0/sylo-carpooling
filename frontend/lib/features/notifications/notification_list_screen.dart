import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/services/notification_service.dart';
import '../../core/services/notification_sync_service.dart';
import '../../core/models/notification_model.dart';
import '../../core/theme/app_colors.dart';
import '../../core/constants/app_constants.dart';
import '../dashboard/home_design_system.dart';
import '../shared/widgets.dart';

class NotificationListScreen extends StatefulWidget {
  const NotificationListScreen({super.key});

  @override
  State<NotificationListScreen> createState() => _NotificationListScreenState();
}

class _NotificationListScreenState extends State<NotificationListScreen> {
  final NotificationService _svc = NotificationService();
  final NotificationSyncService _sync = NotificationSyncService();
  List<AppNotification> _notifications = [];
  int _unreadCount = 0;
  bool _loading = true;
  String? _error;
  bool _showUnreadOnly = false;
  final Set<String> _markingReadIds = <String>{};
  static const Color _notificationHeaderDarkGreen = Color(0xFF02130F);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await _svc.getMyNotifications(
        limit: 100,
        unreadOnly: _showUnreadOnly,
      );
      if (!mounted) return;
      setState(() {
        _notifications = result.notifications;
        _unreadCount = result.unreadCount;
        _loading = false;
      });
      _sync.setUnreadCount(result.unreadCount);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  AppNotification _notificationWithReadState(AppNotification n) {
    return AppNotification(
      id: n.id,
      userId: n.userId,
      title: n.title,
      message: n.message,
      type: n.type,
      priority: n.priority,
      deliveryStatus: 'read',
      sentAt: n.sentAt,
      readAt: n.readAt ?? DateTime.now().toUtc().toIso8601String(),
      metadata: n.metadata,
      createdAt: n.createdAt,
      updatedAt: n.updatedAt,
    );
  }

  void _applyReadLocally(String notificationId) {
    final idx = _notifications.indexWhere((item) => item.id == notificationId);
    if (idx == -1) return;

    final target = _notifications[idx];
    if (target.isRead) return;

    if (_showUnreadOnly) {
      _notifications.removeAt(idx);
    } else {
      _notifications[idx] = _notificationWithReadState(target);
    }

    _unreadCount = _unreadCount > 0 ? _unreadCount - 1 : 0;
  }

  Future<void> _markAsRead(AppNotification n) async {
    if (n.isRead || _markingReadIds.contains(n.id)) return;

    final previousNotifications = List<AppNotification>.from(_notifications);
    final previousUnread = _unreadCount;

    setState(() {
      _markingReadIds.add(n.id);
      _applyReadLocally(n.id);
    });
    _sync.setUnreadCount(_unreadCount);

    try {
      await _svc.markAsRead(n.id);
    } catch (_) {
      if (mounted) {
        setState(() {
          _notifications = previousNotifications;
          _unreadCount = previousUnread;
        });
      }
      _sync.setUnreadCount(previousUnread);
    } finally {
      if (mounted) {
        setState(() {
          _markingReadIds.remove(n.id);
        });
      }
    }
  }

  IconData _iconForType(String type) {
    switch (type) {
      case 'ride':
        return Icons.directions_car_rounded;
      case 'payment':
        return Icons.account_balance_wallet_rounded;
      case 'safety':
        return Icons.shield_rounded;
      case 'verification':
        return Icons.verified_user_rounded;
      case 'custom':
        return Icons.campaign_rounded;
      default:
        return Icons.notifications_rounded;
    }
  }

  Color _colorForType(String type) {
    switch (type) {
      case 'ride':
        return AppColors.primary;
      case 'payment':
        return AppColors.accent;
      case 'safety':
        return AppColors.error;
      case 'verification':
        return AppColors.info;
      default:
        return AppColors.secondary;
    }
  }

  BoxDecoration _notificationCardDecoration({
    required bool isUnread,
    required Color accent,
    required String type,
  }) {
    final borderColor = isUnread
        ? const Color(0xFF26E289).withValues(alpha: 0.95)
        : const Color(0xFF3C4A3F).withValues(alpha: 0.7);
    final unreadBorderWidth =
        type.toLowerCase() == 'ride' ? 4.8 : 4.0; // ride unread cards thicker
    final borderWidth = isUnread ? unreadBorderWidth : 1.4;

    return BoxDecoration(
      borderRadius: BorderRadius.circular(2),
      color: const Color(0xA2123E2A),
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          Color(0xD255E0A0),
          Color(0xB53ABF7C),
          Color(0xA13A7051),
        ],
        stops: [0.0, 0.5, 1.0],
      ),
      border: Border.all(color: borderColor, width: borderWidth),
      boxShadow: [
        if (isUnread)
          BoxShadow(
            color: const Color(0xFF57FFA4).withValues(alpha: 0.12),
            blurRadius: 16,
            spreadRadius: 0.0,
            offset: const Offset(0, 4),
          ),
      ],
    );
  }

  bool _isRatingNotification(AppNotification n) {
    final title = n.title.toLowerCase();
    final message = n.message.toLowerCase();
    return title.contains('rate') || message.contains('rate your');
  }

  (IconData, Color) _iconAndAccent(AppNotification n) {
    final title = n.title.toLowerCase();
    if (title.contains('cancel')) {
      return (Icons.close_rounded, const Color(0xFFE59C9C));
    }
    if (_isRatingNotification(n)) {
      return (Icons.star_rounded, const Color(0xFFE6B55E));
    }
    if (title.contains('booking')) {
      return (Icons.add_card_rounded, const Color(0xFF43E892));
    }
    return (_iconForType(n.type), _colorForType(n.type));
  }

  Widget _buildThemedHeader() {
    return HomeDesignSystem.frostLayer(
      blur: 10,
      radius: 18,
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.fromLTRB(12, 8, 6, 8),
        decoration: HomeDesignSystem.darkTopBarSurface(radius: 18),
        child: Row(
          children: [
            Material(
              color: Colors.transparent,
              child: InkWell(
                borderRadius: BorderRadius.circular(12),
                onTap: () => Navigator.maybePop(context),
                child: Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.10),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: Colors.white.withValues(alpha: 0.16),
                    ),
                  ),
                  child: const Icon(
                    Icons.arrow_back_rounded,
                    size: 19,
                    color: Colors.white,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 10),
            Text(
              'Notifications',
              style: GoogleFonts.inter(
                color: Colors.white,
                fontSize: 28,
                fontWeight: FontWeight.w900,
                height: 0.98,
              ),
            ),
            const Spacer(),
            if (_unreadCount > 0)
              Container(
                margin: const EdgeInsets.only(right: 6),
                padding:
                    const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF43E892).withValues(alpha: 0.24),
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(
                    color: const Color(0xFF43E892).withValues(alpha: 0.62),
                  ),
                ),
                child: Text(
                  '$_unreadCount',
                  style: GoogleFonts.inter(
                    color: const Color(0xFF43E892),
                    fontSize: 11,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
            IconButton(
              icon: Icon(
                _showUnreadOnly
                    ? Icons.mark_email_unread
                    : Icons.all_inbox_rounded,
                color: Colors.white.withValues(alpha: 0.88),
              ),
              tooltip: _showUnreadOnly ? 'Show all' : 'Unread only',
              onPressed: () {
                setState(() => _showUnreadOnly = !_showUnreadOnly);
                _load();
              },
            ),
          ],
        ),
      ),
    );
  }

  String _timeAgo(String? dateStr) {
    if (dateStr == null) return '';
    final raw = dateStr.trim();
    if (raw.isEmpty) return '';

    DateTime? dt = DateTime.tryParse(raw);

    // Backend may return UTC timestamps without timezone suffix.
    // Treat timezone-less values as UTC to avoid fixed local offset drift.
    final hasTimezone =
        raw.endsWith('Z') || RegExp(r'[+-]\d{2}:\d{2}$').hasMatch(raw);
    if (!hasTimezone) {
      final utcParsed = DateTime.tryParse('${raw}Z');
      if (utcParsed != null) {
        dt = utcParsed.toLocal();
      }
    } else if (dt != null && dt.isUtc) {
      dt = dt.toLocal();
    }

    if (dt == null) return '';
    final diff = DateTime.now().difference(dt);
    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    return '${dt.day}/${dt.month}/${dt.year}';
  }

  String? _metadataValue(Map<String, dynamic> metadata, List<String> keys) {
    for (final key in keys) {
      final value = metadata[key];
      if (value == null) continue;
      final text = value.toString().trim();
      if (text.isNotEmpty) return text;
    }
    return null;
  }

  Map<String, dynamic>? _chatRouteArgsFromMetadata(AppNotification n) {
    final metadata = n.metadata;
    if (metadata == null || metadata.isEmpty) return null;

    final event =
        _metadataValue(metadata, const ['event', 'meta_event'])?.toLowerCase();
    final threadId =
        _metadataValue(metadata, const ['thread_id', 'meta_thread_id']);
    final rideId = _metadataValue(metadata, const ['ride_id', 'meta_ride_id']);
    final bookingId =
        _metadataValue(metadata, const ['booking_id', 'meta_booking_id']);
    final passengerId =
        _metadataValue(metadata, const ['passenger_id', 'meta_passenger_id']);
    final senderName =
        _metadataValue(metadata, const ['sender_name', 'meta_sender_name']);

    final isChatEvent = event == 'chat_message' || threadId != null;
    if (!isChatEvent) return null;

    final args = <String, dynamic>{
      if (threadId != null) 'threadId': threadId,
      if (rideId != null) 'rideId': rideId,
      if (bookingId != null) 'bookingId': bookingId,
      if (passengerId != null) 'passengerId': passengerId,
      if (senderName != null) 'counterpartName': senderName,
    };

    final hasChatContext = (args['threadId']?.toString().isNotEmpty ?? false) ||
        (args['rideId']?.toString().isNotEmpty ?? false);
    if (!hasChatContext) return null;
    return args;
  }

  Future<void> _handleNotificationTap(AppNotification n) async {
    await _markAsRead(n);

    final chatArgs = _chatRouteArgsFromMetadata(n);
    if (chatArgs == null || !mounted) return;

    await Navigator.pushNamed(
      context,
      '/chat',
      arguments: chatArgs,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: _loading
          ? const SyloLoader(message: 'Loading notifications…')
          : _error != null
              ? SyloError(message: _error!, onRetry: _load)
              : _notifications.isEmpty
                  ? Stack(
                      children: [
                        HomeDesignSystem.driverHomeSoftWhiteBackground(),
                        Column(
                          children: [
                            Padding(
                              padding: const EdgeInsets.fromLTRB(
                                AppConstants.paddingMedium,
                                AppConstants.paddingSmall,
                                AppConstants.paddingMedium,
                                0,
                              ),
                              child: _buildThemedHeader(),
                            ),
                            Expanded(
                              child: SyloEmpty(
                                icon: Icons.notifications_off_rounded,
                                title: _showUnreadOnly
                                    ? 'All caught up!'
                                    : 'No notifications yet',
                                subtitle: _showUnreadOnly
                                    ? 'You have no unread notifications.'
                                    : 'We\'ll notify you about rides, payments & more.',
                              ),
                            ),
                          ],
                        ),
                      ],
                    )
                  : RefreshIndicator(
                      color: AppColors.primary,
                      onRefresh: _load,
                      child: Stack(
                        children: [
                          HomeDesignSystem.driverHomeSoftWhiteBackground(),
                          ListView.separated(
                        padding: const EdgeInsets.fromLTRB(
                          AppConstants.paddingMedium,
                          AppConstants.paddingSmall,
                          AppConstants.paddingMedium,
                          22,
                        ),
                        itemCount: _notifications.length + 1,
                        separatorBuilder: (_, __) => const SizedBox(height: 8),
                        itemBuilder: (context, index) {
                          if (index == 0) return _buildThemedHeader();
                          final n = _notifications[index - 1];
                          final color = _colorForType(n.type);
                          final isUnread = !n.isRead;
                          final iconTint = isUnread
                              ? Color.alphaBlend(
                                  Colors.black.withValues(alpha: 0.28),
                                  _iconAndAccent(n).$2,
                                )
                              : const Color(0xFF6F7873);
                          const titleColor = _notificationHeaderDarkGreen;
                          const messageColor = _notificationHeaderDarkGreen;
                          const metaColor = _notificationHeaderDarkGreen;
                          return Dismissible(
                            key: ValueKey(n.id),
                            direction: DismissDirection.endToStart,
                            confirmDismiss: (_) async {
                              await _markAsRead(n);
                              return false;
                            },
                            background: Container(
                              alignment: Alignment.centerRight,
                              padding: const EdgeInsets.only(right: 20),
                              decoration: BoxDecoration(
                                color:
                                    AppColors.primary.withValues(alpha: 0.12),
                                borderRadius: BorderRadius.circular(
                                    AppConstants.radiusMedium),
                              ),
                              child: const Icon(Icons.done_all,
                                  color: AppColors.primary),
                            ),
                            child: InkWell(
                              borderRadius: BorderRadius.circular(
                                  AppConstants.radiusMedium),
                              onTap: () => _handleNotificationTap(n),
                              child: Container(
                                padding: const EdgeInsets.fromLTRB(8, 12, 12, 12),
                                constraints: BoxConstraints(
                                  minHeight: isUnread ? 196 : 0,
                                ),
                                decoration: _notificationCardDecoration(
                                  isUnread: isUnread,
                                  accent: color,
                                  type: n.type,
                                ),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Container(
                                      width: 2.8,
                                      margin: const EdgeInsets.only(right: 4),
                                      decoration: BoxDecoration(
                                        color: isUnread
                                            ? _iconAndAccent(n).$2
                                            : const Color(0xFF3C4A3F),
                                        borderRadius: BorderRadius.circular(1),
                                      ),
                                    ),
                                    Container(
                                      width: 44,
                                      height: 44,
                                      margin: const EdgeInsets.only(top: 6),
                                      alignment: Alignment.center,
                                      decoration: BoxDecoration(
                                        color: isUnread
                                            ? _iconAndAccent(n).$2.withValues(alpha: 0.10)
                                            : _notificationHeaderDarkGreen,
                                        borderRadius: BorderRadius.circular(2),
                                        border: Border.all(
                                          color: iconTint.withValues(
                                              alpha: isUnread ? 0.9 : 0.45),
                                          width: 2,
                                        ),
                                      ),
                                      child: Icon(
                                        _iconAndAccent(n).$1,
                                        color: iconTint,
                                        size: 22,
                                      ),
                                    ),
                                    const SizedBox(width: 10),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        mainAxisAlignment: MainAxisAlignment.start,
                                        children: [
                                          const SizedBox(height: 6),
                                          Row(
                                            crossAxisAlignment:
                                                CrossAxisAlignment.center,
                                            children: [
                                              Expanded(
                                                child: Text(
                                                  n.title,
                                                  maxLines: 2,
                                                  overflow:
                                                      TextOverflow.ellipsis,
                                                  style: GoogleFonts.inter(
                                                    color: titleColor,
                                                    fontWeight:
                                                        FontWeight.w800,
                                                    fontSize:
                                                        isUnread ? 22 : 20,
                                                    height: 1.1,
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(width: 8),
                                              Text(
                                                _timeAgo(n.sentAt ?? n.createdAt)
                                                    .toUpperCase(),
                                                style: GoogleFonts.inter(
                                                  color: metaColor,
                                                  fontSize: 10,
                                                  fontWeight: FontWeight.w700,
                                                  letterSpacing: 0.5,
                                                ),
                                              ),
                                            ],
                                          ),
                                          const SizedBox(height: 8),
                                          Text(
                                            n.message,
                                            style: GoogleFonts.inter(
                                              color: messageColor,
                                              fontSize: 12.5,
                                              fontWeight: FontWeight.w600,
                                              height: 1.35,
                                            ),
                                            maxLines: isUnread ? 3 : 2,
                                            overflow: TextOverflow.ellipsis,
                                          ),
                                          if (isUnread) ...[
                                            const SizedBox(height: 14),
                                            SizedBox(
                                              width: double.infinity,
                                              height: 42,
                                              child: FilledButton(
                                                onPressed: _markingReadIds.contains(n.id)
                                                    ? null
                                                    : () => _markAsRead(n),
                                                style: FilledButton.styleFrom(
                                                  backgroundColor:
                                                      const Color(0xFF57FFA4),
                                                  foregroundColor:
                                                      const Color(0xFF00391E),
                                                  shape: RoundedRectangleBorder(
                                                    borderRadius:
                                                        BorderRadius.circular(0),
                                                    side: const BorderSide(
                                                        color: Color(0xFF00391E),
                                                        width: 2),
                                                  ),
                                                  padding: EdgeInsets.zero,
                                                  minimumSize:
                                                      const Size.fromHeight(42),
                                                ),
                                                child: Center(
                                                  child: Text(
                                                    'READ',
                                                    textAlign: TextAlign.center,
                                                    style: GoogleFonts.inter(
                                                      fontWeight: FontWeight.w900,
                                                      fontSize: 14,
                                                      letterSpacing: 0.2,
                                                    ),
                                                  ),
                                                ),
                                              ),
                                            ),
                                          ],
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                        ],
                      ),
                    ),
    );
  }
}
