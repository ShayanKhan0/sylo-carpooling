import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../../core/services/driver_service.dart';
import '../../core/services/maps_service.dart';
import '../../core/services/user_service.dart';
import '../../core/services/verification_service.dart';
import '../../core/models/user_model.dart';
import '../../core/theme/app_colors.dart';
import '../../core/constants/app_constants.dart';
import '../maps/location_picker_screen.dart';
import '../maps/place_search_field.dart';
import '../shared/widgets.dart';
import '../dashboard/home_design_system.dart';

class ProfileEditScreen extends StatefulWidget {
  const ProfileEditScreen({super.key});

  @override
  State<ProfileEditScreen> createState() => _ProfileEditScreenState();
}

class _ProfileEditScreenState extends State<ProfileEditScreen> {
  final UserService _svc = UserService();
  final DriverService _driverSvc = DriverService();
  final VerificationService _verificationSvc = VerificationService();
  User? _user;
  Map<String, dynamic> _verificationStatus = const <String, dynamic>{};
  bool _loading = true;
  bool _saving = false;
  String? _error;

  // Form controllers
  final _formKey = GlobalKey<FormState>();
  late TextEditingController _genderCtrl;
  late TextEditingController _dobCtrl;
  late TextEditingController _orgNameCtrl;
  late TextEditingController _orgTypeCtrl;
  late TextEditingController _cnicCtrl;
  late TextEditingController _licenseCtrl;
  String _initialCnic = '';
  String _initialLicense = '';

  // Saved addresses
  List<SavedAddress> _addresses = [];

  bool get _isDriver => _user?.role.toLowerCase() == 'driver';

  // ─────────────────────────────────────────────────────────
  //  Theme tokens — mirrors the Driver Home screen palette so
  //  this editor feels like a natural extension of that surface.
  // ─────────────────────────────────────────────────────────
  static const Color _textPrimary = Color(0xFF121915);
  static const Color _textSecondary = Color(0xFF25352D);
  static const Color _accentGreen = Color(0xFF1ED760);

  Color _symbolShade(Color base) =>
      Color.alphaBlend(Colors.black.withValues(alpha: 0.28), base);

  BoxDecoration _homeGlass({
    double radius = 22,
    bool elevated = true,
    double borderAlpha = 0.42,
    double borderWidth = 1.1,
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
          color: _accentGreen.withValues(alpha: 0.3),
          blurRadius: 40,
          spreadRadius: -10,
          offset: const Offset(-6, -4),
        ),
      ],
    );
  }

  // ─────────────────────────────────────────────────────────
  //  Profile-photo URL resolver (mirrors the dashboard logic)
  // ─────────────────────────────────────────────────────────
  String _apiOrigin() {
    final parsed = Uri.tryParse(AppConstants.baseUrl);
    if (parsed == null || !parsed.hasScheme || parsed.host.isEmpty) {
      return '';
    }
    final portPart = parsed.hasPort ? ':${parsed.port}' : '';
    return '${parsed.scheme}://${parsed.host}$portPart';
  }

  String? _resolveProfilePhotoUrl(String? rawPhoto) {
    final value = (rawPhoto ?? '').trim();
    if (value.isEmpty || value.startsWith('data:image/')) return null;

    final normalized = value.replaceAll('\\', '/');
    if (normalized.startsWith('http://') || normalized.startsWith('https://')) {
      return normalized;
    }

    final origin = _apiOrigin();
    if (origin.isEmpty) return null;

    if (normalized.startsWith('/')) return '$origin$normalized';
    if (normalized.startsWith('static/')) return '$origin/$normalized';
    if (normalized.startsWith('uploads/')) {
      return '$origin/static/$normalized';
    }
    return '$origin/$normalized';
  }

  ImageProvider? _profileImageProvider(String? rawPhoto) {
    final value = (rawPhoto ?? '').trim();
    if (value.isEmpty) return null;

    if (value.startsWith('data:image/')) {
      try {
        final parts = value.split(',');
        if (parts.length >= 2) {
          return MemoryImage(base64Decode(parts[1]));
        }
      } catch (_) {
        return null;
      }
      return null;
    }

    final photoUrl = _resolveProfilePhotoUrl(value);
    if (photoUrl == null || photoUrl.isEmpty) return null;
    return NetworkImage(photoUrl);
  }

  BoxDecoration _inputBox() {
    return BoxDecoration(
      borderRadius: BorderRadius.circular(14),
      color: const Color(0xFF0B2317).withValues(alpha: 0.55),
      border: Border.all(
        color: const Color(0xFF0B2317).withValues(alpha: 0.28),
        width: 1,
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _genderCtrl = TextEditingController();
    _dobCtrl = TextEditingController();
    _orgNameCtrl = TextEditingController();
    _orgTypeCtrl = TextEditingController();
    _cnicCtrl = TextEditingController();
    _licenseCtrl = TextEditingController();
    _load();
  }

  @override
  void dispose() {
    _genderCtrl.dispose();
    _dobCtrl.dispose();
    _orgNameCtrl.dispose();
    _orgTypeCtrl.dispose();
    _cnicCtrl.dispose();
    _licenseCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final user = await _svc.getMyProfile();
      final addresses = await _svc.getAddresses();
      Map<String, dynamic> verificationStatus = const <String, dynamic>{};
      try {
        verificationStatus = await _verificationSvc.getStatus(user.id);
      } catch (_) {}

      var cnic = user.profile?.cnic?.trim() ?? '';
      var drivingLicense = user.profile?.drivingLicense?.trim() ?? '';

      // Driver onboarding stores docs in driver profile; fallback here if user profile is empty.
      if ((cnic.isEmpty || drivingLicense.isEmpty) &&
          user.role.toLowerCase() == 'driver') {
        try {
          final driverProfile = await _driverSvc.getMyProfile();
          final driverCnic = driverProfile.cnicNumber.trim();
          final driverLicense = driverProfile.licenseNumber.trim();

          if (cnic.isEmpty &&
              driverCnic.isNotEmpty &&
              driverCnic.toLowerCase() != 'n/a') {
            cnic = driverCnic;
          }
          if (drivingLicense.isEmpty && driverLicense.isNotEmpty) {
            drivingLicense = driverLicense;
          }
        } catch (_) {}
      }

      final normalizedOrgType = _normalizeOrganizationTypeForApi(
          user.profile?.organizationType ?? '');

      setState(() {
        _user = user;
        _addresses = addresses;
        _verificationStatus = verificationStatus;
        _genderCtrl.text = user.profile?.gender ?? '';
        _dobCtrl.text = user.profile?.dateOfBirth ?? '';
        _orgNameCtrl.text = user.profile?.organizationName ?? '';
        _orgTypeCtrl.text = normalizedOrgType;
        _cnicCtrl.text = cnic;
        _licenseCtrl.text = drivingLicense;
        _initialCnic = _normalizeIdentityValue(cnic);
        _initialLicense = _normalizeIdentityValue(drivingLicense);
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;

    final cnicValue = _cnicCtrl.text.trim();
    final licenseValue = _licenseCtrl.text.trim();
    final isDriver = _isDriver;
    final cnicChanged = _hasIdentityValueChanged(_initialCnic, cnicValue);
    final licenseChanged =
        isDriver && _hasIdentityValueChanged(_initialLicense, licenseValue);

    if ((cnicChanged || licenseChanged) &&
        !await _confirmReverificationDialog(
          cnicChanged: cnicChanged,
          licenseChanged: licenseChanged,
        )) {
      return;
    }

    final normalizedOrgType =
        _normalizeOrganizationTypeForApi(_orgTypeCtrl.text);

    setState(() => _saving = true);
    try {
      await _svc.updateProfile(
        gender:
            _genderCtrl.text.trim().isNotEmpty ? _genderCtrl.text.trim() : null,
        dateOfBirth:
            _dobCtrl.text.trim().isNotEmpty ? _dobCtrl.text.trim() : null,
        organizationName: _orgNameCtrl.text.trim().isNotEmpty
            ? _orgNameCtrl.text.trim()
            : null,
        organizationType:
            normalizedOrgType.isNotEmpty ? normalizedOrgType : null,
        cnic: cnicValue.isNotEmpty ? cnicValue : null,
        drivingLicense:
            isDriver && licenseValue.isNotEmpty ? licenseValue : null,
      );

      _initialCnic = _normalizeIdentityValue(cnicValue);
      _initialLicense = _normalizeIdentityValue(licenseValue);

      if (mounted) {
        final messenger = ScaffoldMessenger.of(context);
        if (cnicChanged || licenseChanged) {
          messenger.showSnackBar(
            SnackBar(
              content: const Text(
                'Profile updated. Re-upload updated documents in Verification.',
              ),
              backgroundColor: AppColors.accent,
              action: SnackBarAction(
                label: 'Verify Now',
                onPressed: () => Navigator.pushNamed(context, '/verification'),
              ),
            ),
          );
        } else {
          messenger.showSnackBar(
            const SnackBar(
              content: Text('Profile updated successfully!'),
              backgroundColor: AppColors.success,
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Update failed: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _deleteAddress(SavedAddress addr) async {
    try {
      await _svc.deleteAddress(addr.id);
      setState(() => _addresses.removeWhere((a) => a.id == addr.id));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Address deleted')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Delete failed: $e')),
        );
      }
    }
  }

  Future<void> _confirmDeleteAddress(SavedAddress address) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Address'),
        content: Text(
          'Delete ${address.label} from your saved addresses?',
        ),
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
    await _deleteAddress(address);
  }

  String _normalizeIdentityValue(String value) => value.trim();

  bool _hasIdentityValueChanged(String before, String after) {
    return _normalizeIdentityValue(before) != _normalizeIdentityValue(after);
  }

  String _normalizeOrganizationTypeForApi(String value) {
    final normalized = value.trim().toLowerCase();
    switch (normalized) {
      case 'university':
      case 'college':
      case 'school':
      case 'office':
        return normalized;
      case 'corporate':
      case 'government':
      case 'govt':
      case 'company':
      case 'other':
        return 'office';
      default:
        return '';
    }
  }

  Future<bool> _confirmReverificationDialog({
    required bool cnicChanged,
    required bool licenseChanged,
  }) async {
    final isDriver = _isDriver;
    final docs = <String>[
      if (cnicChanged) 'CNIC',
      if (licenseChanged) 'Driving License',
    ];

    final followUpMessage = isDriver
        ? 'You must re-upload updated documents in Verification to continue using driver verification dependent features.'
        : 'You must re-upload updated documents in Verification to continue using verification dependent features.';

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Re-verification Required'),
        content: Text(
          '${docs.join(' and ')} changed. $followUpMessage',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primary,
              foregroundColor: Colors.white,
            ),
            child: const Text('Continue'),
          ),
        ],
      ),
    );

    return result == true;
  }

  String? _validateDateOfBirth(String? value) {
    final input = value?.trim() ?? '';
    if (input.isEmpty) return null;

    final dobPattern = RegExp(r'^\d{4}-\d{2}-\d{2}$');
    if (!dobPattern.hasMatch(input)) {
      return 'Date must be in YYYY-MM-DD format';
    }

    final dob = DateTime.tryParse(input);
    if (dob == null) return 'Invalid date of birth';

    final today = DateTime.now();
    var age = today.year - dob.year;
    final hasBirthdayPassed = today.month > dob.month ||
        (today.month == dob.month && today.day >= dob.day);
    if (!hasBirthdayPassed) age -= 1;

    if (age < 13) return 'User must be at least 13 years old';
    if (age > 120) return 'Invalid date of birth';
    return null;
  }

  String? _validateCnic(String? value) {
    final input = value?.trim() ?? '';
    if (input.isEmpty) return null;
    final cnicPattern = RegExp(r'^\d{5}-\d{7}-\d{1}$');
    if (!cnicPattern.hasMatch(input)) {
      return 'CNIC must be in format: 12345-1234567-1';
    }
    return null;
  }

  // ─────────────────────────────────────────────────────────
  //  BUILD
  // ─────────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        body: Stack(
          children: [
            HomeDesignSystem.driverHomeSoftWhiteBackground(),
            const SafeArea(
              child: Center(
                child: SyloLoader(message: 'Loading profile…'),
              ),
            ),
          ],
        ),
      );
    }

    if (_error != null) {
      return Scaffold(
        body: Stack(
          children: [
            HomeDesignSystem.driverHomeSoftWhiteBackground(),
            SafeArea(
              child: Center(
                child: SyloError(message: _error!, onRetry: _load),
              ),
            ),
          ],
        ),
      );
    }

    return Scaffold(
      extendBodyBehindAppBar: true,
      backgroundColor: Colors.transparent,
      body: Stack(
        children: [
          HomeDesignSystem.driverHomeSoftWhiteBackground(),
          SafeArea(
            child: HomeDesignSystem.contentWidth(
              child: Form(
                key: _formKey,
                child: ListView(
                  physics: const BouncingScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(16, 10, 16, 28),
                  children: [
                    _buildTopBar(),
                    const SizedBox(height: 18),
                    _buildIdentityHeader(),
                    const SizedBox(height: 18),
                    _buildPersonalDetailsCard(),
                    const SizedBox(height: 14),
                    _buildOrganizationCard(),
                    const SizedBox(height: 14),
                    _buildIdentityDocumentsCard(),
                    const SizedBox(height: 14),
                    _buildAddressesCard(),
                    const SizedBox(height: 22),
                    _buildSaveButton(),
                    const SizedBox(height: 28),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ─────────────────────────────────────────────────────────
  //  TOP BAR
  // ─────────────────────────────────────────────────────────
  Widget _buildTopBar() {
    return HomeDesignSystem.frostLayer(
      blur: 10,
      radius: 20,
      child: Container(
        padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
        decoration: _homeGlass(
          radius: 20,
          elevated: false,
          borderAlpha: 0.32,
        ),
        child: Row(
          children: [
            _circleIconButton(
              icon: Icons.arrow_back_rounded,
              onTap: () => Navigator.of(context).maybePop(),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Profile Settings',
                style: GoogleFonts.inter(
                  fontSize: 20,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 0.2,
                  color: _textPrimary,
                ),
              ),
            ),
            _circleIconButton(
              icon: _saving ? Icons.hourglass_top_rounded : Icons.check_rounded,
              onTap: _saving ? null : _save,
              emphasised: true,
            ),
          ],
        ),
      ),
    );
  }

  Widget _circleIconButton({
    required IconData icon,
    required VoidCallback? onTap,
    bool emphasised = false,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Container(
          width: 38,
          height: 38,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: emphasised
                ? _accentGreen.withValues(alpha: 0.2)
                : Colors.white.withValues(alpha: 0.16),
            border: Border.all(
              color: emphasised
                  ? _accentGreen.withValues(alpha: 0.6)
                  : Colors.white.withValues(alpha: 0.32),
              width: 1.1,
            ),
          ),
          child: Icon(
            icon,
            size: 18,
            color: emphasised ? _symbolShade(_accentGreen) : _textPrimary,
          ),
        ),
      ),
    );
  }

  // ─────────────────────────────────────────────────────────
  //  IDENTITY HEADER (avatar + name + id)
  // ─────────────────────────────────────────────────────────
  Widget _buildIdentityHeader() {
    final name = _user?.fullName ?? '—';
    final idLabel = _derivedIdLabel();
    final photoProvider = _profileImageProvider(_user?.profile?.profilePhoto);

    return Column(
      children: [
        Stack(
          clipBehavior: Clip.none,
          alignment: Alignment.center,
          children: [
            Container(
              width: 126,
              height: 126,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: _accentGreen.withValues(alpha: 0.5),
                    blurRadius: 34,
                    spreadRadius: 2,
                  ),
                  BoxShadow(
                    color: _accentGreen.withValues(alpha: 0.2),
                    blurRadius: 52,
                    spreadRadius: 8,
                  ),
                ],
              ),
              child: Container(
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(color: _accentGreen, width: 2.4),
                ),
                child: CircleAvatar(
                  radius: 54,
                  backgroundColor: const Color(0xFF0B2317),
                  backgroundImage: photoProvider,
                  child: photoProvider == null
                      ? Text(
                          _user?.initials ?? '?',
                          style: GoogleFonts.inter(
                            fontSize: 38,
                            fontWeight: FontWeight.w900,
                            color: _accentGreen,
                          ),
                        )
                      : null,
                ),
              ),
            ),
            Positioned(
              right: 6,
              bottom: 6,
              child: Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(
                        content: Text(
                          'Use the Profile tab to update your photo.',
                        ),
                      ),
                    );
                  },
                  borderRadius: BorderRadius.circular(999),
                  child: Container(
                    width: 34,
                    height: 34,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: const Color(0xFF22C56D),
                      border: Border.all(
                        color: Colors.white.withValues(alpha: 0.9),
                        width: 1.6,
                      ),
                    ),
                    child: const Icon(
                      Icons.camera_alt_rounded,
                      size: 16,
                      color: Colors.white,
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 14),
        Text(
          name,
          style: GoogleFonts.inter(
            fontSize: 36,
            fontWeight: FontWeight.w900,
            letterSpacing: 0.1,
            color: _textPrimary,
            height: 1.02,
          ),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 4),
        Text(
          idLabel,
          style: GoogleFonts.inter(
            fontSize: 12,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.4,
            color: _textSecondary,
          ),
        ),
      ],
    );
  }

  String _derivedIdLabel() {
    final role = (_user?.role ?? '').toUpperCase();
    final rawId = _user?.id ?? '';
    if (rawId.isEmpty) return 'ID: $role';
    final slice = rawId.length > 6 ? rawId.substring(0, 6).toUpperCase() : rawId.toUpperCase();
    return 'ID: ${role.isNotEmpty ? '${role.substring(0, 3)}-' : ''}$slice';
  }

  // ─────────────────────────────────────────────────────────
  //  SECTION CARD
  // ─────────────────────────────────────────────────────────
  Widget _sectionCard({
    required IconData icon,
    required String title,
    Widget? trailing,
    required List<Widget> children,
  }) {
    return HomeDesignSystem.frostLayer(
      blur: 10,
      radius: 22,
      child: Container(
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 18),
        decoration: _homeGlass(radius: 22, elevated: true),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  width: 32,
                  height: 32,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _accentGreen.withValues(alpha: 0.22),
                    border: Border.all(
                      color: _accentGreen.withValues(alpha: 0.55),
                      width: 1.1,
                    ),
                  ),
                  child: Icon(
                    icon,
                    size: 16,
                    color: _symbolShade(_accentGreen),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    title,
                    style: GoogleFonts.inter(
                      fontSize: 18,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 0.1,
                      color: _textPrimary,
                    ),
                  ),
                ),
                if (trailing != null) trailing,
              ],
            ),
            const SizedBox(height: 16),
            ...children,
          ],
        ),
      ),
    );
  }

  // ─────────────────────────────────────────────────────────
  //  PERSONAL DETAILS
  // ─────────────────────────────────────────────────────────
  Widget _buildPersonalDetailsCard() {
    return _sectionCard(
      icon: Icons.person_rounded,
      title: 'Personal Details',
      children: [
        _labeled(
          label: 'Gender',
          child: _dropdownField(
            value: _genderCtrl.text.isNotEmpty ? _genderCtrl.text : null,
            items: const ['male', 'female', 'other'],
            hint: 'Select gender',
            onChanged: (v) => setState(() => _genderCtrl.text = v ?? ''),
          ),
        ),
        const SizedBox(height: 14),
        _labeled(
          label: 'Date of Birth',
          child: _dateField(
            controller: _dobCtrl,
            validator: _validateDateOfBirth,
          ),
        ),
      ],
    );
  }

  // ─────────────────────────────────────────────────────────
  //  ORGANIZATION
  // ─────────────────────────────────────────────────────────
  Widget _buildOrganizationCard() {
    return _sectionCard(
      icon: Icons.apartment_rounded,
      title: 'Organization',
      children: [
        _labeled(
          label: 'Organization Name',
          child: _textField(
            controller: _orgNameCtrl,
            hint: 'e.g. Veridian Transit Solutions',
          ),
        ),
        const SizedBox(height: 14),
        _labeled(
          label: 'Organization Type',
          child: _dropdownField(
            value: _orgTypeCtrl.text.isNotEmpty ? _orgTypeCtrl.text : null,
            items: const ['university', 'college', 'school', 'office'],
            hint: 'Select type',
            onChanged: (v) => setState(() => _orgTypeCtrl.text = v ?? ''),
          ),
        ),
      ],
    );
  }

  // ─────────────────────────────────────────────────────────
  //  IDENTITY DOCUMENTS
  // ─────────────────────────────────────────────────────────
  Widget _buildIdentityDocumentsCard() {
    final verifications =
        (_verificationStatus['verifications'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final cnicVerified = verifications['cnic']?.toString().toLowerCase() == 'verified';
    final licenseVerified =
        verifications['driving_license']?.toString().toLowerCase() == 'verified';
    final overallVerified = _isDriver ? (cnicVerified && licenseVerified) : cnicVerified;

    final pillLabel = overallVerified ? 'VERIFIED' : 'UNVERIFIED';
    final pillColor = overallVerified ? _accentGreen : Colors.orangeAccent;
    final pillTextColor = overallVerified
        ? const Color(0xFF0B5B33)
        : const Color(0xFF7A4400);

    return _sectionCard(
      icon: Icons.verified_user_rounded,
      title: 'Identity Documents',
      trailing: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(999),
          color: pillColor.withValues(alpha: 0.22),
          border: Border.all(
            color: pillColor.withValues(alpha: 0.6),
            width: 1,
          ),
        ),
        child: Text(
          pillLabel,
          style: GoogleFonts.inter(
            fontSize: 10,
            fontWeight: FontWeight.w900,
            letterSpacing: 1.3,
            color: pillTextColor,
          ),
        ),
      ),
      children: [
        _labeled(
          label: 'CNIC Number',
          child: _textField(
            controller: _cnicCtrl,
            hint: '12345-1234567-1',
            validator: _validateCnic,
          ),
        ),
        if (_isDriver) ...[
          const SizedBox(height: 14),
          _labeled(
            label: 'Driving License',
            child: _textField(
              controller: _licenseCtrl,
              hint: 'License number',
            ),
          ),
        ],
        const SizedBox(height: 14),
        _docRow(
          icon: Icons.credit_card_rounded,
          title: 'CNIC Card',
          verified: cnicVerified,
        ),
        if (_isDriver) ...[
          const SizedBox(height: 10),
          _docRow(
            icon: Icons.directions_car_rounded,
            title: 'Driving License',
            verified: licenseVerified,
          ),
        ],
        const SizedBox(height: 14),
        Container(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(14),
            color: AppColors.accent.withValues(alpha: 0.12),
            border:
                Border.all(color: AppColors.accent.withValues(alpha: 0.32)),
          ),
          child: Row(
            children: [
              const Icon(
                Icons.info_outline_rounded,
                color: AppColors.accent,
                size: 18,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  _isDriver
                      ? 'If CNIC or Driving License is changed, re-verification upload is required.'
                      : 'If CNIC is changed, re-verification upload is required.',
                  style: GoogleFonts.inter(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: _textPrimary,
                    height: 1.35,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _docRow({
    required IconData icon,
    required String title,
    required bool verified,
  }) {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 12),
      decoration: _inputBox(),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(10),
              color: _accentGreen.withValues(alpha: 0.22),
              border: Border.all(
                color: _accentGreen.withValues(alpha: 0.5),
                width: 1,
              ),
            ),
            child: Icon(
              icon,
              size: 18,
              color: _symbolShade(_accentGreen),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              title,
              style: GoogleFonts.inter(
                fontSize: 14,
                fontWeight: FontWeight.w800,
                color: Colors.white.withValues(alpha: 0.96),
              ),
            ),
          ),
          Icon(
            verified
                ? Icons.check_circle_rounded
                : Icons.cancel_rounded,
            color: verified ? _accentGreen : Colors.redAccent,
            size: 22,
          ),
        ],
      ),
    );
  }

  // ─────────────────────────────────────────────────────────
  //  ADDRESSES
  // ─────────────────────────────────────────────────────────
  Widget _buildAddressesCard() {
    return _sectionCard(
      icon: Icons.location_on_rounded,
      title: 'Saved Addresses',
      trailing: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: _showAddAddressSheet,
          borderRadius: BorderRadius.circular(999),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(999),
              color: _accentGreen.withValues(alpha: 0.22),
              border:
                  Border.all(color: _accentGreen.withValues(alpha: 0.6)),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.add_rounded,
                  size: 15,
                  color: _symbolShade(_accentGreen),
                ),
                const SizedBox(width: 4),
                Text(
                  'Add',
                  style: GoogleFonts.inter(
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.4,
                    color: const Color(0xFF0B5B33),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
      children: [
        if (_addresses.isEmpty)
          Container(
            padding: const EdgeInsets.fromLTRB(14, 18, 14, 18),
            decoration: _inputBox(),
            child: Row(
              children: [
                Icon(
                  Icons.location_off_rounded,
                  color: Colors.white.withValues(alpha: 0.72),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'No saved addresses yet. Tap Add to save your frequent places.',
                    style: GoogleFonts.inter(
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                      color: Colors.white.withValues(alpha: 0.84),
                      height: 1.35,
                    ),
                  ),
                ),
              ],
            ),
          )
        else
          ..._addresses.map(_buildAddressCard),
      ],
    );
  }

  Widget _buildAddressCard(SavedAddress address) {
    return Dismissible(
      key: ValueKey('address-${address.id}'),
      direction: DismissDirection.horizontal,
      background: _buildAddressSwipeBackground(
        color: AppColors.primary,
        icon: Icons.edit_rounded,
        label: 'Edit',
        alignment: MainAxisAlignment.start,
      ),
      secondaryBackground: _buildAddressSwipeBackground(
        color: AppColors.error,
        icon: Icons.delete_outline_rounded,
        label: 'Delete',
        alignment: MainAxisAlignment.end,
      ),
      confirmDismiss: (direction) async {
        if (direction == DismissDirection.startToEnd) {
          _showEditAddressSheet(address);
          return false;
        }
        await _confirmDeleteAddress(address);
        return false;
      },
      child: Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Material(
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(14),
          child: InkWell(
            onTap: () => _showAddressActionsMenu(address),
            borderRadius: BorderRadius.circular(14),
            child: Container(
              padding: const EdgeInsets.all(12),
              decoration: _inputBox(),
              child: Row(
                children: [
                  Container(
                    width: 36,
                    height: 36,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(10),
                      color: _accentGreen.withValues(alpha: 0.22),
                      border: Border.all(
                        color: _accentGreen.withValues(alpha: 0.5),
                      ),
                    ),
                    child: Icon(
                      Icons.location_on_rounded,
                      size: 18,
                      color: _symbolShade(_accentGreen),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          address.label,
                          style: GoogleFonts.inter(
                            fontSize: 14,
                            fontWeight: FontWeight.w800,
                            color: Colors.white.withValues(alpha: 0.96),
                          ),
                        ),
                        Text(
                          address.address,
                          style: GoogleFonts.inter(
                            fontSize: 11.5,
                            fontWeight: FontWeight.w500,
                            color: Colors.white.withValues(alpha: 0.62),
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  Icon(
                    Icons.chevron_right_rounded,
                    color: Colors.white.withValues(alpha: 0.6),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildAddressSwipeBackground({
    required Color color,
    required IconData icon,
    required String label,
    required MainAxisAlignment alignment,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisAlignment: alignment,
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(width: 8),
          Text(
            label,
            style: TextStyle(
              color: color,
              fontWeight: FontWeight.w700,
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }

  // ─────────────────────────────────────────────────────────
  //  SAVE BUTTON
  // ─────────────────────────────────────────────────────────
  Widget _buildSaveButton() {
    return SizedBox(
      height: 56,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(999),
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF2BE088), Color(0xFF16A35B)],
          ),
          boxShadow: [
            BoxShadow(
              color: _accentGreen.withValues(alpha: 0.38),
              blurRadius: 20,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: _saving ? null : _save,
            borderRadius: BorderRadius.circular(999),
            child: Center(
              child: _saving
                  ? const SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(
                        strokeWidth: 2.4,
                        color: Colors.white,
                      ),
                    )
                  : Text(
                      'Save Changes',
                      style: GoogleFonts.inter(
                        fontSize: 16,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 0.4,
                        color: Colors.white,
                      ),
                    ),
            ),
          ),
        ),
      ),
    );
  }

  // ─────────────────────────────────────────────────────────
  //  FIELD HELPERS (styled inputs inside each section)
  // ─────────────────────────────────────────────────────────
  Widget _labeled({required String label, required Widget child}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label.toUpperCase(),
          style: GoogleFonts.inter(
            fontSize: 10.5,
            fontWeight: FontWeight.w800,
            letterSpacing: 1.6,
            color: _textSecondary.withValues(alpha: 0.92),
          ),
        ),
        const SizedBox(height: 6),
        child,
      ],
    );
  }

  InputDecoration _fieldDecoration({String? hint, Widget? suffixIcon}) {
    return InputDecoration(
      hintText: hint,
      hintStyle: GoogleFonts.inter(
        fontSize: 14,
        fontWeight: FontWeight.w500,
        color: Colors.white.withValues(alpha: 0.5),
      ),
      filled: false,
      contentPadding:
          const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      border: InputBorder.none,
      enabledBorder: InputBorder.none,
      focusedBorder: InputBorder.none,
      errorBorder: InputBorder.none,
      focusedErrorBorder: InputBorder.none,
      isDense: true,
      suffixIcon: suffixIcon,
      errorStyle: GoogleFonts.inter(
        fontSize: 11.5,
        fontWeight: FontWeight.w600,
        color: Colors.orangeAccent,
      ),
    );
  }

  Widget _textField({
    required TextEditingController controller,
    String? hint,
    String? Function(String?)? validator,
  }) {
    return Container(
      decoration: _inputBox(),
      child: TextFormField(
        controller: controller,
        validator: validator,
        style: GoogleFonts.inter(
          fontSize: 15,
          fontWeight: FontWeight.w700,
          color: Colors.white.withValues(alpha: 0.97),
        ),
        cursorColor: _accentGreen,
        decoration: _fieldDecoration(hint: hint),
      ),
    );
  }

  Widget _dateField({
    required TextEditingController controller,
    String? Function(String?)? validator,
  }) {
    return Container(
      decoration: _inputBox(),
      child: TextFormField(
        controller: controller,
        validator: validator,
        readOnly: true,
        style: GoogleFonts.inter(
          fontSize: 15,
          fontWeight: FontWeight.w700,
          color: Colors.white.withValues(alpha: 0.97),
        ),
        decoration: _fieldDecoration(
          hint: 'YYYY-MM-DD',
          suffixIcon: Padding(
            padding: const EdgeInsets.only(right: 8),
            child: Icon(
              Icons.calendar_month_rounded,
              size: 18,
              color: Colors.white.withValues(alpha: 0.82),
            ),
          ),
        ),
        onTap: () async {
          final picked = await showDatePicker(
            context: context,
            initialDate: DateTime(2000),
            firstDate: DateTime(1950),
            lastDate: DateTime.now(),
          );
          if (picked != null) {
            setState(() {
              controller.text =
                  '${picked.year}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}';
            });
          }
        },
      ),
    );
  }

  Widget _dropdownField({
    required String? value,
    required List<String> items,
    required ValueChanged<String?> onChanged,
    String? hint,
  }) {
    return Container(
      decoration: _inputBox(),
      padding: const EdgeInsets.symmetric(horizontal: 6),
      child: DropdownButtonFormField<String>(
        value: items.contains(value) ? value : null,
        isExpanded: true,
        dropdownColor: const Color(0xFF0B2317),
        icon: Icon(
          Icons.keyboard_arrow_down_rounded,
          color: Colors.white.withValues(alpha: 0.8),
        ),
        style: GoogleFonts.inter(
          fontSize: 15,
          fontWeight: FontWeight.w700,
          color: Colors.white.withValues(alpha: 0.97),
        ),
        decoration: _fieldDecoration(hint: hint).copyWith(
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
        ),
        items: items
            .map(
              (v) => DropdownMenuItem(
                value: v,
                child: Text(
                  v[0].toUpperCase() + v.substring(1),
                  style: GoogleFonts.inter(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: Colors.white.withValues(alpha: 0.96),
                  ),
                ),
              ),
            )
            .toList(),
        onChanged: onChanged,
      ),
    );
  }

  // ─────────────────────────────────────────────────────────
  //  ADDRESS SHEETS (kept as before, light theme tweaks)
  // ─────────────────────────────────────────────────────────
  void _showAddAddressSheet() {
    final labelCtrl = TextEditingController();
    final mapsSvc = MapsService();
    var selectedAddress = '';
    double? selectedLatitude;
    double? selectedLongitude;
    var showLabelError = false;
    var showAddressError = false;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setModalState) {
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
                  crossAxisAlignment: CrossAxisAlignment.stretch,
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
                      'Add Address',
                      style: GoogleFonts.inter(
                        fontSize: 34,
                        fontWeight: FontWeight.w800,
                        color: const Color(0xFFE7F4ED),
                        height: 1.05,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'Save frequently used addresses for quicker ride setup.',
                      style: GoogleFonts.inter(
                        fontSize: 13,
                        color: const Color(0xFFA7BCB0),
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller: labelCtrl,
                      style: const TextStyle(
                        color: Color(0xFFE9F7EF),
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                      onChanged: (value) {
                        if (showLabelError && value.trim().isNotEmpty) {
                          setModalState(() => showLabelError = false);
                        }
                      },
                      decoration: InputDecoration(
                        labelText: 'Label (e.g. Home, Work)',
                        labelStyle: const TextStyle(color: Color(0xFF8BA095)),
                        prefixIcon:
                            const Icon(Icons.label_rounded, color: Color(0xFF4BF0A1)),
                        errorText: showLabelError ? 'Label is required' : null,
                        filled: true,
                        fillColor: const Color(0xFF121F1B),
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
                        errorBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: const BorderSide(color: AppColors.error),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 150),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(
                          color: showAddressError
                              ? AppColors.error
                              : Colors.white.withValues(alpha: 0.1),
                          width: showAddressError ? 1.5 : 1.0,
                        ),
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(14),
                        child: PlaceSearchField(
                          hint: 'Address - type to search or tap map',
                          dotColor: const Color(0xFF4BF0A1),
                          backgroundColor: const Color(0xFF121F1B),
                          borderColor: Colors.white.withValues(alpha: 0.1),
                          textColor: const Color(0xFFE9F7EF),
                          hintColor: const Color(0xFF8BA095),
                          mapIconColor: const Color(0xFF4BF0A1),
                          suggestionBackgroundColor: const Color(0xFF121F1B),
                          suggestionBorderColor:
                              Colors.white.withValues(alpha: 0.1),
                          suggestionTextColor: const Color(0xFFE9F7EF),
                          suggestionSubtitleColor: const Color(0xFF8BA095),
                          onTextChanged: (value) {
                            selectedAddress = value.trim();
                            selectedLatitude = null;
                            selectedLongitude = null;
                            if (showAddressError && selectedAddress.isNotEmpty) {
                              setModalState(() => showAddressError = false);
                            }
                          },
                          onPlaceSelected: (place) {
                            selectedAddress = place.address.trim();
                            selectedLatitude = place.latLng.latitude;
                            selectedLongitude = place.latLng.longitude;
                            if (showAddressError) {
                              setModalState(() => showAddressError = false);
                            }
                          },
                        ),
                      ),
                    ),
                    if (showAddressError)
                      const Padding(
                        padding: EdgeInsets.only(left: 12, top: 6),
                        child: Text(
                          'Address is required',
                          style: TextStyle(color: AppColors.error, fontSize: 12),
                        ),
                      ),
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
                        final labelValue = labelCtrl.text.trim();
                        final addressValue = selectedAddress.trim();
                        final hasLabel = labelValue.isNotEmpty;
                        final hasAddress = addressValue.isNotEmpty;

                        if (!hasLabel || !hasAddress) {
                          setModalState(() {
                            showLabelError = !hasLabel;
                            showAddressError = !hasAddress;
                          });
                          return;
                        }

                        var latitude = selectedLatitude;
                        var longitude = selectedLongitude;

                        if (latitude == null || longitude == null) {
                          final geocoded =
                              await mapsSvc.getLatLngFromAddress(addressValue);
                          if (geocoded == null) {
                            if (mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text(
                                    'Could not locate this address. Pick it from map or choose a suggestion.',
                                  ),
                                ),
                              );
                            }
                            return;
                          }
                          latitude = geocoded.latitude;
                          longitude = geocoded.longitude;
                        }

                        Navigator.pop(ctx);
                        try {
                          final addr = await _svc.addAddress(
                            label: labelValue,
                            address: addressValue,
                            latitude: latitude,
                            longitude: longitude,
                          );
                          setState(() => _addresses.add(addr));
                        } catch (e) {
                          if (mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(content: Text('Failed: $e')),
                            );
                          }
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
                              Icon(Icons.save_rounded, size: 18),
                              SizedBox(width: 10),
                              Text(
                                'SAVE ADDRESS',
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

  void _showEditAddressSheet(SavedAddress address) {
    final labelCtrl = TextEditingController(text: address.label);
    final mapsSvc = MapsService();
    var selectedAddress = address.address;
    double? selectedLatitude = address.latitude;
    double? selectedLongitude = address.longitude;
    var showLabelError = false;
    var showAddressError = false;
    final initialPicked = PickedLocation(
      latLng: LatLng(address.latitude, address.longitude),
      address: address.address,
      name: address.label,
    );

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (ctx, setModalState) {
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
                        color: Colors.grey[300],
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Edit Address',
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: labelCtrl,
                    onChanged: (value) {
                      if (showLabelError && value.trim().isNotEmpty) {
                        setModalState(() => showLabelError = false);
                      }
                    },
                    decoration: InputDecoration(
                      labelText: 'Label (e.g. Home, Work)',
                      prefixIcon: const Icon(Icons.label_rounded),
                      errorText: showLabelError ? 'Label is required' : null,
                    ),
                  ),
                  const SizedBox(height: 12),
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    decoration: BoxDecoration(
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusMedium),
                      border: Border.all(
                        color: showAddressError
                            ? AppColors.error
                            : Colors.transparent,
                        width: showAddressError ? 1.5 : 0,
                      ),
                    ),
                    child: PlaceSearchField(
                      hint: 'Address - type to search or tap map',
                      dotColor: AppColors.primary,
                      value: initialPicked,
                      backgroundColor: const Color(0xFF121F1B),
                      borderColor: Colors.white.withValues(alpha: 0.1),
                      textColor: const Color(0xFFE9F7EF),
                      hintColor: const Color(0xFF8BA095),
                      mapIconColor: const Color(0xFF4BF0A1),
                      suggestionBackgroundColor: const Color(0xFF121F1B),
                      suggestionBorderColor:
                          Colors.white.withValues(alpha: 0.1),
                      suggestionTextColor: const Color(0xFFE9F7EF),
                      suggestionSubtitleColor: const Color(0xFF8BA095),
                      onTextChanged: (value) {
                        selectedAddress = value.trim();
                        selectedLatitude = null;
                        selectedLongitude = null;
                        if (showAddressError && selectedAddress.isNotEmpty) {
                          setModalState(() => showAddressError = false);
                        }
                      },
                      onPlaceSelected: (place) {
                        selectedAddress = place.address.trim();
                        selectedLatitude = place.latLng.latitude;
                        selectedLongitude = place.latLng.longitude;
                        if (showAddressError) {
                          setModalState(() => showAddressError = false);
                        }
                      },
                    ),
                  ),
                  if (showAddressError)
                    const Padding(
                      padding: EdgeInsets.only(left: 12, top: 6),
                      child: Text(
                        'Address is required',
                        style: TextStyle(color: AppColors.error, fontSize: 12),
                      ),
                    ),
                  const SizedBox(height: 20),
                  SizedBox(
                    height: 48,
                    child: ElevatedButton(
                      onPressed: () async {
                        final labelValue = labelCtrl.text.trim();
                        final addressValue = selectedAddress.trim();
                        final hasLabel = labelValue.isNotEmpty;
                        final hasAddress = addressValue.isNotEmpty;

                        if (!hasLabel || !hasAddress) {
                          setModalState(() {
                            showLabelError = !hasLabel;
                            showAddressError = !hasAddress;
                          });
                          return;
                        }

                        var latitude = selectedLatitude;
                        var longitude = selectedLongitude;

                        if (latitude == null || longitude == null) {
                          final geocoded =
                              await mapsSvc.getLatLngFromAddress(addressValue);
                          if (geocoded == null) {
                            if (mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text(
                                    'Could not locate this address. Pick it from map or choose a suggestion.',
                                  ),
                                ),
                              );
                            }
                            return;
                          }
                          latitude = geocoded.latitude;
                          longitude = geocoded.longitude;
                        }

                        Navigator.pop(ctx);
                        try {
                          final updated = await _svc.updateAddress(
                            address.id,
                            label: labelValue,
                            address: addressValue,
                            latitude: latitude,
                            longitude: longitude,
                          );

                          if (!mounted) return;

                          setState(() {
                            final idx = _addresses.indexWhere(
                              (a) => a.id == address.id,
                            );
                            if (idx != -1) {
                              _addresses[idx] = updated;
                            }
                          });

                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Address updated')),
                          );
                        } catch (e) {
                          if (mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(content: Text('Update failed: $e')),
                            );
                          }
                        }
                      },
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.primary,
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(
                            AppConstants.radiusMedium,
                          ),
                        ),
                      ),
                      child: const Text('Save Changes'),
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

  Future<void> _showAddressActionsMenu(SavedAddress address) async {
    if (!mounted) return;

    await showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) => Container(
        decoration: BoxDecoration(
          color: AppColors.surface,
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
              ListTile(
                leading:
                    const Icon(Icons.more_horiz_rounded, color: AppColors.info),
                title: Text(
                  address.label,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                subtitle: Text(
                  address.address,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              ListTile(
                leading:
                    const Icon(Icons.edit_rounded, color: AppColors.primary),
                title: const Text('Edit Address'),
                onTap: () {
                  Navigator.pop(ctx);
                  _showEditAddressSheet(address);
                },
              ),
              ListTile(
                leading: const Icon(
                  Icons.delete_outline_rounded,
                  color: AppColors.error,
                ),
                title: const Text('Delete Address'),
                onTap: () async {
                  Navigator.pop(ctx);
                  await _confirmDeleteAddress(address);
                },
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }
}
