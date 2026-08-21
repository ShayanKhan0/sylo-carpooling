class UserProfile {
  final String id;
  final String? userId;
  final String? profilePhoto;
  final String? gender;
  final String? dateOfBirth;
  final String? organizationName;
  final String? organizationType;
  final String? cnic;
  final String? drivingLicense;
  final String? carRegistration;
  final bool addressVerification;
  final bool pushNotificationsEnabled;
  final bool shareLocationEnabled;
  final String? createdAt;
  final String? updatedAt;

  UserProfile({
    required this.id,
    this.userId,
    this.profilePhoto,
    this.gender,
    this.dateOfBirth,
    this.organizationName,
    this.organizationType,
    this.cnic,
    this.drivingLicense,
    this.carRegistration,
    this.addressVerification = false,
    this.pushNotificationsEnabled = true,
    this.shareLocationEnabled = true,
    this.createdAt,
    this.updatedAt,
  });

  factory UserProfile.fromJson(Map<String, dynamic> json) {
    return UserProfile(
      id: json['id'] ?? '',
      userId: json['user_id'],
      profilePhoto: json['profile_photo'],
      gender: json['gender'],
      dateOfBirth: json['date_of_birth'],
      organizationName: json['organization_name'],
      organizationType: json['organization_type'],
      cnic: json['cnic'],
      drivingLicense: json['driving_license'],
      carRegistration: json['car_registration'],
      addressVerification: json['address_verification'] ?? false,
      pushNotificationsEnabled: json['push_notifications_enabled'] ?? true,
      shareLocationEnabled: json['share_location_enabled'] ?? true,
      createdAt: json['created_at'],
      updatedAt: json['updated_at'],
    );
  }

  Map<String, dynamic> toJson() => {
        'profile_photo': profilePhoto,
        'gender': gender,
        'date_of_birth': dateOfBirth,
        'organization_name': organizationName,
        'organization_type': organizationType,
        'cnic': cnic,
        'driving_license': drivingLicense,
        'car_registration': carRegistration,
        'push_notifications_enabled': pushNotificationsEnabled,
        'share_location_enabled': shareLocationEnabled,
      };
}

class SavedAddress {
  final String id;
  final String userId;
  final String label;
  final String address;
  final double latitude;
  final double longitude;
  final String? createdAt;

  SavedAddress({
    required this.id,
    required this.userId,
    required this.label,
    required this.address,
    required this.latitude,
    required this.longitude,
    this.createdAt,
  });

  factory SavedAddress.fromJson(Map<String, dynamic> json) {
    return SavedAddress(
      id: json['id'] ?? '',
      userId: json['user_id'] ?? '',
      label: json['label'] ?? '',
      address: json['address'] ?? '',
      latitude: (json['latitude'] ?? 0).toDouble(),
      longitude: (json['longitude'] ?? 0).toDouble(),
      createdAt: json['created_at'],
    );
  }

  Map<String, dynamic> toJson() => {
        'label': label,
        'address': address,
        'latitude': latitude,
        'longitude': longitude,
      };
}

class User {
  final String id;
  final String fullName;
  final String email;
  final String? phone;
  final String role;
  final String? firebaseUid;
  final bool isActive;
  final bool isVerified;
  final String? createdAt;
  final UserProfile? profile;
  final List<SavedAddress> savedAddresses;

  User({
    required this.id,
    required this.fullName,
    required this.email,
    this.phone,
    required this.role,
    this.firebaseUid,
    this.isActive = true,
    this.isVerified = false,
    this.createdAt,
    this.profile,
    this.savedAddresses = const [],
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id: json['id'] ?? '',
      fullName: json['full_name'] ?? '',
      email: json['email'] ?? '',
      phone: json['phone'],
      role: json['role'] ?? 'passenger',
      firebaseUid: json['firebase_uid'],
      isActive: json['is_active'] ?? true,
      isVerified: json['is_verified'] ?? false,
      createdAt: json['created_at'],
      profile: json['profile'] != null
          ? UserProfile.fromJson(json['profile'])
          : null,
      savedAddresses: (json['saved_addresses'] as List<dynamic>?)
              ?.map((a) => SavedAddress.fromJson(a))
              .toList() ??
          [],
    );
  }

  String get firstName => fullName.split(' ').first;

  String get initials {
    final parts = fullName.trim().split(' ');
    if (parts.length >= 2) {
      return '${parts.first[0]}${parts.last[0]}'.toUpperCase();
    }
    return fullName.isNotEmpty ? fullName[0].toUpperCase() : '?';
  }
}
