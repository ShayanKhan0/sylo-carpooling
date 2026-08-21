class AppNotification {
  final String id;
  final String userId;
  final String title;
  final String message;
  final String type; // system, ride, payment, safety, verification, custom
  final String priority; // low, normal, high
  final String deliveryStatus; // pending, sent, failed, read
  final String? sentAt;
  final String? readAt;
  final Map<String, dynamic>? metadata;
  final String? createdAt;
  final String? updatedAt;

  AppNotification({
    required this.id,
    required this.userId,
    required this.title,
    required this.message,
    required this.type,
    this.priority = 'normal',
    this.deliveryStatus = 'sent',
    this.sentAt,
    this.readAt,
    this.metadata,
    this.createdAt,
    this.updatedAt,
  });

  factory AppNotification.fromJson(Map<String, dynamic> json) {
    return AppNotification(
      id: json['id'] ?? '',
      userId: json['user_id'] ?? '',
      title: json['title'] ?? '',
      message: json['message'] ?? '',
      type: json['type'] ?? 'system',
      priority: json['priority'] ?? 'normal',
      deliveryStatus: json['delivery_status'] ?? 'sent',
      sentAt: json['sent_at'],
      readAt: json['read_at'],
      metadata: (json['metadata'] ?? json['meta_data']) != null
          ? Map<String, dynamic>.from(json['metadata'] ?? json['meta_data'])
          : null,
      createdAt: json['created_at'],
      updatedAt: json['updated_at'],
    );
  }

  bool get isRead => deliveryStatus == 'read' || readAt != null;
  bool get isHighPriority => priority == 'high';
}
