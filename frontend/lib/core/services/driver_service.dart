import '../models/vehicle_model.dart';
import 'api_client.dart';

class DriverService {
  final ApiClient _api = ApiClient();

  /// POST /drivers/register
  Future<DriverProfile> register({
    required String licenseNumber,
    required String cnicNumber,
    String? address,
    String? licenseExpiry,
  }) async {
    final res = await _api.post('/drivers/register', data: {
      'license_number': licenseNumber,
      'cnic_number': cnicNumber,
      if (address != null) 'address': address,
      if (licenseExpiry != null) 'license_expiry': licenseExpiry,
    });
    return DriverProfile.fromJson(unwrap(res));
  }

  /// GET /drivers/me
  Future<DriverProfile> getMyProfile() async {
    final res = await _api.get('/drivers/me');
    final data = unwrap(res);
    return DriverProfile.fromJson(data['profile'] ?? data);
  }

  /// PUT /drivers/me
  Future<DriverProfile> updateProfile({
    String? licenseNumber,
    String? licenseExpiry,
    String? address,
  }) async {
    final body = <String, dynamic>{};
    if (licenseNumber != null) body['license_number'] = licenseNumber;
    if (licenseExpiry != null) body['license_expiry'] = licenseExpiry;
    if (address != null) body['address'] = address;
    final res = await _api.put('/drivers/me', data: body);
    return DriverProfile.fromJson(unwrap(res));
  }

  /// PUT /drivers/status
  Future<void> updateStatus(String status) async {
    await _api.put('/drivers/status', data: {'status': status});
  }

  /// GET /drivers/stats
  Future<DriverStats> getStats() async {
    final res = await _api.get('/drivers/stats');
    return DriverStats.fromJson(unwrap(res));
  }

  // ── Vehicle management ────────────────────────────────

  /// GET /drivers/vehicles
  Future<List<Vehicle>> getVehicles() async {
    final res = await _api.get('/drivers/vehicles');
    final list = unwrap(res) as List;
    return list.map((v) => Vehicle.fromJson(v)).toList();
  }

  /// POST /drivers/vehicles
  Future<Vehicle> addVehicle({
    required String make,
    required String model,
    required String plateNumber,
    required int seatsTotal,
    int seatsAvailable = 4,
    List<String>? photos,
  }) async {
    final res = await _api.post('/drivers/vehicles', data: {
      'make': make,
      'model': model,
      'plate_number': plateNumber,
      'seats_total': seatsTotal,
      'seats_available': seatsAvailable,
      if (photos != null) 'photos': photos,
    });
    return Vehicle.fromJson(unwrap(res));
  }

  /// PUT /drivers/vehicles/{id}
  Future<Vehicle> updateVehicle(
    String vehicleId, {
    String? make,
    String? model,
    String? plateNumber,
    int? seatsTotal,
    int? seatsAvailable,
    List<String>? photos,
  }) async {
    final body = <String, dynamic>{};
    if (make != null) body['make'] = make;
    if (model != null) body['model'] = model;
    if (plateNumber != null) body['plate_number'] = plateNumber;
    if (seatsTotal != null) body['seats_total'] = seatsTotal;
    if (seatsAvailable != null) body['seats_available'] = seatsAvailable;
    if (photos != null) body['photos'] = photos;
    final res = await _api.put('/drivers/vehicles/$vehicleId', data: body);
    return Vehicle.fromJson(unwrap(res));
  }

  /// DELETE /drivers/vehicles/{id}
  Future<void> deleteVehicle(String vehicleId) async {
    await _api.delete('/drivers/vehicles/$vehicleId');
  }
}
