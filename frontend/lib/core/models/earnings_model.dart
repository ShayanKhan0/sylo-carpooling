class MonthlyEarnings {
  final int year;
  final int month;
  final int totalRides;
  final double grossEarnings;
  final double commissionDeducted;
  final double netEarnings;
  final String payoutStatus;

  MonthlyEarnings({
    required this.year,
    required this.month,
    required this.totalRides,
    required this.grossEarnings,
    required this.commissionDeducted,
    required this.netEarnings,
    required this.payoutStatus,
  });

  factory MonthlyEarnings.fromJson(Map<String, dynamic> json) {
    return MonthlyEarnings(
      year: json['year'] ?? 0,
      month: json['month'] ?? 0,
      totalRides: json['total_rides'] ?? 0,
      grossEarnings: _toDouble(json['gross_earnings']),
      commissionDeducted: _toDouble(json['commission_deducted']),
      netEarnings: _toDouble(json['net_earnings']),
      payoutStatus: json['payout_status'] ?? 'pending',
    );
  }

  static double _toDouble(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0;
  }
}

class LifetimeEarnings {
  final int totalRides;
  final double lifetimeGross;
  final double lifetimeCommission;
  final double lifetimeNet;
  final double totalWithdrawn;
  final double currentWalletBalance;

  LifetimeEarnings({
    required this.totalRides,
    required this.lifetimeGross,
    required this.lifetimeCommission,
    required this.lifetimeNet,
    required this.totalWithdrawn,
    required this.currentWalletBalance,
  });

  factory LifetimeEarnings.fromJson(Map<String, dynamic> json) {
    return LifetimeEarnings(
      totalRides: json['total_rides'] ?? 0,
      lifetimeGross: _toDouble(json['lifetime_gross']),
      lifetimeCommission: _toDouble(json['lifetime_commission']),
      lifetimeNet: _toDouble(json['lifetime_net']),
      totalWithdrawn: _toDouble(json['total_withdrawn']),
      currentWalletBalance: _toDouble(json['current_wallet_balance']),
    );
  }

  static double _toDouble(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0;
  }
}

class DailyEarningsData {
  final String date;
  final int rides;
  final double earnings;

  DailyEarningsData({
    required this.date,
    required this.rides,
    required this.earnings,
  });

  factory DailyEarningsData.fromJson(Map<String, dynamic> json) {
    return DailyEarningsData(
      date: json['date'] ?? '',
      rides: json['rides'] ?? 0,
      earnings: _toDouble(json['earnings']),
    );
  }

  static double _toDouble(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0;
  }
}

class EarningsChart {
  final String periodStart;
  final String periodEnd;
  final List<DailyEarningsData> dailyData;
  final double totalEarnings;
  final int totalRides;

  EarningsChart({
    required this.periodStart,
    required this.periodEnd,
    required this.dailyData,
    required this.totalEarnings,
    required this.totalRides,
  });

  factory EarningsChart.fromJson(Map<String, dynamic> json) {
    return EarningsChart(
      periodStart: json['period_start'] ?? '',
      periodEnd: json['period_end'] ?? '',
      dailyData: (json['daily_data'] as List<dynamic>?)
              ?.map((d) => DailyEarningsData.fromJson(d))
              .toList() ??
          [],
      totalEarnings: _toDouble(json['total_earnings']),
      totalRides: json['total_rides'] ?? 0,
    );
  }

  static double _toDouble(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0;
  }
}
