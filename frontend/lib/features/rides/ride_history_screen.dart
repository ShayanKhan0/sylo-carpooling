import 'package:flutter/material.dart';
import '../../core/services/ride_service.dart';
import '../../core/services/auth_service.dart';
import '../../core/models/ride_model.dart';
import '../../core/theme/app_colors.dart';
import '../../core/constants/app_constants.dart';
import '../shared/widgets.dart';

class RideHistoryScreen extends StatefulWidget {
  const RideHistoryScreen({super.key});

  @override
  State<RideHistoryScreen> createState() => _RideHistoryScreenState();
}

class _RideHistoryScreenState extends State<RideHistoryScreen>
    with SingleTickerProviderStateMixin {
  final RideService _svc = RideService();
  late TabController _tabCtrl;

  List<RideBooking> _passengerRides = [];
  List<Ride> _driverRides = [];
  bool _loading = true;
  String? _error;
  String? _userRole;
  String _filter = 'all';

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
      _userRole = await AuthService().getUserRole();
      final bookings = await _svc.getMyBookings(
        statusFilter: _filter == 'all' ? null : _filter,
      );
      List<Ride> driverRides = [];
      if (_userRole == 'driver') {
        driverRides = await _svc.getMyDriverRides(
          statusFilter: _filter == 'all' ? null : _filter,
        );
      }
      setState(() {
        _passengerRides = bookings;
        _driverRides = driverRides;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Color _statusColor(String status) {
    final normalized = status.trim().toLowerCase();

    if (normalized.contains('cancelled')) {
      return AppColors.error;
    }
    if (normalized.contains('completed')) {
      return AppColors.success;
    }
    if (normalized.contains('started') || normalized == 'in_progress') {
      return AppColors.accent;
    }
    if (normalized.contains('booked') ||
        normalized.contains('open') ||
        normalized.contains('reserved') ||
        normalized.contains('confirmed')) {
      return AppColors.info;
    }
    return AppColors.textSecondary;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Ride History'),
        bottom: _userRole == 'driver'
            ? TabBar(
                controller: _tabCtrl,
                tabs: const [
                  Tab(text: 'As Passenger'),
                  Tab(text: 'As Driver'),
                ],
              )
            : null,
      ),
      body: Column(
        children: [
          // Filter chips
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(
                horizontal: AppConstants.paddingMedium, vertical: 8),
            child: Row(
              children: [
                _filterChip('All', 'all'),
                const SizedBox(width: 8),
                _filterChip('Completed', 'completed'),
                const SizedBox(width: 8),
                _filterChip('Cancelled', 'cancelled'),
                const SizedBox(width: 8),
                _filterChip('Active', 'active'),
              ],
            ),
          ),
          Expanded(
            child: _loading
                ? const SyloLoader(message: 'Loading ride history…')
                : _error != null
                    ? SyloError(message: _error!, onRetry: _loadAll)
                    : _userRole == 'driver'
                        ? TabBarView(
                            controller: _tabCtrl,
                            children: [
                              _buildPassengerList(theme),
                              _buildDriverList(theme),
                            ],
                          )
                        : _buildPassengerList(theme),
          ),
        ],
      ),
    );
  }

  Widget _filterChip(String label, String value) {
    final selected = _filter == value;
    return ChoiceChip(
      label: Text(label),
      selected: selected,
      selectedColor: AppColors.primary.withValues(alpha: 0.18),
      onSelected: (_) {
        setState(() => _filter = value);
        _loadAll();
      },
    );
  }

  Widget _buildPassengerList(ThemeData theme) {
    if (_passengerRides.isEmpty) {
      return const SyloEmpty(
        icon: Icons.history_rounded,
        title: 'No rides yet',
        subtitle: 'Your ride history will appear here.',
      );
    }

    return RefreshIndicator(
      color: AppColors.primary,
      onRefresh: _loadAll,
      child: ListView.separated(
        padding: const EdgeInsets.all(AppConstants.paddingMedium),
        itemCount: _passengerRides.length,
        separatorBuilder: (_, __) => const SizedBox(height: 10),
        itemBuilder: (context, index) {
          final b = _passengerRides[index];
          final ride = b.ride;
          return RideCard(
            from: ride?.origin ?? 'Unknown',
            to: ride?.destination ?? 'Unknown',
            subtitle: _formatBookingTime(b.bookingTime),
            status: b.effectiveDisplayStatus,
            statusColor: _statusColor(b.effectiveDisplayStatus),
            price: '₨ ${b.totalPrice.toStringAsFixed(0)}',
            onTap: () {
              Navigator.pushNamed(
                context,
                '/ride-detail',
                arguments: b.rideId,
              );
            },
          );
        },
      ),
    );
  }

  Widget _buildDriverList(ThemeData theme) {
    if (_driverRides.isEmpty) {
      return const SyloEmpty(
        icon: Icons.drive_eta_rounded,
        title: 'No driver rides',
        subtitle: 'Rides you\'ve created will appear here.',
      );
    }

    return RefreshIndicator(
      color: AppColors.primary,
      onRefresh: _loadAll,
      child: ListView.separated(
        padding: const EdgeInsets.all(AppConstants.paddingMedium),
        itemCount: _driverRides.length,
        separatorBuilder: (_, __) => const SizedBox(height: 10),
        itemBuilder: (context, index) {
          final r = _driverRides[index];
          return RideCard(
            from: r.origin,
            to: r.destination,
            subtitle: _formatDeparture(r.departureTime),
            status: r.effectiveDisplayStatus,
            statusColor: _statusColor(r.status),
            price: '₨ ${r.totalEarnings.toStringAsFixed(0)}',
            onTap: () {
              Navigator.pushNamed(
                context,
                '/ride-detail',
                arguments: r.id,
              );
            },
          );
        },
      ),
    );
  }

  String _formatBookingTime(String? time) {
    if (time == null) return '';
    final dt = DateTime.tryParse(time);
    if (dt == null) return time;
    return '${dt.day}/${dt.month}/${dt.year} ${dt.hour}:${dt.minute.toString().padLeft(2, '0')}';
  }

  String _formatDeparture(String? time) {
    if (time == null) return '';
    final dt = DateTime.tryParse(time);
    if (dt == null) return time;
    return '${dt.day}/${dt.month}/${dt.year} ${dt.hour}:${dt.minute.toString().padLeft(2, '0')}';
  }
}
