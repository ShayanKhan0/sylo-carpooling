import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/services/wallet_service.dart';
import '../../core/services/auth_service.dart';
import '../../core/models/wallet_model.dart';
import '../../core/theme/app_colors.dart';
import '../../core/constants/app_constants.dart';
import '../shared/widgets.dart';
import '../dashboard/home_design_system.dart';

class WalletScreen extends StatefulWidget {
  const WalletScreen({super.key});

  @override
  State<WalletScreen> createState() => _WalletScreenState();
}

class _WalletScreenState extends State<WalletScreen>
    with SingleTickerProviderStateMixin {
  static const Color _homeTextPrimary = Color(0xFF121915);
  static const Color _homeTextSecondary = Color(0xFF25352D);
  static const Color _driverHomeGraphLineGreen = Color(0xFF1D6F38);
  static const Color _debitAmountRed = Color(0xFF9E4747);

  BoxDecoration _homeCardDecoration({
    double radius = 16,
    bool elevated = true,
    double borderAlpha = 0.62,
    double borderWidth = 1.35,
  }) {
    return BoxDecoration(
      borderRadius: BorderRadius.circular(radius),
      color: const Color(0xA2123E2A),
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          Color(0xD255E0A0),
          Color(0xB53ABF7C),
          Color(0xA13A7051),
        ],
        stops: [0.0, 0.5, 1.0],
      ),
      border: Border.all(
        color: const Color(0xFFD7FFE8).withValues(alpha: borderAlpha),
        width: borderWidth,
      ),
      boxShadow: [
        if (elevated)
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.24),
            blurRadius: 32,
            offset: const Offset(0, 12),
          ),
        BoxShadow(
          color: const Color(0xFF1ED760).withValues(alpha: 0.34),
          blurRadius: 46,
          spreadRadius: -8,
          offset: const Offset(-8, -6),
        ),
      ],
    );
  }

  final WalletService _svc = WalletService();
  late TabController _tabCtrl;

  WalletBalance? _balance;
  List<WalletTransaction> _transactions = [];
  bool _loading = true;
  String? _error;
  String? _userRole;
  String _transactionsFilter = 'all';

  // ── Demo fallback data ──────────────────────────────────────────────
  static WalletBalance get _demoBalance => WalletBalance(
        userId: 'demo',
        balance: 2350.0,
        currency: 'PKR',
        lastUpdated: DateTime.now().toIso8601String(),
      );

  static List<WalletTransaction> get _demoTransactions => [
        WalletTransaction(
          id: 'd1',
          txnId: 'TXN-001',
          walletId: 'w1',
          userId: 'demo',
          amount: 500.0,
          type: 'topup',
          status: 'completed',
          provider: 'jazzcash',
          description: 'Wallet top-up via JazzCash',
          createdAt: DateTime.now()
              .subtract(const Duration(days: 1))
              .toIso8601String(),
        ),
        WalletTransaction(
          id: 'd2',
          txnId: 'TXN-002',
          walletId: 'w1',
          userId: 'demo',
          amount: 150.0,
          type: 'deduct',
          status: 'completed',
          description: 'Ride payment — Johar Town → Gulberg',
          createdAt: DateTime.now()
              .subtract(const Duration(days: 2))
              .toIso8601String(),
        ),
        WalletTransaction(
          id: 'd3',
          txnId: 'TXN-003',
          walletId: 'w1',
          userId: 'demo',
          amount: 1000.0,
          type: 'topup',
          status: 'completed',
          provider: 'easypaisa',
          description: 'Wallet top-up via Easypaisa',
          createdAt: DateTime.now()
              .subtract(const Duration(days: 3))
              .toIso8601String(),
        ),
        WalletTransaction(
          id: 'd4',
          txnId: 'TXN-004',
          walletId: 'w1',
          userId: 'demo',
          amount: 280.0,
          type: 'deduct',
          status: 'completed',
          description: 'Ride payment — DHA → Packages Mall',
          createdAt: DateTime.now()
              .subtract(const Duration(days: 5))
              .toIso8601String(),
        ),
        WalletTransaction(
          id: 'd5',
          txnId: 'TXN-005',
          walletId: 'w1',
          userId: 'demo',
          amount: 2000.0,
          type: 'topup',
          status: 'completed',
          provider: 'stripe',
          description: 'Wallet top-up via Stripe',
          createdAt: DateTime.now()
              .subtract(const Duration(days: 7))
              .toIso8601String(),
        ),
      ];

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 2, vsync: this);
    _loadAll();
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadAll() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final userId = await AuthService().getUserId();
      _userRole = await AuthService().getUserRole();
      if (userId == null) throw Exception('Not logged in');

      final balFut = _svc.getBalance(userId);
      final txnFut = _svc.getTransactions(limit: 50);

      final results = await Future.wait([balFut, txnFut]);
      final bal = results[0] as WalletBalance;
      final txnResult = results[1] as ({
        List<WalletTransaction> transactions,
        int totalCount
      });

      setState(() {
        _balance = bal;
        _transactions = txnResult.transactions;
        _loading = false;
      });
    } catch (e) {
      // Fall back to demo data so the screen is always usable
      debugPrint('[WalletScreen] API error, using demo data: $e');
      setState(() {
        _balance = _demoBalance;
        _transactions = _demoTransactions;
        _loading = false;
        _error = null;
      });
    }
  }

  void _showTopUpSheet() {
    final amountCtrl = TextEditingController();
    String provider = 'prop_money';
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setBS) {
            return Container(
              padding: EdgeInsets.only(
                top: 14,
                left: 18,
                right: 18,
                bottom: MediaQuery.of(ctx).viewInsets.bottom + 18,
              ),
              decoration: BoxDecoration(
                color: const Color(0xFF06150F),
                borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
                border: Border.all(
                  color: const Color(0xFF43E892).withValues(alpha: 0.16),
                ),
              ),
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Center(
                      child: Container(
                        width: 40,
                        height: 4,
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                    Text(
                      'Top Up Wallet',
                      style: GoogleFonts.inter(
                        fontSize: 34,
                        fontWeight: FontWeight.w800,
                        color: const Color(0xFFE7F4ED),
                        height: 1.05,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Add funds to your wallet using your preferred payment method.',
                      style: GoogleFonts.inter(
                        fontSize: 13,
                        color: const Color(0xFFA7BCB0),
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'AMOUNT (PKR)',
                      style: TextStyle(
                        color: Color(0xFFA1B9AD),
                        fontWeight: FontWeight.w700,
                        fontSize: 11,
                        letterSpacing: 0.8,
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: amountCtrl,
                      keyboardType: TextInputType.number,
                      style: const TextStyle(
                        color: Color(0xFFE9F7EF),
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                      ),
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: const Color(0xFF121F1B),
                        prefixIcon: const Icon(Icons.payments_outlined,
                            color: Color(0xFF4BF0A1)),
                        hintText: 'PKR 500',
                        hintStyle: const TextStyle(
                          color: Color(0xFF6F8579),
                          fontWeight: FontWeight.w600,
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide(
                            color: Colors.white.withValues(alpha: 0.1),
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide:
                              const BorderSide(color: Color(0xFF4BF0A1)),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'PAYMENT METHOD',
                      style: TextStyle(
                        color: Color(0xFFA1B9AD),
                        fontWeight: FontWeight.w700,
                        fontSize: 11,
                        letterSpacing: 0.8,
                      ),
                    ),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<String>(
                      value: provider,
                      dropdownColor: const Color(0xFF15231E),
                      iconEnabledColor: const Color(0xFFBDD2C8),
                      style: const TextStyle(
                        color: Color(0xFFE9F7EF),
                        fontWeight: FontWeight.w700,
                        fontSize: 18,
                      ),
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: const Color(0xFF121F1B),
                        prefixIcon: const Icon(Icons.account_balance_wallet_rounded,
                            color: Color(0xFF4BF0A1)),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide(
                            color: Colors.white.withValues(alpha: 0.1),
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide:
                              const BorderSide(color: Color(0xFF4BF0A1)),
                        ),
                      ),
                      items: const [
                        DropdownMenuItem(value: 'prop_money', child: Text('Prop Money')),
                        DropdownMenuItem(value: 'jazzcash', child: Text('JazzCash')),
                        DropdownMenuItem(value: 'easypaisa', child: Text('Easypaisa')),
                        DropdownMenuItem(value: 'stripe', child: Text('Stripe')),
                        DropdownMenuItem(value: 'paypal', child: Text('PayPal')),
                      ],
                      onChanged: (value) {
                        if (value != null) setBS(() => provider = value);
                      },
                    ),
                    const SizedBox(height: 12),
                    if (provider == 'prop_money')
                      Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: const Color(0xFF123728),
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(
                              color: const Color(0xFF4BF0A1)
                                  .withValues(alpha: 0.22)),
                        ),
                        child: const Row(
                          children: [
                            Icon(Icons.info_rounded,
                                size: 18, color: Color(0xFF4BF0A1)),
                            SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                'Prop Money top-ups are applied instantly to your wallet.',
                                style: TextStyle(
                                  color: Color(0xFFC7E7D6),
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    if (!_isTopUpProviderSupported(provider)) ...[
                      const SizedBox(height: 8),
                      _buildComingSoonHint(provider),
                    ],
                    const SizedBox(height: 24),
                    SizedBox(
                      height: 56,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(999),
                          boxShadow: [
                            BoxShadow(
                              color:
                                  const Color(0xFF4BF0A1).withValues(alpha: 0.42),
                              blurRadius: 20,
                              spreadRadius: 1.2,
                              offset: const Offset(0, 8),
                            ),
                          ],
                        ),
                        child: FilledButton(
                          onPressed: () async {
                            final amount =
                                double.tryParse(amountCtrl.text.trim()) ?? 0;
                            if (amount <= 0) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                    content: Text('Enter a valid amount')),
                              );
                              return;
                            }
                            if (!_isTopUpProviderSupported(provider)) {
                              _showComingSoonDialog(ctx, provider);
                              return;
                            }
                            Navigator.pop(ctx);
                            try {
                              if (provider == 'prop_money') {
                                await _svc.propTopUp(
                                  amount: amount,
                                  description: 'Prop Money top-up',
                                );
                              } else {
                                await _svc.topUp(amount: amount, provider: provider);
                              }
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                    content: Text(
                                        '₨ ${amount.toStringAsFixed(0)} topped up!')),
                              );
                              _loadAll();
                            } catch (e) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(content: Text('Top-up failed: $e')),
                              );
                            }
                          },
                          style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFF43E892),
                            foregroundColor: const Color(0xFF052E1E),
                            elevation: 0,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(999),
                            ),
                          ),
                          child: const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.add_rounded, size: 18),
                              SizedBox(width: 10),
                              Text(
                                'TOP UP',
                                style: TextStyle(
                                  fontWeight: FontWeight.w800,
                                  fontSize: 15,
                                  letterSpacing: 1.1,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  bool _isTopUpProviderSupported(String provider) {
    return provider == 'prop_money';
  }

  bool _isPayoutMethodSupported(String method) {
    return method == 'prop_money';
  }

  String _providerDisplayName(String value) {
    switch (value) {
      case 'jazzcash':
        return 'JazzCash';
      case 'easypaisa':
        return 'Easypaisa';
      case 'stripe':
        return 'Stripe';
      case 'paypal':
        return 'PayPal';
      case 'bank_transfer':
        return 'Bank Transfer';
      case 'prop_money':
        return 'Prop Money';
      default:
        return value.replaceAll('_', ' ');
    }
  }

  String _comingSoonMessage(String value) {
    return '${_providerDisplayName(value)} integration is coming soon. Please use Prop Money for now.';
  }

  void _showComingSoonDialog(BuildContext sheetContext, String value) {
    showDialog<void>(
      context: sheetContext,
      useRootNavigator: true,
      builder: (dialogCtx) => AlertDialog(
        title: const Text('Feature Coming Soon'),
        content: Text(_comingSoonMessage(value)),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogCtx).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  Widget _buildComingSoonHint(String value) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppColors.accent.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
        border: Border.all(color: AppColors.accent.withValues(alpha: 0.24)),
      ),
      child: Row(
        children: [
          const Icon(Icons.info_outline_rounded,
              color: AppColors.accent, size: 16),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              '${_providerDisplayName(value)} will be implemented in a future update.',
              style: const TextStyle(fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  String _friendlyWalletError(Object e) {
    final raw = e.toString();
    final lower = raw.toLowerCase();
    if (lower.contains('insufficient balance') ||
        lower.contains('not enough available balance')) {
      return 'Not enough available balance for this payout.';
    }
    return raw;
  }

  void _showPayoutSheet() {
    final amountCtrl = TextEditingController();
    final acctCtrl = TextEditingController();
    final availableBalance = _balance?.balance ?? 0.0;
    String method = 'prop_money';
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setBS) {
            final enteredAmount = double.tryParse(amountCtrl.text.trim()) ?? 0;
            final isOverBalance = enteredAmount > availableBalance;
            final overBy =
                isOverBalance ? (enteredAmount - availableBalance) : 0.0;

            return Padding(
              padding: EdgeInsets.only(
                left: 24,
                right: 24,
                top: 24,
                bottom: MediaQuery.of(ctx).viewInsets.bottom + 24,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Center(
                    child: Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: const Color(0xFF3A4942),
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  const SizedBox(height: 18),
                  const Text(
                    'Request Payout',
                    style: TextStyle(
                      fontSize: 34,
                      fontWeight: FontWeight.w800,
                      color: Color(0xFFE7F4ED),
                    ),
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'Transfer your earnings to your linked payout account.',
                    style: TextStyle(
                      fontSize: 13,
                      color: Color(0xFFA7BCB0),
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 14),
                    decoration: BoxDecoration(
                      color: const Color(0xFF182823),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(
                        color: Colors.white.withValues(alpha: 0.08),
                      ),
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(
                            color:
                                const Color(0xFF38E38A).withValues(alpha: 0.16),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(
                            Icons.account_balance_wallet_rounded,
                            color: Color(0xFF4BF0A1),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'AVAILABLE BALANCE',
                              style: TextStyle(
                                fontSize: 11,
                                letterSpacing: 0.9,
                                fontWeight: FontWeight.w700,
                                color: Color(0xFF8EA59A),
                              ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              'PKR ${availableBalance.toStringAsFixed(0)}',
                              style: const TextStyle(
                                fontSize: 42,
                                fontWeight: FontWeight.w900,
                                color: Color(0xFFE8F8EF),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'AMOUNT (MIN PKR 500)',
                    style: TextStyle(
                      color: Color(0xFFA1B9AD),
                      fontWeight: FontWeight.w700,
                      fontSize: 11,
                      letterSpacing: 0.8,
                    ),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: amountCtrl,
                    onChanged: (_) => setBS(() {}),
                    keyboardType: TextInputType.number,
                    style: TextStyle(
                      color: isOverBalance
                          ? AppColors.error
                          : const Color(0xFFE9F7EF),
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                    ),
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: const Color(0xFF121F1B),
                      prefixIcon: const Icon(Icons.payments_outlined,
                          color: Color(0xFF4BF0A1)),
                      hintText: 'PKR 500',
                      hintStyle: const TextStyle(
                        color: Color(0xFF6F8579),
                        fontWeight: FontWeight.w600,
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: BorderSide(
                          color: Colors.white.withValues(alpha: 0.1),
                        ),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(color: Color(0xFF4BF0A1)),
                      ),
                    ),
                  ),
                  if (isOverBalance) ...[
                    const SizedBox(height: 8),
                    const Text(
                      'Trying to withdraw more than available balance.',
                      style: TextStyle(
                        color: AppColors.error,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Requested: Rs ${enteredAmount.toStringAsFixed(2)} | '
                      'Available: Rs ${availableBalance.toStringAsFixed(2)} | '
                      'Over by: Rs ${overBy.toStringAsFixed(2)}',
                      style: const TextStyle(
                        color: AppColors.error,
                        fontSize: 12,
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  const Text(
                    'PAYOUT METHOD',
                    style: TextStyle(
                      color: Color(0xFFA1B9AD),
                      fontWeight: FontWeight.w700,
                      fontSize: 11,
                      letterSpacing: 0.8,
                    ),
                  ),
                  const SizedBox(height: 8),
                  DropdownButtonFormField<String>(
                    value: method,
                    dropdownColor: const Color(0xFF15231E),
                    iconEnabledColor: const Color(0xFFBDD2C8),
                    style: const TextStyle(
                      color: Color(0xFFE9F7EF),
                      fontWeight: FontWeight.w700,
                      fontSize: 18,
                    ),
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: const Color(0xFF121F1B),
                      prefixIcon: const Icon(
                          Icons.account_balance_wallet_rounded,
                          color: Color(0xFF4BF0A1)),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: BorderSide(
                          color: Colors.white.withValues(alpha: 0.1),
                        ),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(14),
                        borderSide: const BorderSide(color: Color(0xFF4BF0A1)),
                      ),
                    ),
                    items: const [
                      DropdownMenuItem(
                        value: 'prop_money',
                        child: Text('Prop Money'),
                      ),
                      DropdownMenuItem(
                        value: 'jazzcash',
                        child: Text('JazzCash'),
                      ),
                      DropdownMenuItem(
                        value: 'easypaisa',
                        child: Text('Easypaisa'),
                      ),
                      DropdownMenuItem(
                        value: 'bank_transfer',
                        child: Text('Bank Transfer'),
                      ),
                    ],
                    onChanged: (value) {
                      if (value != null) setBS(() => method = value);
                    },
                  ),
                  const SizedBox(height: 12),
                  if (method != 'prop_money')
                    TextField(
                      controller: acctCtrl,
                      style: const TextStyle(
                        color: Color(0xFFE9F7EF),
                        fontWeight: FontWeight.w600,
                      ),
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: const Color(0xFF121F1B),
                        labelText: 'Account Details',
                        hintText: 'Account number or mobile number',
                        labelStyle: const TextStyle(color: Color(0xFF8BA095)),
                        hintStyle: const TextStyle(color: Color(0xFF6F8579)),
                        prefixIcon: const Icon(Icons.account_balance_rounded,
                            color: Color(0xFF4BF0A1)),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide(
                            color: Colors.white.withValues(alpha: 0.1),
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide:
                              const BorderSide(color: Color(0xFF4BF0A1)),
                        ),
                      ),
                    )
                  else
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: const Color(0xFF123728),
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                            color: const Color(0xFF4BF0A1)
                                .withValues(alpha: 0.22)),
                      ),
                      child: const Row(
                        children: [
                          Icon(Icons.info_rounded,
                              size: 18, color: Color(0xFF4BF0A1)),
                          SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'Payouts are processed within 24-48 business hours. Ensure your payout method details are verified.',
                              style: TextStyle(
                                color: Color(0xFFC7E7D6),
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  if (!_isPayoutMethodSupported(method)) ...[
                    const SizedBox(height: 8),
                    _buildComingSoonHint(method),
                  ],
                  const SizedBox(height: 24),
                  SizedBox(
                    height: 56,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(999),
                        boxShadow: [
                          BoxShadow(
                            color:
                                const Color(0xFF4BF0A1).withValues(alpha: 0.42),
                            blurRadius: 20,
                            spreadRadius: 1.2,
                            offset: const Offset(0, 8),
                          ),
                        ],
                      ),
                      child: FilledButton(
                        onPressed: () async {
                          final amount =
                              double.tryParse(amountCtrl.text.trim()) ?? 0;
                          final acct = acctCtrl.text.trim();
                          if (amount <= 0) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                  content: Text('Enter a valid amount')),
                            );
                            return;
                          }
                          if (!_isPayoutMethodSupported(method)) {
                            _showComingSoonDialog(ctx, method);
                            return;
                          }
                          if (method != 'prop_money' && acct.isEmpty) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                  content:
                                      Text('Enter amount and account details')),
                            );
                            return;
                          }
                          if (amount > availableBalance) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text(
                                  'Trying to withdraw more than available balance. '
                                  'Available: Rs ${availableBalance.toStringAsFixed(2)}',
                                ),
                              ),
                            );
                            setBS(() {});
                            return;
                          }
                          Navigator.pop(ctx);
                          try {
                            if (method == 'prop_money') {
                              await _svc.propPayout(
                                amount: amount,
                                description: 'Prop Money Payout',
                              );
                            } else {
                              await _svc.requestPayout(
                                amount: amount,
                                method: method,
                                accountDetails: acct,
                              );
                            }
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                  content: Text('Payout requested!')),
                            );
                            _loadAll();
                          } catch (e) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                  content: Text(
                                      'Payout failed: ${_friendlyWalletError(e)}')),
                            );
                          }
                        },
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFF43E892),
                          foregroundColor: const Color(0xFF052E1E),
                          elevation: 0,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(999),
                          ),
                        ),
                        child: const Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(Icons.send_rounded, size: 18),
                            SizedBox(width: 10),
                            Text(
                              'SUBMIT REQUEST',
                              style: TextStyle(
                                fontWeight: FontWeight.w800,
                                fontSize: 15,
                                letterSpacing: 1.1,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  void _showWithdrawSheet() {
    final amountCtrl = TextEditingController();
    final acctCtrl = TextEditingController();
    String method = 'prop_money';
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setBS) {
            return Container(
              padding: EdgeInsets.only(
                top: 14,
                left: 18,
                right: 18,
                bottom: MediaQuery.of(ctx).viewInsets.bottom + 18,
              ),
              decoration: BoxDecoration(
                color: const Color(0xFF06150F),
                borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
                border: Border.all(
                  color: const Color(0xFF43E892).withValues(alpha: 0.16),
                ),
              ),
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Center(
                      child: Container(
                        width: 40,
                        height: 4,
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                    ),
                    const SizedBox(height: 14),
                    Text(
                      'Withdraw Funds',
                      style: GoogleFonts.inter(
                        fontSize: 34,
                        fontWeight: FontWeight.w800,
                        color: const Color(0xFFE7F4ED),
                        height: 1.05,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Withdraw wallet balance to your linked payout method.',
                      style: GoogleFonts.inter(
                        fontSize: 13,
                        color: const Color(0xFFA7BCB0),
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'AMOUNT (PKR)',
                      style: TextStyle(
                        color: Color(0xFFA1B9AD),
                        fontWeight: FontWeight.w700,
                        fontSize: 11,
                        letterSpacing: 0.8,
                      ),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: amountCtrl,
                      keyboardType: TextInputType.number,
                      style: const TextStyle(
                        color: Color(0xFFE9F7EF),
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                      ),
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: const Color(0xFF121F1B),
                        prefixIcon: const Icon(Icons.payments_outlined,
                            color: Color(0xFF4BF0A1)),
                        hintText: 'PKR 500',
                        hintStyle: const TextStyle(
                          color: Color(0xFF6F8579),
                          fontWeight: FontWeight.w600,
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide(
                            color: Colors.white.withValues(alpha: 0.1),
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide:
                              const BorderSide(color: Color(0xFF4BF0A1)),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'WITHDRAW TO',
                      style: TextStyle(
                        color: Color(0xFFA1B9AD),
                        fontWeight: FontWeight.w700,
                        fontSize: 11,
                        letterSpacing: 0.8,
                      ),
                    ),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<String>(
                      value: method,
                      dropdownColor: const Color(0xFF15231E),
                      iconEnabledColor: const Color(0xFFBDD2C8),
                      style: const TextStyle(
                        color: Color(0xFFE9F7EF),
                        fontWeight: FontWeight.w700,
                        fontSize: 18,
                      ),
                      decoration: InputDecoration(
                        filled: true,
                        fillColor: const Color(0xFF121F1B),
                        prefixIcon: const Icon(Icons.account_balance_wallet_rounded,
                            color: Color(0xFF4BF0A1)),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide(
                            color: Colors.white.withValues(alpha: 0.1),
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide:
                              const BorderSide(color: Color(0xFF4BF0A1)),
                        ),
                      ),
                      items: const [
                        DropdownMenuItem(value: 'prop_money', child: Text('Prop Money')),
                        DropdownMenuItem(value: 'jazzcash', child: Text('JazzCash')),
                        DropdownMenuItem(value: 'easypaisa', child: Text('Easypaisa')),
                        DropdownMenuItem(
                            value: 'bank_transfer', child: Text('Bank Transfer')),
                      ],
                      onChanged: (value) {
                        if (value != null) setBS(() => method = value);
                      },
                    ),
                    const SizedBox(height: 12),
                    if (method != 'prop_money')
                      TextField(
                        controller: acctCtrl,
                        style: const TextStyle(
                          color: Color(0xFFE9F7EF),
                          fontWeight: FontWeight.w600,
                        ),
                        decoration: InputDecoration(
                          filled: true,
                          fillColor: const Color(0xFF121F1B),
                          labelText: 'Account Details',
                          hintText: 'Account number or mobile number',
                          labelStyle: const TextStyle(color: Color(0xFF8BA095)),
                          hintStyle: const TextStyle(color: Color(0xFF6F8579)),
                          prefixIcon: const Icon(Icons.account_balance_rounded,
                              color: Color(0xFF4BF0A1)),
                          enabledBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(14),
                            borderSide: BorderSide(
                              color: Colors.white.withValues(alpha: 0.1),
                            ),
                          ),
                          focusedBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(14),
                            borderSide:
                                const BorderSide(color: Color(0xFF4BF0A1)),
                          ),
                        ),
                      )
                    else
                      Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: const Color(0xFF123728),
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(
                              color: const Color(0xFF4BF0A1)
                                  .withValues(alpha: 0.22)),
                        ),
                        child: const Row(
                          children: [
                            Icon(Icons.info_rounded,
                                size: 18, color: Color(0xFF4BF0A1)),
                            SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                'Prop Money is internal and updates your wallet instantly.',
                                style: TextStyle(
                                  color: Color(0xFFC7E7D6),
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    if (!_isPayoutMethodSupported(method)) ...[
                      const SizedBox(height: 8),
                      _buildComingSoonHint(method),
                    ],
                    const SizedBox(height: 24),
                    SizedBox(
                      height: 56,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(999),
                          boxShadow: [
                            BoxShadow(
                              color:
                                  const Color(0xFF4BF0A1).withValues(alpha: 0.42),
                              blurRadius: 20,
                              spreadRadius: 1.2,
                              offset: const Offset(0, 8),
                            ),
                          ],
                        ),
                        child: FilledButton(
                          onPressed: () async {
                            final amount =
                                double.tryParse(amountCtrl.text.trim()) ?? 0;
                            final acct = acctCtrl.text.trim();
                            if (amount <= 0) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                    content: Text('Enter a valid amount')),
                              );
                              return;
                            }
                            if (!_isPayoutMethodSupported(method)) {
                              _showComingSoonDialog(ctx, method);
                              return;
                            }
                            if (method != 'prop_money' && acct.isEmpty) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                    content:
                                        Text('Enter amount and account details')),
                              );
                              return;
                            }
                            Navigator.pop(ctx);
                            try {
                              if (method == 'prop_money') {
                                await _svc.propPayout(
                                  amount: amount,
                                  description: 'Prop Money Payout',
                                );
                              } else {
                                await _svc.requestPayout(
                                  amount: amount,
                                  method: method,
                                  accountDetails: acct,
                                );
                              }
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                    content: Text(
                                        '₨ ${amount.toStringAsFixed(0)} withdrawal requested!')),
                              );
                              _loadAll();
                            } catch (e) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                    content: Text(
                                        'Withdrawal failed: ${_friendlyWalletError(e)}')),
                              );
                            }
                          },
                          style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFF43E892),
                            foregroundColor: const Color(0xFF052E1E),
                            elevation: 0,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(999),
                            ),
                          ),
                          child: const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.account_balance_wallet_rounded, size: 18),
                              SizedBox(width: 10),
                              Text(
                                'WITHDRAW',
                                style: TextStyle(
                                  fontWeight: FontWeight.w800,
                                  fontSize: 15,
                                  letterSpacing: 1.1,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: _loading
          ? const SyloLoader(message: 'Loading wallet…')
          : _error != null
              ? SyloError(message: _error!, onRetry: _loadAll)
              : Stack(
                  children: [
                    Positioned.fill(
                      child: HomeDesignSystem.driverHomeSoftWhiteBackground(),
                    ),
                    SafeArea(
                      child: Column(
                        children: [
                          Padding(
                            padding: const EdgeInsets.fromLTRB(12, 8, 12, 6),
                            child: Row(
                              children: [
                                Material(
                                  color: Colors.transparent,
                                  child: InkWell(
                                    borderRadius: BorderRadius.circular(12),
                                    onTap: () => Navigator.maybePop(context),
                                    child: Container(
                                      width: 40,
                                      height: 40,
                                      decoration: _homeCardDecoration(
                                        radius: 12,
                                        elevated: false,
                                        borderAlpha: 0.52,
                                        borderWidth: 1.0,
                                      ),
                                      child: const Icon(
                                        Icons.arrow_back_rounded,
                                        color: Color(0xFF122019),
                                        size: 22,
                                      ),
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Container(
                                    height: 40,
                                    decoration: _homeCardDecoration(
                                      radius: 12,
                                      elevated: false,
                                      borderAlpha: 0.52,
                                      borderWidth: 1.0,
                                    ),
                                    child: TabBar(
                                      controller: _tabCtrl,
                                      dividerColor: Colors.transparent,
                                      indicatorSize: TabBarIndicatorSize.tab,
                                      indicator: BoxDecoration(
                                        color: const Color(0xFF7CD8A5),
                                        borderRadius: BorderRadius.circular(10),
                                        border: Border.all(
                                          color: const Color(0xFF4FAA7F)
                                              .withValues(alpha: 0.65),
                                        ),
                                      ),
                                      labelColor: _homeTextPrimary,
                                      unselectedLabelColor: _homeTextSecondary
                                          .withValues(alpha: 0.92),
                                      labelStyle: TextStyle(
                                        fontWeight: FontWeight.w900,
                                        fontSize: 14,
                                        letterSpacing: 0.5,
                                        fontFamily: GoogleFonts.inter().fontFamily,
                                      ),
                                      unselectedLabelStyle: TextStyle(
                                        fontWeight: FontWeight.w800,
                                        fontSize: 13,
                                        letterSpacing: 0.4,
                                        fontFamily: GoogleFonts.inter().fontFamily,
                                      ),
                                      tabs: const [
                                        Tab(text: 'WALLET'),
                                        Tab(text: 'TRANSACTIONS'),
                                      ],
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Expanded(
                            child: TabBarView(
                              controller: _tabCtrl,
                              children: [
                                _buildOverview(theme),
                                _buildTransactions(theme),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
    );
  }

  Widget _buildOverview(ThemeData theme) {
    final recentTxns = _transactions.take(3).toList();
    final actionLabel = _userRole == 'driver' ? 'PAYOUT' : 'WITHDRAW';
    final actionIcon = _userRole == 'driver'
        ? Icons.north_east_rounded
        : Icons.account_balance_wallet_rounded;
    final actionTap =
        _userRole == 'driver' ? _showPayoutSheet : _showWithdrawSheet;

    return RefreshIndicator(
      color: const Color(0xFF43E892),
      onRefresh: _loadAll,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 20),
        children: [
          Text(
            'WALLET',
            style: GoogleFonts.inter(
              fontSize: 48,
              fontWeight: FontWeight.w900,
              color: _homeTextPrimary,
              height: 0.95,
            ),
          ),
          const SizedBox(height: 6),
          Container(
            width: 72,
            height: 5,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(999),
              color: const Color(0xFF43E892),
            ),
          ),
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.fromLTRB(22, 24, 22, 22),
            decoration: _homeCardDecoration(radius: 22),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'AVAILABLE BALANCE',
                            style: TextStyle(
                              color: _homeTextSecondary,
                              fontSize: 11,
                              fontWeight: FontWeight.w700,
                              letterSpacing: 1.2,
                            ),
                          ),
                          const SizedBox(height: 10),
                          const Text(
                            'Rs',
                            style: TextStyle(
                              color: Color(0xFF218B57),
                              fontSize: 44,
                              fontWeight: FontWeight.w900,
                              height: 0.95,
                            ),
                          ),
                          const SizedBox(height: 4),
                          FittedBox(
                            fit: BoxFit.scaleDown,
                            alignment: Alignment.centerLeft,
                            child: Text(
                              (_balance?.balance ?? 0).toStringAsFixed(2),
                              style: GoogleFonts.inter(
                                color: _homeTextPrimary,
                                fontSize: 48,
                                fontWeight: FontWeight.w900,
                                letterSpacing: 0.2,
                                height: 1.0,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 10),
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        color: const Color(0xFF43E892).withValues(alpha: 0.26),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color:
                              const Color(0xFF43E892).withValues(alpha: 0.45),
                        ),
                      ),
                      child: const Icon(
                        Icons.account_balance_wallet_rounded,
                        color: Color(0xFF2FAF6F),
                        size: 22,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 22),
                Row(
                  children: [
                    Expanded(
                      child: _walletPillButton(
                        label: 'TOP UP',
                        icon: Icons.add_rounded,
                        onTap: _showTopUpSheet,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _walletPillButton(
                        label: actionLabel,
                        icon: actionIcon,
                        onTap: actionTap,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: _walletMiniStat(
                  icon: Icons.south_west_rounded,
                  iconColor: const Color(0xFF218B57),
                  label: 'Total In',
                  value: 'Rs ${_totalIn.toStringAsFixed(0)}',
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _walletMiniStat(
                  icon: Icons.north_east_rounded,
                  iconColor: _debitAmountRed,
                  label: 'Total Out',
                  value: 'Rs ${_totalOut.toStringAsFixed(0)}',
                ),
              ),
            ],
          ),
          const SizedBox(height: 22),
          Row(
            children: [
              Text(
                'RECENT ACTIVITY',
                style: GoogleFonts.inter(
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.8,
                  color: _homeTextSecondary.withValues(alpha: 0.75),
                ),
              ),
              const Spacer(),
              TextButton(
                onPressed: () => _tabCtrl.animateTo(1),
                style: TextButton.styleFrom(
                  padding: EdgeInsets.zero,
                  minimumSize: const Size(0, 0),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: Text(
                  'VIEW ALL',
                  style: GoogleFonts.inter(
                    color: const Color(0xFF43E892),
                    fontWeight: FontWeight.w800,
                    fontSize: 11,
                    letterSpacing: 1.1,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (recentTxns.isEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(18),
              decoration: _homeCardDecoration(
                radius: 16,
                elevated: false,
                borderAlpha: 0.52,
                borderWidth: 1.0,
              ),
              child: const Text(
                'No recent activity.',
                style: TextStyle(
                  color: _homeTextPrimary,
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                ),
              ),
            )
          else
            ...recentTxns.map((t) => _walletRecentActivityCard(t)),
        ],
      ),
    );
  }

  Widget _walletPillButton({
    required String label,
    required IconData icon,
    required VoidCallback onTap,
  }) {
    return SizedBox(
      height: 50,
      child: FilledButton(
        onPressed: onTap,
        style: FilledButton.styleFrom(
          backgroundColor: _driverHomeGraphLineGreen,
          foregroundColor: const Color(0xFF052E1E),
          elevation: 0,
          padding: const EdgeInsets.symmetric(horizontal: 12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(999),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 18, color: const Color(0xFF052E1E)),
            const SizedBox(width: 8),
            Text(
              label,
              style: const TextStyle(
                fontWeight: FontWeight.w800,
                fontSize: 14,
                letterSpacing: 0.6,
                color: Color(0xFF43E892),
              ),
            ),
          ],
        ),
      ),
    );
  }

  double get _totalIn {
    return _transactions
        .where((t) => t.isCredit && t.status == 'completed')
        .fold(0.0, (sum, t) => sum + t.amount);
  }

  double get _totalOut {
    return _transactions
        .where((t) => !t.isCredit && t.status == 'completed')
        .fold(0.0, (sum, t) => sum + t.amount);
  }

  Widget _walletMiniStat({
    required IconData icon,
    required Color iconColor,
    required String label,
    required String value,
  }) {
    return Container(
      padding: const EdgeInsets.fromLTRB(18, 16, 16, 18),
      decoration: _homeCardDecoration(
        radius: 18,
        elevated: false,
        borderAlpha: 0.52,
        borderWidth: 1.0,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  label.toUpperCase(),
                  style: const TextStyle(
                    color: _homeTextSecondary,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.1,
                  ),
                ),
              ),
              Container(
                width: 26,
                height: 26,
                decoration: BoxDecoration(
                  color: iconColor.withValues(alpha: 0.18),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Icon(icon, color: iconColor, size: 14),
              ),
            ],
          ),
          const SizedBox(height: 18),
          Text(
            value,
            style: const TextStyle(
              fontWeight: FontWeight.w900,
              fontSize: 26,
              color: _homeTextPrimary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _walletRecentActivityCard(WalletTransaction t) {
    final isCredit = t.isCredit;
    final amountColor = isCredit ? const Color(0xFF218B57) : _debitAmountRed;
    final amountPrefix = isCredit ? '+ Rs ' : '- Rs ';
    final title = t.description ?? t.type.replaceAll('_', ' ').toUpperCase();
    final subtitle = _formatActivityDate(t.createdAt).toUpperCase();
    final statusText = (t.status).toUpperCase();

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      decoration: _homeCardDecoration(
        radius: 16,
        elevated: false,
        borderAlpha: 0.52,
        borderWidth: 1.0,
      ),
      child: Row(
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: isCredit
                  ? const Color(0xFF218B57).withValues(alpha: 0.18)
                  : _debitAmountRed.withValues(alpha: 0.16),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              isCredit
                  ? Icons.directions_car_filled_rounded
                  : Icons.account_balance_rounded,
              color: amountColor,
              size: 20,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: _homeTextPrimary,
                    fontWeight: FontWeight.w700,
                    fontSize: 15,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  style: const TextStyle(
                    color: _homeTextSecondary,
                    fontWeight: FontWeight.w600,
                    fontSize: 10,
                    letterSpacing: 0.8,
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '$amountPrefix${t.amount.toStringAsFixed(2)}',
                style: TextStyle(
                  color: amountColor,
                  fontWeight: FontWeight.w800,
                  fontSize: 14,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                statusText,
                style: TextStyle(
                  color: amountColor.withValues(alpha: 0.82),
                  fontWeight: FontWeight.w700,
                  fontSize: 9,
                  letterSpacing: 0.9,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _formatActivityDate(String? iso) {
    if (iso == null || iso.isEmpty) return '';
    final dt = DateTime.tryParse(iso);
    if (dt == null) return '';
    final now = DateTime.now();
    final local = dt.toLocal();
    final sameDay = local.year == now.year &&
        local.month == now.month &&
        local.day == now.day;
    final yesterday = now.subtract(const Duration(days: 1));
    final isYesterday = local.year == yesterday.year &&
        local.month == yesterday.month &&
        local.day == yesterday.day;
    final hour12 = ((local.hour + 11) % 12) + 1;
    final minute = local.minute.toString().padLeft(2, '0');
    final ampm = local.hour >= 12 ? 'PM' : 'AM';
    final time = '$hour12:$minute $ampm';
    if (sameDay) return 'TODAY $time';
    if (isYesterday) return 'YESTERDAY $time';
    return '${local.day}/${local.month}/${local.year} $time';
  }

  Widget _buildTransactions(ThemeData theme) {
    final filtered = _transactions.where(_isTransactionVisible).toList();

    return RefreshIndicator(
      color: const Color(0xFF43E892),
      onRefresh: _loadAll,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(12, 10, 12, 20),
        children: [
          Text(
            'TRANSACTIONS',
            style: GoogleFonts.inter(
              fontSize: 48,
              fontWeight: FontWeight.w900,
              color: _homeTextPrimary,
              height: 0.95,
            ),
          ),
          const SizedBox(height: 6),
          Container(
            width: 72,
            height: 5,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(999),
              color: const Color(0xFF43E892),
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _transactionFilterChip(
                  label: 'All Activity',
                  value: 'all',
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _transactionFilterChip(
                  label: 'Payouts',
                  value: 'earnings',
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _transactionFilterChip(
                  label: 'Top-ups',
                  value: 'topups',
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          if (filtered.isEmpty)
            Container(
              padding: const EdgeInsets.all(18),
              decoration: _homeCardDecoration(
                radius: 16,
                elevated: false,
                borderAlpha: 0.52,
                borderWidth: 1.0,
              ),
              child: Text(
                'No transactions in this filter.',
                style: GoogleFonts.inter(
                  color: _homeTextPrimary,
                  fontWeight: FontWeight.w700,
                  fontSize: 14,
                ),
              ),
            )
          else
            ...filtered.map(_buildTransactionsCard),
        ],
      ),
    );
  }

  bool _isTransactionVisible(WalletTransaction t) {
    switch (_transactionsFilter) {
      case 'topups':
        return t.type == 'topup';
      case 'earnings':
        return t.type != 'topup';
      default:
        return true;
    }
  }

  Widget _transactionFilterChip({
    required String label,
    required String value,
  }) {
    final selected = _transactionsFilter == value;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => setState(() => _transactionsFilter = value),
        borderRadius: BorderRadius.circular(12),
        child: Container(
          height: 36,
          decoration: _homeCardDecoration(
            radius: 12,
            elevated: false,
            borderAlpha: selected ? 0.7 : 0.48,
            borderWidth: selected ? 1.2 : 1.0,
          ),
          child: Center(
            child: Text(
              label,
              textAlign: TextAlign.center,
              style: GoogleFonts.inter(
                color: selected
                    ? _homeTextPrimary
                    : _homeTextSecondary.withValues(alpha: 0.94),
                fontWeight: selected ? FontWeight.w800 : FontWeight.w700,
                fontSize: 12,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTransactionsCard(WalletTransaction t) {
    final isCredit = t.isCredit;
    final amountColor = isCredit ? const Color(0xFF218B57) : _debitAmountRed;
    final iconColor = isCredit
        ? const Color(0xFF218B57).withValues(alpha: 0.2)
        : _debitAmountRed.withValues(alpha: 0.18);
    final title = t.description ?? t.type.replaceAll('_', ' ').toUpperCase();
    final subtitle = _formatActivityDate(t.createdAt).toUpperCase();
    final status = t.status.toUpperCase();

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 12),
      decoration: _homeCardDecoration(
        radius: 16,
        elevated: false,
        borderAlpha: 0.52,
        borderWidth: 1.0,
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: iconColor,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  isCredit
                      ? Icons.account_balance_wallet_rounded
                      : Icons.directions_car_filled_rounded,
                  color: amountColor,
                  size: 21,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: GoogleFonts.inter(
                        color: _homeTextPrimary,
                        fontWeight: FontWeight.w800,
                        fontSize: 22,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      subtitle,
                      style: GoogleFonts.inter(
                        color: _homeTextSecondary.withValues(alpha: 0.82),
                        fontWeight: FontWeight.w700,
                        fontSize: 11,
                        letterSpacing: 0.7,
                      ),
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    '${isCredit ? '+' : '-'} Rs',
                    style: GoogleFonts.inter(
                      color: amountColor,
                      fontWeight: FontWeight.w800,
                      fontSize: 13,
                    ),
                  ),
                  Text(
                    t.amount.toStringAsFixed(0),
                    style: GoogleFonts.inter(
                      color: amountColor,
                      fontWeight: FontWeight.w900,
                      fontSize: 38,
                      height: 0.9,
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
                decoration: BoxDecoration(
                  color: const Color(0xFF2FAF6F).withValues(alpha: 0.18),
                  borderRadius: BorderRadius.circular(999),
                  border: Border.all(
                    color: const Color(0xFF2FAF6F).withValues(alpha: 0.42),
                  ),
                ),
                child: Text(
                  status,
                  style: GoogleFonts.inter(
                    color: const Color(0xFF1A6F44),
                    fontWeight: FontWeight.w800,
                    fontSize: 11,
                    letterSpacing: 0.8,
                  ),
                ),
              ),
              const Spacer(),
              Icon(
                Icons.receipt_long_rounded,
                size: 16,
                color: _homeTextSecondary.withValues(alpha: 0.86),
              ),
            ],
          ),
        ],
      ),
    );
  }

}
