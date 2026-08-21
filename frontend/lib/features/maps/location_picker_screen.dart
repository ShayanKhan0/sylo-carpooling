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

/// Data returned when user picks a location.
class PickedLocation {
  final LatLng latLng;
  final String address;
  final String? name;
  final String? placeId;

  PickedLocation({
    required this.latLng,
    required this.address,
    this.name,
    this.placeId,
  });

  @override
  String toString() => address;
}

/// Full-screen location picker with:
/// - Google Map with draggable marker
/// - Places Autocomplete search bar
/// - Current-location button
/// - Confirm button with address preview
class LocationPickerScreen extends StatefulWidget {
  final String title; // e.g. "Select Pickup" or "Select Destination"
  final LatLng? initialLocation;

  const LocationPickerScreen({
    super.key,
    this.title = 'Select Location',
    this.initialLocation,
  });

  @override
  State<LocationPickerScreen> createState() => _LocationPickerScreenState();
}

class _LocationPickerScreenState extends State<LocationPickerScreen> {
  GoogleMapController? _mapController;
  final MapsService _mapsService = MapsService();
  final TextEditingController _searchCtrl = TextEditingController();
  final FocusNode _searchFocus = FocusNode();

  late LatLng _selectedLocation;
  String _selectedAddress = 'Move the map to select location';
  String? _selectedName;
  String? _selectedPlaceId;
  bool _isLoadingAddress = false;
  bool _isSearching = false;
  List<PlacePrediction> _predictions = [];
  Timer? _debounce;
  String _sessionToken = const Uuid().v4();
  bool _skipNextCameraIdle = false;
  bool _locationServiceEnabled = false;
  bool _hasLocationPermission = false;
  LatLng? _currentLocation;
  BitmapDescriptor? _webLiveLocationIcon;

  @override
  void initState() {
    super.initState();
    _selectedLocation = widget.initialLocation ??
        const LatLng(AppConstants.defaultLat, AppConstants.defaultLng);
    _reverseGeocode(_selectedLocation);
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
    _mapController?.dispose();
    super.dispose();
  }

  // ─── Reverse Geocode: LatLng → Address ──────────────
  Future<void> _reverseGeocode(LatLng pos) async {
    setState(() => _isLoadingAddress = true);
    try {
      final address = await _mapsService.getAddressFromLatLng(pos);
      if (mounted) {
        setState(() {
          _selectedAddress = address ?? 'Selected location';
          _isLoadingAddress = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _selectedAddress =
              '${pos.latitude.toStringAsFixed(4)}, ${pos.longitude.toStringAsFixed(4)}';
          _isLoadingAddress = false;
        });
      }
    }
  }

  // ─── Search with debounce ───────────────────────────
  void _onSearchChanged(String query) {
    _debounce?.cancel();
    if (query.trim().isEmpty) {
      setState(() {
        _predictions = [];
        _isSearching = false;
      });
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 400), () async {
      setState(() => _isSearching = true);
      final results = await _mapsService.searchPlaces(
        query,
        location: _selectedLocation,
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

  // ─── Select a prediction ───────────────────────────
  Future<void> _selectPrediction(PlacePrediction prediction) async {
    _searchFocus.unfocus();
    setState(() {
      _predictions = [];
      _searchCtrl.text = prediction.mainText;
      _isLoadingAddress = true;
    });

    final detail = await _mapsService.getPlaceDetails(
      prediction.placeId,
      sessionToken: _sessionToken,
    );

    // Generate new session token after detail fetch
    _sessionToken = const Uuid().v4();

    if (detail != null && mounted) {
      setState(() {
        _selectedLocation = detail.location;
        _selectedAddress = detail.address;
        _selectedName = detail.name;
        _selectedPlaceId = prediction.placeId;
        _isLoadingAddress = false;
      });
      _skipNextCameraIdle = true;
      _mapController?.animateCamera(
        CameraUpdate.newCameraPosition(
          CameraPosition(target: detail.location, zoom: 16),
        ),
      );
    }
  }

  // ─── Go to user's current location ─────────────────
  Future<void> _initializeLocationLayer() async {
    final granted = await _ensureLocationPermission(requestIfDenied: true);
    if (!granted) return;
    await _refreshCurrentLocation(
      moveCamera: widget.initialLocation == null,
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
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 10),
        ),
      );

      final latLng = LatLng(position.latitude, position.longitude);
      if (!mounted) return;

      setState(() {
        _currentLocation = latLng;
        if (moveCamera) _selectedLocation = latLng;
      });

      if (moveCamera) {
        _mapController?.animateCamera(
          CameraUpdate.newCameraPosition(
            CameraPosition(target: latLng, zoom: 16),
          ),
        );
        _reverseGeocode(latLng);
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
  }

  // ─── Set / Confirm selection ───────────────────────
  Future<PickedLocation?> _setPinnedLocation() async {
    final currentSelection = _selectedLocation;
    var finalLocation = currentSelection;
    var finalAddress = _selectedAddress;

    if (mounted) {
      setState(() => _isLoadingAddress = true);
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

    if (!mounted) return null;
    final picked = PickedLocation(
      latLng: finalLocation,
      address: finalAddress,
      name: _selectedName,
      // Map-confirmed picks should route by snapped lat/lng, not place_id.
      placeId: null,
    );
    setState(() {
      _selectedLocation = finalLocation;
      _selectedAddress = finalAddress;
      _isLoadingAddress = false;
    });
    _skipNextCameraIdle = true;
    _mapController?.animateCamera(
      CameraUpdate.newCameraPosition(
        CameraPosition(target: finalLocation, zoom: 16),
      ),
    );
    return picked;
  }

  Future<void> _confirmLocation() async {
    final picked = await _setPinnedLocation();
    if (!mounted || picked == null) return;
    Navigator.pop(context, picked);
  }

  Widget _interceptPointer(Widget child) {
    return PointerInterceptor(child: child);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      resizeToAvoidBottomInset: false,
      body: Stack(
        children: [
          // ── Google Map ──────────────────────────────
          GoogleMap(
            initialCameraPosition: CameraPosition(
              target: _selectedLocation,
              zoom: AppConstants.defaultZoom,
            ),
            onMapCreated: (controller) => _mapController = controller,
            onCameraMove: (position) {
              _selectedLocation = position.target;
            },
            onCameraIdle: () {
              if (_skipNextCameraIdle) {
                _skipNextCameraIdle = false;
                return;
              }
              _selectedPlaceId = null;
              _reverseGeocode(_selectedLocation);
            },
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
            },
            circles: {
              if (_currentLocation != null && kIsWeb)
                Circle(
                  circleId: const CircleId('currentLocationAura'),
                  center: _currentLocation!,
                  radius: 18,
                  fillColor: Colors.blue.withValues(alpha: 0.22),
                  strokeColor: Colors.blue.withValues(alpha: 0.65),
                  strokeWidth: 1,
                ),
            },
          ),

          // ── Center pin icon (always at center) ─────
          Center(
            child: Padding(
              padding: const EdgeInsets.only(bottom: 36),
              child: Icon(
                Icons.location_on,
                color: AppColors.error,
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

          // ── Pin shadow dot ─────────────────────────
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

          // ── Search bar + back button ───────────────
          _interceptPointer(
            SafeArea(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Padding(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    child: Row(
                      children: [
                        // Back button
                        Container(
                          decoration: BoxDecoration(
                            color: AppColors.surface,
                            shape: BoxShape.circle,
                            boxShadow: [
                              BoxShadow(
                                  color: AppColors.shadow,
                                  blurRadius: 8,
                                  offset: const Offset(0, 2))
                            ],
                          ),
                          child: IconButton(
                            icon: const Icon(Icons.arrow_back_rounded),
                            onPressed: () => Navigator.pop(context),
                          ),
                        ),
                        const SizedBox(width: 8),
                        // Search field
                        Expanded(
                          child: Container(
                            decoration: BoxDecoration(
                              color: AppColors.surface,
                              borderRadius: BorderRadius.circular(28),
                              boxShadow: [
                                BoxShadow(
                                    color: AppColors.shadow,
                                    blurRadius: 10,
                                    offset: const Offset(0, 3))
                              ],
                            ),
                            child: TextField(
                              controller: _searchCtrl,
                              focusNode: _searchFocus,
                              onChanged: _onSearchChanged,
                              decoration: InputDecoration(
                                hintText:
                                    'Search ${widget.title.toLowerCase()}…',
                                hintStyle: TextStyle(color: AppColors.textHint),
                                prefixIcon: Icon(Icons.search,
                                    color: AppColors.textSecondary),
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
                                    horizontal: 16, vertical: 14),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),

                  // ── Predictions dropdown ─────────────
                  if (_predictions.isNotEmpty)
                    Container(
                      margin: const EdgeInsets.symmetric(horizontal: 24),
                      constraints: const BoxConstraints(maxHeight: 300),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: BorderRadius.circular(16),
                        boxShadow: [
                          BoxShadow(
                              color: AppColors.shadow,
                              blurRadius: 12,
                              offset: const Offset(0, 4))
                        ],
                      ),
                      child: ListView.separated(
                        shrinkWrap: true,
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        itemCount: _predictions.length,
                        separatorBuilder: (_, __) =>
                            const Divider(height: 1, indent: 56),
                        itemBuilder: (context, i) {
                          final p = _predictions[i];
                          return ListTile(
                            dense: true,
                            leading: const Icon(Icons.location_on_outlined,
                                color: AppColors.primary),
                            title: Text(p.mainText,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600, fontSize: 14)),
                            subtitle: Text(p.secondaryText,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                    color: AppColors.textSecondary,
                                    fontSize: 12)),
                            onTap: () => _selectPrediction(p),
                          );
                        },
                      ),
                    ),

                  if (_isSearching)
                    Container(
                      margin: const EdgeInsets.symmetric(horizontal: 24),
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: AppColors.surface,
                        borderRadius: BorderRadius.circular(16),
                        boxShadow: [
                          BoxShadow(color: AppColors.shadow, blurRadius: 8)
                        ],
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: AppColors.primary)),
                          const SizedBox(width: 12),
                          Text('Searching…',
                              style: TextStyle(color: AppColors.textSecondary)),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          ),

          // ── My Location FAB ────────────────────────
          Positioned(
            right: 16,
            bottom: 180,
            child: _interceptPointer(
              FloatingActionButton.small(
                heroTag: 'myLocation',
                backgroundColor: AppColors.surface,
                onPressed: _goToCurrentLocation,
                child: const Icon(Icons.my_location, color: AppColors.primary),
              ),
            ),
          ),

          // ── Bottom address card + confirm ──────────
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: _interceptPointer(
              Container(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius:
                      const BorderRadius.vertical(top: Radius.circular(24)),
                  boxShadow: [
                    BoxShadow(
                        color: AppColors.shadowDark,
                        blurRadius: 16,
                        offset: const Offset(0, -4)),
                  ],
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Drag handle
                    Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: AppColors.border,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: AppColors.primary.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: const Icon(Icons.location_on,
                              color: AppColors.primary, size: 22),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                widget.title,
                                style: TextStyle(
                                    color: AppColors.textSecondary,
                                    fontSize: 12,
                                    fontWeight: FontWeight.w500),
                              ),
                              const SizedBox(height: 4),
                              _isLoadingAddress
                                  ? const SizedBox(
                                      height: 14,
                                      width: 14,
                                      child: CircularProgressIndicator(
                                          strokeWidth: 2,
                                          color: AppColors.primary),
                                    )
                                  : Text(
                                      _selectedAddress,
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                      style: const TextStyle(
                                          fontWeight: FontWeight.w600,
                                          fontSize: 14),
                                    ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 8),
                        _actionPillButton(
                          label: 'SET',
                          icon: Icons.check_rounded,
                          compact: true,
                          onPressed: _isLoadingAddress
                              ? null
                              : () async {
                                  await _setPinnedLocation();
                                },
                        ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    _actionPillButton(
                      label: 'CONFIRM LOCATION',
                      icon: Icons.check_circle_rounded,
                      fullWidth: true,
                      onPressed: _confirmLocation,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _actionPillButton({
    required String label,
    required IconData icon,
    required Future<void> Function()? onPressed,
    bool compact = false,
    bool fullWidth = false,
  }) {
    final enabled = onPressed != null;
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 160),
      opacity: enabled ? 1 : 0.45,
      child: Container(
        width: fullWidth ? double.infinity : null,
        height: compact ? 34 : 46,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(999),
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
          onPressed: enabled ? () => onPressed() : null,
          style: FilledButton.styleFrom(
            backgroundColor: const Color(0xFF43E892),
            foregroundColor: const Color(0xFF052E1E),
            disabledBackgroundColor: const Color(0xFF43E892),
            disabledForegroundColor: const Color(0xFF052E1E),
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(999),
            ),
            padding: EdgeInsets.symmetric(
              horizontal: compact ? 12 : 16,
              vertical: compact ? 8 : 12,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: compact ? 18 : 20,
                height: compact ? 18 : 20,
                decoration: BoxDecoration(
                  color: const Color(0xFF052E1E),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Icon(icon,
                    size: compact ? 12 : 14, color: const Color(0xFF43E892)),
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
