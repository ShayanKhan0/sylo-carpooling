import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/services/api_client.dart';
import '../../core/services/maps_service.dart';
import '../../core/services/ride_service.dart';
import '../../core/services/schedule_service.dart';
import '../../core/theme/app_colors.dart';
import '../../core/utils/fare_calculator.dart';
import '../dashboard/home_design_system.dart';
import '../maps/dual_location_picker_screen.dart';
import '../maps/location_picker_screen.dart';
import '../maps/place_search_field.dart';
import '../maps/route_map_widget.dart';

class PassengerRecurringDiscoveryTab extends StatefulWidget {
  const PassengerRecurringDiscoveryTab({super.key});

  @override
  State<PassengerRecurringDiscoveryTab> createState() =>
      _PassengerRecurringDiscoveryTabState();
}

class _PassengerRecurringDiscoveryTabState
    extends State<PassengerRecurringDiscoveryTab> {
  static const Color _flowCard = Color(0xFFD9FCE8);
  static const Color _flowBorder = Color(0xFF5DAA7E);

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
    );
  }
  final ScheduleService _scheduleService = ScheduleService();
  final RideService _rideService = RideService();
  final MapsService _mapsService = MapsService();

  PickedLocation? _origin;
  PickedLocation? _destination;
  bool _isDetailsStep = false;

  DateTime _passengerFromDate = DateTime.now();
  DateTime _passengerUntilDate = DateTime.now().add(const Duration(days: 30));
  TimeOfDay? _windowStart = const TimeOfDay(hour: 8, minute: 0);
  TimeOfDay? _windowEnd = const TimeOfDay(hour: 10, minute: 0);
  int _minSeats = 1;
  int? _driverTotalSeats;

  FareEstimate? _fareEstimate;
  bool _fareLoading = false;
  DirectionsRoute? _routeDetails;

  bool _loadingOccupiedSlots = false;
  bool _showSlotConflictError = false;
  List<Map<String, dynamic>> _occupiedSlots = [];

  int _fareRequestVersion = 0;
  int _slotsRequestVersion = 0;
  int _searchRequestVersion = 0;

  bool _showOriginError = false;
  bool _showDestinationError = false;
  bool _showFromDateError = false;
  bool _showUntilDateError = false;
  bool _showWindowStartError = false;
  bool _showWindowEndError = false;
  bool _showWindowRangeError = false;
  String? _windowRangeErrorText;

  bool _isSearching = false;
  bool _hasSearched = false;
  List<Map<String, dynamic>> _results = [];
  final Set<String> _bookingScheduleIds = <String>{};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _loadOccupiedSlotsForFromDate();
      _calculateFare();
    });
  }

  @override
  Widget build(BuildContext context) {
    if (!_isDetailsStep) {
      return DualLocationPickerScreen(
        initialOrigin: _origin,
        initialDestination: _destination,
        showBackButton: false,
        onLocationsConfirmed: (result) {
          setState(() {
            _origin = result.origin;
            _destination = result.destination;
            _isDetailsStep = true;
            _showOriginError = false;
            _showDestinationError = false;
            _clearSearchResultsState();
          });
          _calculateFare();
          _loadOccupiedSlotsForFromDate();
        },
      );
    }

    return Theme(
      data: _flowTheme(context),
      child: Stack(
      children: [
        HomeDesignSystem.driverHomeSoftWhiteBackground(),
        SafeArea(
          child: Column(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.transparent,
            ),
            child: Row(
              children: [
                IconButton(
                  onPressed: _returnToMap,
                  icon: const Icon(Icons.arrow_back_rounded),
                  tooltip: 'Back to Map',
                ),
                Expanded(
                  child: Center(
                    child: Text(
                      'Find Recurring Rides',
                      style: GoogleFonts.inter(
                        fontSize: 24,
                        fontWeight: FontWeight.w900,
                        color: const Color(0xFF0B3D24),
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 48),
              ],
            ),
          ),
          Expanded(
            child: Container(
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
                child: ListView(
                  padding: EdgeInsets.zero,
                  children: [
                if (_origin != null && _destination != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 14),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(14),
                      child: SizedBox(
                        height: 240,
                        child: RouteMapWidget(
                          origin: _origin!.latLng,
                          destination: _destination!.latLng,
                          originPlaceId: _origin!.placeId,
                          destinationPlaceId: _destination!.placeId,
                          originLabel: _origin!.address,
                          destinationLabel: _destination!.address,
                          showAlternatives: true,
                          interactive: false,
                          showInfoCard: false,
                          height: 240,
                        ),
                      ),
                    ),
                  ),
                _buildOriginField(),
                const SizedBox(height: 10),
                _buildDestinationField(),
                const SizedBox(height: 10),
                OutlinedButton.icon(
                  onPressed: _pickBothOnMap,
                  icon: const Icon(Icons.map_rounded, size: 18),
                  label: const Text('Pick Both on Map'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: AppColors.primary,
                    side: BorderSide(
                        color: AppColors.primary.withValues(alpha: 0.5)),
                    minimumSize: const Size(double.infinity, 44),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: _flowCard,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: _flowBorder),
                  ),
                  child: const Text(
                    'Passenger From/Until applies to every day in the selected range. No weekday selection is needed.',
                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: _buildDateTile(
                        label: 'From Date',
                        value: _passengerFromDate,
                        hasError: _showFromDateError,
                        onTap: () => _pickDate(isFromDate: true),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _buildDateTile(
                        label: 'Until Date',
                        value: _passengerUntilDate,
                        hasError: _showUntilDateError,
                        onTap: () => _pickDate(isFromDate: false),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: _buildTimeTile(
                        label: 'From Time',
                        value: _windowStart,
                        hasError: _showWindowStartError,
                        onTap: () => _pickWindowTime(isStart: true),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _buildTimeTile(
                        label: 'To Time',
                        value: _windowEnd,
                        hasError: _showWindowEndError,
                        onTap: () => _pickWindowTime(isStart: false),
                      ),
                    ),
                  ],
                ),
                if (_showWindowRangeError)
                  Padding(
                    padding: const EdgeInsets.only(left: 8, top: 6),
                    child: Text(
                      _windowRangeErrorText ?? 'Select a valid time window.',
                      style:
                          const TextStyle(color: AppColors.error, fontSize: 12),
                    ),
                  ),
                if (_routeDetails != null && !_fareLoading)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 12),
                      decoration: HomeDesignSystem.darkTopBarSurface(
                        radius: 14,
                      ),
                      child: Builder(builder: (_) {
                        final durationMin = _routeDetails!.durationMinutes;
                        final departureReference =
                            _selectedWindowStartDateTimeForFromDay() ??
                                _passengerFromDate;
                        final arrival = departureReference
                            .add(Duration(minutes: durationMin));
                        final h = arrival.hour;
                        final m = arrival.minute.toString().padLeft(2, '0');
                        final period = h >= 12 ? 'PM' : 'AM';
                        final h12 = h > 12 ? h - 12 : (h == 0 ? 12 : h);

                        return Row(
                          mainAxisAlignment: MainAxisAlignment.spaceAround,
                          children: [
                            _routeInfoChip(
                              Icons.straighten_rounded,
                              AppColors.primary,
                              '${_routeDetails!.distanceKm.toStringAsFixed(1)} km',
                              'Distance',
                            ),
                            Container(
                                width: 1, height: 36, color: AppColors.border),
                            _routeInfoChip(
                              Icons.timer_rounded,
                              AppColors.secondary,
                              '~$durationMin min',
                              'Duration',
                            ),
                            Container(
                                width: 1, height: 36, color: AppColors.border),
                            _routeInfoChip(
                              Icons.access_time_rounded,
                              AppColors.success,
                              '$h12:$m $period',
                              'Arrives',
                            ),
                          ],
                        );
                      }),
                    ),
                  ),
                if (_fareLoading)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(16),
                      decoration: HomeDesignSystem.darkTopBarSurface(
                        radius: 14,
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: AppColors.primary,
                            ),
                          ),
                          const SizedBox(width: 10),
                          Text(
                            'Calculating fare...',
                            style: TextStyle(
                              color: AppColors.textSecondary,
                              fontSize: 13,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                if (_fareEstimate != null && !_fareLoading)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(16),
                      decoration: HomeDesignSystem.darkTopBarSurface(
                        radius: 14,
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Icon(
                                Icons.calculate_rounded,
                                color: AppColors.primary,
                                size: 18,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                'Estimated Trip Cost',
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 15,
                                  color: Colors.white,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          Row(
                            children: [
                              Expanded(
                                child: _fareInfoTile(
                                  Icons.route_rounded,
                                  '${_fareEstimate!.distanceKm.toStringAsFixed(1)} km',
                                  'Route Distance',
                                ),
                              ),
                              Expanded(
                                child: _fareInfoTile(
                                  Icons.payments_rounded,
                                  'Rs ${_fareEstimate!.farePerSeat.toStringAsFixed(0)}',
                                  'Estimated Rs / Seat',
                                ),
                              ),
                              Expanded(
                                child: _fareInfoTile(
                                  Icons.receipt_long_rounded,
                                  'Rs ${_fareEstimate!.totalFare.toStringAsFixed(0)}',
                                  'Estimated Trip Total',
                                ),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                const SizedBox(height: 14),
                Text(
                  'Seats Needed',
                  style: TextStyle(
                    color: AppColors.textPrimary,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: List.generate(8, (index) {
                    final seats = index + 1;
                    final isSelected = _minSeats == seats;
                    return GestureDetector(
                      onTap: () {
                        setState(() {
                          _minSeats = seats;
                          _clearSearchResultsState();
                        });
                        _calculateFare();
                      },
                      child: Container(
                        width: 36,
                        height: 36,
                        decoration: BoxDecoration(
                          color: isSelected
                              ? AppColors.primary
                              : _flowCard,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: isSelected
                                ? AppColors.primary
                                : AppColors.border,
                          ),
                        ),
                        child: Center(
                          child: Text(
                            '$seats',
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              color: isSelected
                                  ? Colors.white
                                  : AppColors.textPrimary,
                            ),
                          ),
                        ),
                      ),
                    );
                  }),
                ),
                const SizedBox(height: 14),
                Divider(height: 1, thickness: 1, color: AppColors.border),
                const SizedBox(height: 14),
                Text(
                  'Driver Total Offered Seats',
                  style: TextStyle(
                    color: AppColors.textPrimary,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    GestureDetector(
                      onTap: () {
                        setState(() {
                          _driverTotalSeats = null;
                          _clearSearchResultsState();
                        });
                      },
                      child: Container(
                        height: 36,
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        decoration: BoxDecoration(
                          color: _driverTotalSeats == null
                              ? AppColors.primary
                                : _flowCard,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: _driverTotalSeats == null
                                ? AppColors.primary
                                : AppColors.border,
                          ),
                        ),
                        child: Center(
                          child: Text(
                            'Any',
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              color: _driverTotalSeats == null
                                  ? Colors.white
                                  : AppColors.textPrimary,
                            ),
                          ),
                        ),
                      ),
                    ),
                    ...List.generate(8, (index) {
                      final seats = index + 1;
                      final isSelected = _driverTotalSeats == seats;
                      return GestureDetector(
                        onTap: () {
                          setState(() {
                            _driverTotalSeats = seats;
                            _clearSearchResultsState();
                          });
                        },
                        child: Container(
                          width: 36,
                          height: 36,
                          decoration: BoxDecoration(
                            color: isSelected
                                ? AppColors.primary
                                : _flowCard,
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                              color: isSelected
                                  ? AppColors.primary
                                  : AppColors.border,
                            ),
                          ),
                          child: Center(
                            child: Text(
                              '$seats',
                              style: TextStyle(
                                fontWeight: FontWeight.bold,
                                color: isSelected
                                    ? Colors.white
                                    : AppColors.textPrimary,
                              ),
                            ),
                          ),
                        ),
                      );
                    }),
                  ],
                ),
                const SizedBox(height: 14),
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
                        'Conflict check uses selected From Date with the chosen time window.',
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
                          'No occupied slots on selected From Date.',
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
                                _slotConflictsWithSelectedFromDayWindow(slot);
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
                      'Selected time overlaps with an occupied slot on From Date.',
                      style: TextStyle(color: AppColors.error, fontSize: 12),
                    ),
                  ),
                const SizedBox(height: 14),
                Container(
                  width: double.infinity,
                  decoration: HomeDesignSystem.darkTopBarSurface(radius: 12),
                  child: ElevatedButton.icon(
                    onPressed: _isSearching ? null : _searchRecurringRides,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.transparent,
                      foregroundColor: const Color(0xFF43E892),
                      shadowColor: Colors.transparent,
                      elevation: 0,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    icon: _isSearching
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Icon(Icons.search_rounded),
                    label: Text(
                        _isSearching ? 'Searching...' : 'Find Recurring Rides'),
                  ),
                ),
                const SizedBox(height: 14),
                if (_hasSearched && !_isSearching && _results.isEmpty)
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppColors.backgroundLight,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: AppColors.border),
                    ),
                    child: const Text(
                      'No recurring rides matched your route, date range, and time window.',
                      style: TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ),
                if (_results.isNotEmpty) ...[
                  Text(
                    'Recurring Matches (${_results.length})',
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 10),
                  ..._results.map(_buildRecurringResultCard),
                ],
                const SizedBox(height: 20),
                ],
                ),
              ),
            ),
          ),
        ],
      ),
        ),
      ],
    ));
  }

  Widget _buildOriginField() {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: _showOriginError ? AppColors.error : Colors.transparent,
          width: _showOriginError ? 1.5 : 0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          PlaceSearchField(
            hint: 'From - type to search or tap map',
            dotColor: AppColors.primary,
            textColor: const Color(0xFF0B3D24),
            hintColor: const Color(0xFF114B2D).withValues(alpha: 0.7),
            mapIconColor: const Color(0xFF0B3D24),
            backgroundColor: const Color(0xFFE9FFF2),
            borderColor: const Color(0xFF5DAA7E),
            value: _origin,
            onTextChanged: (value) {
              final query = value.trim();
              final currentAddress = _origin?.address.trim() ?? '';
              if (query.isEmpty ||
                  (_origin != null && query != currentAddress)) {
                setState(() {
                  _origin = null;
                  _clearSearchResultsState();
                });
                _calculateFare();
              }
            },
            onPlaceSelected: (place) {
              setState(() {
                _origin = place;
                _showOriginError = false;
                _clearSearchResultsState();
              });
              _calculateFare();
            },
          ),
          if (_showOriginError)
            const Padding(
              padding: EdgeInsets.only(left: 12, top: 6),
              child: Text(
                'Start point is required',
                style: TextStyle(color: AppColors.error, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildDestinationField() {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: _showDestinationError ? AppColors.error : Colors.transparent,
          width: _showDestinationError ? 1.5 : 0,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          PlaceSearchField(
            hint: 'To - type to search or tap map',
            dotColor: AppColors.accent,
            textColor: const Color(0xFF0B3D24),
            hintColor: const Color(0xFF114B2D).withValues(alpha: 0.7),
            mapIconColor: const Color(0xFF0B3D24),
            backgroundColor: const Color(0xFFE9FFF2),
            borderColor: const Color(0xFF5DAA7E),
            value: _destination,
            onTextChanged: (value) {
              final query = value.trim();
              final currentAddress = _destination?.address.trim() ?? '';
              if (query.isEmpty ||
                  (_destination != null && query != currentAddress)) {
                setState(() {
                  _destination = null;
                  _clearSearchResultsState();
                });
                _calculateFare();
              }
            },
            onPlaceSelected: (place) {
              setState(() {
                _destination = place;
                _showDestinationError = false;
                _clearSearchResultsState();
              });
              _calculateFare();
            },
          ),
          if (_showDestinationError)
            const Padding(
              padding: EdgeInsets.only(left: 12, top: 6),
              child: Text(
                'Destination is required',
                style: TextStyle(color: AppColors.error, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildDateTile({
    required String label,
    required DateTime value,
    required bool hasError,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: _flowCard,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: hasError ? AppColors.error : _flowBorder,
            width: hasError ? 1.5 : 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
            const SizedBox(height: 4),
            Text(_formatDate(value),
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: AppColors.textPrimary,
                )),
          ],
        ),
      ),
    );
  }

  Widget _buildTimeTile({
    required String label,
    required TimeOfDay? value,
    required bool hasError,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: _flowCard,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: hasError ? AppColors.error : _flowBorder,
            width: hasError ? 1.5 : 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: TextStyle(fontSize: 12, color: AppColors.textSecondary)),
            const SizedBox(height: 4),
            Text(
              value == null ? 'Select time' : _formatTime(value),
              style: TextStyle(
                fontWeight: FontWeight.w600,
                color: value == null
                    ? AppColors.textSecondary
                    : AppColors.textPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRecurringResultCard(Map<String, dynamic> result) {
    final scheduleId = (result['schedule_id'] ?? '').toString();
    final isBooking = _bookingScheduleIds.contains(scheduleId);
    final startPoint = _asMap(result['start_point']);
    final endPoint = _asMap(result['end_point']);

    final driverName = (result['driver_name'] ?? 'Driver').toString();
    final startAddress = (startPoint['address'] ?? 'Unknown start').toString();
    final endAddress =
        (endPoint['address'] ?? 'Unknown destination').toString();

    final rideTimeRaw = (result['ride_time'] ?? '').toString();
    final matchingDays = _toInt(result['matching_days_count']);
    final firstDate = (result['first_matching_date'] ?? '-').toString();
    final overlapStart = (result['overlap_start_date'] ?? '-').toString();
    final overlapEnd = (result['overlap_end_date'] ?? '-').toString();
    final seats = _toInt(result['template_available_seats']);
    final fare = _toDouble(result['base_price']);
    final fromDistance = _toDouble(result['distance_from_origin_km']);
    final toDistance = _toDouble(result['distance_to_destination_km']);
    final proximitySummary = _buildProximitySummary(fromDistance, toDistance);

    return Material(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(14),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () => _showRecurringResultDetails(result),
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: _flowBorder),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.repeat_rounded,
                      size: 18, color: AppColors.primary),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      driverName,
                      style: const TextStyle(
                          fontWeight: FontWeight.w700, fontSize: 14),
                    ),
                  ),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppColors.primary.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      'Rs ${fare.toStringAsFixed(0)}/seat',
                      style: const TextStyle(
                        color: AppColors.primaryDark,
                        fontWeight: FontWeight.w700,
                        fontSize: 12,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  const Icon(Icons.trip_origin,
                      size: 14, color: AppColors.success),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      startAddress,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style:
                          TextStyle(color: AppColors.textPrimary, fontSize: 13),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  const Icon(Icons.location_on,
                      size: 14, color: AppColors.error),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      endAddress,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style:
                          TextStyle(color: AppColors.textPrimary, fontSize: 13),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _metaChip(Icons.access_time_rounded, 'Departs $rideTimeRaw'),
                  _metaChip(Icons.event_available_rounded,
                      '$matchingDays matching rides'),
                  _metaChip(Icons.event_seat_rounded, '$seats seats'),
                  _metaChip(Icons.near_me_rounded, proximitySummary),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                'Overlap: $overlapStart to $overlapEnd',
                style: TextStyle(color: AppColors.textSecondary, fontSize: 12),
              ),
              const SizedBox(height: 2),
              Text(
                'First ride date: $firstDate',
                style: TextStyle(color: AppColors.textSecondary, fontSize: 12),
              ),
              const SizedBox(height: 2),
              Text(
                'Tap card to view full recurring ride details',
                style: TextStyle(color: AppColors.textHint, fontSize: 11),
              ),
              const SizedBox(height: 10),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: isBooking ? null : () => _bookRecurringSeries(result),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.primary,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 11),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                  ),
                  icon: isBooking
                      ? const SizedBox(
                          width: 14,
                          height: 14,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Icon(Icons.playlist_add_check_rounded, size: 18),
                  label: Text(
                    isBooking
                        ? 'Booking Full Series...'
                        : 'Book Full Recurring Series',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _showRecurringResultDetails(Map<String, dynamic> result) async {
    if (!mounted) return;

    final scheduleId = (result['schedule_id'] ?? '').toString();
    final isBooking = _bookingScheduleIds.contains(scheduleId);
    final startPoint = _asMap(result['start_point']);
    final endPoint = _asMap(result['end_point']);

    final driverName = (result['driver_name'] ?? 'Driver').toString();
    final startAddress = (startPoint['address'] ?? 'Unknown start').toString();
    final endAddress =
        (endPoint['address'] ?? 'Unknown destination').toString();

    final rideTimeRaw = (result['ride_time'] ?? '-').toString();
    final matchingDays = _toInt(result['matching_days_count']);
    final firstDate = (result['first_matching_date'] ?? '-').toString();
    final overlapStart = (result['overlap_start_date'] ?? '-').toString();
    final overlapEnd = (result['overlap_end_date'] ?? '-').toString();
    final scheduleStartDate = (result['schedule_start_date'] ?? '-').toString();
    final scheduleEndDate = (result['schedule_end_date'] ?? '-').toString();
    final seatsOffered = _toInt(result['seats_offered']);
    final bufferSeats = _toInt(result['buffer_seats']);
    final seatsAvailable = _toInt(result['template_available_seats']);
    final fare = _toDouble(result['base_price']);
    final fromDistance = _toDouble(result['distance_from_origin_km']);
    final toDistance = _toDouble(result['distance_to_destination_km']);
    final daysOfWeek = _toStringList(result['days_of_week']);

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (sheetCtx) {
        return FractionallySizedBox(
          heightFactor: 0.92,
          child: Column(
            children: [
              const SizedBox(height: 10),
              Container(
                width: 44,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.divider,
                  borderRadius: BorderRadius.circular(99),
                ),
              ),
              const SizedBox(height: 10),
              Text(
                'Recurring Ride Details',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                  color: AppColors.textPrimary,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                'Driver: $driverName',
                style: TextStyle(
                  fontSize: 13,
                  color: AppColors.textSecondary,
                ),
              ),
              const SizedBox(height: 10),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(14),
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
                                const Icon(Icons.trip_origin,
                                    size: 14, color: AppColors.success),
                                const SizedBox(width: 6),
                                Expanded(
                                  child: Text(
                                    startAddress,
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w600),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                            Row(
                              children: [
                                const Icon(Icons.location_on,
                                    size: 14, color: AppColors.error),
                                const SizedBox(width: 6),
                                Expanded(
                                  child: Text(
                                    endAddress,
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w600),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 12),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          _metaChip(Icons.access_time_rounded, 'Departs $rideTimeRaw'),
                          _metaChip(Icons.event_repeat_rounded,
                              '$matchingDays matching rides'),
                          _metaChip(Icons.event_seat_rounded,
                              '$seatsAvailable seats available'),
                          _metaChip(
                            Icons.directions_car_rounded,
                            'Total $seatsOffered • Buffer $bufferSeats',
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: _flowCard,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: _flowBorder),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Pickup proximity: ${_formatProximityKm(fromDistance)}',
                              style: const TextStyle(fontWeight: FontWeight.w600),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              'Dropoff proximity: ${_formatProximityKm(toDistance)}',
                              style: const TextStyle(fontWeight: FontWeight.w600),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              'These are straight-line distances between your selected points and this driver\'s recurring route endpoints.',
                              style: TextStyle(
                                fontSize: 12,
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        'Fare: Rs ${fare.toStringAsFixed(0)}/seat',
                        style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 15,
                          color: AppColors.success,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Schedule range: $scheduleStartDate to $scheduleEndDate',
                        style:
                            TextStyle(color: AppColors.textSecondary, fontSize: 13),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Overlap with your dates: $overlapStart to $overlapEnd',
                        style:
                            TextStyle(color: AppColors.textSecondary, fontSize: 13),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'First matching ride date: $firstDate',
                        style:
                            TextStyle(color: AppColors.textSecondary, fontSize: 13),
                      ),
                      if (daysOfWeek.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        Text(
                          'Runs on: ${daysOfWeek.join(', ')}',
                          style:
                              TextStyle(color: AppColors.textSecondary, fontSize: 13),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                child: SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: isBooking
                        ? null
                        : () async {
                            Navigator.pop(sheetCtx);
                            await _bookRecurringSeries(result);
                          },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.primary,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    icon: isBooking
                        ? const SizedBox(
                            width: 14,
                            height: 14,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Icon(Icons.playlist_add_check_rounded, size: 18),
                    label: Text(
                      isBooking
                          ? 'Booking Full Series...'
                          : 'Book Full Recurring Series',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _metaChip(IconData icon, String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: _flowCard,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: _flowBorder),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: AppColors.primaryDark),
          const SizedBox(width: 6),
          Text(
            text,
            style: TextStyle(
              fontSize: 11,
              color: AppColors.textPrimary,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _fareInfoTile(IconData icon, String value, String label) {
    return Column(
      children: [
        Icon(icon, color: AppColors.primary, size: 22),
        const SizedBox(height: 6),
        Text(
          value,
          style: TextStyle(
            fontWeight: FontWeight.bold,
            fontSize: 15,
            color: Colors.white,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          label,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 12,
            color: Colors.white.withValues(alpha: 0.84),
          ),
        ),
      ],
    );
  }

  Widget _routeInfoChip(
      IconData icon, Color color, String value, String label) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 18, color: color),
        const SizedBox(height: 4),
        Text(
          value,
          style: TextStyle(
            fontWeight: FontWeight.w700,
            fontSize: 13,
            color: Colors.white,
          ),
        ),
        Text(
          label,
          style: TextStyle(
            fontSize: 11,
            color: Colors.white.withValues(alpha: 0.84),
          ),
        ),
      ],
    );
  }

  Future<void> _pickBothOnMap() async {
    final result = await Navigator.push<DualPickResult>(
      context,
      MaterialPageRoute(
        builder: (_) => DualLocationPickerScreen(
          initialOrigin: _origin,
          initialDestination: _destination,
        ),
      ),
    );

    if (result == null) return;

    setState(() {
      if (result.origin != null) {
        _origin = result.origin;
        _showOriginError = false;
      }
      if (result.destination != null) {
        _destination = result.destination;
        _showDestinationError = false;
      }
      _clearSearchResultsState();
    });
    _calculateFare();
    _loadOccupiedSlotsForFromDate();
  }

  Future<void> _pickDate({required bool isFromDate}) async {
    final initial = isFromDate ? _passengerFromDate : _passengerUntilDate;
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );

    if (picked == null) return;

    setState(() {
      if (isFromDate) {
        _passengerFromDate = DateTime(picked.year, picked.month, picked.day);
        if (_passengerUntilDate.isBefore(_passengerFromDate)) {
          _passengerUntilDate = _passengerFromDate;
        }
      } else {
        _passengerUntilDate = DateTime(picked.year, picked.month, picked.day);
      }

      _showFromDateError = false;
      _showUntilDateError = false;
      _showWindowRangeError = false;
      _windowRangeErrorText = null;
      _showSlotConflictError = false;
      _clearSearchResultsState();
    });

    _loadOccupiedSlotsForFromDate();
  }

  Future<void> _pickWindowTime({required bool isStart}) async {
    final initial = isStart
        ? (_windowStart ?? const TimeOfDay(hour: 8, minute: 0))
        : (_windowEnd ?? const TimeOfDay(hour: 10, minute: 0));

    final picked = await showTimePicker(
      context: context,
      initialTime: initial,
    );

    if (picked == null) return;

    setState(() {
      if (isStart) {
        _windowStart = picked;
        _showWindowStartError = false;
      } else {
        _windowEnd = picked;
        _showWindowEndError = false;
      }
      _showWindowRangeError = false;
      _windowRangeErrorText = null;
      _showSlotConflictError = false;
      _clearSearchResultsState();
    });

    _loadOccupiedSlotsForFromDate();
  }

  Future<void> _searchRecurringRides() async {
    final hasOrigin = _origin != null;
    final hasDestination = _destination != null;
    final hasWindowStart = _windowStart != null;
    final hasWindowEnd = _windowEnd != null;
    final selectedWindowStart = _selectedWindowStartDateTimeForFromDay();
    final selectedWindowEnd = _selectedWindowEndDateTimeForFromDay();

    final fromDate = DateTime(
      _passengerFromDate.year,
      _passengerFromDate.month,
      _passengerFromDate.day,
    );
    final untilDate = DateTime(
      _passengerUntilDate.year,
      _passengerUntilDate.month,
      _passengerUntilDate.day,
    );

    final windowError = _validateWindow();

    if (!hasOrigin ||
        !hasDestination ||
        !hasWindowStart ||
        !hasWindowEnd ||
        untilDate.isBefore(fromDate) ||
        windowError != null ||
        selectedWindowStart == null ||
        selectedWindowEnd == null) {
      setState(() {
        _showOriginError = !hasOrigin;
        _showDestinationError = !hasDestination;
        _showFromDateError = false;
        _showUntilDateError = untilDate.isBefore(fromDate);
        _showWindowStartError = !hasWindowStart;
        _showWindowEndError = !hasWindowEnd;
        _showWindowRangeError = windowError != null;
        _windowRangeErrorText = windowError;
        _showSlotConflictError = false;
      });

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content:
                Text('Please complete route, date range, and time window.'),
            backgroundColor: AppColors.error,
          ),
        );
      }
      return;
    }

    if (_loadingOccupiedSlots) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Checking occupied slots. Please try again.'),
            backgroundColor: AppColors.error,
          ),
        );
      }
      return;
    }

    final hasSlotConflict =
        _occupiedSlots.any(_slotConflictsWithSelectedFromDayWindow);
    if (hasSlotConflict) {
      setState(() {
        _showSlotConflictError = true;
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
                'Selected time overlaps with an occupied slot on From Date.'),
            backgroundColor: AppColors.error,
          ),
        );
      }
      return;
    }

    final requestVersion = ++_searchRequestVersion;

    setState(() {
      _isSearching = true;
      _hasSearched = true;
      _results = [];
      _showSlotConflictError = false;
    });

    try {
      final schedules = await _scheduleService.discoverSchedules(
        originLat: _origin!.latLng.latitude,
        originLng: _origin!.latLng.longitude,
        originAddress: _origin!.address,
        destinationLat: _destination!.latLng.latitude,
        destinationLng: _destination!.latLng.longitude,
        destinationAddress: _destination!.address,
        passengerFromDate: _toIsoDate(_passengerFromDate),
        passengerUntilDate: _toIsoDate(_passengerUntilDate),
        departureWindowStart: _toApiTime(_windowStart!),
        departureWindowEnd: _toApiTime(_windowEnd!),
        minSeats: _minSeats,
        driverTotalSeats: _driverTotalSeats,
        maxPrice: _fareEstimate?.farePerSeat,
      );

      if (!mounted || requestVersion != _searchRequestVersion) return;

      final budgetPerSeat = _fareEstimate?.farePerSeat;
      final filtered = schedules.where((schedule) {
        final availableSeats = _toInt(schedule['template_available_seats']);
        final offeredSeats = _toInt(schedule['seats_offered']);
        final seatPrice = _toDouble(schedule['base_price']);

        final meetsSeatsNeeded = availableSeats >= _minSeats;
        final meetsDriverTotal = _driverTotalSeats == null ||
            (offeredSeats > 0 && offeredSeats == _driverTotalSeats);
        final meetsEstimatedBudget =
            budgetPerSeat == null || seatPrice <= budgetPerSeat;

        return meetsSeatsNeeded && meetsDriverTotal && meetsEstimatedBudget;
      }).toList();

      filtered.sort((a, b) {
        final aMatchingDays = _toInt(a['matching_days_count']);
        final bMatchingDays = _toInt(b['matching_days_count']);
        final matchingDaysCompare = bMatchingDays.compareTo(aMatchingDays);
        if (matchingDaysCompare != 0) return matchingDaysCompare;

        final aDistance = _toDouble(a['distance_from_origin_km']) +
            _toDouble(a['distance_to_destination_km']);
        final bDistance = _toDouble(b['distance_from_origin_km']) +
            _toDouble(b['distance_to_destination_km']);
        final distanceCompare = aDistance.compareTo(bDistance);
        if (distanceCompare != 0) return distanceCompare;

        final aPrice = _toDouble(a['base_price']);
        final bPrice = _toDouble(b['base_price']);
        return aPrice.compareTo(bPrice);
      });

      setState(() {
        _results = filtered;
      });
    } catch (e) {
      if (!mounted || requestVersion != _searchRequestVersion) return;
      final message = e is DioException
          ? extractError(e)
          : 'Failed to search recurring rides.';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message), backgroundColor: AppColors.error),
      );
    } finally {
      if (mounted && requestVersion == _searchRequestVersion) {
        setState(() {
          _isSearching = false;
        });
      }
    }
  }

  Future<void> _bookRecurringSeries(Map<String, dynamic> result) async {
    final scheduleId = (result['schedule_id'] ?? '').toString();
    if (scheduleId.isEmpty || _origin == null || _destination == null) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Missing recurring schedule or route details.'),
          backgroundColor: AppColors.error,
        ),
      );
      return;
    }

    if (_windowStart == null || _windowEnd == null) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Select From Time and To Time before booking.'),
          backgroundColor: AppColors.error,
        ),
      );
      return;
    }

    setState(() {
      _bookingScheduleIds.add(scheduleId);
    });

    try {
      final payload = await _scheduleService.bookRecurringSeries(
        scheduleId: scheduleId,
        passengerFromDate: _toIsoDate(_passengerFromDate),
        passengerUntilDate: _toIsoDate(_passengerUntilDate),
        departureWindowStart: _toApiTime(_windowStart!),
        departureWindowEnd: _toApiTime(_windowEnd!),
        seatsReserved: _minSeats,
        pickupLat: _origin!.latLng.latitude,
        pickupLng: _origin!.latLng.longitude,
        pickupAddress: _origin!.address,
        dropoffLat: _destination!.latLng.latitude,
        dropoffLng: _destination!.latLng.longitude,
        dropoffAddress: _destination!.address,
      );

      if (!mounted) return;

      final bookedInstances = _toInt(payload['bookings_created']);
      final matchingInstances = _toInt(payload['matching_days_count']);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Recurring ride booked. $bookedInstances/$matchingInstances instances linked.',
          ),
          backgroundColor: AppColors.success,
        ),
      );

      setState(() {
        _results.removeWhere(
          (item) => (item['schedule_id'] ?? '').toString() == scheduleId,
        );
      });
      _loadOccupiedSlotsForFromDate();
    } catch (e) {
      if (!mounted) return;

      final message = e is DioException
          ? extractError(e)
          : 'Failed to book recurring ride.';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message), backgroundColor: AppColors.error),
      );
    } finally {
      if (mounted) {
        setState(() {
          _bookingScheduleIds.remove(scheduleId);
        });
      }
    }
  }

  void _clearSearchResultsState() {
    _searchRequestVersion++;
    _hasSearched = false;
    _results = [];
    _isSearching = false;
    _showSlotConflictError = false;
    _bookingScheduleIds.clear();
  }

  String _dateKeyUtc(DateTime dt) {
    final utc = dt.toUtc();
    final m = utc.month.toString().padLeft(2, '0');
    final d = utc.day.toString().padLeft(2, '0');
    return '${utc.year}-$m-$d';
  }

  String _dateKeyLocal(DateTime dt) {
    final m = dt.month.toString().padLeft(2, '0');
    final d = dt.day.toString().padLeft(2, '0');
    return '${dt.year}-$m-$d';
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

  DateTime _withTime(DateTime day, TimeOfDay time) {
    return DateTime(
      day.year,
      day.month,
      day.day,
      time.hour,
      time.minute,
    );
  }

  DateTime? _selectedWindowStartDateTimeForFromDay() {
    final start = _windowStart;
    if (start == null) return null;
    return _withTime(_passengerFromDate, start);
  }

  DateTime? _selectedWindowEndDateTimeForFromDay() {
    final end = _windowEnd;
    if (end == null) return null;
    return _withTime(_passengerFromDate, end);
  }

  bool _slotConflictsWithSelectedFromDayWindow(Map<String, dynamic> slot) {
    final startRaw = slot['start_time']?.toString();
    final endRaw = slot['end_time']?.toString();
    final slotStart = startRaw != null ? DateTime.tryParse(startRaw) : null;
    final slotEnd = endRaw != null ? DateTime.tryParse(endRaw) : null;
    if (slotStart == null || slotEnd == null) return false;

    // Conflict barrier is evaluated against the selected From Date.
    final selectedStart = _selectedWindowStartDateTimeForFromDay();
    final selectedEnd = _selectedWindowEndDateTimeForFromDay();
    if (selectedStart == null || selectedEnd == null) return false;

    final selectedStartUtc = selectedStart.toUtc();
    final selectedEndUtc = selectedEnd.toUtc();
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
    final source = (slot['source']?.toString() ?? '').trim().toLowerCase();
    if (source == 'ride_request') return 'Ride Request';
    if (source == 'passenger_booking' || source == 'passenger_booking_legacy') {
      return 'Booked Ride';
    }
    return 'Occupied Slot';
  }

  Future<void> _loadOccupiedSlotsForFromDate() async {
    final requestVersion = ++_slotsRequestVersion;

    if (mounted) {
      setState(() {
        _loadingOccupiedSlots = true;
        _showSlotConflictError = false;
      });
    }

    try {
      final selectedFromDate = DateTime(
        _passengerFromDate.year,
        _passengerFromDate.month,
        _passengerFromDate.day,
      );

      final localDateKey = _dateKeyLocal(selectedFromDate);
      final utcDateKey = _dateKeyUtc(selectedFromDate);
      final timezoneOffsetMinutes = selectedFromDate.timeZoneOffset.inMinutes;

      var slots = await _rideService.getMyOccupiedSlots(
        targetDate: localDateKey,
        mode: 'passenger',
        timezoneOffsetMinutes: timezoneOffsetMinutes,
      );

      slots = _slotsForSelectedLocalDay(slots, selectedFromDate);

      if (slots.isEmpty && localDateKey != utcDateKey) {
        final utcSlots = await _rideService.getMyOccupiedSlots(
          targetDate: utcDateKey,
          mode: 'passenger',
        );
        slots = _slotsForSelectedLocalDay(
          _mergeSlotsByWindow(slots, utcSlots),
          selectedFromDate,
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

  Future<void> _calculateFare() async {
    if (_origin == null || _destination == null) {
      _fareRequestVersion++;
      if (!mounted) return;

      setState(() {
        _fareEstimate = null;
        _fareLoading = false;
        _routeDetails = null;
      });
      return;
    }

    final requestVersion = ++_fareRequestVersion;
    if (mounted) {
      setState(() => _fareLoading = true);
    }

    try {
      final directions = await _mapsService.getDirections(
        origin: _origin!.latLng,
        destination: _destination!.latLng,
        originPlaceId: _origin!.placeId,
        destinationPlaceId: _destination!.placeId,
      );

      if (!mounted || requestVersion != _fareRequestVersion) return;

      final bestRoute = directions?.bestRoute;
      if (bestRoute == null) {
        setState(() {
          _routeDetails = null;
          _fareEstimate = null;
          _fareLoading = false;
        });
        return;
      }

      final distanceKm = bestRoute.distanceKm;
      final durationMinutes = bestRoute.durationMinutes.toDouble();
      final totalSeats = _minSeats.clamp(1, 8).toInt();

      FareEstimate estimate;
      try {
        final serverFare = await _rideService.getFareEstimate(
          distanceKm: distanceKm,
          durationMinutes: durationMinutes,
          totalSeats: totalSeats,
        );

        if (!mounted || requestVersion != _fareRequestVersion) return;

        final serverDistance = _toDouble(serverFare['distance_km']);
        final serverSeatsRaw = _toInt(serverFare['total_seats']);
        final seatsForEstimate =
            (serverSeatsRaw > 0 ? serverSeatsRaw : totalSeats)
                .clamp(1, 8)
                .toInt();
        final farePerSeat = _toDouble(serverFare['fare_per_seat']);
        if (farePerSeat <= 0) {
          throw Exception('Invalid server fare payload');
        }

        estimate = FareEstimate(
          distanceKm: serverDistance > 0 ? serverDistance : distanceKm,
          totalSeats: seatsForEstimate,
          fuelCostRaw: _toDouble(serverFare['fuel_cost_raw']),
          timeCost: _toDouble(serverFare['time_cost']),
          durationMinutes: _toDouble(serverFare['duration_minutes']),
          baseFare: _toDouble(serverFare['base_fare']),
          platformFee: _toDouble(serverFare['platform_fee']),
          totalFare: _toDouble(serverFare['total_fare']),
          farePerSeat: farePerSeat,
          petrolPriceUsed: _toDouble(serverFare['petrol_price_used']),
          fuelAverageUsed: _toDouble(serverFare['fuel_average_used']),
        );
      } catch (_) {
        estimate = FareCalculator.estimate(
          distanceKm: distanceKm,
          durationMinutes: durationMinutes,
          totalSeats: totalSeats,
        );
      }

      if (!mounted || requestVersion != _fareRequestVersion) return;

      setState(() {
        _routeDetails = bestRoute;
        _fareEstimate = estimate;
        _fareLoading = false;
      });
    } catch (_) {
      if (!mounted || requestVersion != _fareRequestVersion) return;

      setState(() {
        _routeDetails = null;
        _fareEstimate = null;
        _fareLoading = false;
      });
    }
  }

  String? _validateWindow() {
    final start = _windowStart;
    final end = _windowEnd;
    if (start == null || end == null) return null;

    final startMinutes = (start.hour * 60) + start.minute;
    final endMinutes = (end.hour * 60) + end.minute;

    if (endMinutes <= startMinutes) {
      return 'To Time must be after From Time.';
    }
    return null;
  }

  void _returnToMap() {
    setState(() {
      _isDetailsStep = false;
      _clearSearchResultsState();
      _showOriginError = false;
      _showDestinationError = false;
      _showFromDateError = false;
      _showUntilDateError = false;
      _showWindowStartError = false;
      _showWindowEndError = false;
      _showWindowRangeError = false;
      _windowRangeErrorText = null;
      _fareEstimate = null;
      _fareLoading = false;
      _routeDetails = null;
      _occupiedSlots = [];
      _loadingOccupiedSlots = false;
      _showSlotConflictError = false;
    });
  }

  String _formatDate(DateTime value) {
    final day = value.day.toString().padLeft(2, '0');
    final month = value.month.toString().padLeft(2, '0');
    return '$day/$month/${value.year}';
  }

  String _formatTime(TimeOfDay value) {
    final hour = value.hour;
    final minute = value.minute.toString().padLeft(2, '0');
    final period = hour >= 12 ? 'PM' : 'AM';
    final h12 = hour > 12 ? hour - 12 : (hour == 0 ? 12 : hour);
    return '$h12:$minute $period';
  }

  String _toIsoDate(DateTime value) {
    final month = value.month.toString().padLeft(2, '0');
    final day = value.day.toString().padLeft(2, '0');
    return '${value.year}-$month-$day';
  }

  String _toApiTime(TimeOfDay value) {
    final hour = value.hour.toString().padLeft(2, '0');
    final minute = value.minute.toString().padLeft(2, '0');
    return '$hour:$minute:00';
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) {
      return Map<String, dynamic>.from(value);
    }
    return const <String, dynamic>{};
  }

  int _toInt(dynamic value) {
    if (value is int) return value;
    return int.tryParse((value ?? '').toString()) ?? 0;
  }

  double _toDouble(dynamic value) {
    if (value is num) return value.toDouble();
    return double.tryParse((value ?? '').toString()) ?? 0.0;
  }

  List<String> _toStringList(dynamic value) {
    if (value is List) {
      return value
          .map((item) => item.toString().trim())
          .where((item) => item.isNotEmpty)
          .toList();
    }
    return const <String>[];
  }

  String _formatProximityKm(double distanceKm) {
    if (distanceKm > 0 && distanceKm < 0.1) {
      return '<0.1 km';
    }
    return '${distanceKm.toStringAsFixed(1)} km';
  }

  String _buildProximitySummary(double fromDistance, double toDistance) {
    return 'P ${_formatProximityKm(fromDistance)} • D ${_formatProximityKm(toDistance)}';
  }
}
