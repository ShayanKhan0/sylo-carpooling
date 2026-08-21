import 'api_client.dart';

class TripService {
  final ApiClient _api = ApiClient();

  // Trips module uses /api/v2/trips prefix — need to go outside baseUrl.
  // Our baseUrl is /api/v1, so we prepend full path.
  static const String _prefix = '/api/v2/trips';

  /// POST /api/v2/trips/{rideId}/start — start a live trip
  Future<Map<String, dynamic>> startTrip(String rideId) async {
    final res = await _api.post('$_prefix/$rideId/start');
    return Map<String, dynamic>.from(unwrap(res));
  }

  /// POST /api/v2/trips/{rideId}/complete — complete trip
  Future<Map<String, dynamic>> completeTrip(
    String rideId, {
    bool settlePayments = true,
  }) async {
    final res = await _api.post('$_prefix/$rideId/complete', data: {
      'settle_payments': settlePayments,
    });
    return Map<String, dynamic>.from(unwrap(res));
  }

  /// POST /api/v2/trips/{rideId}/settle — settle payments
  Future<Map<String, dynamic>> settlePayments(String rideId) async {
    final res = await _api.post('$_prefix/$rideId/settle');
    return Map<String, dynamic>.from(unwrap(res));
  }

  /// GET /api/v2/trips/{rideId}/summary — trip summary
  Future<Map<String, dynamic>> getTripSummary(String rideId) async {
    final res = await _api.get('$_prefix/$rideId/summary');
    return Map<String, dynamic>.from(unwrap(res));
  }
}
