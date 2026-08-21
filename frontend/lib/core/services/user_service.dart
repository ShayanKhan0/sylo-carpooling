import '../models/user_model.dart';
import 'api_client.dart';

class UserService {
  final ApiClient _api = ApiClient();

  /// GET /users/me → UserWithProfilePublic
  Future<User> getMyProfile() async {
    final res = await _api.get('/users/me');
    return User.fromJson(unwrap(res));
  }

  /// PUT /users/me → update profile fields
  Future<void> updateProfile({
    String? gender,
    String? dateOfBirth,
    String? organizationName,
    String? organizationType,
    String? cnic,
    String? drivingLicense,
    String? carRegistration,
    String? profilePhoto,
    bool? pushNotificationsEnabled,
    bool? shareLocationEnabled,
  }) async {
    final body = <String, dynamic>{};
    if (gender != null) body['gender'] = gender;
    if (dateOfBirth != null) body['date_of_birth'] = dateOfBirth;
    if (organizationName != null) body['organization_name'] = organizationName;
    if (organizationType != null) body['organization_type'] = organizationType;
    if (cnic != null) body['cnic'] = cnic;
    if (drivingLicense != null) body['driving_license'] = drivingLicense;
    if (carRegistration != null) body['car_registration'] = carRegistration;
    if (profilePhoto != null) body['profile_photo'] = profilePhoto;
    if (pushNotificationsEnabled != null) {
      body['push_notifications_enabled'] = pushNotificationsEnabled;
    }
    if (shareLocationEnabled != null) {
      body['share_location_enabled'] = shareLocationEnabled;
    }
    await _api.put('/users/me', data: body);
  }

  /// POST /users/me/photo
  Future<void> uploadPhoto(String photoData) async {
    await _api.post('/users/me/photo', data: {'photo': photoData});
  }

  // ── Saved Addresses ───────────────────────────────────

  /// GET /users/addresses
  Future<List<SavedAddress>> getAddresses() async {
    final res = await _api.get('/users/addresses');
    final list = unwrap(res) as List;
    return list.map((a) => SavedAddress.fromJson(a)).toList();
  }

  /// POST /users/addresses
  Future<SavedAddress> addAddress({
    required String label,
    required String address,
    required double latitude,
    required double longitude,
  }) async {
    final res = await _api.post('/users/addresses', data: {
      'label': label,
      'address': address,
      'latitude': latitude,
      'longitude': longitude,
    });
    return SavedAddress.fromJson(unwrap(res));
  }

  /// PUT /users/addresses/{id}
  Future<SavedAddress> updateAddress(
    String addressId, {
    String? label,
    String? address,
    double? latitude,
    double? longitude,
  }) async {
    final body = <String, dynamic>{};
    if (label != null) body['label'] = label;
    if (address != null) body['address'] = address;
    if (latitude != null) body['latitude'] = latitude;
    if (longitude != null) body['longitude'] = longitude;

    final res = await _api.put('/users/addresses/$addressId', data: body);
    return SavedAddress.fromJson(unwrap(res));
  }

  /// DELETE /users/addresses/{id}
  Future<void> deleteAddress(String addressId) async {
    await _api.delete('/users/addresses/$addressId');
  }
}
