import 'dart:async';

import 'package:flutter/material.dart';
import 'package:dio/dio.dart';

import '../../core/services/api_client.dart';
import '../../core/services/auth_service.dart';
import '../../core/services/chat_service.dart';
import '../../core/services/chat_sync_service.dart';
import '../../core/theme/app_colors.dart';

class ChatScreen extends StatefulWidget {
  final String? threadId;
  final String? rideId;
  final String? bookingId;
  final String? passengerId;
  final String? rideTitle;
  final String? counterpartName;

  const ChatScreen({
    super.key,
    this.threadId,
    this.rideId,
    this.bookingId,
    this.passengerId,
    this.rideTitle,
    this.counterpartName,
  });

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final ChatService _chatService = ChatService();
  final ChatSyncService _chatSync = ChatSyncService();
  final TextEditingController _messageController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final FocusNode _focusNode = FocusNode();

  ChatThreadModel? _thread;
  List<ChatMessageModel> _messages = <ChatMessageModel>[];
  String? _threadId;
  String? _currentUserId;

  bool _isLoading = true;
  bool _isSending = false;
  String? _error;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _init();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _messageController.dispose();
    _scrollController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  Future<void> _init() async {
    _currentUserId = await AuthService().getUserId();
    await _resolveThread();
    if (!mounted || _threadId == null) {
      return;
    }
    await _loadMessages();

    _pollTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      _loadMessages(silent: true);
    });
  }

  Future<void> _resolveThread() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      if (widget.threadId != null && widget.threadId!.isNotEmpty) {
        _threadId = widget.threadId;
      } else if (widget.rideId != null && widget.rideId!.isNotEmpty) {
        final thread = await _chatService.ensureThread(
          rideId: widget.rideId!,
          bookingId: widget.bookingId,
          passengerId: widget.passengerId,
        );
        _thread = thread;
        _threadId = thread.id;
      } else {
        throw Exception('Missing chat context (thread/ride).');
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e is DioException ? extractError(e) : e.toString();
        _isLoading = false;
      });
    }
  }

  Future<void> _loadMessages({bool silent = false}) async {
    if (_threadId == null) return;

    if (!silent) {
      setState(() {
        _isLoading = true;
        _error = null;
      });
    }
    try {
      final conversation = await _chatService.getThreadMessages(_threadId!);
      if (!mounted) return;

      setState(() {
        _thread = conversation.thread;
        _messages = conversation.messages;
        _isLoading = false;
      });

      await _chatSync.refreshUnreadCount(force: true);
      if (!silent) _scrollToBottom();
    } catch (e) {
      if (!mounted || silent) return;
      setState(() {
        _error = e is DioException ? extractError(e) : e.toString();
        _isLoading = false;
      });
    }
  }

  Future<void> _sendMessage() async {
    final text = _messageController.text.trim();
    if (text.isEmpty || _isSending || _threadId == null) return;
    if (!(_thread?.canSend ?? false)) return;

    setState(() => _isSending = true);
    _messageController.clear();

    try {
      final msg = await _chatService.sendThreadMessage(_threadId!, text);
      if (!mounted) return;

      setState(() {
        _messages.add(msg);
        _isSending = false;
      });
      _scrollToBottom();
      await _chatSync.refreshUnreadCount(force: true);
      await _loadMessages(silent: true);
    } catch (e) {
      if (!mounted) return;

      setState(() => _isSending = false);
      final message = e is DioException ? extractError(e) : 'Failed to send message';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
      );
      _messageController.text = text;
      await _loadMessages(silent: true);
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  String _lockReasonLabel(String? reason) {
    switch ((reason ?? '').trim().toLowerCase()) {
      case 'ride_completed':
        return 'Ride completed. Chat is now read-only.';
      case 'ride_cancelled':
        return 'Ride cancelled. Chat is now read-only.';
      case 'booking_cancelled':
        return 'Booking cancelled. Chat is now read-only.';
      default:
        return 'Chat is locked for this ride.';
    }
  }

  String _headerTitle() {
    final counterpart = widget.counterpartName?.trim();
    if (counterpart != null && counterpart.isNotEmpty) {
      return counterpart;
    }
    final threadCounterpart = _thread?.counterpartName.trim();
    if (threadCounterpart != null && threadCounterpart.isNotEmpty) {
      return threadCounterpart;
    }
    final rideTitle = widget.rideTitle?.trim();
    if (rideTitle != null && rideTitle.isNotEmpty) {
      return rideTitle;
    }
    final fromThreadRide = [
      _thread?.rideOrigin?.trim() ?? '',
      _thread?.rideDestination?.trim() ?? '',
    ].where((v) => v.isNotEmpty).toList();
    if (fromThreadRide.length == 2) {
      return '${fromThreadRide[0]} → ${fromThreadRide[1]}';
    }
    return 'Ride Chat';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final canSend = _thread?.canSend ?? false;

    return Scaffold(
      appBar: AppBar(
        title: Text(_headerTitle()),
        elevation: 1,
      ),
      body: Column(
        children: [
          if (_thread != null && !canSend)
            Container(
              width: double.infinity,
              color: AppColors.warning.withValues(alpha: 0.12),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              child: Row(
                children: [
                  const Icon(Icons.lock_outline_rounded,
                      size: 18, color: AppColors.warning),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _lockReasonLabel(_thread?.lockReason),
                      style: const TextStyle(
                        color: AppColors.warning,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),

          Expanded(
            child: _isLoading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                    ? Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Padding(
                              padding:
                                  const EdgeInsets.symmetric(horizontal: 20),
                              child: Text(
                                _error!,
                                textAlign: TextAlign.center,
                                style: TextStyle(color: theme.hintColor),
                              ),
                            ),
                            const SizedBox(height: 12),
                            ElevatedButton(
                              onPressed: _loadMessages,
                              child: const Text('Retry'),
                            ),
                          ],
                        ),
                      )
                    : _messages.isEmpty
                        ? Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.chat_bubble_outline_rounded,
                                  size: 64,
                                  color: AppColors.primary.withValues(alpha: 0.3),
                                ),
                                const SizedBox(height: 12),
                                Text(
                                  'No messages yet',
                                  style: TextStyle(color: theme.hintColor),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  canSend
                                      ? 'Send a message to start the conversation'
                                      : 'No chat history for this ride',
                                  style: TextStyle(
                                    color: theme.hintColor,
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ),
                          )
                        : ListView.builder(
                            controller: _scrollController,
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 8),
                            itemCount: _messages.length,
                            itemBuilder: (context, index) {
                              final msg = _messages[index];
                              final isMe = msg.senderId == _currentUserId;
                              final showAvatar = index == 0 ||
                                  _messages[index - 1].senderId != msg.senderId;
                              return _buildBubble(msg, isMe, showAvatar, theme);
                            },
                          ),
          ),

          Container(
            decoration: BoxDecoration(
              color: theme.cardColor,
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.06),
                  blurRadius: 8,
                  offset: const Offset(0, -2),
                ),
              ],
            ),
            padding: EdgeInsets.only(
              left: 12,
              right: 8,
              top: 8,
              bottom: MediaQuery.of(context).padding.bottom + 8,
            ),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _messageController,
                    focusNode: _focusNode,
                    enabled: canSend,
                    textCapitalization: TextCapitalization.sentences,
                    maxLines: 4,
                    minLines: 1,
                    decoration: InputDecoration(
                      hintText:
                          canSend ? 'Type a message…' : 'Chat locked for this ride',
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(24),
                        borderSide: BorderSide.none,
                      ),
                      filled: true,
                      fillColor: theme.scaffoldBackgroundColor,
                      contentPadding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 10),
                    ),
                    onSubmitted: (_) => _sendMessage(),
                  ),
                ),
                const SizedBox(width: 8),
                Container(
                  decoration: BoxDecoration(
                    color: canSend
                        ? AppColors.primary
                        : AppColors.textSecondary.withValues(alpha: 0.4),
                    shape: BoxShape.circle,
                  ),
                  child: IconButton(
                    onPressed: (!canSend || _isSending) ? null : _sendMessage,
                    icon: _isSending
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Icon(Icons.send_rounded, color: Colors.white),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBubble(
    ChatMessageModel msg,
    bool isMe,
    bool showAvatar,
    ThemeData theme,
  ) {
    return Padding(
      padding: EdgeInsets.only(
        top: showAvatar ? 12 : 2,
        left: isMe ? 48 : 0,
        right: isMe ? 0 : 48,
      ),
      child: Column(
        crossAxisAlignment:
            isMe ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        children: [
          if (showAvatar && !isMe)
            Padding(
              padding: const EdgeInsets.only(left: 4, bottom: 4),
              child: Text(
                msg.senderName ?? 'User',
                style: const TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  color: AppColors.primary,
                ),
              ),
            ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: isMe
                  ? AppColors.primary
                  : theme.brightness == Brightness.dark
                      ? AppColors.charcoalMid
                      : AppColors.backgroundLight,
              borderRadius: BorderRadius.only(
                topLeft: const Radius.circular(16),
                topRight: const Radius.circular(16),
                bottomLeft: Radius.circular(isMe ? 16 : 4),
                bottomRight: Radius.circular(isMe ? 4 : 16),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  msg.content,
                  style: TextStyle(
                    color: isMe ? Colors.white : theme.textTheme.bodyMedium?.color,
                    fontSize: 15,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  _formatTime(msg.createdAt),
                  style: TextStyle(
                    fontSize: 10,
                    color: isMe
                        ? Colors.white.withValues(alpha: 0.7)
                        : theme.hintColor,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _formatTime(DateTime dt) {
    final now = DateTime.now();
    final local = dt.isUtc ? dt.toLocal() : dt;
    final diff = now.difference(local);

    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inHours < 1) return '${diff.inMinutes}m ago';
    if (diff.inDays < 1) {
      return '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
    }
    return '${local.day}/${local.month} ${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
  }
}

