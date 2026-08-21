import 'package:flutter/material.dart';

class AuthDesignTokens {
  AuthDesignTokens._();

  // User-provided core palette (kept as anchors)
  static const Color brandDeep = Color(0xFF02542D);
  static const Color brandAction = Color(0xFF009951);
  static const Color white = Color(0xFFFFFFFF);
  static const Color ink = Color(0xFF252525);

  // Splash-inspired map palette
  static const Color midnight = Color(0xFF022825);
  static const Color slate800 = Color(0xFF033733);
  static const Color slate700 = Color(0xFF044640);
  static const Color routeBlue = Color(0xFF11CDA6);
  static const Color sky400 = Color(0xFF52EED0);
  static const Color cardSurface = Color(0xFFFCFEFE);
  static const Color cardBorder = Color(0xFFD8ECE6);
  static const Color textPrimary = Color(0xFF14312E);
  static const Color textMuted = Color(0xFF4E6A66);
  static const Color lineFog = Color(0xFF9DD8CC);
  static const Color surfaceSoft = Color(0xFFF5FBF9);
  static const Color glowMint = Color(0xFF78F5DD);

  // Compatibility aliases used across auth files
  static const Color night900 = midnight;
  static const Color night800 = slate800;
  static const Color surface700 = slate700;
  static const Color accent500 = routeBlue;
  static const Color accent400 = sky400;
  static const Color textSecondary = textMuted;

  static const LinearGradient pageGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [
      Color(0xFF022F2A),
      midnight,
      Color(0xFF055A4F),
      Color(0xFF0A7464),
    ],
    stops: [0.0, 0.34, 0.74, 1.0],
  );

  static const LinearGradient pageVeilGradient = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: [
      Color(0x29FFFFFF),
      Color(0x12000000),
      Color(0x26000000),
    ],
    stops: [0.0, 0.45, 1.0],
  );

  static const LinearGradient ctaGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: [
      routeBlue,
      brandAction,
      sky400,
    ],
    stops: [0.0, 0.62, 1.0],
  );

  static BoxDecoration authCardDecoration() {
    return BoxDecoration(
      borderRadius: BorderRadius.circular(28),
      border: Border.all(
        color: cardBorder.withValues(alpha: 0.96),
        width: 1.2,
      ),
      gradient: LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          white.withValues(alpha: 0.985),
          surfaceSoft.withValues(alpha: 0.965),
        ],
      ),
      boxShadow: [
        BoxShadow(
          color: midnight.withValues(alpha: 0.32),
          blurRadius: 52,
          offset: const Offset(0, 24),
        ),
        BoxShadow(
          color: glowMint.withValues(alpha: 0.19),
          blurRadius: 34,
          spreadRadius: -6,
          offset: const Offset(0, 6),
        ),
      ],
    );
  }
}
