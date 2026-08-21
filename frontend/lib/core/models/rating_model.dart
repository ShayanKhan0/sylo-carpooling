class Rating {
  final String id;
  final String rideId;
  final String fromUserId;
  final String toUserId;
  final int rating;
  final String? comment;
  final String? createdAt;
  final String? fromUserName;
  final String? toUserName;
  final String? fromUserProfilePhoto;
  final String? toUserProfilePhoto;

  Rating({
    required this.id,
    required this.rideId,
    required this.fromUserId,
    required this.toUserId,
    required this.rating,
    this.comment,
    this.createdAt,
    this.fromUserName,
    this.toUserName,
    this.fromUserProfilePhoto,
    this.toUserProfilePhoto,
  });

  factory Rating.fromJson(Map<String, dynamic> json) {
    return Rating(
      id: json['id'] ?? '',
      rideId: json['ride_id'] ?? '',
      fromUserId: json['from_user_id'] ?? '',
      toUserId: json['to_user_id'] ?? '',
      rating: json['rating'] ?? 0,
      comment: json['comment'],
      createdAt: json['created_at'],
      fromUserName: json['from_user_name'],
      toUserName: json['to_user_name'],
      fromUserProfilePhoto: json['from_user_profile_photo'] ??
          json['from_profile_photo'] ??
          json['rater_profile_photo'],
      toUserProfilePhoto: json['to_user_profile_photo'] ??
          json['to_profile_photo'] ??
          json['ratee_profile_photo'],
    );
  }

  Map<String, dynamic> toCreateJson() => {
        'ride_id': rideId,
        'rating': rating,
        if (comment != null) 'comment': comment,
      };
}

class RatingStats {
  final String userId;
  final int totalRatings;
  final double averageRating;
  final double weightedAverage;
  final int fiveStar;
  final int fourStar;
  final int threeStar;
  final int twoStar;
  final int oneStar;
  final double? mostRecentRating;

  RatingStats({
    required this.userId,
    required this.totalRatings,
    required this.averageRating,
    required this.weightedAverage,
    required this.fiveStar,
    required this.fourStar,
    required this.threeStar,
    required this.twoStar,
    required this.oneStar,
    this.mostRecentRating,
  });

  factory RatingStats.fromJson(Map<String, dynamic> json) {
    return RatingStats(
      userId: json['user_id'] ?? '',
      totalRatings: json['total_ratings'] ?? 0,
      averageRating: (json['average_rating'] ?? 0).toDouble(),
      weightedAverage: (json['weighted_average'] ?? 0).toDouble(),
      fiveStar: json['five_star'] ?? json['5_star'] ?? 0,
      fourStar: json['four_star'] ?? json['4_star'] ?? 0,
      threeStar: json['three_star'] ?? json['3_star'] ?? 0,
      twoStar: json['two_star'] ?? json['2_star'] ?? 0,
      oneStar: json['one_star'] ?? json['1_star'] ?? 0,
      mostRecentRating: json['most_recent_rating']?.toDouble(),
    );
  }
}
