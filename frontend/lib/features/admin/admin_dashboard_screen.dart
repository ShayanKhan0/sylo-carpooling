import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../../core/services/admin_auth_service.dart';
import '../../core/services/admin_sos_service.dart';

class AdminDashboardScreen extends StatefulWidget {
  const AdminDashboardScreen({super.key});

  @override
  State<AdminDashboardScreen> createState() => _AdminDashboardScreenState();
}

class _AdminDashboardScreenState extends State<AdminDashboardScreen> {
  final AdminSosService _service = AdminSosService();
  final AdminAuthService _auth = AdminAuthService();
  Timer? _pollTimer;
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _active = const [];
  List<Map<String, dynamic>> _history = const [];

  @override
  void initState() {
    super.initState();
    _refresh();
    _pollTimer = Timer.periodic(const Duration(seconds: 2), (_) => _refresh());
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    try {
      final active = await _service.getActiveIncidents();
      final historyRide = await _service.getHistoryIncidents();
      final mergedHistory = <Map<String, dynamic>>[
        ...historyRide.map((e) => {...e, 'history_type': 'ride'}),
      ];
      mergedHistory.sort((a, b) {
        final ad = DateTime.tryParse((a['resolved_at'] ?? a['detected_at'] ?? '').toString()) ??
            DateTime.fromMillisecondsSinceEpoch(0);
        final bd = DateTime.tryParse((b['resolved_at'] ?? b['detected_at'] ?? '').toString()) ??
            DateTime.fromMillisecondsSinceEpoch(0);
        return bd.compareTo(ad);
      });
      if (!mounted) return;
      setState(() {
        _active = active;
        _history = mergedHistory;
        _loading = false;
        _error = null;
      });
    } on DioException catch (e) {
      if (!mounted) return;
      final status = e.response?.statusCode;
      if (status == 401 || status == 403) {
        _auth.logout();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Admin session expired. Please sign in again.'),
            behavior: SnackBarBehavior.floating,
          ),
        );
        Navigator.of(context).pushReplacementNamed('/admin-signin');
        return;
      }
      setState(() {
        _error = 'Unable to load admin incidents right now.';
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'Unable to load admin incidents right now.';
        _loading = false;
      });
    }
  }

  String _sosLabel(int index, {int? total, bool descending = false}) {
    if (descending && total != null && total > 0) {
      return 'SOS #${total - index}';
    }
    return 'SOS #${index + 1}';
  }

  String _date(String? iso) {
    if (iso == null || iso.isEmpty) return '-';
    final dt = DateTime.tryParse(iso)?.toLocal();
    if (dt == null) return '-';
    return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          automaticallyImplyLeading: false,
          title: const Text('Admin Safety Dashboard'),
          actions: [
            IconButton(
              tooltip: 'Refresh',
              onPressed: _refresh,
              icon: const Icon(Icons.refresh_rounded),
            ),
            IconButton(
              tooltip: 'Logout',
              onPressed: _confirmLogout,
              icon: const Icon(Icons.logout_rounded),
            ),
          ],
          bottom: const TabBar(
            tabs: [
              Tab(text: 'Active Ride SOS'),
              Tab(text: 'History'),
            ],
          ),
        ),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(child: Text(_error!))
                : TabBarView(
                    children: [
                      _buildList(_active, isActiveRide: true),
                      _buildList(_history, isActiveRide: false),
                    ],
                  ),
      ),
    );
  }

  Future<void> _confirmLogout() async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Log out?'),
        content: const Text('Are you sure you want to log out from admin panel?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Log out'),
          ),
        ],
      ),
    );
    if (yes != true || !mounted) return;
    _auth.logout();
    Navigator.of(context).pushReplacementNamed('/admin-signin');
  }

  Future<void> _resolveRideSos(String incidentId) async {
    try {
      await _service.resolve(incidentId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('SOS resolved and moved to History.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      await _refresh();
    } on DioException catch (e) {
      final detail = (e.response?.data is Map)
          ? ((e.response?.data['detail'] ??
                  e.response?.data['error']?['detail'] ??
                  e.response?.data['error'])
              ?.toString())
          : null;
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(detail?.isNotEmpty == true
              ? detail!
              : 'Unable to resolve SOS right now.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Unable to resolve SOS right now.'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  Widget _buildList(List<Map<String, dynamic>> items, {required bool isActiveRide}) {
    if (items.isEmpty) {
      return Center(
        child: Text(isActiveRide ? 'No active ride SOS incidents.' : 'No resolved SOS incidents.'),
      );
    }
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView.separated(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(12),
        itemCount: items.length,
        separatorBuilder: (_, __) => const SizedBox(height: 8),
        itemBuilder: (context, i) {
          final item = items[i];
          final incidentId = item['incident_id']?.toString() ?? '';
          final label = _sosLabel(
            i,
            total: items.length,
            descending: !isActiveRide,
          );
          final senderRole = (item['sender_role']?.toString().trim().isNotEmpty ?? false)
              ? item['sender_role'].toString().trim()
              : null;
          final statusText = isActiveRide
              ? 'ACTIVE RIDE SOS'
                  : 'RESOLVED RIDE SOS';
          return InkWell(
            borderRadius: BorderRadius.circular(20),
            onTap: (incidentId.isEmpty)
                ? null
                : () async {
                    await Navigator.of(context).pushNamed(
                      '/admin-incident-detail',
                      arguments: {
                        'incidentId': incidentId,
                        'sosLabel': label,
                      },
                    );
                    _refresh();
                  },
            child: Container(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(20),
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [Color(0xFF032F2A), Color(0xFF073F37)],
                ),
                border: Border.all(color: const Color(0xFF2BC89A).withValues(alpha: 0.35)),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 40,
                    height: 40,
                    decoration: BoxDecoration(
                      color: const Color(0xFF0A5D50),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: const Icon(Icons.directions_car_filled_rounded,
                        color: Color(0xFF8CF8D1)),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                senderRole != null ? '$label ($senderRole)' : label,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 16,
                                ),
                              ),
                            ),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: 0.12),
                                borderRadius: BorderRadius.circular(999),
                              ),
                              child: Text(
                                statusText,
                                style: const TextStyle(
                                  color: Color(0xFF9EF8D7),
                                  fontSize: 11,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'Ride: ${item['ride_id'] ?? '-'}',
                          style: const TextStyle(color: Color(0xFFAFF9DF)),
                        ),
                        Text(
                          'Created: ${_date(item['detected_at']?.toString())}',
                          style: const TextStyle(color: Color(0xFFAFF9DF)),
                        ),
                        if (isActiveRide && incidentId.isNotEmpty)
                          Padding(
                            padding: const EdgeInsets.only(top: 10),
                            child: SizedBox(
                              width: double.infinity,
                              child: ElevatedButton(
                                onPressed: () => _resolveRideSos(incidentId),
                                child: const Text('Resolve'),
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                  const Padding(
                    padding: EdgeInsets.only(left: 6),
                    child: Icon(Icons.chevron_right_rounded, color: Color(0xFF9EF8D7)),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
