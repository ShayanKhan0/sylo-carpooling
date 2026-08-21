import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../../core/services/admin_sos_service.dart';
import '../maps/route_map_widget.dart';

class AdminIncidentDetailScreen extends StatefulWidget {
  final String incidentId;
  final String? sosLabel;

  const AdminIncidentDetailScreen({
    super.key,
    required this.incidentId,
    this.sosLabel,
  });

  @override
  State<AdminIncidentDetailScreen> createState() =>
      _AdminIncidentDetailScreenState();
}

class _AdminIncidentDetailScreenState extends State<AdminIncidentDetailScreen> {
  final AdminSosService _service = AdminSosService();
  Timer? _poll;
  bool _loading = true;
  bool _actionBusy = false;
  Map<String, dynamic>? _detail;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
    _poll = Timer.periodic(const Duration(seconds: 2), (_) => _load());
  }

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }
  String _date(String? iso) {
    if (iso == null || iso.isEmpty) return '-';
    final dt = DateTime.tryParse(iso)?.toLocal();
    if (dt == null) return '-';
    return '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }


  Future<void> _load() async {
    try {
      final detail = await _service.getIncidentDetail(widget.incidentId);
      if (!mounted) return;
      setState(() {
        _detail = detail;
        _loading = false;
        _error = null;
      });
    } on DioException catch (e) {
      final detail = (e.response?.data is Map)
          ? ((e.response?.data['detail'] ??
                  e.response?.data['error']?['detail'] ??
                  e.response?.data['error'])
              ?.toString())
          : null;
      if (!mounted) return;
      setState(() {
        _error = detail?.isNotEmpty == true
            ? detail
            : 'Unable to load SOS detail right now.';
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _runAction(Future<void> Function() action) async {
    setState(() => _actionBusy = true);
    try {
      await action();
      await _load();
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
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.toString())));
    } finally {
      if (mounted) setState(() => _actionBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Incident Detail')),
        body: Center(child: Text(_error!)),
      );
    }

    final data = _detail ?? {};
    final incident = Map<String, dynamic>.from(data['incident'] ?? {});
    final ride = Map<String, dynamic>.from(data['ride'] ?? {});
    final driver = Map<String, dynamic>.from(data['driver'] ?? {});
    final vehicle = Map<String, dynamic>.from(data['vehicle'] ?? {});
    final passengers = List<Map<String, dynamic>>.from(
      ((data['passengers'] ?? []) as List).map((e) => Map<String, dynamic>.from(e)),
    );
    final route = Map<String, dynamic>.from(data['route'] ?? {});
    final isResolved = (incident['resolved_at']?.toString().trim().isNotEmpty ?? false) &&
        incident['resolved_at']?.toString() != '-';
    final stops = List<Map<String, dynamic>>.from(
      ((route['stops'] ?? []) as List).map((e) => Map<String, dynamic>.from(e)),
    );

    final origin = Map<String, dynamic>.from(ride['origin'] ?? {});
    final destination = Map<String, dynamic>.from(ride['destination'] ?? {});
    final originLat = (origin['lat'] as num?)?.toDouble();
    final originLng = (origin['lng'] as num?)?.toDouble();
    final destLat = (destination['lat'] as num?)?.toDouble();
    final destLng = (destination['lng'] as num?)?.toDouble();
    final polyline = ride['polyline']?.toString();

    final extraMarkers = <RouteMapMarkerData>[];
    for (final stop in stops) {
      final lat = (stop['lat'] as num?)?.toDouble();
      final lng = (stop['lng'] as num?)?.toDouble();
      if (lat == null || lng == null) continue;
      extraMarkers.add(
        RouteMapMarkerData(
          id: '${stop['type']}-${stop['booking_id']}',
          position: LatLng(lat, lng),
          title: '${stop['type']} (${stop['booking_id'] ?? ''})',
          snippet: stop['address']?.toString(),
          markerColor:
              stop['type'] == 'pickup' ? Colors.orangeAccent : Colors.lightBlueAccent,
          isPassengerStop: true,
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.sosLabel ?? 'SOS'),
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.all(12),
          children: [
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Ride ID: ${incident['ride_id'] ?? '-'}'),
                    Text('Description: ${incident['description'] ?? '-'}'),
                    Text('Detected At: ${_date(incident['detected_at']?.toString())}'),
                    Text('Resolved At: ${_date(incident['resolved_at']?.toString())}'),
                  ],
                ),
              ),
            ),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Driver',
                        style: TextStyle(fontWeight: FontWeight.w700)),
                    Text('Name: ${driver['name'] ?? '-'}'),
                    Text('Email: ${driver['email'] ?? '-'}'),
                    Text('Phone: ${driver['phone'] ?? '-'}'),
                    const SizedBox(height: 8),
                    const Text('Vehicle',
                        style: TextStyle(fontWeight: FontWeight.w700)),
                    Text('Make/Model: ${vehicle['make'] ?? '-'} ${vehicle['model'] ?? ''}'),
                    Text('Plate: ${vehicle['plate_number'] ?? '-'}'),
                  ],
                ),
              ),
            ),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Passengers (${passengers.length})',
                        style: const TextStyle(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 6),
                    ...passengers.map(
                      (p) => Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Text(
                          '${p['name'] ?? '-'} | ${p['phone'] ?? '-'} | ${p['email'] ?? '-'}\n'
                          'Pickup: ${p['pickup_address'] ?? '-'}\n'
                          'Drop-off: ${p['dropoff_address'] ?? '-'}',
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            if (originLat != null &&
                originLng != null &&
                destLat != null &&
                destLng != null)
              RouteMapWidget(
                origin: LatLng(originLat, originLng),
                destination: LatLng(destLat, destLng),
                originLabel: 'Ride Start',
                destinationLabel: 'Ride End',
                encodedPolyline: polyline,
                extraMarkers: extraMarkers,
                showAlternatives: false,
                showInfoCard: true,
                height: 320,
              ),
            if (!isResolved) ...[
              const SizedBox(height: 12),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _actionBusy
                      ? null
                      : () => _runAction(() async {
                            await _service.resolve(widget.incidentId);
                            if (!mounted) return;
                            Navigator.of(context).pop();
                          }),
                  child: const Text('Resolve'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
