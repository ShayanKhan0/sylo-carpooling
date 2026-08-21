import 'package:flutter/material.dart';
import 'package:dio/dio.dart';

import '../../core/services/api_client.dart';
import '../../core/services/chat_service.dart';
import '../../core/services/chat_sync_service.dart';
import '../../core/theme/app_colors.dart';

class ChatHistoryScreen extends StatefulWidget {
  const ChatHistoryScreen({super.key});

  @override
  State<ChatHistoryScreen> createState() => _ChatHistoryScreenState();
}

class _ChatHistoryScreenState extends State<ChatHistoryScreen> {
  final ChatService _chatService = ChatService();
  final ChatSyncService _chatSync = ChatSyncService();

  bool _isLoading = true;
  String? _error;
  List<ChatThreadModel> _threads = <ChatThreadModel>[];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final result =
          await _chatService.getThreads(state: 'history', limit: 200);
      if (!mounted) return;
      setState(() {
        _threads = result.threads;
        _isLoading = false;
      });
      await _chatSync.applyHistoryThreadsSnapshot(
        result.threads,
        fromHistoryVisit: true,
      );
      await _chatSync.refreshUnreadCount(force: true);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e is DioException ? extractError(e) : e.toString();
        _isLoading = false;
      });
    }
  }

  String _lockReasonLabel(String? reason) {
    switch ((reason ?? '').trim().toLowerCase()) {
      case 'ride_completed':
        return 'Ride Completed';
      case 'ride_cancelled':
        return 'Ride Cancelled';
      case 'booking_cancelled':
        return 'Booking Cancelled';
      default:
        return 'Chat Locked';
    }
  }

  String _formatTime(DateTime? dt) {
    if (dt == null) return '';
    final local = dt.isUtc ? dt.toLocal() : dt;
    final now = DateTime.now();
    final diff = now.difference(local);

    if (diff.inMinutes < 1) return 'Now';
    if (diff.inHours < 1) return '${diff.inMinutes}m';
    if (diff.inDays < 1) {
      return '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
    }
    return '${local.day}/${local.month}/${local.year}';
  }

  Future<void> _openThread(ChatThreadModel thread) async {
    final title = [
      (thread.rideOrigin ?? '').trim(),
      (thread.rideDestination ?? '').trim(),
    ].where((e) => e.isNotEmpty).join(' → ');

    await Navigator.pushNamed(
      context,
      '/chat',
      arguments: {
        'threadId': thread.id,
        'counterpartName': thread.counterpartName,
        'rideTitle': title.isEmpty ? 'Ride Chat' : title,
      },
    );

    if (!mounted) return;
    await _chatSync.markHistoryThreadOpened(thread.id);
    await _chatSync.refreshHistoryBadgeCount(force: true);
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Chat History'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        color: AppColors.primary,
        child: _isLoading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    children: [
                      Padding(
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          children: [
                            Text(
                              _error!,
                              textAlign: TextAlign.center,
                              style: const TextStyle(color: AppColors.error),
                            ),
                            const SizedBox(height: 12),
                            ElevatedButton(
                              onPressed: _load,
                              child: const Text('Retry'),
                            ),
                          ],
                        ),
                      ),
                    ],
                  )
                : _threads.isEmpty
                    ? ListView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        children: [
                          const SizedBox(height: 120),
                          Icon(Icons.chat_bubble_outline_rounded,
                              size: 64, color: AppColors.textHint),
                          const SizedBox(height: 12),
                          Center(
                            child: Text(
                              'No locked chats yet',
                              style: TextStyle(
                                color: AppColors.textSecondary,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          const SizedBox(height: 6),
                          Center(
                            child: Text(
                              'Chats appear here when rides are completed or cancelled.',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: AppColors.textHint,
                                fontSize: 12,
                              ),
                            ),
                          ),
                        ],
                      )
                    : ListView.separated(
                        physics: const AlwaysScrollableScrollPhysics(),
                        itemCount: _threads.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (context, index) {
                          final thread = _threads[index];
                          final title = thread.counterpartName;
                          final route = [
                            (thread.rideOrigin ?? '').trim(),
                            (thread.rideDestination ?? '').trim(),
                          ].where((e) => e.isNotEmpty).join(' → ');
                          final subtitle =
                              (thread.lastMessagePreview ?? '').trim();

                          return ListTile(
                            onTap: () => _openThread(thread),
                            contentPadding: const EdgeInsets.symmetric(
                              horizontal: 14,
                              vertical: 4,
                            ),
                            leading: CircleAvatar(
                              backgroundColor:
                                  AppColors.primary.withValues(alpha: 0.12),
                              child: Text(
                                title.isNotEmpty ? title[0].toUpperCase() : 'U',
                                style: const TextStyle(
                                  color: AppColors.primary,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                            title: Text(
                              title,
                              style:
                                  const TextStyle(fontWeight: FontWeight.w700),
                            ),
                            subtitle: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (route.isNotEmpty) ...[
                                  const SizedBox(height: 2),
                                  Text(
                                    route,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: AppColors.textSecondary,
                                    ),
                                  ),
                                ],
                                if (subtitle.isNotEmpty) ...[
                                  const SizedBox(height: 2),
                                  Text(
                                    subtitle,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: AppColors.textHint,
                                    ),
                                  ),
                                ],
                              ],
                            ),
                            trailing: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                Text(
                                  _formatTime(thread.lastMessageAt),
                                  style: TextStyle(
                                    fontSize: 11,
                                    color: AppColors.textHint,
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Container(
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 8, vertical: 4),
                                  decoration: BoxDecoration(
                                    color: AppColors.warning
                                        .withValues(alpha: 0.12),
                                    borderRadius: BorderRadius.circular(999),
                                  ),
                                  child: Text(
                                    _lockReasonLabel(thread.lockReason),
                                    style: const TextStyle(
                                      fontSize: 10,
                                      fontWeight: FontWeight.w700,
                                      color: AppColors.warning,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          );
                        },
                      ),
      ),
    );
  }
}
