import '../models/rating_model.dart';
import 'api_client.dart';

class RatingService {
  final ApiClient _api = ApiClient();

  /// POST /ratings
  Future<Rating> createRating({
    required String rideId,
    required int rating,
    String? toUserId,
    String? bookingId,
    String? comment,
  }) async {
    final res = await _api.post('/ratings', data: {
      'ride_id': rideId,
      'rating': rating,
      if (toUserId != null) 'to_user_id': toUserId,
      if (bookingId != null) 'booking_id': bookingId,
      if (comment != null) 'comment': comment,
    });
    // Ratings module returns flat response (no wrapper)
    return Rating.fromJson(res.data);
  }

  /// GET /ratings/user/{userId}
  Future<({List<Rating> ratings, int total})> getUserRatings(
    String userId, {
    int page = 1,
    int pageSize = 20,
    bool asRater = false,
  }) async {
    final res = await _api.get('/ratings/user/$userId', queryParameters: {
      'page': page,
      'page_size': pageSize,
      'as_rater': asRater,
    });
    final data = res.data;
    final list =
        (data['ratings'] as List?)?.map((r) => Rating.fromJson(r)).toList() ??
            [];
    return (ratings: list, total: (data['total'] ?? 0) as int);
  }

  /// GET /ratings/stats/{userId}
  Future<RatingStats> getStats(String userId) async {
    final res = await _api.get('/ratings/stats/$userId');
    return RatingStats.fromJson(res.data);
  }

  /// GET /ratings/ride/{rideId}
  Future<Rating?> getRideRating(String rideId, {String? toUserId}) async {
    try {
      final res = await _api.get('/ratings/ride/$rideId', queryParameters: {
        if (toUserId != null) 'to_user_id': toUserId,
      });
      return Rating.fromJson(res.data);
    } catch (_) {
      return null;
    }
  }
}
