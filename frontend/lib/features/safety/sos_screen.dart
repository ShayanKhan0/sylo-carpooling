import 'dart:async';

import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'package:geolocator/geolocator.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/services/safety_service.dart';
import '../../core/theme/app_colors.dart';
import '../dashboard/home_design_system.dart';

class SOSScreen extends StatefulWidget {
  final String? rideId;

  const SOSScreen({super.key, this.rideId});

  @override
  State<SOSScreen> createState() => _SOSScreenState();
}

class _SOSScreenState extends State<SOSScreen> {
  final SafetyService _svc = SafetyService();
  static const Color _homeTextPrimary = Color(0xFF122019);
  static const Color _homeTextSecondary = Color(0xFF355143);

  bool _sending = false;
  bool _sosSent = false;
  double _sliderProgress = 0;
  bool _triggeredFromSlide = false;
  bool _eligibilityLoaded = false;
  bool _canSendSos = false;
  String _eligibilityMessage = 'You can send SOS only after the ride starts.';
  String? _eligibleRideId;

  @override
  void initState() {
    super.initState();
    unawaited(_loadEligibility());
  }

  @override
  void dispose() {
    super.dispose();
  }

  Future<void> _sendSOS() async {
    if (!_canSendSos) {
      await _showSosUnavailablePopup();
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF16202B),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(
            color: Colors.white.withValues(alpha: 0.16),
            width: 1,
          ),
        ),
        title: Row(
          children: [
            const Icon(Icons.warning_rounded, color: AppColors.error, size: 28),
            const SizedBox(width: 8),
            Text(
              'Send SOS?',
              style: GoogleFonts.inter(
                color: Colors.white,
                fontWeight: FontWeight.w700,
                fontSize: 20,
              ),
            ),
          ],
        ),
        content: Text(
          'This will send an in-app emergency alert to the Sylo admin team. '
          'Note: This does NOT contact police, ambulance, or any real emergency service. '
          'In a real emergency, please call 1122 or 15 directly.',
          style: GoogleFonts.inter(
            color: Colors.white.withValues(alpha: 0.84),
            fontSize: 14,
            height: 1.4,
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(
              'Cancel',
              style: GoogleFonts.inter(
                color: Colors.white.withValues(alpha: 0.8),
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.error,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            child: const Text('Send SOS'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    setState(() => _sending = true);
    try {
      double? lat;
      double? lng;
      try {
        final pos = await Geolocator.getCurrentPosition(
          locationSettings: const LocationSettings(
            accuracy: LocationAccuracy.high,
            timeLimit: Duration(seconds: 5),
          ),
        );
        lat = pos.latitude;
        lng = pos.longitude;
      } catch (_) {
        // GPS unavailable, SOS still sends.
      }

      await _svc.sendSOS(
        rideId: widget.rideId ?? _eligibleRideId,
        latitude: lat,
        longitude: lng,
        message: 'Emergency SOS from Sylo app',
      );

      if (!mounted) return;
      setState(() {
        _sending = false;
        _sosSent = true;
        _sliderProgress = 1;
      });
    } on DioException catch (e) {
      final status = e.response?.statusCode;
      final detail = (e.response?.data is Map)
          ? ((e.response?.data['detail'] ??
                  e.response?.data['error']?['detail'] ??
                  e.response?.data['error'])
              ?.toString())
          : null;
      if (status == 403) {
        if (detail != null && detail.trim().isNotEmpty) {
          _eligibilityMessage = detail.trim();
        }
        await _loadEligibility();
        if (!mounted) return;
        setState(() {
          _sending = false;
          _triggeredFromSlide = false;
          _sliderProgress = 0;
        });
        await _showSosUnavailablePopup();
        return;
      }
      if (!mounted) return;
      setState(() {
        _sending = false;
        _triggeredFromSlide = false;
        _sliderProgress = 0;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('SOS failed: ${detail ?? e.message ?? e}')),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _sending = false;
        _triggeredFromSlide = false;
        _sliderProgress = 0;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('SOS failed: $e')),
      );
    }
  }

  Future<void> _loadEligibility() async {
    try {
      final data = await _svc.getSosEligibility();
      if (!mounted) return;
      setState(() {
        _eligibilityLoaded = true;
        _canSendSos = data['can_send'] == true;
        _eligibleRideId = data['ride_id']?.toString();
        final msg = data['reason']?.toString().trim();
        if (msg != null && msg.isNotEmpty) {
          _eligibilityMessage = msg;
        }
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _eligibilityLoaded = true;
        _canSendSos = false;
      });
    }
  }

  Future<void> _showSosUnavailablePopup() async {
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('SOS unavailable'),
        content: Text(_eligibilityMessage),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  BoxDecoration _homeCardDecoration({
    double radius = 22,
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
            offset: const Offset(0, 14),
          ),
        if (elevated)
          BoxShadow(
            color: const Color(0xFF31CD83).withValues(alpha: 0.12),
            blurRadius: 26,
            spreadRadius: -10,
            offset: const Offset(0, 8),
          ),
        BoxShadow(
          color: Colors.white.withValues(alpha: 0.07),
          blurRadius: 18,
          spreadRadius: -8,
          offset: const Offset(-6, -6),
        ),
      ],
    );
  }

  Widget _buildDriverThemeBackground() {
    return HomeDesignSystem.driverHomeSoftWhiteBackground();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: Stack(
        children: [
          _buildDriverThemeBackground(),
          SafeArea(
            child: HomeDesignSystem.contentWidth(
              child: ListView(
                physics: const BouncingScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(16, 10, 16, 28),
                children: [
                  _buildTopBar(),
                  const SizedBox(height: 16),
                  _buildSlideSosCard(),
                  const SizedBox(height: 16),
                  _buildEmergencyContactsSection(),
                  const SizedBox(height: 16),
                  _buildSafetyProtocolsCard(),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTopBar() {
    return HomeDesignSystem.frostLayer(
      blur: 10,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        decoration: _homeCardDecoration(
          radius: 24,
          elevated: true,
          borderAlpha: 0.52,
          borderWidth: 1.05,
        ),
        child: Row(
          children: [
            Container(
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    Color(0x33FFFFFF),
                    Color(0x1A20283B),
                  ],
                ),
                border: Border.all(
                  color: Colors.white.withValues(alpha: 0.34),
                  width: 1.05,
                ),
                shape: BoxShape.circle,
              ),
              child: IconButton(
                onPressed: () => Navigator.maybePop(context),
                icon: const Icon(Icons.arrow_back_rounded,
                    color: _homeTextPrimary, size: 22),
                padding: const EdgeInsets.all(10),
                constraints: const BoxConstraints(minWidth: 42, minHeight: 42),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Emergency SOS',
                    style: GoogleFonts.inter(
                      color: _homeTextPrimary,
                      fontSize: 40,
                      fontWeight: FontWeight.w900,
                      height: 0.96,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Immediate assistance is available. Slide to\nalert authorities.',
                    style: GoogleFonts.inter(
                      color: _homeTextSecondary,
                      fontSize: 14,
                      height: 1.3,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSlideSosCard() {
    const trackHeight = 76.0;
    const thumbSize = 62.0;
    return HomeDesignSystem.frostLayer(
      blur: 12,
      child: Container(
        padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
        decoration: _homeCardDecoration(
          radius: 22,
          elevated: true,
          borderAlpha: 0.54,
        ),
        child: LayoutBuilder(
          builder: (context, constraints) {
            final maxSlide = (constraints.maxWidth - thumbSize).clamp(1, 9999);
            final thumbLeft = maxSlide * _sliderProgress;
            return SizedBox(
              height: trackHeight,
              child: Stack(
                children: [
                  Positioned.fill(
                    child: Container(
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                          colors: [
                            Color(0xFF0F241C),
                            Color(0xFF10261E),
                          ],
                        ),
                        borderRadius: BorderRadius.circular(999),
                        border: Border.all(
                          color: Colors.white.withValues(alpha: 0.08),
                        ),
                      ),
                    ),
                  ),
                  Positioned.fill(
                    child: Center(
                      child: Text(
                        _sosSent
                            ? 'SOS SENT'
                            : !_eligibilityLoaded
                                ? 'CHECKING SOS ELIGIBILITY'
                                : _canSendSos
                                    ? 'SLIDE TO SEND SOS'
                                    : 'SOS UNAVAILABLE',
                        style: GoogleFonts.inter(
                          color: Colors.white.withValues(alpha: 0.52),
                          fontWeight: FontWeight.w800,
                          letterSpacing: 2.1,
                          fontSize: 11,
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    left: thumbLeft,
                    top: (trackHeight - thumbSize) / 2,
                    child: GestureDetector(
                      onHorizontalDragUpdate: _sending || _sosSent
                          ? null
                          : (details) {
                              setState(() {
                                _sliderProgress = (_sliderProgress +
                                        details.delta.dx / maxSlide)
                                    .clamp(0.0, 1.0);
                              });
                            },
                      onHorizontalDragEnd: _sending || _sosSent
                          ? null
                          : (_) async {
                              if (_sliderProgress >= 0.92 &&
                                  !_triggeredFromSlide) {
                                _triggeredFromSlide = true;
                                await _sendSOS();
                                if (!mounted) return;
                                if (!_sosSent) {
                                  setState(() {
                                    _sliderProgress = 0;
                                    _triggeredFromSlide = false;
                                  });
                                }
                              } else {
                                setState(() => _sliderProgress = 0);
                              }
                            },
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 140),
                        width: thumbSize,
                        height: thumbSize,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          gradient: const RadialGradient(
                            colors: [
                              Color(0xFFF9A0A0),
                              Color(0xFFD84C4C),
                              Color(0xFF8E2020),
                            ],
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: AppColors.error.withValues(alpha: 0.45),
                              blurRadius: 16,
                              spreadRadius: 1.4,
                            ),
                          ],
                        ),
                        child: Center(
                          child: _sending
                              ? const SizedBox(
                                  width: 22,
                                  height: 22,
                                  child: CircularProgressIndicator(
                                    color: Color(0xFF2A0000),
                                    strokeWidth: 2.4,
                                  ),
                                )
                              : Icon(
                                  _sosSent
                                      ? Icons.check_rounded
                                      : Icons.emergency_rounded,
                                  color: const Color(0xFF3A0505),
                                  size: 26,
                                ),
                        ),
                      ),
                    ),
                  ),
                  Positioned(
                    right: 20,
                    top: 0,
                    bottom: 0,
                    child: Icon(
                      Icons.chevron_right_rounded,
                      color: Colors.white.withValues(alpha: 0.4),
                    ),
                  ),
                ],
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildSafetyProtocolsCard() {
    const protocols = <({String title, String desc})>[
      (
        title: 'Share your ride details',
        desc: 'Share trip details with a trusted contact before leaving.'
      ),
      (
        title: 'Verify driver and vehicle',
        desc: 'Check plate and profile before starting your ride.'
      ),
      (
        title: 'Stay visible and alert',
        desc: 'Prefer well-lit public areas and avoid isolated stops.'
      ),
      (
        title: 'Trust your instincts',
        desc: 'Cancel and report immediately if something feels wrong.'
      ),
      (
        title: 'Keep belongings with you',
        desc: 'Do not leave important items unattended in the vehicle.'
      ),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 10),
          child: Text(
            'SAFETY PROTOCOLS',
            style: GoogleFonts.inter(
              color: const Color(0xFF1E7D53),
              fontSize: 14,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.0,
            ),
          ),
        ),
        ...protocols.map((p) => _protocolTile(p.title, p.desc)),
      ],
    );
  }

  Widget _buildEmergencyContactsSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 10),
          child: Text(
            'EMERGENCY CONTACTS',
            style: GoogleFonts.inter(
              color: const Color(0xFF4CF2A8),
              fontSize: 14,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.0,
            ),
          ),
        ),
        Row(
          children: [
            Expanded(
              child: _emergencyContactCard(
                icon: Icons.local_police_rounded,
                title: 'Police',
                subtitle: 'Emergency\nDispatch',
                number: '15',
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _emergencyContactCard(
                icon: Icons.local_hospital_rounded,
                title: 'Ambulance',
                subtitle: 'Medical\nEmergency',
                number: '1122',
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        _emergencyContactCard(
          icon: Icons.support_agent_rounded,
          title: 'Sylo Support',
          subtitle: 'In-app\nEmergency Desk',
          number: '0800-SYLO',
          fullWidth: true,
        ),
      ],
    );
  }

  Widget _emergencyContactCard({
    required IconData icon,
    required String title,
    required String subtitle,
    required String number,
    bool fullWidth = false,
  }) {
    final card = Container(
      constraints: BoxConstraints(minHeight: fullWidth ? 104 : 138),
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
      decoration: BoxDecoration(
        color: const Color(0xFF1F2926),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.32),
            blurRadius: 18,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: const BoxDecoration(
                  shape: BoxShape.circle,
                  color: Color(0xFF2B3934),
                ),
                child: Icon(icon, size: 18, color: const Color(0xFF4CF2A8)),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF0F1614),
                  borderRadius: BorderRadius.circular(999),
                  border:
                      Border.all(color: Colors.white.withValues(alpha: 0.08)),
                ),
                child: Text(
                  number,
                  style: GoogleFonts.inter(
                    color: const Color(0xFFE6FFF3),
                    fontWeight: FontWeight.w700,
                    fontSize: 11,
                    letterSpacing: 0.4,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Text(
            title,
            style: GoogleFonts.inter(
              color: const Color(0xFFF4FFF8),
              fontSize: 15.5,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            subtitle,
            style: GoogleFonts.inter(
              color: const Color(0xFFDCF4E8),
              fontSize: 11,
              fontWeight: FontWeight.w600,
              height: 1.3,
            ),
          ),
        ],
      ),
    );
    return fullWidth ? SizedBox(width: double.infinity, child: card) : card;
  }

  Widget _protocolTile(String title, String desc) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: HomeDesignSystem.frostLayer(
        blur: 8,
        radius: 18,
        child: Container(
          constraints: const BoxConstraints(minHeight: 96),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
          decoration: _homeCardDecoration(
            radius: 18,
            elevated: false,
            borderAlpha: 0.54,
            borderWidth: 1.1,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: const Color(0xFF43E892).withValues(alpha: 0.24),
                  border: Border.all(
                    color: const Color(0xFF43E892).withValues(alpha: 0.48),
                  ),
                ),
                child: Icon(
                  Icons.shield_outlined,
                  size: 20,
                  color: const Color(0xFF0E6A42).withValues(alpha: 0.96),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: GoogleFonts.inter(
                        color: _homeTextPrimary,
                        fontSize: 16,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      desc,
                      style: GoogleFonts.inter(
                        color: _homeTextSecondary,
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        height: 1.35,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
