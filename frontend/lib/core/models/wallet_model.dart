class Wallet {
  final String id;
  final String userId;
  final double balance;
  final String currency;
  final String? createdAt;
  final String? lastUpdated;

  Wallet({
    required this.id,
    required this.userId,
    required this.balance,
    this.currency = 'PKR',
    this.createdAt,
    this.lastUpdated,
  });

  factory Wallet.fromJson(Map<String, dynamic> json) {
    return Wallet(
      id: json['id'] ?? '',
      userId: json['user_id'] ?? '',
      balance: _toDouble(json['balance']),
      currency: json['currency'] ?? 'PKR',
      createdAt: json['created_at'],
      lastUpdated: json['last_updated'],
    );
  }

  static double _toDouble(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0;
  }
}

class WalletBalance {
  final String userId;
  final double balance;
  final String currency;
  final String? lastUpdated;

  WalletBalance({
    required this.userId,
    required this.balance,
    this.currency = 'PKR',
    this.lastUpdated,
  });

  factory WalletBalance.fromJson(Map<String, dynamic> json) {
    return WalletBalance(
      userId: json['user_id'] ?? '',
      balance: _toDouble(json['balance']),
      currency: json['currency'] ?? 'PKR',
      lastUpdated: json['last_updated'],
    );
  }

  static double _toDouble(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0;
  }
}

class WalletTransaction {
  final String id;
  final String txnId;
  final String walletId;
  final String userId;
  final double amount;
  final String
      type; // topup, deduct, refund, transfer, commission, payout, ride_payment
  final String status; // pending, completed, failed, reversed
  final String? rideId;
  final String? payoutId;
  final String? provider;
  final String? providerTxnId;
  final String? description;
  final String? createdAt;
  final String? updatedAt;
  final String? completedAt;

  WalletTransaction({
    required this.id,
    required this.txnId,
    required this.walletId,
    required this.userId,
    required this.amount,
    required this.type,
    required this.status,
    this.rideId,
    this.payoutId,
    this.provider,
    this.providerTxnId,
    this.description,
    this.createdAt,
    this.updatedAt,
    this.completedAt,
  });

  factory WalletTransaction.fromJson(Map<String, dynamic> json) {
    return WalletTransaction(
      id: json['id'] ?? '',
      txnId: json['txn_id'] ?? '',
      walletId: json['wallet_id'] ?? '',
      userId: json['user_id'] ?? '',
      amount: _toDouble(json['amount']),
      type: json['type'] ?? '',
      status: json['status'] ?? 'pending',
      rideId: json['ride_id'],
      payoutId: json['payout_id'],
      provider: json['provider'],
      providerTxnId: json['provider_txn_id'],
      description: json['description'],
      createdAt: json['created_at'],
      updatedAt: json['updated_at'],
      completedAt: json['completed_at'],
    );
  }

  static double _toDouble(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0;
  }

  bool get isCredit =>
      type == 'topup' || type == 'refund' || type == 'transfer';
}

class Payout {
  final String id;
  final String driverId;
  final double amount;
  final String method; // bank_transfer, jazzcash, easypaisa, stripe, paypal
  final String accountDetails;
  final String status; // pending, processing, completed, failed, cancelled
  final String? provider;
  final String? providerPayoutId;
  final String? createdAt;
  final String? updatedAt;
  final String? processedAt;
  final String? completedAt;
  final String? notes;

  Payout({
    required this.id,
    required this.driverId,
    required this.amount,
    required this.method,
    required this.accountDetails,
    required this.status,
    this.provider,
    this.providerPayoutId,
    this.createdAt,
    this.updatedAt,
    this.processedAt,
    this.completedAt,
    this.notes,
  });

  factory Payout.fromJson(Map<String, dynamic> json) {
    return Payout(
      id: json['id'] ?? '',
      driverId: json['driver_id'] ?? '',
      amount: _toDouble(json['amount']),
      method: json['method'] ?? '',
      accountDetails: json['account_details'] ?? '',
      status: json['status'] ?? 'pending',
      provider: json['provider'],
      providerPayoutId: json['provider_payout_id'],
      createdAt: json['created_at'],
      updatedAt: json['updated_at'],
      processedAt: json['processed_at'],
      completedAt: json['completed_at'],
      notes: json['notes'],
    );
  }

  static double _toDouble(dynamic v) {
    if (v == null) return 0;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? 0;
  }
}
