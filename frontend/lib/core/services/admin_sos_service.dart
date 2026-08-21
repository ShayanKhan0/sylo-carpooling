import 'admin_api_client.dart';

class AdminSosService {
  final AdminApiClient _api = AdminApiClient();

  Future<List<Map<String, dynamic>>> getActiveIncidents() async {
    final res = await _api.get('/api/admin/sos/active');
    final data = unwrapAdmin(res);
    final items = (data is Map ? data['items'] : null) as List?;
    return (items ?? []).map((e) => Map<String, dynamic>.from(e)).toList();
  }

  Future<List<Map<String, dynamic>>> getHistoryIncidents() async {
    final res = await _api.get('/api/admin/sos/history');
    final data = unwrapAdmin(res);
    final items = (data is Map ? data['items'] : null) as List?;
    return (items ?? []).map((e) => Map<String, dynamic>.from(e)).toList();
  }

  Future<List<Map<String, dynamic>>> getUnlinkedActiveIncidents() async {
    final res = await _api.get('/api/admin/sos/unlinked/active');
    final data = unwrapAdmin(res);
    final items = (data is Map ? data['items'] : null) as List?;
    return (items ?? []).map((e) => Map<String, dynamic>.from(e)).toList();
  }

  Future<List<Map<String, dynamic>>> getUnlinkedHistoryIncidents() async {
    final res = await _api.get('/api/admin/sos/unlinked/history');
    final data = unwrapAdmin(res);
    final items = (data is Map ? data['items'] : null) as List?;
    return (items ?? []).map((e) => Map<String, dynamic>.from(e)).toList();
  }

  Future<Map<String, dynamic>> getIncidentDetail(String incidentId) async {
    final res = await _api.get('/api/admin/sos/$incidentId');
    final data = unwrapAdmin(res);
    return Map<String, dynamic>.from(data as Map);
  }

  Future<void> acknowledge(String incidentId, {String? remarks}) async {
    await _api.post(
      '/api/admin/sos/$incidentId/acknowledge',
      data: {'remarks': remarks},
    );
  }

  Future<void> assign(
    String incidentId, {
    required String assignedTo,
    String? remarks,
  }) async {
    await _api.post(
      '/api/admin/sos/$incidentId/assign',
      data: {'assigned_to': assignedTo, 'remarks': remarks},
    );
  }

  Future<void> resolve(String incidentId, {String? remarks}) async {
    try {
      await _api.post(
        '/api/admin/sos/$incidentId/resolve',
        data: {'remarks': remarks},
      );
      return;
    } catch (_) {
      // Compatibility fallback for older/newer backend route variants.
      await _api.post('/api/admin/sos/resolve/$incidentId', data: {'remarks': remarks});
    }
  }

  Future<void> resolveUnlinked(String incidentId) async {
    try {
      await _api.post('/api/admin/sos/unlinked/$incidentId/resolve');
      return;
    } catch (_) {
      await _api.post('/api/admin/sos/unlinked/resolve/$incidentId');
    }
  }

  Future<void> addNote(String incidentId, {required String note}) async {
    await _api.post(
      '/api/admin/sos/$incidentId/notes',
      data: {'note': note},
    );
  }
}
