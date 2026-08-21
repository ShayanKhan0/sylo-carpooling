import 'api_client.dart';

class SafetyService {
  final ApiClient _api = ApiClient();

  /// POST /safety/sos — send emergency SOS signal
  Future<Map<String, dynamic>> sendSOS({
    String? rideId,
    double? latitude,
    double? longitude,
    String? message,
  }) async {
    final res = await _api.post('/safety/sos', data: {
      if (rideId != null) 'ride_id': rideId,
      if (latitude != null) 'gps_lat': latitude,
      if (longitude != null) 'gps_lng': longitude,
      if (message != null) 'message': message,
    });
    return Map<String, dynamic>.from(unwrap(res));
  }

  Future<Map<String, dynamic>> getSosEligibility() async {
    final res = await _api.get('/safety/sos/eligibility');
    return Map<String, dynamic>.from(unwrap(res) as Map);
  }

  /// GET /safety/incident/{rideId} — list incidents for a ride
  Future<List<Map<String, dynamic>>> getIncidents(String rideId) async {
    final res = await _api.get('/safety/incident/$rideId');
    final data = unwrap(res);
    if (data is List) {
      return data.map((e) => Map<String, dynamic>.from(e)).toList();
    }
    return (data['incidents'] as List?)
            ?.map((e) => Map<String, dynamic>.from(e))
            .toList() ??
        [];
  }

  /// GET /safety/driver/{driverId}/safety — driver safety summary
  Future<Map<String, dynamic>> getDriverSafety(String driverId) async {
    final res = await _api.get('/safety/driver/$driverId/safety');
    return Map<String, dynamic>.from(unwrap(res));
  }

  /// POST /safety/ai/ride/{rideId}/user_response — respond to safety alert
  Future<void> respondToAlert(String rideId, String response) async {
    await _api.post('/safety/ai/ride/$rideId/user_response', data: {
      'response': response,
    });
  }

  /// GET /safety/ai/active_alerts — get active alerts (admin)
  Future<List<Map<String, dynamic>>> getActiveAlerts() async {
    final res = await _api.get('/safety/ai/active_alerts');
    final data = unwrap(res);
    if (data is List) {
      return data.map((e) => Map<String, dynamic>.from(e)).toList();
    }
    return (data['alerts'] as List?)
            ?.map((e) => Map<String, dynamic>.from(e))
            .toList() ??
        [];
  }
}
