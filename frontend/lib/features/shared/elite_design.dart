import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../dashboard/home_design_system.dart';

/// EliteDesign is a small design-system façade used by the settings /
/// content screens (Help & FAQ, Terms of Service, Privacy Policy).
///
/// It reuses the Driver Home screen palette so these surfaces blend into
/// the rest of the app: the same green glass cards, black-on-green
/// typography, and neon green accents.
class EliteDesign {
  EliteDesign._();

  // ─────────────────────────────────────────────────────────
  //  Palette (mirrors the Driver Home screen)
  // ─────────────────────────────────────────────────────────
  static const Color textPrimary = Color(0xFF121915);
  static const Color textSecondary = Color(0xFF25352D);
  static const Color accentGreen = Color(0xFF1ED760);
  static const Color accentGreenDark = Color(0xFF0B5B33);

  // ─────────────────────────────────────────────────────────
  //  Typography helpers
  // ─────────────────────────────────────────────────────────
  static TextStyle sectionEyebrow({Color? color}) {
    return GoogleFonts.inter(
      fontSize: 12,
      fontWeight: FontWeight.w800,
      letterSpacing: 2.4,
      color: color ?? textSecondary,
    );
  }

  static TextStyle hero({double size = 32, Color? color}) {
    return GoogleFonts.playfairDisplay(
      fontSize: size,
      fontWeight: FontWeight.w900,
      height: 1.04,
      letterSpacing: 0.2,
      color: color ?? textPrimary,
    );
  }

  static TextStyle sectionTitle({Color? color}) {
    return GoogleFonts.inter(
      fontSize: 17,
      fontWeight: FontWeight.w900,
      letterSpacing: 0.2,
      color: color ?? textPrimary,
    );
  }

  static TextStyle cardTitle({Color? color}) {
    return GoogleFonts.inter(
      fontSize: 15,
      fontWeight: FontWeight.w800,
      letterSpacing: 0.1,
      color: color ?? textPrimary,
    );
  }

  static TextStyle cardBody({double size = 13, Color? color}) {
    return GoogleFonts.inter(
      fontSize: size,
      fontWeight: FontWeight.w500,
      height: 1.5,
      color: (color ?? textSecondary).withValues(alpha: 0.92),
    );
  }

  // ─────────────────────────────────────────────────────────
  //  Decorations
  // ─────────────────────────────────────────────────────────
  static BoxDecoration _homeGlass({
    double radius = 22,
    double borderAlpha = 0.42,
    double borderWidth = 1.1,
    bool elevated = true,
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
            color: Colors.black.withValues(alpha: 0.22),
            blurRadius: 28,
            offset: const Offset(0, 10),
          ),
        BoxShadow(
          color: accentGreen.withValues(alpha: 0.28),
          blurRadius: 40,
          spreadRadius: -10,
          offset: const Offset(-6, -4),
        ),
      ],
    );
  }

  // ─────────────────────────────────────────────────────────
  //  Primary panel (card) used for content blocks
  // ─────────────────────────────────────────────────────────
  static Widget panel({
    required Widget child,
    EdgeInsetsGeometry? padding,
    double radius = 22,
  }) {
    return HomeDesignSystem.frostLayer(
      blur: 10,
      radius: radius,
      child: Container(
        padding: padding ?? const EdgeInsets.fromLTRB(18, 18, 18, 18),
        decoration: _homeGlass(radius: radius),
        child: child,
      ),
    );
  }

  // ─────────────────────────────────────────────────────────
  //  Pill-shaped label chip
  // ─────────────────────────────────────────────────────────
  static Widget pill({
    required String label,
    Color? color,
  }) {
    final c = color ?? accentGreen;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        color: c.withValues(alpha: 0.22),
        border: Border.all(color: c.withValues(alpha: 0.6), width: 1),
      ),
      child: Text(
        label,
        style: GoogleFonts.inter(
          fontSize: 10,
          fontWeight: FontWeight.w900,
          letterSpacing: 1.2,
          color: accentGreenDark,
        ),
      ),
    );
  }

  // ─────────────────────────────────────────────────────────
  //  Segmented chip (tab / filter)
  // ─────────────────────────────────────────────────────────
  static Widget segmentedChip({
    required String label,
    required IconData icon,
    required bool selected,
    required VoidCallback onTap,
  }) {
    final bg = selected
        ? accentGreen.withValues(alpha: 0.28)
        : Colors.white.withValues(alpha: 0.12);
    final border = selected
        ? accentGreen.withValues(alpha: 0.72)
        : Colors.white.withValues(alpha: 0.32);
    final textColor = selected ? accentGreenDark : textPrimary;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(999),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(999),
            color: bg,
            border: Border.all(color: border, width: 1.1),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 15, color: textColor),
              const SizedBox(width: 8),
              Text(
                label,
                style: GoogleFonts.inter(
                  fontSize: 11.5,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.4,
                  color: textColor,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ─────────────────────────────────────────────────────────
  //  Scaffold wrapper with the Home-screen background + a
  //  compact top bar (back + title + optional subtitle).
  // ─────────────────────────────────────────────────────────
  static Widget scaffold({
    required BuildContext context,
    required String title,
    String? subtitle,
    required Widget body,
  }) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      backgroundColor: Colors.transparent,
      body: Stack(
        children: [
          HomeDesignSystem.driverHomeSoftWhiteBackground(),
          Positioned.fill(child: body),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 0),
              child: Align(
                alignment: Alignment.topCenter,
                child: ConstrainedBox(
                  constraints:
                      const BoxConstraints(maxWidth: HomeDesignSystem.maxContentWidth),
                  child: HomeDesignSystem.frostLayer(
                    blur: 10,
                    radius: 20,
                    child: Container(
                      padding: const EdgeInsets.fromLTRB(10, 8, 14, 8),
                      decoration: _homeGlass(
                        radius: 20,
                        elevated: false,
                        borderAlpha: 0.32,
                      ),
                      child: Row(
                        children: [
                          _backButton(context),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  title,
                                  style: GoogleFonts.inter(
                                    fontSize: 18,
                                    fontWeight: FontWeight.w900,
                                    letterSpacing: 0.2,
                                    color: textPrimary,
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                if (subtitle != null && subtitle.isNotEmpty) ...[
                                  const SizedBox(height: 2),
                                  Text(
                                    subtitle,
                                    style: GoogleFonts.inter(
                                      fontSize: 12,
                                      fontWeight: FontWeight.w600,
                                      letterSpacing: 0.2,
                                      color: textSecondary,
                                    ),
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                ],
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  static Widget _backButton(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => Navigator.of(context).maybePop(),
        borderRadius: BorderRadius.circular(999),
        child: Container(
          width: 38,
          height: 38,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: Colors.white.withValues(alpha: 0.16),
            border: Border.all(
              color: Colors.white.withValues(alpha: 0.32),
              width: 1.1,
            ),
          ),
          child: const Icon(
            Icons.arrow_back_rounded,
            size: 18,
            color: textPrimary,
          ),
        ),
      ),
    );
  }
}
