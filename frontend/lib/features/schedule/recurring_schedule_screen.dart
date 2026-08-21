import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import '../../core/services/schedule_service.dart';
import '../../core/services/ride_service.dart';
import '../../core/services/maps_service.dart';
import '../../core/utils/fare_calculator.dart';
import '../../core/theme/app_colors.dart';
import '../../core/constants/app_constants.dart';
import '../dashboard/home_design_system.dart';
import '../maps/location_picker_screen.dart';
import '../maps/place_search_field.dart';
import '../maps/dual_location_picker_screen.dart';
import '../maps/route_map_widget.dart';

class RecurringScheduleScreen extends StatefulWidget {
  const RecurringScheduleScreen({
    super.key,
    this.initialOrigin,
    this.initialDestination,
    this.onBackToMap,
  });

  final PickedLocation? initialOrigin;
  final PickedLocation? initialDestination;
  final VoidCallback? onBackToMap;

  @override
  State<RecurringScheduleScreen> createState() =>
      _RecurringScheduleScreenState();
}

class _RecurringScheduleScreenState extends State<RecurringScheduleScreen> {
  static const Color _flowCard = Color(0xFFD9FCE8);
  static const Color _flowBorder = Color(0xFF5DAA7E);
  final ScheduleService _scheduleService = ScheduleService();
  final RideService _rideService = RideService();
  final MapsService _mapsService = MapsService();
  final _formKey = GlobalKey<FormState>();

  // Form fields
  TimeOfDay _rideTime = const TimeOfDay(hour: 8, minute: 0);
  final TextEditingController _seatsController =
      TextEditingController(text: '3');
  final TextEditingController _priceController = TextEditingController();
  DateTime _startDate = DateTime.now();
  DateTime _endDate = DateTime.now().add(const Duration(days: 90));

  // Location
  double? _startLat, _startLng, _endLat, _endLng;
  String _startAddress = '';
  String _endAddress = '';
  bool _showStartLocationError = false;
  bool _showEndLocationError = false;

  // Fare estimation
  Map<String, dynamic>? _fareEstimate;
  bool _fareLoading = false;
  double? _routeDistanceKm;

  // State
  bool _isSubmitting = false;
  List<Map<String, dynamic>> _existingSchedules = [];
  bool _loadingSchedules = true;
  bool _loadingOccupiedSlots = false;
  bool _showSlotConflictError = false;
  List<Map<String, dynamic>> _occupiedSlots = [];

  int _slotsRequestVersion = 0;

  static const _allDays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  ThemeData _flowTheme(BuildContext context) {
    final base = Theme.of(context);
    return base.copyWith(
      textTheme: GoogleFonts.interTextTheme(base.textTheme).apply(
        bodyColor: const Color(0xFF0B3D24),
        displayColor: const Color(0xFF0B3D24),
      ),
      listTileTheme: const ListTileThemeData(
        textColor: Color(0xFF0B3D24),
        iconColor: Color(0xFF0B3D24),
      ),
      appBarTheme: base.appBarTheme.copyWith(
        foregroundColor: const Color(0xFF0B3D24),
        titleTextStyle: GoogleFonts.inter(
          fontSize: 24,
          fontWeight: FontWeight.w900,
          color: const Color(0xFF0B3D24),
        ),
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _applyInitialLocations();
    _loadExistingSchedules();
    _loadOccupiedSlotsForStartDate();
    if (_hasValidStartLocation && _hasValidEndLocation) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        _recalcFare();
      });
    }
  }

  @override
  void dispose() {
    _seatsController.dispose();
    _priceController.dispose();
    super.dispose();
  }

  Future<void> _loadExistingSchedules() async {
    try {
      final schedules = await _scheduleService.getMySchedules();
      if (mounted) {
        setState(() {
          _existingSchedules = schedules;
          _loadingSchedules = false;
        });
      }
    } catch (_) {
      if (mounted) setState(() => _loadingSchedules = false);
    }
  }

  bool get _hasValidStartLocation =>
      _startLat != null && _startLng != null && _startAddress.trim().isNotEmpty;

  bool get _hasValidEndLocation =>
      _endLat != null && _endLng != null && _endAddress.trim().isNotEmpty;

  void _applyInitialLocations() {
    final origin = widget.initialOrigin;
    final destination = widget.initialDestination;

    if (origin != null) {
      _startLat = origin.latLng.latitude;
      _startLng = origin.latLng.longitude;
      _startAddress = origin.address.trim();
      _showStartLocationError = false;
    }

    if (destination != null) {
      _endLat = destination.latLng.latitude;
      _endLng = destination.latLng.longitude;
      _endAddress = destination.address.trim();
      _showEndLocationError = false;
    }
  }

  void _clearFareState() {
    _fareEstimate = null;
    _fareLoading = false;
    _routeDistanceKm = null;
    _priceController.clear();
  }

  void _onStartLocationTextChanged(String value) {
    final text = value.trim();
    setState(() {
      _startLat = null;
      _startLng = null;
      _startAddress = text;
      if (text.isEmpty) {
        _showStartLocationError = true;
      } else if (_showStartLocationError) {
        _showStartLocationError = false;
      }
      _clearFareState();
    });
  }

  void _onEndLocationTextChanged(String value) {
    final text = value.trim();
    setState(() {
      _endLat = null;
      _endLng = null;
      _endAddress = text;
      if (text.isEmpty) {
        _showEndLocationError = true;
      } else if (_showEndLocationError) {
        _showEndLocationError = false;
      }
      _clearFareState();
    });
  }

  /// Called whenever both locations are set OR seats change.
  /// Fetches route distance then calls the backend fare calculator.
  Future<void> _recalcFare() async {
    if (!_hasValidStartLocation || !_hasValidEndLocation) {
      if (_fareEstimate != null ||
          _fareLoading ||
          _routeDistanceKm != null ||
          _priceController.text.isNotEmpty) {
        if (mounted) {
          setState(_clearFareState);
        } else {
          _clearFareState();
        }
      }
      return;
    }
    if (mounted) {
      setState(() {
        _fareLoading = true;
        _fareEstimate = null;
      });
    }

    try {
      final dirs = await _mapsService.getDirections(
        origin: LatLng(_startLat!, _startLng!),
        destination: LatLng(_endLat!, _endLng!),
      );

      if (dirs?.bestRoute == null) {
        if (mounted) setState(() => _fareLoading = false);
        return;
      }

      _routeDistanceKm = dirs!.bestRoute!.distanceKm;
      final seats = (int.tryParse(_seatsController.text) ?? 3).clamp(1, 8);

      Map<String, dynamic>? fareData;
      try {
        fareData = await _rideService.getFareEstimate(
          distanceKm: _routeDistanceKm!,
          durationMinutes: dirs.bestRoute!.durationMinutes.toDouble(),
          totalSeats: seats,
        );
      } catch (_) {
        // Fallback to local calculator if backend unreachable
        final est = FareCalculator.estimate(
          distanceKm: _routeDistanceKm!,
          durationMinutes: dirs.bestRoute!.durationMinutes.toDouble(),
          totalSeats: seats,
        );
        fareData = {
          'distance_km': est.distanceKm,
          'total_seats': est.totalSeats,
          'fuel_cost_raw': est.fuelCostRaw,
          'time_cost': est.timeCost,
          'duration_minutes': est.durationMinutes,
          'base_fare': est.baseFare,
          'platform_fee': est.platformFee,
          'total_fare': est.totalFare,
          'fare_per_seat': est.farePerSeat,
          'markup_percent': FareCalculator.platformMarkup * 100,
          'petrol_price': FareCalculator.petrolPricePerLitre,
          'fuel_average': FareCalculator.fuelAverageKmPerLitre,
        };
      }

      if (mounted) {
        setState(() {
          _fareEstimate = fareData;
          _fareLoading = false;
        });
        // Auto-fill price field from backend estimate (authoritative)
        final perSeat = fareData['fare_per_seat'];
        if (perSeat != null) {
          _priceController.text = (perSeat is double)
              ? perSeat.toStringAsFixed(0)
              : perSeat.toString();
        }
      }
    } catch (_) {
      if (mounted) setState(() => _fareLoading = false);
    }
  }

  Future<void> _recalcFareForRoute({
    required double distanceKm,
    required double durationMinutes,
  }) async {
    final seats = (int.tryParse(_seatsController.text) ?? 3).clamp(1, 8);
    if (mounted) {
      setState(() {
        _fareLoading = true;
      });
    }

    try {
      Map<String, dynamic>? fareData;
      try {
        fareData = await _rideService.getFareEstimate(
          distanceKm: distanceKm,
          durationMinutes: durationMinutes,
          totalSeats: seats,
        );
      } catch (_) {
        final est = FareCalculator.estimate(
          distanceKm: distanceKm,
          durationMinutes: durationMinutes,
          totalSeats: seats,
        );
        fareData = {
          'distance_km': est.distanceKm,
          'total_seats': est.totalSeats,
          'fuel_cost_raw': est.fuelCostRaw,
          'time_cost': est.timeCost,
          'duration_minutes': est.durationMinutes,
          'base_fare': est.baseFare,
          'platform_fee': est.platformFee,
          'total_fare': est.totalFare,
          'fare_per_seat': est.farePerSeat,
          'markup_percent': FareCalculator.platformMarkup * 100,
          'petrol_price': FareCalculator.petrolPricePerLitre,
          'fuel_average': FareCalculator.fuelAverageKmPerLitre,
        };
      }

      if (!mounted) return;
      setState(() {
        _routeDistanceKm = distanceKm;
        _fareEstimate = fareData;
        _fareLoading = false;
      });
      final perSeat = fareData['fare_per_seat'];
      if (perSeat != null) {
        _priceController.text = (perSeat is double)
            ? perSeat.toStringAsFixed(0)
            : perSeat.toString();
      }
    } catch (_) {
      if (mounted) setState(() => _fareLoading = false);
    }
  }

  int _selectedRideDurationMinutes() {
    final durationRaw = _fareEstimate?['duration_minutes'];
    if (durationRaw is num && durationRaw > 0) {
      return durationRaw.round();
    }
    return 60;
  }

  DateTime _selectedWindowStartDateTimeForStartDay() {
    return DateTime(
      _startDate.year,
      _startDate.month,
      _startDate.day,
      _rideTime.hour,
      _rideTime.minute,
    );
  }

  DateTime _selectedWindowEndDateTimeForStartDay() {
    return _selectedWindowStartDateTimeForStartDay().add(
      Duration(minutes: _selectedRideDurationMinutes()),
    );
  }

  bool _slotConflictsWithSelectedStartDayWindow(Map<String, dynamic> slot) {
    final startRaw = slot['start_time']?.toString();
    final endRaw = slot['end_time']?.toString();
    final slotStart = startRaw != null ? DateTime.tryParse(startRaw) : null;
    final slotEnd = endRaw != null ? DateTime.tryParse(endRaw) : null;
    if (slotStart == null || slotEnd == null) return false;

    final selectedStartUtc = _selectedWindowStartDateTimeForStartDay().toUtc();
    final selectedEndUtc = _selectedWindowEndDateTimeForStartDay().toUtc();

    return selectedStartUtc.isBefore(slotEnd) &&
        selectedEndUtc.isAfter(slotStart);
  }

  String _formatSlotTime(DateTime dt) {
    final local = dt.toLocal();
    final h = local.hour;
    final m = local.minute.toString().padLeft(2, '0');
    final period = h >= 12 ? 'PM' : 'AM';
    final h12 = h > 12 ? h - 12 : (h == 0 ? 12 : h);
    return '$h12:$m $period';
  }

  String _slotSourceLabel(Map<String, dynamic> slot) {
    final source = (slot['source']?.toString() ?? '').toLowerCase();
    if (source.contains('driver')) return 'Driver Ride';
    if (source.contains('booking')) return 'Passenger Booking';
    if (source.contains('request')) return 'Ride Request';
    return 'Occupied Slot';
  }

  String _dateKeyLocal(DateTime dt) {
    final m = dt.month.toString().padLeft(2, '0');
    final d = dt.day.toString().padLeft(2, '0');
    return '${dt.year}-$m-$d';
  }

  String _dateKeyUtc(DateTime dt) {
    final utc = dt.toUtc();
    final m = utc.month.toString().padLeft(2, '0');
    final d = utc.day.toString().padLeft(2, '0');
    return '${utc.year}-$m-$d';
  }

  List<Map<String, dynamic>> _mergeSlotsByWindow(
    List<Map<String, dynamic>> first,
    List<Map<String, dynamic>> second,
  ) {
    final merged = <Map<String, dynamic>>[];
    final seen = <String>{};
    for (final slot in [...first, ...second]) {
      final key =
          '${slot['source'] ?? ''}|${slot['entity_id'] ?? ''}|${slot['start_time'] ?? ''}|${slot['end_time'] ?? ''}';
      if (seen.add(key)) {
        merged.add(slot);
      }
    }
    return merged;
  }

  List<Map<String, dynamic>> _slotsForSelectedLocalDay(
    List<Map<String, dynamic>> slots,
    DateTime selectedDay,
  ) {
    final dayStartLocal = DateTime(
      selectedDay.year,
      selectedDay.month,
      selectedDay.day,
    );
    final dayEndLocal = dayStartLocal.add(const Duration(days: 1));

    return slots.where((slot) {
      final startRaw = slot['start_time']?.toString();
      final endRaw = slot['end_time']?.toString();
      final slotStartUtc =
          startRaw != null ? DateTime.tryParse(startRaw) : null;
      final slotEndUtc = endRaw != null ? DateTime.tryParse(endRaw) : null;
      if (slotStartUtc == null || slotEndUtc == null) return false;

      final slotStartLocal = slotStartUtc.toLocal();
      final slotEndLocal = slotEndUtc.toLocal();
      return slotStartLocal.isBefore(dayEndLocal) &&
          slotEndLocal.isAfter(dayStartLocal);
    }).toList();
  }

  Future<void> _loadOccupiedSlotsForStartDate() async {
    final requestVersion = ++_slotsRequestVersion;
    setState(() {
      _loadingOccupiedSlots = true;
      _showSlotConflictError = false;
    });

    try {
      final selectedDate =
          DateTime(_startDate.year, _startDate.month, _startDate.day);
      final timezoneOffsetMinutes = selectedDate.timeZoneOffset.inMinutes;
      final localDateKey = _dateKeyLocal(selectedDate);
      final utcDateKey = _dateKeyUtc(selectedDate);

      var slots = await _rideService.getMyOccupiedSlots(
        targetDate: localDateKey,
        mode: 'driver',
        timezoneOffsetMinutes: timezoneOffsetMinutes,
      );
      slots = _slotsForSelectedLocalDay(slots, selectedDate);

      if (slots.isEmpty && localDateKey != utcDateKey) {
        final utcSlots = await _rideService.getMyOccupiedSlots(
          targetDate: utcDateKey,
          mode: 'driver',
        );
        slots = _slotsForSelectedLocalDay(
          _mergeSlotsByWindow(slots, utcSlots),
          selectedDate,
        );
      }

      if (!mounted || requestVersion != _slotsRequestVersion) return;

      setState(() {
        _occupiedSlots = slots;
        _loadingOccupiedSlots = false;
      });
    } catch (_) {
      if (!mounted || requestVersion != _slotsRequestVersion) return;

      setState(() {
        _occupiedSlots = [];
        _loadingOccupiedSlots = false;
      });
    }
  }

  Future<void> _pickTime() async {
    final picked = await showTimePicker(
      context: context,
      initialTime: _rideTime,
    );
    if (picked != null) {
      setState(() {
        _rideTime = picked;
        _showSlotConflictError = false;
      });
    }
  }

  Future<void> _pickDate(bool isStart) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: isStart ? _startDate : _endDate,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked != null) {
      setState(() {
        if (isStart) {
          _startDate = picked;
          if (_endDate.isBefore(_startDate)) {
            _endDate = _startDate.add(const Duration(days: 30));
          }
          _showSlotConflictError = false;
        } else {
          _endDate = picked;
        }
      });
      if (isStart) {
        _loadOccupiedSlotsForStartDate();
      }
    }
  }

  Future<void> _submitSchedule() async {
    if (!_formKey.currentState!.validate()) return;
    if (!_hasValidStartLocation || !_hasValidEndLocation) {
      setState(() {
        _showStartLocationError = !_hasValidStartLocation;
        _showEndLocationError = !_hasValidEndLocation;
        _clearFareState();
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('Pick both start and destination locations')),
      );
      return;
    }

    if (_loadingOccupiedSlots) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('Checking occupied slots. Please wait...')),
      );
      return;
    }

    final hasSlotConflict =
        _occupiedSlots.any(_slotConflictsWithSelectedStartDayWindow);
    if (hasSlotConflict) {
      setState(() => _showSlotConflictError = true);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
              'Selected departure time overlaps with an occupied slot on From date.'),
          backgroundColor: AppColors.error,
        ),
      );
      return;
    }

    // Ensure fare is computed before submit; backend estimate is authoritative.
    if (_fareEstimate == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Calculating fare, please wait…')),
      );
      await _recalcFare();
      if (_fareEstimate == null) return;
    }

    final backendFarePerSeatRaw = _fareEstimate?['fare_per_seat'];
    final backendFarePerSeat = backendFarePerSeatRaw is num
        ? backendFarePerSeatRaw.toDouble()
        : double.tryParse(backendFarePerSeatRaw?.toString() ?? '');
    if (backendFarePerSeat == null || backendFarePerSeat <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Unable to calculate fare from backend')),
      );
      return;
    }

    setState(() => _isSubmitting = true);

    try {
      await _scheduleService.createSchedule(
        daysOfWeek: _allDays,
        rideTime:
            '${_rideTime.hour.toString().padLeft(2, '0')}:${_rideTime.minute.toString().padLeft(2, '0')}:00',
        startLat: _startLat!,
        startLng: _startLng!,
        startAddress: _startAddress,
        endLat: _endLat!,
        endLng: _endLng!,
        endAddress: _endAddress,
        seatsOffered: int.tryParse(_seatsController.text) ?? 3,
        startDate:
            '${_startDate.year}-${_startDate.month.toString().padLeft(2, '0')}-${_startDate.day.toString().padLeft(2, '0')}',
        endDate:
            '${_endDate.year}-${_endDate.month.toString().padLeft(2, '0')}-${_endDate.day.toString().padLeft(2, '0')}',
        basePrice: backendFarePerSeat,
      );

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Schedule created successfully!'),
            backgroundColor: AppColors.success,
          ),
        );
        _loadExistingSchedules();
        _resetForm();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text(
                  'Failed to create schedule: $e\nData: ${(e is DioException) ? e.response?.data : ""}')),
        );
      }
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  void _resetForm() {
    setState(() {
      _rideTime = const TimeOfDay(hour: 8, minute: 0);
      _seatsController.text = '3';
      _priceController.clear();
      _startLat = null;
      _startLng = null;
      _startAddress = '';
      _endLat = null;
      _endLng = null;
      _endAddress = '';
      _showStartLocationError = false;
      _showEndLocationError = false;
      _fareEstimate = null;
      _fareLoading = false;
      _routeDistanceKm = null;
      _occupiedSlots = [];
      _showSlotConflictError = false;
    });
    _loadOccupiedSlotsForStartDate();
  }

  // ── helpers ──────────────────────────────────────────
  String _fmtNum(dynamic v, {int dec = 0}) {
    if (v == null) return '0';
    final d = (v is num) ? v.toDouble() : double.tryParse(v.toString()) ?? 0.0;
    return dec > 0 ? d.toStringAsFixed(dec) : d.toStringAsFixed(0);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Theme(
      data: _flowTheme(context),
      child: Scaffold(
      backgroundColor: Colors.transparent,
      appBar: AppBar(
        leading: widget.onBackToMap != null
            ? IconButton(
                icon: const Icon(Icons.arrow_back_rounded),
                onPressed: widget.onBackToMap,
                tooltip: 'Back to map',
              )
            : null,
        title: const Text('Recurring Rides'),
        elevation: 0,
      ),
      body: Stack(
        children: [
          HomeDesignSystem.driverHomeSoftWhiteBackground(),
          Container(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
            decoration: const BoxDecoration(
              color: Color(0xFFD9FCE8),
              borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
            ),
            child: Theme(
              data: Theme.of(context).copyWith(
              inputDecorationTheme: InputDecorationTheme(
                filled: true,
                fillColor: const Color(0xFFE9FFF2),
                labelStyle: const TextStyle(
                  color: Color(0xFF114B2D),
                  fontWeight: FontWeight.w700,
                ),
                hintStyle: TextStyle(
                  color: const Color(0xFF114B2D).withValues(alpha: 0.72),
                  fontWeight: FontWeight.w600,
                ),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: const BorderSide(color: Color(0xFF5DAA7E)),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: const BorderSide(color: Color(0xFF5DAA7E)),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(14),
                  borderSide: const BorderSide(
                    color: Color(0xFF1D6F38),
                    width: 1.4,
                  ),
                ),
              ),
            ),
              child: SingleChildScrollView(
              padding: EdgeInsets.zero,
              child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ── Existing schedules ───────────────────────────
              if (_loadingSchedules)
                const Center(
                    child: Padding(
                  padding: EdgeInsets.all(16),
                  child: CircularProgressIndicator(),
                ))
              else if (_existingSchedules.isNotEmpty) ...[
                Text('Active Schedules',
                    style: theme.textTheme.titleMedium
                        ?.copyWith(fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                ..._existingSchedules.map((s) => _buildScheduleCard(s, theme)),
                const Divider(height: 32),
              ],

              // ── Route preview (selectable alternatives) ──────
              if (_hasValidStartLocation && _hasValidEndLocation)
                Padding(
                  padding: const EdgeInsets.only(bottom: 14),
                  child: RouteMapWidget(
                    origin: LatLng(_startLat!, _startLng!),
                    destination: LatLng(_endLat!, _endLng!),
                    originLabel: _startAddress,
                    destinationLabel: _endAddress,
                    height: 300,
                    showAlternatives: true,
                    interactive: true,
                    showInfoCard: true,
                    onRouteSelected: (route) {
                      _recalcFareForRoute(
                        distanceKm: route.distanceKm,
                        durationMinutes: route.durationMinutes.toDouble(),
                      );
                    },
                  ),
                ),

              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: _flowCard,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: _flowBorder),
                ),
                child: const Text(
                  'Recurring rides are applied daily between From and Until dates.',
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                ),
              ),
              const SizedBox(height: 16),

              // Time picker
              ListTile(
                contentPadding: EdgeInsets.zero,
                leading: const Icon(Icons.access_time_rounded,
                    color: AppColors.primary),
                title: const Text('Departure Time'),
                subtitle: Text(_rideTime.format(context)),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: _pickTime,
              ),
              const Divider(),
              const SizedBox(height: 8),

              // ── Start location ───────────────────────────────
              AnimatedContainer(
                duration: const Duration(milliseconds: 150),
                decoration: BoxDecoration(
                  borderRadius:
                      BorderRadius.circular(AppConstants.radiusMedium),
                  border: Border.all(
                    color: _showStartLocationError
                        ? AppColors.error
                        : Colors.transparent,
                    width: _showStartLocationError ? 1.5 : 0,
                  ),
                ),
                child: PlaceSearchField(
                  hint: 'Start Location – type to search or tap map',
                  dotColor: AppColors.success,
                  textColor: const Color(0xFF1F6F4B),
                  hintColor: const Color(0xFF114B2D).withValues(alpha: 0.7),
                  mapIconColor: const Color(0xFF0B3D24),
                  backgroundColor: const Color(0xFFE9FFF2),
                  borderColor: const Color(0xFF5DAA7E),
                  value: _startLat != null
                      ? PickedLocation(
                          latLng: LatLng(_startLat!, _startLng!),
                          address: _startAddress,
                        )
                      : null,
                  onTextChanged: _onStartLocationTextChanged,
                  onPlaceSelected: (place) {
                    setState(() {
                      _startLat = place.latLng.latitude;
                      _startLng = place.latLng.longitude;
                      _startAddress = place.address.trim();
                      _showStartLocationError = false;
                    });
                    _recalcFare();
                  },
                ),
              ),
              if (_showStartLocationError)
                const Padding(
                  padding: EdgeInsets.only(left: 12, top: 6),
                  child: Text(
                    'Start location is required',
                    style: TextStyle(color: AppColors.error, fontSize: 12),
                  ),
                ),
              const SizedBox(height: 10),

              // ── End location ─────────────────────────────────
              AnimatedContainer(
                duration: const Duration(milliseconds: 150),
                decoration: BoxDecoration(
                  borderRadius:
                      BorderRadius.circular(AppConstants.radiusMedium),
                  border: Border.all(
                    color: _showEndLocationError
                        ? AppColors.error
                        : Colors.transparent,
                    width: _showEndLocationError ? 1.5 : 0,
                  ),
                ),
                child: PlaceSearchField(
                  hint: 'Destination – type to search or tap map',
                  dotColor: AppColors.error,
                  textColor: const Color(0xFF1F6F4B),
                  hintColor: const Color(0xFF114B2D).withValues(alpha: 0.7),
                  mapIconColor: const Color(0xFF0B3D24),
                  backgroundColor: const Color(0xFFE9FFF2),
                  borderColor: const Color(0xFF5DAA7E),
                  value: _endLat != null
                      ? PickedLocation(
                          latLng: LatLng(_endLat!, _endLng!),
                          address: _endAddress,
                        )
                      : null,
                  onTextChanged: _onEndLocationTextChanged,
                  onPlaceSelected: (place) {
                    setState(() {
                      _endLat = place.latLng.latitude;
                      _endLng = place.latLng.longitude;
                      _endAddress = place.address.trim();
                      _showEndLocationError = false;
                    });
                    _recalcFare();
                  },
                ),
              ),
              if (_showEndLocationError)
                const Padding(
                  padding: EdgeInsets.only(left: 12, top: 6),
                  child: Text(
                    'Destination is required',
                    style: TextStyle(color: AppColors.error, fontSize: 12),
                  ),
                ),
              const SizedBox(height: 10),

              // ── Or pick both on map ──────────────────────────
              OutlinedButton.icon(
                onPressed: () async {
                  final result = await Navigator.push<DualPickResult>(
                    context,
                    MaterialPageRoute(
                      builder: (_) => DualLocationPickerScreen(
                        initialOrigin: _startLat != null
                            ? PickedLocation(
                                latLng: LatLng(_startLat!, _startLng!),
                                address: _startAddress,
                              )
                            : null,
                        initialDestination: _endLat != null
                            ? PickedLocation(
                                latLng: LatLng(_endLat!, _endLng!),
                                address: _endAddress,
                              )
                            : null,
                      ),
                    ),
                  );
                  if (result != null) {
                    setState(() {
                      if (result.origin != null) {
                        _startLat = result.origin!.latLng.latitude;
                        _startLng = result.origin!.latLng.longitude;
                        _startAddress = result.origin!.address.trim();
                        _showStartLocationError = false;
                      }
                      if (result.destination != null) {
                        _endLat = result.destination!.latLng.latitude;
                        _endLng = result.destination!.latLng.longitude;
                        _endAddress = result.destination!.address.trim();
                        _showEndLocationError = false;
                      }
                    });
                    _recalcFare();
                  }
                },
                icon: const Icon(Icons.map_rounded, size: 18),
                label: const Text('Pick Both on Map'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.primary,
                  side: BorderSide(
                      color: AppColors.primary.withValues(alpha: 0.5)),
                  minimumSize: const Size(double.infinity, 44),
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12)),
                ),
              ),
              const SizedBox(height: 16),

              // ── Seats ────────────────────────────────────────
              TextFormField(
                controller: _seatsController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  labelText: 'Seats Offered',
                  prefixIcon: Icon(Icons.event_seat_rounded),
                  border: OutlineInputBorder(),
                ),
                onChanged: (_) => _recalcFare(),
                validator: (v) {
                  final n = int.tryParse(v ?? '');
                  if (n == null || n < 1 || n > 8) return '1-8 seats';
                  return null;
                },
              ),
              const SizedBox(height: 16),

              // ── Fare Estimate Card ───────────────────────────
              if (_fareLoading)
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: _flowCard,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: _flowBorder),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: AppColors.primary)),
                      const SizedBox(width: 12),
                      Text('Calculating fare…',
                          style: TextStyle(
                              color: AppColors.textSecondary, fontSize: 13)),
                    ],
                  ),
                ),
              if (_fareEstimate != null && !_fareLoading) ...[
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(16),
                  decoration: HomeDesignSystem.darkTopBarSurface(
                    radius: 14,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Row(
                        children: [
                          Icon(Icons.calculate_outlined,
                              size: 18, color: AppColors.primary),
                          SizedBox(width: 8),
                          Text('Fare Estimate (backend)',
                              style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 14,
                                  color: AppColors.primary)),
                        ],
                      ),
                      const SizedBox(height: 12),
                      // Summary row: distance | duration | per seat
                      Row(
                        children: [
                          Expanded(
                              child: _fareChip(
                                  Icons.route_rounded,
                                  AppColors.primary,
                                  '${_fmtNum(_fareEstimate!['distance_km'], dec: 1)} km',
                                  'Distance')),
                          Expanded(
                              child: _fareChip(
                                  Icons.local_gas_station_rounded,
                                  AppColors.secondary,
                                  'Rs ${_fmtNum(_fareEstimate!['fuel_cost_raw'])}',
                                  'Fuel Cost')),
                          Expanded(
                              child: _fareChip(
                                  Icons.payments_rounded,
                                  AppColors.success,
                                  'Rs ${_fmtNum(_fareEstimate!['fare_per_seat'])}',
                                  'Per Seat')),
                        ],
                      ),
                      const SizedBox(height: 10),
                      // Detail breakdown
                      _fareRow('Base fare',
                          'Rs ${_fmtNum(_fareEstimate!['base_fare'])}'),
                      _fareRow('Fuel cost',
                          'Rs ${_fmtNum(_fareEstimate!['fuel_cost_raw'])}'),
                      _fareRow(
                          'Platform fee (${_fmtNum(_fareEstimate!['markup_percent'])}%)',
                          'Rs ${_fmtNum(_fareEstimate!['platform_fee'])}'),
                      const Divider(height: 12),
                      _fareRow('Total trip cost',
                          'Rs ${_fmtNum(_fareEstimate!['total_fare'])}',
                          bold: true),
                      _fareRow(
                          'Per seat (${_fareEstimate!['total_seats']} seats)',
                          'Rs ${_fmtNum(_fareEstimate!['fare_per_seat'])}',
                          bold: true,
                          highlight: true),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Price is auto-set from backend estimate.',
                  style: TextStyle(
                      fontSize: 11,
                      color: AppColors.textSecondary,
                      fontStyle: FontStyle.italic),
                ),
              ],
              const SizedBox(height: 12),

              // ── Price field (editable, auto-filled) ──────────
              TextFormField(
                controller: _priceController,
                readOnly: true,
                keyboardType: TextInputType.number,
                decoration: InputDecoration(
                  labelText: 'Price per Seat (PKR) - Auto',
                  prefixIcon: const Icon(Icons.payments_rounded),
                  border: const OutlineInputBorder(),
                  helperText: _fareEstimate != null
                      ? 'Estimated: Rs ${_fmtNum(_fareEstimate!['fare_per_seat'])}/seat'
                      : 'Will auto-fill after picking locations',
                ),
              ),
              const SizedBox(height: 16),

              // ── Date range ───────────────────────────────────
              Row(
                children: [
                  Expanded(
                    child: _dateTile(
                        'From', _startDate, () => _pickDate(true), theme),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: _dateTile(
                        'Until', _endDate, () => _pickDate(false), theme),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: _flowCard,
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(color: _flowBorder),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.event_busy_rounded,
                            size: 16, color: AppColors.textHint),
                        const SizedBox(width: 8),
                        Text(
                          'Slots Taken',
                          style: TextStyle(
                            color: AppColors.textPrimary,
                            fontWeight: FontWeight.w700,
                            fontSize: 13,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'From date conflict check uses selected departure time and estimated duration.',
                      style: TextStyle(
                        color: AppColors.textSecondary,
                        fontSize: 11,
                      ),
                    ),
                    const SizedBox(height: 8),
                    if (_loadingOccupiedSlots)
                      const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    else if (_occupiedSlots.isEmpty)
                      Text(
                        'No occupied slots on selected From date.',
                        style: TextStyle(
                          color: AppColors.textSecondary,
                          fontSize: 12,
                        ),
                      )
                    else
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: _occupiedSlots.map((slot) {
                          final start = DateTime.tryParse(
                              slot['start_time']?.toString() ?? '');
                          final end = DateTime.tryParse(
                              slot['end_time']?.toString() ?? '');
                          final isConflict =
                              _slotConflictsWithSelectedStartDayWindow(slot);
                          final sourceLabel = _slotSourceLabel(slot);
                          final timeLabel = (start != null && end != null)
                              ? '${_formatSlotTime(start)} - ${_formatSlotTime(end)}'
                              : null;
                          final label = timeLabel == null
                              ? sourceLabel
                              : '$sourceLabel: $timeLabel';
                          return Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 10, vertical: 6),
                            decoration: BoxDecoration(
                              color: isConflict
                                  ? AppColors.error.withValues(alpha: 0.12)
                                  : AppColors.surface,
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(
                                color: isConflict
                                    ? AppColors.error
                                    : AppColors.border,
                              ),
                            ),
                            child: Text(
                              label,
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: isConflict
                                    ? AppColors.error
                                    : AppColors.textPrimary,
                              ),
                            ),
                          );
                        }).toList(),
                      ),
                  ],
                ),
              ),
              if (_showSlotConflictError)
                const Padding(
                  padding: EdgeInsets.only(left: 12, top: 6),
                  child: Text(
                    'Selected departure time overlaps with an occupied slot on From date.',
                    style: TextStyle(color: AppColors.error, fontSize: 12),
                  ),
                ),
              const SizedBox(height: 24),

              // ── Submit ───────────────────────────────────────
              Container(
                width: double.infinity,
                height: 50,
                decoration: HomeDesignSystem.darkTopBarSurface(
                  radius: AppConstants.radiusMedium,
                ),
                child: ElevatedButton.icon(
                  onPressed: _isSubmitting ? null : _submitSchedule,
                  icon: _isSubmitting
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.schedule_rounded),
                  label: Text(
                    _isSubmitting ? 'Creating…' : 'Create Recurring Ride',
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.transparent,
                    foregroundColor: const Color(0xFF43E892),
                    shadowColor: Colors.transparent,
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusMedium),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 32),
            ],
          ),
              ),
            ),
          ),
          ),
        ],
      ),
    ));
  }

  Widget _fareChip(IconData icon, Color color, String value, String label) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(height: 4),
        Text(value,
            style: TextStyle(
                fontWeight: FontWeight.w700,
                fontSize: 13,
                color: Colors.white)),
        Text(label,
            style: TextStyle(
              fontSize: 10,
              color: Colors.white.withValues(alpha: 0.84),
            )),
      ],
    );
  }

  Widget _fareRow(String label, String value,
      {bool bold = false, bool highlight = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label,
              style: TextStyle(
                  fontSize: 12,
                  color: Colors.white.withValues(alpha: 0.86),
                  fontWeight: bold ? FontWeight.w700 : FontWeight.normal)),
          Text(value,
              style: TextStyle(
                  fontSize: 12,
                  fontWeight: bold ? FontWeight.w700 : FontWeight.w500,
                  color:
                      highlight ? AppColors.primary : Colors.white)),
        ],
      ),
    );
  }

  Widget _dateTile(
      String label, DateTime date, VoidCallback onTap, ThemeData theme) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(AppConstants.radiusSmall),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFFE9FFF2),
          border: Border.all(color: const Color(0xFF5DAA7E)),
          borderRadius: BorderRadius.circular(AppConstants.radiusSmall),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: TextStyle(fontSize: 12, color: theme.hintColor)),
            const SizedBox(height: 4),
            Text(
              '${date.day}/${date.month}/${date.year}',
              style: const TextStyle(fontWeight: FontWeight.w600),
            ),
          ],
        ),
      ),
    );
  }

  TimeOfDay _parseTimeOfDay(String raw) {
    final parts = raw.split(':');
    if (parts.length < 2) return const TimeOfDay(hour: 8, minute: 0);
    final hour = int.tryParse(parts[0]) ?? 8;
    final minute = int.tryParse(parts[1]) ?? 0;
    return TimeOfDay(hour: hour.clamp(0, 23), minute: minute.clamp(0, 59));
  }

  DateTime _parseDate(dynamic value, DateTime fallback) {
    if (value == null) return fallback;
    final parsed = DateTime.tryParse(value.toString());
    return parsed ?? fallback;
  }

  String _dateToIso(DateTime d) {
    return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
  }

  Widget _buildScheduleSwipeBackground({
    required Color color,
    required IconData icon,
    required String label,
    required MainAxisAlignment alignment,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
        border: Border.all(color: color.withValues(alpha: 0.28)),
      ),
      child: Row(
        mainAxisAlignment: alignment,
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(width: 8),
          Text(label,
              style: TextStyle(
                  color: color, fontWeight: FontWeight.w600, fontSize: 13)),
        ],
      ),
    );
  }

  Future<void> _showScheduleActionsMenu(Map<String, dynamic> schedule) async {
    await showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Container(
        decoration: BoxDecoration(
          color: Theme.of(context).cardColor,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
        ),
        child: SafeArea(
          top: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(height: 10),
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.border,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(height: 12),
              const ListTile(
                leading: Icon(Icons.repeat_rounded, color: AppColors.info),
                title: Text('Schedule Actions',
                    style: TextStyle(fontWeight: FontWeight.w700)),
              ),
              ListTile(
                leading:
                    const Icon(Icons.edit_rounded, color: AppColors.primary),
                title: const Text('Edit Schedule'),
                onTap: () {
                  Navigator.pop(ctx);
                  _showEditScheduleDialog(schedule);
                },
              ),
              ListTile(
                leading: const Icon(Icons.delete_outline_rounded,
                    color: AppColors.error),
                title: const Text('Delete Schedule'),
                onTap: () async {
                  Navigator.pop(ctx);
                  await _confirmDeleteSchedule(schedule);
                },
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showEditScheduleDialog(Map<String, dynamic> schedule) async {
    final scheduleId = schedule['id']?.toString() ?? '';
    if (scheduleId.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Invalid schedule id for edit')),
      );
      return;
    }

    var rideTime = _parseTimeOfDay(schedule['time']?.toString() ?? '08:00:00');
    final now = DateTime.now();
    var startDate = _parseDate(schedule['start_date'], now);
    var endDate = _parseDate(
        schedule['end_date'], startDate.add(const Duration(days: 30)));

    var startLat = (schedule['start_point']?['lat'] as num?)?.toDouble();
    var startLng = (schedule['start_point']?['lng'] as num?)?.toDouble();
    var endLat = (schedule['end_point']?['lat'] as num?)?.toDouble();
    var endLng = (schedule['end_point']?['lng'] as num?)?.toDouble();
    var startAddress = schedule['start_point']?['address']?.toString() ?? '';
    var endAddress = schedule['end_point']?['address']?.toString() ?? '';

    final seatsCtrl = TextEditingController(
        text: (schedule['seats_offered'] ?? 3).toString());
    final bufferCtrl =
        TextEditingController(text: (schedule['buffer_seats'] ?? 0).toString());
    final priceCtrl =
        TextEditingController(text: schedule['base_price']?.toString() ?? '0');
    var isSaving = false;
    var showStartLocationError = false;
    var showEndLocationError = false;

    bool hasValidStartLocation() =>
        startLat != null && startLng != null && startAddress.trim().isNotEmpty;

    bool hasValidEndLocation() =>
        endLat != null && endLng != null && endAddress.trim().isNotEmpty;

    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSheetState) {
          return Container(
            padding: EdgeInsets.only(
              top: 20,
              left: 20,
              right: 20,
              bottom: MediaQuery.of(ctx).viewInsets.bottom + 20,
            ),
            decoration: BoxDecoration(
              color: Theme.of(context).cardColor,
              borderRadius:
                  const BorderRadius.vertical(top: Radius.circular(24)),
            ),
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Center(
                    child: Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: AppColors.border,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  const Text('Edit Active Schedule',
                      style:
                          TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 16),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: _flowCard,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: _flowBorder),
                    ),
                    child: const Text(
                      'This recurring schedule is applied daily across the selected date range.',
                      style:
                          TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                    ),
                  ),
                  const SizedBox(height: 12),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.access_time_rounded,
                        color: AppColors.primary),
                    title: const Text('Departure Time'),
                    subtitle: Text(rideTime.format(context)),
                    trailing: const Icon(Icons.chevron_right_rounded),
                    onTap: () async {
                      final picked = await showTimePicker(
                        context: context,
                        initialTime: rideTime,
                      );
                      if (picked != null) {
                        setSheetState(() => rideTime = picked);
                      }
                    },
                  ),
                  const Divider(),
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    decoration: BoxDecoration(
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusMedium),
                      border: Border.all(
                        color: showStartLocationError
                            ? AppColors.error
                            : Colors.transparent,
                        width: showStartLocationError ? 1.5 : 0,
                      ),
                    ),
                    child: PlaceSearchField(
                      hint: 'Start Location – type to search or tap map',
                      dotColor: AppColors.success,
                      textColor: const Color(0xFF1F6F4B),
                      value: startLat != null
                          ? PickedLocation(
                              latLng: LatLng(startLat!, startLng!),
                              address: startAddress,
                            )
                          : null,
                      onTextChanged: (value) {
                        final text = value.trim();
                        setSheetState(() {
                          startLat = null;
                          startLng = null;
                          startAddress = text;
                          if (text.isEmpty) {
                            showStartLocationError = true;
                          } else if (showStartLocationError) {
                            showStartLocationError = false;
                          }
                        });
                      },
                      onPlaceSelected: (place) {
                        setSheetState(() {
                          startLat = place.latLng.latitude;
                          startLng = place.latLng.longitude;
                          startAddress = place.address.trim();
                          showStartLocationError = false;
                        });
                      },
                    ),
                  ),
                  if (showStartLocationError)
                    const Padding(
                      padding: EdgeInsets.only(left: 12, top: 6),
                      child: Text(
                        'Start location is required',
                        style: TextStyle(color: AppColors.error, fontSize: 12),
                      ),
                    ),
                  const SizedBox(height: 10),
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    decoration: BoxDecoration(
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusMedium),
                      border: Border.all(
                        color: showEndLocationError
                            ? AppColors.error
                            : Colors.transparent,
                        width: showEndLocationError ? 1.5 : 0,
                      ),
                    ),
                    child: PlaceSearchField(
                      hint: 'Destination – type to search or tap map',
                      dotColor: AppColors.error,
                      textColor: const Color(0xFF1F6F4B),
                      value: endLat != null
                          ? PickedLocation(
                              latLng: LatLng(endLat!, endLng!),
                              address: endAddress,
                            )
                          : null,
                      onTextChanged: (value) {
                        final text = value.trim();
                        setSheetState(() {
                          endLat = null;
                          endLng = null;
                          endAddress = text;
                          if (text.isEmpty) {
                            showEndLocationError = true;
                          } else if (showEndLocationError) {
                            showEndLocationError = false;
                          }
                        });
                      },
                      onPlaceSelected: (place) {
                        setSheetState(() {
                          endLat = place.latLng.latitude;
                          endLng = place.latLng.longitude;
                          endAddress = place.address.trim();
                          showEndLocationError = false;
                        });
                      },
                    ),
                  ),
                  if (showEndLocationError)
                    const Padding(
                      padding: EdgeInsets.only(left: 12, top: 6),
                      child: Text(
                        'Destination is required',
                        style: TextStyle(color: AppColors.error, fontSize: 12),
                      ),
                    ),
                  const SizedBox(height: 10),
                  OutlinedButton.icon(
                    onPressed: () async {
                      final result = await Navigator.push<DualPickResult>(
                        context,
                        MaterialPageRoute(
                          builder: (_) => DualLocationPickerScreen(
                            initialOrigin: startLat != null
                                ? PickedLocation(
                                    latLng: LatLng(startLat!, startLng!),
                                    address: startAddress,
                                  )
                                : null,
                            initialDestination: endLat != null
                                ? PickedLocation(
                                    latLng: LatLng(endLat!, endLng!),
                                    address: endAddress,
                                  )
                                : null,
                          ),
                        ),
                      );
                      if (result != null) {
                        setSheetState(() {
                          if (result.origin != null) {
                            startLat = result.origin!.latLng.latitude;
                            startLng = result.origin!.latLng.longitude;
                            startAddress = result.origin!.address.trim();
                            showStartLocationError = false;
                          }
                          if (result.destination != null) {
                            endLat = result.destination!.latLng.latitude;
                            endLng = result.destination!.latLng.longitude;
                            endAddress = result.destination!.address.trim();
                            showEndLocationError = false;
                          }
                        });
                      }
                    },
                    icon: const Icon(Icons.map_rounded, size: 18),
                    label: const Text('Pick Both on Map'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.primary,
                      side: BorderSide(
                          color: AppColors.primary.withValues(alpha: 0.5)),
                      minimumSize: const Size(double.infinity, 44),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12)),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: TextFormField(
                          controller: seatsCtrl,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(
                            labelText: 'Seats Offered',
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: TextFormField(
                          controller: bufferCtrl,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(
                            labelText: 'Buffer Seats',
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: priceCtrl,
                    keyboardType: TextInputType.number,
                    decoration: const InputDecoration(
                      labelText: 'Price per Seat (PKR)',
                      border: OutlineInputBorder(),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: _dateTile('From', startDate, () async {
                          final picked = await showDatePicker(
                            context: context,
                            initialDate: startDate,
                            firstDate: DateTime.now(),
                            lastDate:
                                DateTime.now().add(const Duration(days: 365)),
                          );
                          if (picked != null) {
                            setSheetState(() {
                              startDate = picked;
                              if (!endDate.isAfter(startDate)) {
                                endDate =
                                    startDate.add(const Duration(days: 30));
                              }
                            });
                          }
                        }, Theme.of(context)),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: _dateTile('Until', endDate, () async {
                          final picked = await showDatePicker(
                            context: context,
                            initialDate: endDate,
                            firstDate: startDate,
                            lastDate:
                                DateTime.now().add(const Duration(days: 365)),
                          );
                          if (picked != null) {
                            setSheetState(() => endDate = picked);
                          }
                        }, Theme.of(context)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: ElevatedButton.icon(
                      onPressed: isSaving
                          ? null
                          : () async {
                              final seats = int.tryParse(seatsCtrl.text.trim());
                              final buffer =
                                  int.tryParse(bufferCtrl.text.trim()) ?? 0;
                              final basePrice =
                                  double.tryParse(priceCtrl.text.trim());

                              if (!hasValidStartLocation() ||
                                  !hasValidEndLocation()) {
                                setSheetState(() {
                                  showStartLocationError =
                                      !hasValidStartLocation();
                                  showEndLocationError = !hasValidEndLocation();
                                });
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                      content: Text(
                                          'Pick both start and destination locations')),
                                );
                                return;
                              }
                              if (seats == null || seats < 1 || seats > 8) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                      content:
                                          Text('Seats must be between 1-8')),
                                );
                                return;
                              }
                              if (buffer < 0 || buffer > 3 || buffer >= seats) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                      content: Text(
                                          'Buffer seats must be 0-3 and less than seats offered')),
                                );
                                return;
                              }
                              if (basePrice == null || basePrice <= 0) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                      content: Text(
                                          'Enter a valid positive base price')),
                                );
                                return;
                              }
                              if (!endDate.isAfter(startDate)) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                      content: Text(
                                          'End date must be after start date')),
                                );
                                return;
                              }

                              setSheetState(() => isSaving = true);
                              try {
                                await _scheduleService.updateSchedule(
                                  scheduleId: scheduleId,
                                  daysOfWeek: _allDays,
                                  rideTime:
                                      '${rideTime.hour.toString().padLeft(2, '0')}:${rideTime.minute.toString().padLeft(2, '0')}:00',
                                  startLat: startLat!,
                                  startLng: startLng!,
                                  startAddress: startAddress,
                                  endLat: endLat!,
                                  endLng: endLng!,
                                  endAddress: endAddress,
                                  seatsOffered: seats,
                                  bufferSeats: buffer,
                                  basePrice: basePrice,
                                  startDate: _dateToIso(startDate),
                                  endDate: _dateToIso(endDate),
                                  purgeFutureRides: true,
                                );

                                if (mounted) {
                                  Navigator.pop(ctx);
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    const SnackBar(
                                      content: Text(
                                          'Schedule updated. Previous generated future rides removed.'),
                                      backgroundColor: AppColors.success,
                                    ),
                                  );
                                  _loadExistingSchedules();
                                }
                              } catch (e) {
                                if (mounted) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                        content: Text(
                                            'Failed to update schedule: $e')),
                                  );
                                }
                              } finally {
                                if (mounted) {
                                  setSheetState(() => isSaving = false);
                                }
                              }
                            },
                      icon: isSaving
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.save_rounded),
                      label: Text(isSaving ? 'Saving…' : 'Save Schedule'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.primary,
                        foregroundColor: Colors.white,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Future<void> _confirmDeleteSchedule(Map<String, dynamic> schedule) async {
    final scheduleId = schedule['id']?.toString() ?? '';
    if (scheduleId.isEmpty) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Schedule'),
        content: const Text(
            'This will deactivate the schedule and remove previously generated future open rides for it. Continue?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child:
                const Text('Delete', style: TextStyle(color: AppColors.error)),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    try {
      await _scheduleService.deleteSchedule(
        scheduleId,
        purgeFutureRides: true,
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
                'Schedule deleted. Previous generated future rides removed.'),
            backgroundColor: AppColors.success,
          ),
        );
        _loadExistingSchedules();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to delete schedule: $e')),
        );
      }
    }
  }

  Widget _buildScheduleCard(Map<String, dynamic> schedule, ThemeData theme) {
    final scheduleId = schedule['id']?.toString() ?? '${schedule.hashCode}';
    final time = schedule['time']?.toString() ?? '';
    final startAddr = schedule['start_point']?['address'] ?? '';
    final endAddr = schedule['end_point']?['address'] ?? '';
    final startDate = schedule['start_date']?.toString() ?? '';
    final endDate = schedule['end_date']?.toString() ?? '';
    final price = schedule['base_price'];
    final seats = schedule['seats_offered']?.toString() ?? '';
    final isActive = schedule['is_active'] == true;

    final priceStr = price != null ? 'Rs ${_fmtNum(price)}/seat' : 'N/A';

    return Dismissible(
      key: ValueKey('schedule-$scheduleId'),
      direction: DismissDirection.horizontal,
      background: _buildScheduleSwipeBackground(
        color: AppColors.primary,
        icon: Icons.edit_rounded,
        label: 'Edit',
        alignment: MainAxisAlignment.start,
      ),
      secondaryBackground: _buildScheduleSwipeBackground(
        color: AppColors.error,
        icon: Icons.delete_outline_rounded,
        label: 'Delete',
        alignment: MainAxisAlignment.end,
      ),
      confirmDismiss: (direction) async {
        if (direction == DismissDirection.startToEnd) {
          await _showEditScheduleDialog(schedule);
          return false;
        }
        await _confirmDeleteSchedule(schedule);
        return false;
      },
      child: InkWell(
        borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
        onTap: () => _showScheduleActionsMenu(schedule),
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: _flowCard,
            borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
            border: Border.all(
              color: isActive
                  ? _flowBorder
                  : _flowBorder.withValues(alpha: 0.8),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.repeat_rounded,
                      size: 18,
                      color: isActive ? AppColors.primary : AppColors.textHint),
                  const SizedBox(width: 8),
                  const Expanded(
                    child: Text('Daily',
                        style: TextStyle(fontWeight: FontWeight.w600)),
                  ),
                  Text(time,
                      style: const TextStyle(
                          color: AppColors.primary,
                          fontWeight: FontWeight.w600)),
                  const SizedBox(width: 6),
                  Icon(Icons.more_horiz_rounded,
                      size: 20, color: AppColors.textHint),
                ],
              ),
              const SizedBox(height: 8),
              Text('$startAddr → $endAddr',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: theme.hintColor, fontSize: 13)),
              const SizedBox(height: 4),
              Text('$seats seats • $priceStr • $startDate to $endDate',
                  style: TextStyle(color: theme.hintColor, fontSize: 12)),
            ],
          ),
        ),
      ),
    );
  }
}
