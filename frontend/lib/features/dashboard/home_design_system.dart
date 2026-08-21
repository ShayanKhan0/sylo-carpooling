import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../auth/auth_design_tokens.dart';

class HomeDesignSystem {
  HomeDesignSystem._();

  static const double maxContentWidth = 1020;
  static const double sectionHorizontalPadding = 24;

  static const LinearGradient pageGradient = AuthDesignTokens.pageGradient;

  static TextStyle sectionTitle({Color? color}) {
    return GoogleFonts.inter(
      fontSize: 19,
      fontWeight: FontWeight.w700,
      letterSpacing: 0.1,
      color: color ?? AuthDesignTokens.white.withValues(alpha: 0.96),
    );
  }

  static TextStyle cardTitle({Color? color}) {
    return GoogleFonts.inter(
      fontSize: 14,
      fontWeight: FontWeight.w700,
      color: color ?? AuthDesignTokens.white.withValues(alpha: 0.95),
    );
  }

  static TextStyle cardBody({Color? color, double size = 12}) {
    return GoogleFonts.inter(
      fontSize: size,
      fontWeight: FontWeight.w500,
      color: color ?? AuthDesignTokens.white.withValues(alpha: 0.78),
      height: 1.35,
    );
  }

  static TextStyle heroTitleOnDark() {
    return GoogleFonts.playfairDisplay(
      fontSize: 28,
      height: 1.08,
      fontWeight: FontWeight.w800,
      letterSpacing: 0.3,
      color: AuthDesignTokens.white,
      shadows: const [
        Shadow(color: Color(0x66000000), blurRadius: 10),
      ],
    );
  }

  static TextStyle heroSubtitleOnDark() {
    return GoogleFonts.inter(
      fontSize: 13,
      fontWeight: FontWeight.w600,
      color: AuthDesignTokens.white,
      letterSpacing: 0.2,
    );
  }

  static BoxDecoration glassShell({double radius = 26}) {
    return BoxDecoration(
      borderRadius: BorderRadius.circular(radius),
      gradient: LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          AuthDesignTokens.slate800.withValues(alpha: 0.78),
          AuthDesignTokens.midnight.withValues(alpha: 0.84),
        ],
      ),
      border: Border.all(
        color: AuthDesignTokens.white.withValues(alpha: 0.34),
        width: 1.1,
      ),
      boxShadow: [
        BoxShadow(
          color: Colors.black.withValues(alpha: 0.26),
          blurRadius: 28,
          offset: const Offset(0, 12),
        ),
        BoxShadow(
          color: AuthDesignTokens.routeBlue.withValues(alpha: 0.06),
          blurRadius: 24,
          spreadRadius: -8,
          offset: const Offset(0, 8),
        ),
      ],
    );
  }

  static BoxDecoration softPanel({
    double radius = 18,
    bool elevated = false,
  }) {
    return BoxDecoration(
      borderRadius: BorderRadius.circular(radius),
      gradient: LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          AuthDesignTokens.slate800.withValues(alpha: 0.7),
          AuthDesignTokens.midnight.withValues(alpha: 0.76),
        ],
      ),
      border: Border.all(
        color: AuthDesignTokens.white.withValues(alpha: 0.34),
      ),
      boxShadow: [
        if (elevated)
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.28),
            blurRadius: 20,
            offset: const Offset(0, 8),
          ),
      ],
    );
  }

  static BoxDecoration darkTopBarSurface({double radius = 18}) {
    return BoxDecoration(
      borderRadius: BorderRadius.circular(radius),
      gradient: LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          AuthDesignTokens.midnight.withValues(alpha: 0.88),
          AuthDesignTokens.slate800.withValues(alpha: 0.84),
        ],
      ),
      border: Border.all(
        color: AuthDesignTokens.white.withValues(alpha: 0.32),
      ),
    );
  }

  static ButtonStyle subtleOutlineButton(Color color) {
    return OutlinedButton.styleFrom(
      foregroundColor: color,
      side: BorderSide(color: color.withValues(alpha: 0.56)),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      padding: const EdgeInsets.symmetric(vertical: 10),
      textStyle: GoogleFonts.inter(
        fontWeight: FontWeight.w600,
        fontSize: 12,
      ),
    );
  }

  static Widget contentWidth({required Widget child}) {
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: maxContentWidth),
        child: child,
      ),
    );
  }

  static Widget frostLayer({
    required Widget child,
    double blur = 14,
    double radius = 24,
  }) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: blur, sigmaY: blur),
        child: child,
      ),
    );
  }

  static Widget driverHomeBackground() {
    return Stack(
      children: [
        const Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment(-0.75, -1.0),
                end: Alignment(0.85, 1.0),
                colors: [
                  Color(0xFF041A15),
                  Color(0xFF031611),
                  Color(0xFF02130F),
                  Color(0xFF01110D),
                ],
                stops: [0.0, 0.36, 0.72, 1.0],
              ),
            ),
          ),
        ),
        const Positioned.fill(
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  center: Alignment(0.16, -1.08),
                  radius: 1.48,
                  colors: [
                    Color(0x6634E28F),
                    Color(0x1F1CA964),
                    Color(0x0015955A),
                  ],
                  stops: [0.0, 0.34, 1.0],
                ),
              ),
            ),
          ),
        ),
        const Positioned.fill(
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Color(0x2C3FD58A),
                    Color(0x0E1EA866),
                    Color(0x00000000),
                  ],
                  stops: [0.0, 0.26, 0.62],
                ),
              ),
            ),
          ),
        ),
        Align(
          alignment: const Alignment(0.0, 0.47),
          child: IgnorePointer(
            child: FractionallySizedBox(
              widthFactor: 1.22,
              child: AspectRatio(
                aspectRatio: 1,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: const RadialGradient(
                      center: Alignment(0.0, -0.72),
                      radius: 1.08,
                      colors: [
                        Color(0xFF021510),
                        Color(0xFF01130E),
                        Color(0xFF01110D),
                      ],
                      stops: [0.0, 0.58, 1.0],
                    ),
                    border: Border.all(
                      color: const Color(0x102CC37D),
                      width: 1.2,
                    ),
                    boxShadow: const [
                      BoxShadow(
                        color: Color(0x66000000),
                        blurRadius: 64,
                        spreadRadius: 8,
                        offset: Offset(0, 24),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
        const Positioned.fill(
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment(-0.95, -0.1),
                  end: Alignment(1.0, 0.56),
                  colors: [
                    Color(0x00000000),
                    Color(0x22010807),
                    Color(0x00000000),
                  ],
                  stops: [0.16, 0.44, 0.88],
                ),
              ),
            ),
          ),
        ),
        const Positioned.fill(
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Color(0x12FFFFFF),
                    Color(0x08000000),
                    Color(0x22000000),
                  ],
                  stops: [0.0, 0.38, 1.0],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  static Widget driverHomeSoftWhiteBackground() {
    return Stack(
      children: [
        const Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment(-0.9, -1.0),
                end: Alignment(0.95, 1.0),
                colors: [
                  Color(0xFFF0F2F5),
                  Color(0xFFE7EAEE),
                  Color(0xFFDDE2E8),
                ],
                stops: [0.0, 0.58, 1.0],
              ),
            ),
          ),
        ),
        const Positioned.fill(
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment(-1.0, -0.78),
                  end: Alignment(1.0, 0.92),
                  colors: [
                    Color(0x2CFFFFFF),
                    Color(0x00FFFFFF),
                    Color(0x16FFFFFF),
                  ],
                  stops: [0.0, 0.52, 1.0],
                ),
              ),
            ),
          ),
        ),
        Positioned(
          top: -200,
          right: -160,
          child: IgnorePointer(
            child: Transform.rotate(
              angle: -0.33,
              child: Container(
                width: 520,
                height: 400,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(320),
                  gradient: const LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Color(0xD3FFFFFF),
                      Color(0x6DEEF1F5),
                      Color(0x12E1E6ED),
                    ],
                    stops: [0.0, 0.62, 1.0],
                  ),
                  boxShadow: const [
                    BoxShadow(
                      color: Color(0x0DFFFFFF),
                      blurRadius: 72,
                      spreadRadius: 16,
                      offset: Offset(-20, 10),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        Positioned(
          top: 28,
          left: -130,
          right: -88,
          child: IgnorePointer(
            child: Transform.rotate(
              angle: -0.08,
              child: Container(
                height: 320,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(280),
                  gradient: const LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      Color(0x42FFFFFF),
                      Color(0x14EDF1F6),
                      Color(0x00E8EDF4),
                    ],
                    stops: [0.0, 0.5, 1.0],
                  ),
                ),
              ),
            ),
          ),
        ),
        Positioned(
          left: -238,
          bottom: -194,
          child: IgnorePointer(
            child: Transform.rotate(
              angle: -0.24,
              child: Container(
                width: 640,
                height: 370,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(340),
                  gradient: const LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      Color(0x9AFFFFFF),
                      Color(0x34E9EEF4),
                      Color(0x09DEE4EC),
                    ],
                    stops: [0.02, 0.56, 1.0],
                  ),
                  boxShadow: const [
                    BoxShadow(
                      color: Color(0x0FADB6C3),
                      blurRadius: 54,
                      spreadRadius: 8,
                      offset: Offset(0, 24),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        const Positioned.fill(
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Color(0x00FFFFFF),
                    Color(0x0EC3CBD5),
                    Color(0x210D161F),
                  ],
                  stops: [0.0, 0.66, 1.0],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
