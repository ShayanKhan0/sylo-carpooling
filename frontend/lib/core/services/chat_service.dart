import 'api_client.dart';

class ChatService {
  final ApiClient _api = ApiClient();

  int _asInt(dynamic value, {int fallback = 0}) {
    if (value is int) return value;
    if (value is num) return value.toInt();
    if (value is String) return int.tryParse(value.trim()) ?? fallback;
    return fallback;
  }

  Future<ChatThreadModel> ensureThread({
    required String rideId,
    String? bookingId,
    String? passengerId,
  }) async {
    final payload = <String, dynamic>{
      'ride_id': rideId,
      if (bookingId != null && bookingId.isNotEmpty) 'booking_id': bookingId,
      if (passengerId != null && passengerId.isNotEmpty)
        'passenger_id': passengerId,
    };
    final res = await _api.post('/chat/thread', data: payload);
    final data = unwrap(res);
    return ChatThreadModel.fromJson(data);
  }

  Future<ChatThreadsResult> getThreads({
    String state = 'all',
    int limit = 100,
    int skip = 0,
  }) async {
    final res = await _api.get('/chat/threads', queryParameters: {
      'state': state,
      'limit': limit,
      'skip': skip,
    });
    final data = unwrap(res) as Map<String, dynamic>;
    final threads = (data['threads'] as List?)
            ?.map((e) => ChatThreadModel.fromJson(e))
            .toList() ??
        <ChatThreadModel>[];
    return ChatThreadsResult(
      threads: threads,
      total: _asInt(data['total']),
      unreadTotal: _asInt(data['unread_total']),
    );
  }

  Future<ChatConversation> getThreadMessages(
    String threadId, {
    int limit = 50,
    String? beforeId,
  }) async {
    final params = <String, dynamic>{'limit': limit};
    if (beforeId != null && beforeId.isNotEmpty) {
      params['before'] = beforeId;
    }
    final res = await _api.get(
      '/chat/threads/$threadId/messages',
      queryParameters: params,
    );
    final data = unwrap(res);
    return ChatConversation.fromJson(data);
  }

  Future<ChatMessageModel> sendThreadMessage(String threadId, String content) async {
    final res = await _api.post(
      '/chat/threads/$threadId/messages',
      data: {'content': content},
    );
    final data = unwrap(res);
    return ChatMessageModel.fromJson(data);
  }

  Future<int> getThreadUnreadCount(String threadId) async {
    final res = await _api.get('/chat/threads/$threadId/unread');
    final data = unwrap(res);
    return _asInt(data['unread_count']);
  }

  Future<void> markThreadAsRead(String threadId) async {
    await _api.post('/chat/threads/$threadId/read');
  }

  Future<int> getGlobalUnreadCount() async {
    final res = await _api.get('/chat/unread-count');
    final data = unwrap(res);
    return _asInt(data['unread_count']);
  }

  // Legacy ride-based fallback.
  Future<ChatConversation> getMessagesByRide(
    String rideId, {
    int limit = 50,
    String? beforeId,
    String? bookingId,
    String? passengerId,
  }) async {
    final params = <String, dynamic>{'limit': limit};
    if (beforeId != null && beforeId.isNotEmpty) params['before'] = beforeId;
    if (bookingId != null && bookingId.isNotEmpty) params['booking_id'] = bookingId;
    if (passengerId != null && passengerId.isNotEmpty) {
      params['passenger_id'] = passengerId;
    }
    final res = await _api.get('/chat/$rideId', queryParameters: params);
    final data = unwrap(res);
    return ChatConversation.fromJson(data);
  }
}

class ChatThreadsResult {
  final List<ChatThreadModel> threads;
  final int total;
  final int unreadTotal;

  ChatThreadsResult({
    required this.threads,
    required this.total,
    required this.unreadTotal,
  });
}

class ChatConversation {
  final ChatThreadModel thread;
  final List<ChatMessageModel> messages;
  final int total;

  ChatConversation({
    required this.thread,
    required this.messages,
    required this.total,
  });

  factory ChatConversation.fromJson(Map<String, dynamic> json) {
    return ChatConversation(
      thread: ChatThreadModel.fromJson(
        Map<String, dynamic>.from(json['thread'] ?? const {}),
      ),
      messages: (json['messages'] as List?)
              ?.map((m) => ChatMessageModel.fromJson(m))
              .toList() ??
          <ChatMessageModel>[],
      total: (json['total'] ?? 0) as int,
    );
  }
}

class ChatThreadModel {
  final String id;
  final String rideId;
  final String bookingId;
  final String bookingSource;
  final String driverId;
  final String passengerId;
  final String status;
  final String? lockReason;
  final DateTime? lockedAt;
  final bool canSend;
  final int messageCount;
  final int unreadCount;
  final DateTime? lastMessageAt;
  final String? lastMessagePreview;
  final String counterpartUserId;
  final String counterpartName;
  final String? counterpartProfilePhoto;
  final String? rideOrigin;
  final String? rideDestination;
  final DateTime? rideDepartureTime;

  ChatThreadModel({
    required this.id,
    required this.rideId,
    required this.bookingId,
    required this.bookingSource,
    required this.driverId,
    required this.passengerId,
    required this.status,
    this.lockReason,
    this.lockedAt,
    required this.canSend,
    required this.messageCount,
    required this.unreadCount,
    this.lastMessageAt,
    this.lastMessagePreview,
    required this.counterpartUserId,
    required this.counterpartName,
    this.counterpartProfilePhoto,
    this.rideOrigin,
    this.rideDestination,
    this.rideDepartureTime,
  });

  bool get isLocked => !canSend;

  factory ChatThreadModel.fromJson(Map<String, dynamic> json) {
    return ChatThreadModel(
      id: json['id']?.toString() ?? '',
      rideId: json['ride_id']?.toString() ?? '',
      bookingId: json['booking_id']?.toString() ?? '',
      bookingSource: json['booking_source']?.toString() ?? 'ride_bookings',
      driverId: json['driver_id']?.toString() ?? '',
      passengerId: json['passenger_id']?.toString() ?? '',
      status: json['status']?.toString() ?? 'active',
      lockReason: json['lock_reason']?.toString(),
      lockedAt: DateTime.tryParse(json['locked_at']?.toString() ?? ''),
      canSend: json['can_send'] == true,
      messageCount: (json['message_count'] ?? 0) as int,
      unreadCount: (json['unread_count'] ?? 0) as int,
      lastMessageAt:
          DateTime.tryParse(json['last_message_at']?.toString() ?? ''),
      lastMessagePreview: json['last_message_preview']?.toString(),
      counterpartUserId: json['counterpart_user_id']?.toString() ?? '',
      counterpartName: json['counterpart_name']?.toString() ?? 'User',
      counterpartProfilePhoto: json['counterpart_profile_photo']?.toString(),
      rideOrigin: json['ride_origin']?.toString(),
      rideDestination: json['ride_destination']?.toString(),
      rideDepartureTime:
          DateTime.tryParse(json['ride_departure_time']?.toString() ?? ''),
    );
  }
}

class ChatMessageModel {
  final String id;
  final String threadId;
  final String rideId;
  final String senderId;
  final String? senderName;
  final String receiverId;
  final String content;
  final bool isRead;
  final DateTime createdAt;

  ChatMessageModel({
    required this.id,
    required this.threadId,
    required this.rideId,
    required this.senderId,
    this.senderName,
    required this.receiverId,
    required this.content,
    required this.isRead,
    required this.createdAt,
  });

  factory ChatMessageModel.fromJson(Map<String, dynamic> json) {
    return ChatMessageModel(
      id: json['id']?.toString() ?? '',
      threadId: json['thread_id']?.toString() ?? '',
      rideId: json['ride_id']?.toString() ?? '',
      senderId: json['sender_id']?.toString() ?? '',
      senderName: json['sender_name']?.toString(),
      receiverId: json['receiver_id']?.toString() ?? '',
      content: json['content']?.toString() ?? '',
      isRead: json['is_read'] == true,
      createdAt: DateTime.tryParse(json['created_at']?.toString() ?? '') ??
          DateTime.now(),
    );
  }
}

