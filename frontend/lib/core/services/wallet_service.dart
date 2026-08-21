import '../models/wallet_model.dart';
import 'api_client.dart';

class WalletService {
  final ApiClient _api = ApiClient();

  /// POST /payments/wallet/create
  Future<Wallet> createWallet() async {
    // Payments router uses its own /api/v1/payments prefix.
    // Our baseUrl is already /api/v1, so path = /payments/wallet/create
    final res = await _api.post('/payments/wallet/create');
    return Wallet.fromJson(unwrap(res));
  }

  /// GET /payments/wallet/balance/{userId}
  Future<WalletBalance> getBalance(String userId) async {
    final res = await _api.get('/payments/wallet/balance/$userId');
    return WalletBalance.fromJson(unwrap(res));
  }

  /// POST /payments/wallet/topup
  Future<Map<String, dynamic>> topUp({
    required double amount,
    required String provider, // jazzcash, easypaisa, stripe, paypal, mock
    String? providerTxnId,
    String? description,
  }) async {
    final res = await _api.post('/payments/wallet/topup', data: {
      'amount': amount,
      'provider': provider,
      if (providerTxnId != null) 'provider_txn_id': providerTxnId,
      if (description != null) 'description': description,
    });
    final data = unwrap(res);
    return Map<String, dynamic>.from(data);
  }

  /// POST /payments/wallet/prop/topup
  Future<Map<String, dynamic>> propTopUp({
    required double amount,
    String? description,
  }) async {
    final res = await _api.post('/payments/wallet/prop/topup', data: {
      'amount': amount,
      if (description != null) 'description': description,
    });
    final data = unwrap(res);
    return Map<String, dynamic>.from(data);
  }

  /// POST /payments/wallet/prop/payout
  Future<Map<String, dynamic>> propPayout({
    required double amount,
    String? description,
  }) async {
    final res = await _api.post('/payments/wallet/prop/payout', data: {
      'amount': amount,
      if (description != null) 'description': description,
    });
    final data = unwrap(res);
    return Map<String, dynamic>.from(data);
  }

  /// GET /payments/wallet/transactions
  Future<({List<WalletTransaction> transactions, int totalCount})>
      getTransactions({
    String? type,
    String? status,
    int limit = 20,
    int offset = 0,
  }) async {
    final res =
        await _api.get('/payments/wallet/transactions', queryParameters: {
      if (type != null) 'type': type,
      if (status != null) 'status': status,
      'limit': limit,
      'offset': offset,
    });
    final data = unwrap(res);
    final txns = (data['transactions'] as List?)
            ?.map((t) => WalletTransaction.fromJson(t))
            .toList() ??
        [];
    return (transactions: txns, totalCount: (data['total_count'] ?? 0) as int);
  }

  // ── Payouts (Driver) ─────────────────────────────────

  /// POST /payments/payout/request
  Future<Payout> requestPayout({
    required double amount,
    required String method, // bank_transfer, jazzcash, easypaisa
    required String accountDetails,
    String? notes,
  }) async {
    final res = await _api.post('/payments/payout/request', data: {
      'amount': amount,
      'method': method,
      'account_details': accountDetails,
      if (notes != null) 'notes': notes,
    });
    return Payout.fromJson(unwrap(res));
  }

  /// GET /payments/payout/history
  Future<List<Payout>> getPayoutHistory({
    String? status,
    int limit = 20,
    int offset = 0,
  }) async {
    final res = await _api.get('/payments/payout/history', queryParameters: {
      if (status != null) 'status': status,
      'limit': limit,
      'offset': offset,
    });
    final data = unwrap(res);
    final payouts =
        (data['payouts'] as List?)?.map((p) => Payout.fromJson(p)).toList() ??
            [];
    return payouts;
  }
}
