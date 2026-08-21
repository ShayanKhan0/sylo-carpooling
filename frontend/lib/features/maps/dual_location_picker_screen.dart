import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:geolocator/geolocator.dart';
import 'package:pointer_interceptor/pointer_interceptor.dart';
import 'package:uuid/uuid.dart';
import '../../core/constants/app_constants.dart';
import '../../core/theme/app_colors.dart';
import '../../core/services/maps_service.dart';
import '../../core/utils/live_location_marker_icon.dart';
import '../dashboard/home_design_system.dart';
import 'location_picker_screen.dart'; // for PickedLocation

/// Result returned by [DualLocationPickerScreen].
class DualPickResult {
  final PickedLocation? origin;
  final PickedLocation? destination;
  const DualPickResult({this.origin, this.destination});
}

/// Which slot is currently being edited on the map.
enum _ActiveSlot { origin, destination }

/// Full-screen map picker for setting BOTH pickup and dropoff in one screen.
///
/// - Tap the "From" or "To" chip at the top to switch which location is active.
/// - Drag the map (or search) to set the active location.
/// - Both locations are summarised in the bottom card.
/// - Returns [DualPickResult] via [Navigator.pop].
class DualLocationPickerScreen extends StatefulWidget {
  final PickedLocation? initialOrigin;
  final PickedLocation? initialDestination;
  final ValueChanged<DualPickResult>? onLocationsConfirmed;
  final bool showBackButton;

  const DualLocationPickerScreen({
    super.key,
    this.initialOrigin,
    this.initialDestination,
    this.onLocationsConfirmed,
    this.showBackButton = true,
  });

  @override
  State<DualLocationPickerScreen> createState() =>
      _DualLocationPickerScreenState();
}

class _DualLocationPickerScreenState extends State<DualLocationPickerScreen> {
  GoogleMapController? _mapController;
  final DraggableScrollableController _sheetController =
      DraggableScrollableController();
  final Object _myLocationHeroTag = Object();
  final MapsService _mapsService = MapsService();
  final TextEditingController _searchCtrl = TextEditingController();
  final FocusNode _searchFocus = FocusNode();

  _ActiveSlot _active = _ActiveSlot.origin;

  // Confirmed locations
  PickedLocation? _origin;
  PickedLocation? _destination;

  // Current camera center (tracks the active slot while dragging)
  late LatLng _cameraCenter;

  // Address being resolved for the pin
  String _pinAddress = 'Move the map to select location';
  String? _pinName;
  String? _pinPlaceId;
  bool _isResolvingAddress = false;

  // Autocomplete state
  List<PlacePrediction> _predictions = [];
  bool _isSearching = false;
  Timer? _debounce;
  String _sessionToken = const Uuid().v4();

  // Track whether the camera was moved by selecting a prediction (skip reverse geocode)
  bool _skipNextCameraIdle = false;
  double _sheetExtent = 0.22;

  bool _locationServiceEnabled = false;
  bool _hasLocationPermission = false;
  LatLng? _currentLocation;
  BitmapDescriptor? _webLiveLocationIcon;

  @override
  void initState() {
    super.initState();
    _origin = widget.initialOrigin;
    _destination = widget.initialDestination;

    // Start the camera at whichever initial location is available
    final start = widget.initialOrigin?.latLng ??
        widget.initialDestination?.latLng ??
        const LatLng(AppConstants.defaultLat, AppConstants.defaultLng);
    _cameraCenter = start;

    // Pre-populate pin address from initial value for active slot
    _pinAddress =
        widget.initialOrigin?.address ?? 'Move the map to pin a location';

    _sheetController.addListener(_onSheetExtentChanged);
    _loadWebLiveLocationIcon();
    _initializeLocationLayer();
  }

  Future<void> _loadWebLiveLocationIcon() async {
    if (!kIsWeb) return;
    final icon = await LiveLocationMarkerIcon.forWeb();
    if (!mounted) return;
    setState(() => _webLiveLocationIcon = icon);
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchCtrl.dispose();
    _searchFocus.dispose();
    if (!kIsWeb) {
      _mapController?.dispose();
    }
    _sheetController.removeListener(_onSheetExtentChanged);
    _sheetController.dispose();
    super.dispose();
  }

  void _onSheetExtentChanged() {
    if (!mounted) return;
    final next = _sheetController.size;
    if ((next - _sheetExtent).abs() < 0.001) return;
    setState(() => _sheetExtent = next);
  }

  // ─── Switch active slot ────────────────────────────────────────────────────

  void _switchSlot(_ActiveSlot slot) {
    if (_active == slot) return;
    setState(() {
      _active = slot;
      _searchCtrl.clear();
      _predictions = [];
      final pref = slot == _ActiveSlot.origin ? _origin : _destination;
      _pinAddress = pref?.address ?? 'Move the map to pin a location';
      _pinName = pref?.name;
      _pinPlaceId = pref?.placeId;
    });
    // Fly camera to the other slot's location if it was already set
    final target =
        slot == _ActiveSlot.origin ? _origin?.latLng : _destination?.latLng;
    if (target != null) {
      _skipNextCameraIdle = true;
      _mapController?.animateCamera(
        CameraUpdate.newCameraPosition(
            CameraPosition(target: target, zoom: 15)),
      );
      _cameraCenter = target;
    }
  }

  // ─── Map camera events ─────────────────────────────────────────────────────

  void _onCameraMove(CameraPosition pos) {
    _cameraCenter = pos.target;
  }

  Future<void> _onCameraIdle() async {
    if (_skipNextCameraIdle) {
      _skipNextCameraIdle = false;
      return;
    }
    _searchFocus.unfocus();
    _reverseGeocode(_cameraCenter);
  }

  Future<void> _reverseGeocode(LatLng pos) async {
    if (mounted) setState(() => _isResolvingAddress = true);
    try {
      final addr = await _mapsService.getAddressFromLatLng(pos);
      if (mounted) {
        setState(() {
          _pinAddress = addr ??
              '${pos.latitude.toStringAsFixed(4)}, ${pos.longitude.toStringAsFixed(4)}';
          _pinName = null;
          _pinPlaceId = null;
          _isResolvingAddress = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _pinAddress =
              '${pos.latitude.toStringAsFixed(4)}, ${pos.longitude.toStringAsFixed(4)}';
          _isResolvingAddress = false;
        });
      }
    }
  }

  // ─── Search ────────────────────────────────────────────────────────────────

  void _onSearchChanged(String query) {
    _debounce?.cancel();
    if (query.trim().isEmpty) {
      setState(() {
        _predictions = [];
        _isSearching = false;
      });
      return;
    }

    setState(() => _isSearching = true);
    _debounce = Timer(const Duration(milliseconds: 400), () async {
      final results = await _mapsService.searchPlaces(
        query,
        location: _cameraCenter,
        sessionToken: _sessionToken,
      );
      if (mounted) {
        setState(() {
          _predictions = results;
          _isSearching = false;
        });
      }
    });
  }

  Future<void> _selectPrediction(PlacePrediction prediction) async {
    _searchFocus.unfocus();
    setState(() {
      _predictions = [];
      _searchCtrl.clear();
      _isResolvingAddress = true;
    });

    final detail = await _mapsService.getPlaceDetails(
      prediction.placeId,
      sessionToken: _sessionToken,
    );
    _sessionToken = const Uuid().v4();

    if (detail != null && mounted) {
      final picked = PickedLocation(
        latLng: detail.location,
        address: detail.address,
        name: detail.name,
        placeId: prediction.placeId,
      );
      setState(() {
        _pinAddress = detail.address;
        _pinName = detail.name;
        _pinPlaceId = prediction.placeId;
        _cameraCenter = detail.location;
        _isResolvingAddress = false;
        if (_active == _ActiveSlot.origin) {
          _origin = picked;
        } else {
          _destination = picked;
        }
      });
      _skipNextCameraIdle = true;
      _mapController?.animateCamera(
        CameraUpdate.newCameraPosition(
          CameraPosition(target: detail.location, zoom: 16),
        ),
      );
    } else if (mounted) {
      setState(() => _isResolvingAddress = false);
    }
  }

  // ─── Confirm pin for active slot ───────────────────────────────────────────

  Future<void> _confirmPin() async {
    final currentSelection = _cameraCenter;
    var finalLocation = currentSelection;
    var finalAddress = _pinAddress;

    if (mounted) {
      setState(() => _isResolvingAddress = true);
    }

    try {
      final snapped = await _mapsService.snapToNearestRoad(currentSelection);
      if (snapped != null) {
        finalLocation = snapped;
        final snappedAddress = await _mapsService.getAddressFromLatLng(snapped);
        if (snappedAddress != null && snappedAddress.isNotEmpty) {
          finalAddress = snappedAddress;
        } else {
          finalAddress =
              '${snapped.latitude.toStringAsFixed(4)}, ${snapped.longitude.toStringAsFixed(4)}';
        }
      }
    } catch (_) {
      // Keep original picked location if snap-to-road is unavailable.
    }

    if (!mounted) return;

    final picked = PickedLocation(
      latLng: finalLocation,
      address: finalAddress,
      name: _pinName,
      // Map-confirmed picks should route by snapped lat/lng, not place_id.
      placeId: null,
    );

    setState(() {
      _cameraCenter = finalLocation;
      _pinAddress = finalAddress;
      _isResolvingAddress = false;

      if (_active == _ActiveSlot.origin) {
        _origin = picked;
        // Auto-switch to destination if not set yet
        if (_destination == null) {
          _active = _ActiveSlot.destination;
          _pinAddress = 'Move the map to pin a location';
          _pinName = null;
          _pinPlaceId = null;
        }
      } else {
        _destination = picked;
      }
    });

    _skipNextCameraIdle = true;
    _mapController?.animateCamera(
      CameraUpdate.newCameraPosition(
        CameraPosition(target: finalLocation, zoom: 16),
      ),
    );
  }

  // ─── My Location ───────────────────────────────────────────────────────────

  Future<void> _initializeLocationLayer() async {
    final granted = await _ensureLocationPermission(requestIfDenied: true);
    if (!granted) return;
    await _refreshCurrentLocation(
      moveCamera: _origin == null && _destination == null,
    );
  }

  Future<bool> _ensureLocationPermission({
    bool requestIfDenied = false,
  }) async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      if (mounted) {
        setState(() {
          _locationServiceEnabled = false;
          _hasLocationPermission = false;
        });
      }
      return false;
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied && requestIfDenied) {
      permission = await Geolocator.requestPermission();
    }

    final granted = permission == LocationPermission.always ||
        permission == LocationPermission.whileInUse;

    if (mounted) {
      setState(() {
        _locationServiceEnabled = serviceEnabled;
        _hasLocationPermission = granted;
      });
    }
    return granted;
  }

  Future<void> _refreshCurrentLocation({bool moveCamera = false}) async {
    try {
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 10),
        ),
      );
      final latLng = LatLng(pos.latitude, pos.longitude);

      if (!mounted) return;
      setState(() {
        _currentLocation = latLng;
        if (moveCamera) _cameraCenter = latLng;
      });

      if (moveCamera) {
        _mapController?.animateCamera(
          CameraUpdate.newCameraPosition(
            CameraPosition(target: latLng, zoom: 16),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Location error: $e')),
        );
      }
    }
  }

  Future<void> _goToCurrentLocation() async {
    final granted = await _ensureLocationPermission(requestIfDenied: true);
    if (!granted) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
              content: Text('Enable location permission to use this feature')),
        );
      }
      return;
    }

    await _refreshCurrentLocation(moveCamera: true);
    if (_currentLocation != null) {
      _reverseGeocode(_currentLocation!);
    }
  }

  // ─── Final confirm ─────────────────────────────────────────────────────────

  void _onConfirm() {
    final result = DualPickResult(origin: _origin, destination: _destination);
    final callback = widget.onLocationsConfirmed;
    if (callback != null) {
      callback(result);
      return;
    }
    Navigator.pop(context, result);
  }

  Widget _interceptPointer(Widget child) {
    return PointerInterceptor(child: child);
  }

  // ─── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    const lightGreen = Color(0xFF6DF0B3);
    const darkGreen = Color(0xFF2FAF6F);
    final activeColor = _active == _ActiveSlot.origin ? lightGreen : darkGreen;
    final screenHeight = MediaQuery.of(context).size.height;
    final fabBottom = (screenHeight * _sheetExtent) + 12;

    return Scaffold(
      backgroundColor: Colors.transparent,
      resizeToAvoidBottomInset: false,
      body: Stack(
        children: [
          HomeDesignSystem.driverHomeSoftWhiteBackground(),
          // ── Google Map ──────────────────────────────────────────────────
          GoogleMap(
            initialCameraPosition: CameraPosition(
              target: _cameraCenter,
              zoom: AppConstants.defaultZoom,
            ),
            onMapCreated: (c) => _mapController = c,
            onCameraMove: _onCameraMove,
            onCameraIdle: _onCameraIdle,
            myLocationEnabled:
                !kIsWeb && _hasLocationPermission && _locationServiceEnabled,
            myLocationButtonEnabled: false,
            zoomControlsEnabled: false,
            mapToolbarEnabled: false,
            compassEnabled: true,
            markers: {
              if (_currentLocation != null && kIsWeb)
                Marker(
                  markerId: const MarkerId('currentLocationFallback'),
                  position: _currentLocation!,
                  icon: _webLiveLocationIcon ??
                      BitmapDescriptor.defaultMarkerWithHue(
                          BitmapDescriptor.hueAzure),
                  zIndexInt: 0,
                ),
              if (_origin != null && _active != _ActiveSlot.origin)
                Marker(
                  markerId: const MarkerId('origin'),
                  position: _origin!.latLng,
                  icon: BitmapDescriptor.defaultMarkerWithHue(120),
                  infoWindow: InfoWindow(
                    title: 'Pickup',
                    snippet: _origin!.address,
                  ),
                ),
              if (_destination != null && _active != _ActiveSlot.destination)
                Marker(
                  markerId: const MarkerId('destination'),
                  position: _destination!.latLng,
                  icon: BitmapDescriptor.defaultMarkerWithHue(95),
                  infoWindow: InfoWindow(
                    title: 'Dropoff',
                    snippet: _destination!.address,
                  ),
                ),
            },
            circles: {
              if (_currentLocation != null && kIsWeb)
                Circle(
                  circleId: const CircleId('currentLocationAura'),
                  center: _currentLocation!,
                  radius: 18,
                  fillColor: const Color(0xFF6DF0B3).withValues(alpha: 0.22),
                  strokeColor: const Color(0xFF2FAF6F).withValues(alpha: 0.70),
                  strokeWidth: 1,
                ),
            },
          ),

          // ── Centre pin (active slot) ────────────────────────────────────
          Center(
            child: Padding(
              padding: const EdgeInsets.only(bottom: 36),
              child: Icon(
                Icons.location_on,
                color: activeColor,
                size: 48,
                shadows: [
                  Shadow(
                    color: Colors.black.withValues(alpha: 0.3),
                    blurRadius: 8,
                    offset: const Offset(0, 3),
                  ),
                ],
              ),
            ),
          ),
          // Pin shadow dot
          Center(
            child: Container(
              width: 8,
              height: 8,
              margin: const EdgeInsets.only(top: 12),
              decoration: BoxDecoration(
                color: Colors.black.withValues(alpha: 0.3),
                shape: BoxShape.circle,
              ),
            ),
          ),

          // ── Top overlay: back + slot selector + search ─────────────────
          _interceptPointer(
            SafeArea(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Row: back button + slot tabs
                  Padding(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    child: Row(
                      children: [
                        if (widget.showBackButton) ...[
                          // Back button
                          Container(
                            decoration: BoxDecoration(
                              color: const Color(0xFF0C241B)
                                  .withValues(alpha: 0.96),
                              shape: BoxShape.circle,
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withValues(alpha: 0.28),
                                  blurRadius: 10,
                                  offset: const Offset(0, 3),
                                )
                              ],
                            ),
                            child: IconButton(
                              icon: const Icon(Icons.arrow_back_rounded,
                                  color: Color(0xFFE9FFF5)),
                              onPressed: () => Navigator.pop(context),
                            ),
                          ),
                          const SizedBox(width: 10),
                        ],
                        // Slot chips
                        Expanded(
                          child: Container(
                            padding: const EdgeInsets.all(4),
                            decoration: BoxDecoration(
                              gradient: const LinearGradient(
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                                colors: [
                                  Color(0xFF264E42),
                                  Color(0xFF1A3A31),
                                ],
                              ),
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(
                                color: const Color(0xFFD7FFE8)
                                    .withValues(alpha: 0.45),
                              ),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withValues(alpha: 0.2),
                                  blurRadius: 10,
                                  offset: const Offset(0, 3),
                                )
                              ],
                            ),
                            child: Row(
                              children: [
                                _slotChip(_ActiveSlot.origin, 'From',
                                    _origin?.address, lightGreen),
                                const SizedBox(width: 4),
                                _slotChip(_ActiveSlot.destination, 'To',
                                    _destination?.address, darkGreen),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),

                  // Search field
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 16),
                    child: Container(
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [
                            Color(0xFF264E42),
                            Color(0xFF1A3A31),
                          ],
                        ),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color:
                              const Color(0xFFD7FFE8).withValues(alpha: 0.45),
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.2),
                            blurRadius: 10,
                            offset: const Offset(0, 3),
                          )
                        ],
                      ),
                      child: TextField(
                        controller: _searchCtrl,
                        focusNode: _searchFocus,
                        onChanged: _onSearchChanged,
                        decoration: InputDecoration(
                          hintText: _active == _ActiveSlot.origin
                              ? 'Search pickup location…'
                              : 'Search destination…',
                          hintStyle: TextStyle(
                            color: activeColor,
                            fontWeight: FontWeight.w600,
                          ),
                          prefixIcon: Icon(Icons.search, color: activeColor),
                          suffixIcon: _searchCtrl.text.isNotEmpty
                              ? IconButton(
                                  icon: const Icon(Icons.clear, size: 18),
                                  onPressed: () {
                                    _searchCtrl.clear();
                                    setState(() => _predictions = []);
                                  },
                                )
                              : null,
                          border: InputBorder.none,
                          contentPadding: const EdgeInsets.symmetric(
                              horizontal: 16, vertical: 12),
                        ),
                        style: const TextStyle(
                          color: Color(0xFF1F6F4B),
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 4),

                  // Predictions / searching indicator
                  if (_isSearching)
                    Container(
                      margin: const EdgeInsets.symmetric(horizontal: 16),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 20, vertical: 12),
                      decoration: BoxDecoration(
                        color: const Color(0xFF0C241B).withValues(alpha: 0.96),
                        borderRadius: BorderRadius.circular(14),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.22),
                            blurRadius: 8,
                          )
                        ],
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                                strokeWidth: 2, color: activeColor),
                          ),
                          const SizedBox(width: 10),
                          const Text('Searching…',
                              style: TextStyle(color: Color(0xFFE9FFF5))),
                        ],
                      ),
                    ),

                  if (_predictions.isNotEmpty)
                    Container(
                      margin: const EdgeInsets.symmetric(horizontal: 16),
                      constraints: const BoxConstraints(maxHeight: 260),
                      decoration: BoxDecoration(
                        color: const Color(0xFF0C241B).withValues(alpha: 0.98),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: const Color(0xFFD7FFE8).withValues(alpha: 0.3),
                        ),
                        boxShadow: [
                          BoxShadow(
                              color: Colors.black.withValues(alpha: 0.25),
                              blurRadius: 12,
                              offset: const Offset(0, 4))
                        ],
                      ),
                      child: ListView.separated(
                        shrinkWrap: true,
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        itemCount: _predictions.length,
                        separatorBuilder: (_, __) => Divider(
                            height: 1,
                            indent: 56,
                            color: Colors.white.withValues(alpha: 0.12)),
                        itemBuilder: (_, i) {
                          final p = _predictions[i];
                          return ListTile(
                            dense: true,
                            leading: Icon(Icons.location_on_outlined,
                                color: activeColor, size: 20),
                            title: Text(p.mainText,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600,
                                    fontSize: 14,
                                    color: Color(0xFFF4FFF8))),
                            subtitle: Text(
                              p.secondaryText,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                  color: Colors.white.withValues(alpha: 0.68),
                                  fontSize: 12),
                            ),
                            onTap: () => _selectPrediction(p),
                          );
                        },
                      ),
                    ),
                ],
              ),
            ),
          ),

          // ── My Location FAB ────────────────────────────────────────────
          AnimatedPositioned(
            duration: const Duration(milliseconds: 120),
            curve: Curves.easeOut,
            right: 16,
            bottom: fabBottom,
            child: _interceptPointer(
              FloatingActionButton.small(
                heroTag: _myLocationHeroTag,
                backgroundColor: const Color(0xFF43E892),
                onPressed: _goToCurrentLocation,
                child: const Icon(Icons.gps_fixed_rounded,
                    color: Color(0xFF032417), size: 22),
              ),
            ),
          ),

          // ── Bottom panel (draggable) ──────────────────────────────────
          DraggableScrollableSheet(
            controller: _sheetController,
            initialChildSize: 0.22,
            minChildSize: 0.08,
            maxChildSize: 0.50,
            snap: true,
            snapSizes: const [0.08, 0.22, 0.50],
            builder: (ctx, scrollController) {
              return _interceptPointer(
                Container(
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFE4F2E9),
                    borderRadius:
                        const BorderRadius.vertical(top: Radius.circular(24)),
                    boxShadow: [
                      BoxShadow(
                          color: AppColors.shadowDark,
                          blurRadius: 16,
                          offset: const Offset(0, -4)),
                    ],
                  ),
                  child: SingleChildScrollView(
                    controller: scrollController,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // Drag handle
                        Container(
                          width: 40,
                          height: 4,
                          decoration: BoxDecoration(
                              color: AppColors.border,
                              borderRadius: BorderRadius.circular(2)),
                        ),
                        const SizedBox(height: 12),

                        // Joined pickup + destination card
                        Container(
                          decoration: BoxDecoration(
                            gradient: const LinearGradient(
                              begin: Alignment.topLeft,
                              end: Alignment.bottomRight,
                              colors: [
                                Color(0xFF264E42),
                                Color(0xFF1A3A31),
                              ],
                            ),
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(
                              color: const Color(0xFF43E892)
                                  .withValues(alpha: 0.18),
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: const Color(0xFF031009)
                                    .withValues(alpha: 0.24),
                                blurRadius: 14,
                                offset: const Offset(0, 6),
                              ),
                            ],
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(14),
                            child: Stack(
                              children: [
                                Positioned(
                                  left: 0,
                                  top: 0,
                                  bottom: 0,
                                  child: Container(
                                    width: 7,
                                    decoration: BoxDecoration(
                                      color: const Color(0xFF43E892),
                                      boxShadow: [
                                        BoxShadow(
                                          color: const Color(0xFF43E892)
                                              .withValues(alpha: 0.4),
                                          blurRadius: 10,
                                          spreadRadius: 0.3,
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                                Padding(
                                  padding:
                                      const EdgeInsets.fromLTRB(14, 12, 14, 12),
                                  child: Stack(
                                    children: [
                                      Positioned(
                                        left: 9,
                                        top: 28,
                                        bottom: 28,
                                        child: Container(
                                          width: 2,
                                          decoration: BoxDecoration(
                                            color: const Color(0xFF43E892)
                                                .withValues(alpha: 0.62),
                                            borderRadius:
                                                BorderRadius.circular(999),
                                          ),
                                        ),
                                      ),
                                      Column(
                                        children: [
                                          _joinedLocationRow(
                                            label: 'PICKUP POINT',
                                            address: _active ==
                                                    _ActiveSlot.origin
                                                ? _pinAddress
                                                : (_origin?.address ??
                                                    'Move map to pin pickup'),
                                            icon: Icons
                                                .radio_button_checked_rounded,
                                            color: const Color(0xFF43E892),
                                            isActive:
                                                _active == _ActiveSlot.origin,
                                            isSet: _origin != null,
                                            onTap: () =>
                                                _switchSlot(_ActiveSlot.origin),
                                            onSetPressed: !_isResolvingAddress
                                                ? () {
                                                    _switchSlot(
                                                        _ActiveSlot.origin);
                                                    _confirmPin();
                                                  }
                                                : null,
                                          ),
                                          const SizedBox(height: 10),
                                          Divider(
                                            color: const Color(0xFFEEFFF5)
                                                .withValues(alpha: 0.18),
                                            height: 1,
                                          ),
                                          const SizedBox(height: 10),
                                          _joinedLocationRow(
                                            label: 'DESTINATION',
                                            address: _active ==
                                                    _ActiveSlot.destination
                                                ? _pinAddress
                                                : (_destination?.address ??
                                                    'Move map to pin destination'),
                                            icon: Icons.location_on_rounded,
                                            color: const Color(0xFF43E892),
                                            isActive: _active ==
                                                _ActiveSlot.destination,
                                            isSet: _destination != null,
                                            onTap: () => _switchSlot(
                                                _ActiveSlot.destination),
                                            onSetPressed: !_isResolvingAddress
                                                ? () {
                                                    _switchSlot(_ActiveSlot
                                                        .destination);
                                                    _confirmPin();
                                                  }
                                                : null,
                                          ),
                                        ],
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 16),

                        // Confirm button
                        _actionPillButton(
                          label: 'CONFIRM LOCATION',
                          icon: Icons.check_circle_rounded,
                          enabled: _origin != null && _destination != null,
                          fullWidth: true,
                          onPressed: _onConfirm,
                        ),
                      ],
                    ),
                  ),
                ),
              );
            },
          ),
        ],
      ),
    );
  }

  // ─── Helper widgets ────────────────────────────────────────────────────────

  Widget _slotChip(
      _ActiveSlot slot, String label, String? address, Color color) {
    final isActive = _active == slot;
    final isSet = (slot == _ActiveSlot.origin ? _origin : _destination) != null;
    return Expanded(
      child: GestureDetector(
        onTap: () => _switchSlot(slot),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
          decoration: BoxDecoration(
            color: isActive
                ? color.withValues(alpha: 0.22)
                : Colors.white.withValues(alpha: 0.05),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: isActive ? color : Colors.white.withValues(alpha: 0.16),
              width: 1.5,
            ),
          ),
          child: Row(
            children: [
              Icon(
                isSet ? Icons.check_circle : Icons.circle_outlined,
                size: 14,
                color: isSet ? color : AppColors.textHint,
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(label,
                        style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w700,
                            color: isActive
                                ? color
                                : const Color(0xFFE9FFF5)
                                    .withValues(alpha: 0.85))),
                    if (address != null)
                      Text(
                        address,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 11,
                          color: Color(0xFFF4FFF8),
                          fontWeight: FontWeight.w600,
                        ),
                      )
                    else
                      Text('Tap to set',
                          style: TextStyle(
                              fontSize: 11,
                              color: const Color(0xFFE9FFF5)
                                  .withValues(alpha: 0.65))),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _joinedLocationRow({
    required String label,
    required String address,
    required IconData icon,
    required Color color,
    required bool isActive,
    required bool isSet,
    required VoidCallback onTap,
    required VoidCallback? onSetPressed,
  }) {
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: onTap,
      child: SizedBox(
        height: 56,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 2),
          child: Row(
            children: [
              Icon(icon, size: 16, color: color),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      label,
                      style: GoogleFonts.inter(
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.8,
                        color: const Color(0xFFECFFF5).withValues(alpha: 0.8),
                      ),
                    ),
                    const SizedBox(height: 2),
                    _isResolvingAddress && isActive
                        ? const SizedBox(
                            height: 14,
                            width: 14,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Color(0xFF43E892),
                            ),
                          )
                        : Text(
                            address,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: GoogleFonts.inter(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                              color: const Color(0xFFF4FFF8),
                            ),
                          ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              _actionPillButton(
                label: 'SET',
                icon: Icons.check_rounded,
                inverted: isSet,
                enabled: onSetPressed != null,
                compact: true,
                onPressed: onSetPressed ?? () {},
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _actionPillButton({
    required String label,
    required IconData icon,
    required VoidCallback onPressed,
    bool enabled = true,
    bool compact = false,
    bool fullWidth = false,
    bool inverted = false,
  }) {
    final buttonHeight = compact ? 34.0 : 46.0;
    final horizontalPadding = compact ? 12.0 : 16.0;
    final bgColor =
        inverted ? const Color(0xFF052E1E) : const Color(0xFF43E892);
    final fgColor =
        inverted ? const Color(0xFF43E892) : const Color(0xFF052E1E);
    final chipColor =
        inverted ? const Color(0xFF43E892) : const Color(0xFF052E1E);
    final chipIconColor =
        inverted ? const Color(0xFF052E1E) : const Color(0xFF43E892);
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 160),
      opacity: enabled ? 1 : 0.45,
      child: Container(
        width: fullWidth ? double.infinity : null,
        height: buttonHeight,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(999),
          border: compact && inverted
              ? Border.all(
                  color: const Color(0xFF43E892).withValues(alpha: 0.7),
                )
              : null,
          boxShadow: enabled
              ? [
                  BoxShadow(
                    color: const Color(0xFF4BF0A1).withValues(alpha: 0.30),
                    blurRadius: compact ? 12 : 18,
                    spreadRadius: compact ? 0.4 : 1.0,
                    offset: const Offset(0, 6),
                  ),
                ]
              : null,
        ),
        child: FilledButton(
          onPressed: enabled ? onPressed : null,
          style: FilledButton.styleFrom(
            backgroundColor: bgColor,
            foregroundColor: fgColor,
            disabledBackgroundColor: bgColor,
            disabledForegroundColor: fgColor,
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(999),
            ),
            padding: EdgeInsets.symmetric(
              horizontal: horizontalPadding,
              vertical: compact ? 8 : 12,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: compact ? 18 : 20,
                height: compact ? 18 : 20,
                decoration: BoxDecoration(
                  color: chipColor,
                  borderRadius: BorderRadius.circular(999),
                ),
                child:
                    Icon(icon, size: compact ? 12 : 14, color: chipIconColor),
              ),
              SizedBox(width: compact ? 7 : 10),
              Text(
                label,
                style: GoogleFonts.inter(
                  fontWeight: FontWeight.w800,
                  fontSize: compact ? 11 : 14,
                  letterSpacing: compact ? 0.9 : 1.2,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
