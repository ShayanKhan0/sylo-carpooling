import 'package:flutter/material.dart';

/// Sylo App Color Palette — Clean, Modern & Professional
///
/// Theme-sensitive colors automatically switch between light and dark mode
/// via the [isDark] flag, which is synced by [ThemeProvider].
class AppColors {
  AppColors._();

  /// Updated by ThemeProvider when theme changes.
  static bool isDark = false;

  // ── Brand Colors (Sylo Green Theme) ──────────
  static const Color primary = Color(0xFF43E892); // Light mode brand green
  static const Color primaryDark = Color(0xFF2FCB77); // Dark mode active green

  // ── Dark Surface (used for contrast) ─────────
  static const Color charcoal = Color(0xFF111827);
  static const Color charcoalLight = Color(0xFF1E1E1E);
  static const Color charcoalMid = Color(0xFF2D2D2D);

  // ── Secondary & Accent (constant) ─────────────────────────
  static const Color secondary = Color(0xFF6366F1);
  static const Color accent = Color(0xFFF59E0B);
  static const Color accentDark = Color(0xFFD97706);
  static const Color primaryLight = Color(0xFFBFDBFE);

  // ── Background (theme-aware) ──────────────────────────────
  static Color get background =>
      isDark ? const Color(0xFF121212) : const Color(0xFFF9FAFB);
  static Color get backgroundLight =>
      isDark ? const Color(0xFF2C2C2C) : const Color(0xFFF3F4F6);
  static Color get surface =>
      isDark ? const Color(0xFF1E1E1E) : const Color(0xFFFFFFFF);

  // ── Text (theme-aware) ────────────────────────────────────
  static Color get textPrimary =>
      isDark ? const Color(0xFFE0E0E0) : const Color(0xFF111827);
  static Color get textSecondary =>
      isDark ? const Color(0xFFB0B0B0) : const Color(0xFF6B7280);
  static Color get textHint =>
      isDark ? const Color(0xFF757575) : const Color(0xFF9CA3AF);
  static const Color textOnPrimary = Color(0xFFFFFFFF);
  static const Color textOnDark = Color(0xFFF9FAFB);

  // ── Status (constant) ─────────────────────────────────────
  static const Color success = Color(0xFF22C55E);
  static const Color warning = Color(0xFFFBBF24);
  static const Color error = Color(0xFFEF4444);
  static const Color info = Color(0xFF43E892);

  // ── Divider & Border (theme-aware) ────────────────────────
  static Color get divider =>
      isDark ? const Color(0xFF424242) : const Color(0xFFE5E7EB);
  static Color get border =>
      isDark ? const Color(0xFF424242) : const Color(0xFFE5E7EB);

  // ── Shadow ────────────────────────────────────────────────
  static Color get shadow =>
      isDark ? const Color(0x26000000) : const Color(0x14111827);
  static Color get shadowDark =>
      isDark ? const Color(0x40000000) : const Color(0x26111827);

  // ── Gradients (convenience) ───────────────────────────────
  static const List<Color> brandGradient = [
    Color(0xFF43E892),
    Color(0xFF2FCB77),
  ];

  static const List<Color> darkGradient = [
    Color(0xFF111827),
    Color(0xFF1F2937),
  ];

  static const List<Color> splashGradient = [
    Color(0xFF111827),
    Color(0xFF1F2937),
    Color(0xFF374151),
  ];
}
