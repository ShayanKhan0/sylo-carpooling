class Vehicle {
  final String id;
  final String ownerId;
  final String make;
  final String model;
  final String plateNumber;
  final int seatsTotal;
  final int seatsAvailable;
  final List<String>? photos;
  final String? createdAt;
  final String? updatedAt;

  Vehicle({
    required this.id,
    required this.ownerId,
    required this.make,
    required this.model,
    required this.plateNumber,
    required this.seatsTotal,
    required this.seatsAvailable,
    this.photos,
    this.createdAt,
    this.updatedAt,
  });

  factory Vehicle.fromJson(Map<String, dynamic> json) {
    final seatsAvailable = json['seats_available'] ?? 4;
    return Vehicle(
      id: json['id'] ?? '',
      ownerId: json['owner_id'] ?? json['driver_id'] ?? '',
      make: json['make'] ?? '',
      model: json['model'] ?? '',
      plateNumber: json['plate_number'] ?? json['license_plate'] ?? '',
      seatsTotal: json['seats_total'] ?? seatsAvailable ?? 5,
      seatsAvailable: seatsAvailable,
      photos:
          (json['photos'] as List<dynamic>?)?.map((e) => e.toString()).toList(),
      createdAt: json['created_at'],
      updatedAt: json['updated_at'],
    );
  }

  Map<String, dynamic> toCreateJson() => {
        'make': make,
        'model': model,
        'plate_number': plateNumber,
        'seats_total': seatsTotal,
        'seats_available': seatsAvailable,
        if (photos != null) 'photos': photos,
      };

  String get displayName => '$make $model';
  String get shortName => '$make $model';
}

class DriverProfile {
  final String id;
  final String userId;
  final bool isVerified;
  final String licenseNumber;
  final String? licenseExpiry;
  final String cnicNumber;
  final bool cnicVerified;
  final String? address;
  final double rating;
  final int totalRides;
  final double totalEarnings;
  final String status; // pending, active, suspended, inactive
  final String? joinedAt;
  final String? updatedAt;
  final List<Vehicle> vehicles;

  DriverProfile({
    required this.id,
    required this.userId,
    this.isVerified = false,
    required this.licenseNumber,
    this.licenseExpiry,
    required this.cnicNumber,
    this.cnicVerified = false,
    this.address,
    this.rating = 0,
    this.totalRides = 0,
    this.totalEarnings = 0,
    required this.status,
    this.joinedAt,
    this.updatedAt,
    this.vehicles = const [],
  });

  factory DriverProfile.fromJson(Map<String, dynamic> json) {
    return DriverProfile(
      id: json['id'] ?? '',
      userId: json['user_id'] ?? '',
      isVerified: json['is_verified'] ?? false,
      licenseNumber: json['license_number'] ?? '',
      licenseExpiry: json['license_expiry'],
      cnicNumber: json['cnic_number'] ?? 'N/A',
      cnicVerified: json['cnic_verified'] ?? false,
      address: json['address'],
      rating: (json['rating'] ?? json['rating_average'] ?? 0).toDouble(),
      totalRides: json['total_rides'] ?? 0,
      totalEarnings: (json['total_earnings'] ?? 0).toDouble(),
      status: json['status'] ?? 'pending',
      joinedAt: json['joined_at'] ?? json['created_at'],
      updatedAt: json['updated_at'] ?? json['verification_date'],
      vehicles: (json['vehicles'] as List<dynamic>?)
              ?.map((v) => Vehicle.fromJson(v))
              .toList() ??
          [],
    );
  }

  Map<String, dynamic> toCreateJson() => {
        'license_number': licenseNumber,
        'cnic_number': cnicNumber,
        if (address != null) 'address': address,
        if (licenseExpiry != null) 'license_expiry': licenseExpiry,
      };

  bool get isEligible => isVerified && status == 'active';
}

class DriverStats {
  final String driverId;
  final double rating;
  final int totalRides;
  final double totalEarnings;
  final int activeVehicles;
  final bool isRideEligible;
  final String status;

  DriverStats({
    required this.driverId,
    required this.rating,
    required this.totalRides,
    required this.totalEarnings,
    required this.activeVehicles,
    required this.isRideEligible,
    required this.status,
  });

  factory DriverStats.fromJson(Map<String, dynamic> json) {
    return DriverStats(
      driverId: json['driver_id'] ?? '',
      rating: (json['rating'] ?? 0).toDouble(),
      totalRides: json['total_rides'] ?? 0,
      totalEarnings: (json['total_earnings'] ?? 0).toDouble(),
      activeVehicles: json['active_vehicles'] ?? 0,
      isRideEligible: json['is_ride_eligible'] ?? false,
      status: json['status'] ?? 'pending',
    );
  }
}
