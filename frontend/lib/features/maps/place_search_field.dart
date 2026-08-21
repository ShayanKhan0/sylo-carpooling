import 'dart:async';
import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';
import '../../core/theme/app_colors.dart';
import '../../core/services/maps_service.dart';
import 'location_picker_screen.dart';

/// Inline place-search text field with Google Places autocomplete dropdown.
///
/// As the user types, predictions appear immediately below the field.
/// Tapping a prediction resolves the Place ID to coordinates and fires
/// [onPlaceSelected]. The map-pin button opens [LocationPickerScreen]
/// for manual map-based picking.
class PlaceSearchField extends StatefulWidget {
  final String hint;

  /// Colour of the dot icon and focus highlight (green = origin, red = dest)
  final Color dotColor;

  /// Currently confirmed location (displayed address in field)
  final PickedLocation? value;

  final ValueChanged<PickedLocation> onPlaceSelected;

  /// Show the map-pin button that opens [LocationPickerScreen]
  final bool showMapButton;

  /// Optional callback for raw text input updates.
  final ValueChanged<String>? onTextChanged;
  final Color? backgroundColor;
  final Color? borderColor;
  final Color? textColor;
  final Color? hintColor;
  final Color? mapIconColor;
  final Color? suggestionBackgroundColor;
  final Color? suggestionBorderColor;
  final Color? suggestionTextColor;
  final Color? suggestionSubtitleColor;

  const PlaceSearchField({
    super.key,
    required this.hint,
    required this.dotColor,
    required this.onPlaceSelected,
    this.value,
    this.showMapButton = true,
    this.onTextChanged,
    this.backgroundColor,
    this.borderColor,
    this.textColor,
    this.hintColor,
    this.mapIconColor,
    this.suggestionBackgroundColor,
    this.suggestionBorderColor,
    this.suggestionTextColor,
    this.suggestionSubtitleColor,
  });

  @override
  State<PlaceSearchField> createState() => _PlaceSearchFieldState();
}

class _PlaceSearchFieldState extends State<PlaceSearchField> {
  final _ctrl = TextEditingController();
  final _focus = FocusNode();
  final _mapsService = MapsService();

  List<PlacePrediction> _predictions = [];
  bool _loading = false;
  bool _searchedOnce = false; // true after at least one search returned
  Timer? _debounce;
  String _sessionToken = const Uuid().v4();
  bool _isSelectingPrediction = false;

  // The confirmed location held locally (mirrors widget.value unless user
  // has started typing a new query or cleared the field).
  PickedLocation? _confirmedValue;

  @override
  void initState() {
    super.initState();
    _confirmedValue = widget.value;
    if (widget.value != null) {
      _ctrl.text = widget.value!.address;
    }
    _focus.addListener(_onFocusChange);
  }

  @override
  void didUpdateWidget(PlaceSearchField old) {
    super.didUpdateWidget(old);
    // Only sync when parent value itself changes. Rebuilds caused by sibling
    // validation/UI state should not wipe the user's in-progress text.
    if (widget.value != old.value) {
      _confirmedValue = widget.value;
      if (!_focus.hasFocus) {
        _ctrl.text = widget.value?.address ?? '';
      }
    }
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _ctrl.dispose();
    _focus.removeListener(_onFocusChange);
    _focus.dispose();
    super.dispose();
  }

  void _onFocusChange() {
    if (!_focus.hasFocus) {
      // Delay blur handling slightly so tapping an autocomplete row
      // doesn't get canceled by the field losing focus first.
      Future.delayed(const Duration(milliseconds: 120), () {
        if (!mounted || _focus.hasFocus || _isSelectingPrediction) return;

        // If user blurred without selecting, restore confirmed address.
        if (_confirmedValue != null && _predictions.isNotEmpty) {
          _ctrl.text = _confirmedValue!.address;
        }
        setState(() => _predictions = []);
      });
    } else {
      // When focused, clear the text so the user can type fresh
      if (_confirmedValue != null) {
        _ctrl.clear();
      }
    }
  }

  void _onChanged(String query) {
    _debounce?.cancel();
    widget.onTextChanged?.call(query);
    if (query.trim().isEmpty) {
      if (mounted) {
        setState(() {
          _predictions = [];
          _loading = false;
          _searchedOnce = false;
        });
      }
      return;
    }
    if (mounted) setState(() => _loading = true);
    _debounce = Timer(const Duration(milliseconds: 400), () async {
      final results = await _mapsService.searchPlaces(
        query,
        sessionToken: _sessionToken,
      );
      debugPrint(
          '[PlaceSearchField] searchPlaces("$query") → ${results.length} results');
      if (mounted) {
        setState(() {
          _searchedOnce = true;
          _predictions = results;
          _loading = false;
        });
      }
    });
  }

  Future<void> _selectPrediction(PlacePrediction p) async {
    if (_isSelectingPrediction) return;
    _isSelectingPrediction = true;
    _focus.unfocus();
    if (mounted) {
      setState(() {
        _ctrl.text = p.description;
        _predictions = [];
        _loading = true;
      });
    }

    final detail = await _mapsService.getPlaceDetails(
      p.placeId,
      sessionToken: _sessionToken,
    );

    // Rotate session token after each Place Details call (billing)
    _sessionToken = const Uuid().v4();

    if (detail != null && mounted) {
      final picked = PickedLocation(
        latLng: detail.location,
        address: detail.address,
        name: detail.name,
        placeId: p.placeId,
      );
      setState(() {
        _confirmedValue = picked;
        _ctrl.text = detail.address;
        _loading = false;
      });
      widget.onPlaceSelected(picked);
      _isSelectingPrediction = false;
      return;
    }

    // Fallback path: if place-details fails, geocode the selected description.
    final fallbackLatLng =
        await _mapsService.getLatLngFromAddress(p.description);
    if (fallbackLatLng != null && mounted) {
      final picked = PickedLocation(
        latLng: fallbackLatLng,
        address: p.description,
        name: p.mainText,
        placeId: p.placeId,
      );
      setState(() {
        _confirmedValue = picked;
        _ctrl.text = p.description;
        _loading = false;
      });
      widget.onPlaceSelected(picked);
    } else if (mounted) {
      setState(() => _loading = false);
    }

    _isSelectingPrediction = false;
  }

  Future<void> _openMapPicker() async {
    _focus.unfocus();
    final result = await Navigator.push<PickedLocation>(
      context,
      MaterialPageRoute(
        builder: (_) => LocationPickerScreen(
          title: widget.hint,
          initialLocation: _confirmedValue?.latLng,
        ),
      ),
    );
    if (result != null && mounted) {
      setState(() {
        _confirmedValue = result;
        _ctrl.text = result.address;
        _predictions = [];
      });
      widget.onPlaceSelected(result);
    }
  }

  void _clear() {
    _ctrl.clear();
    widget.onTextChanged?.call('');
    setState(() {
      _confirmedValue = null;
      _predictions = [];
    });
    _focus.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    final fieldBackground = widget.backgroundColor ?? AppColors.backgroundLight;
    final fieldBorder = widget.borderColor ?? AppColors.border;
    final fieldText = widget.textColor ?? AppColors.textPrimary;
    final fieldHint = widget.hintColor ?? AppColors.textHint;
    final mapIcon = widget.mapIconColor ?? AppColors.primary;
    final suggestionBackground =
        widget.suggestionBackgroundColor ?? AppColors.surface;
    final suggestionBorder = widget.suggestionBorderColor ?? AppColors.border;
    final suggestionText = widget.suggestionTextColor ?? AppColors.textPrimary;
    final suggestionSubtitle =
        widget.suggestionSubtitleColor ?? AppColors.textSecondary;

    final hasValue = _confirmedValue != null && !_focus.hasFocus;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        // ── Input field ───────────────────────────────────────────────────
        AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          clipBehavior: Clip.antiAlias,
          decoration: BoxDecoration(
            color: fieldBackground,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
              color: _focus.hasFocus ? widget.dotColor : fieldBorder,
              width: _focus.hasFocus ? 1.5 : 1.0,
              strokeAlign: BorderSide.strokeAlignInside,
            ),
          ),
          child: Stack(
            children: [
              Row(
                children: [
                  Padding(
                    padding: const EdgeInsets.only(left: 14),
                    child: Icon(
                      Icons.circle,
                      size: 12,
                      color: hasValue ? widget.dotColor : AppColors.textHint,
                    ),
                  ),
                  Expanded(
                    child: TextField(
                      controller: _ctrl,
                      focusNode: _focus,
                      onChanged: _onChanged,
                      style: TextStyle(
                        fontSize: 14,
                        color: fieldText,
                      ),
                      decoration: InputDecoration(
                        hintText: widget.hint,
                        hintStyle: TextStyle(color: fieldHint, fontSize: 14),
                        filled: true,
                        fillColor: Colors.transparent,
                        border: InputBorder.none,
                        enabledBorder: InputBorder.none,
                        focusedBorder: InputBorder.none,
                        errorBorder: InputBorder.none,
                        disabledBorder: InputBorder.none,
                        contentPadding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 16),
                        suffixIcon: _loading
                            ? Padding(
                                padding: const EdgeInsets.all(14),
                                child: SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(
                                      strokeWidth: 2, color: widget.dotColor),
                                ),
                              )
                            : hasValue
                                ? IconButton(
                                    icon: Icon(Icons.clear,
                                        size: 18, color: fieldHint),
                                    tooltip: 'Clear',
                                    onPressed: _clear,
                                  )
                                : null,
                      ),
                    ),
                  ),
                  if (widget.showMapButton)
                    IconButton(
                      icon: Icon(
                        Icons.map_outlined,
                        size: 20,
                        color: mapIcon,
                      ),
                      tooltip: 'Pick on map',
                      onPressed: _openMapPicker,
                    ),
                ],
              ),
              // Paint border on top so rounded edges stay visible.
              Positioned.fill(
                child: IgnorePointer(
                  child: Container(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(
                        color: _focus.hasFocus ? widget.dotColor : fieldBorder,
                        width: _focus.hasFocus ? 1.5 : 1.0,
                        strokeAlign: BorderSide.strokeAlignInside,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),

        // ── Autocomplete predictions ──────────────────────────────────────
        if (_predictions.isNotEmpty)
          Container(
            margin: const EdgeInsets.only(top: 4),
            decoration: BoxDecoration(
              color: suggestionBackground,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: suggestionBorder),
              boxShadow: [
                BoxShadow(
                    color: AppColors.shadow,
                    blurRadius: 8,
                    offset: const Offset(0, 4)),
              ],
            ),
            child: ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              padding: const EdgeInsets.symmetric(vertical: 4),
              itemCount: _predictions.length,
              separatorBuilder: (_, __) => const Divider(height: 1, indent: 50),
              itemBuilder: (_, i) {
                final p = _predictions[i];
                return ListTile(
                  dense: true,
                  leading: Icon(Icons.location_on_outlined,
                      color: widget.dotColor, size: 20),
                  title: Text(
                    p.mainText,
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                      color: suggestionText,
                    ),
                  ),
                  subtitle: p.secondaryText.isNotEmpty
                      ? Text(
                          p.secondaryText,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              color: suggestionSubtitle, fontSize: 11),
                        )
                      : null,
                  onTap: () => _selectPrediction(p),
                );
              },
            ),
          ),

        // ── No results hint ──────────────────────────────────────────────
        if (_predictions.isEmpty &&
            _searchedOnce &&
            !_loading &&
            _focus.hasFocus &&
            _ctrl.text.trim().length >= 2)
          Container(
            margin: const EdgeInsets.only(top: 4),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: suggestionBackground,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: suggestionBorder),
            ),
            child: Row(
              children: [
                Icon(Icons.info_outline, size: 16, color: fieldHint),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'No results found. Try a different query or tap the map icon to pick manually.',
                    style: TextStyle(color: suggestionSubtitle, fontSize: 12),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
