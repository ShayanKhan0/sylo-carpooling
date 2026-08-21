import 'dart:math';
import 'dart:ui';

import 'package:flutter/material.dart';

const _shaderMotionSpeed = 1.65;

class AuthShaderLoader {
  static Future<FragmentProgram?>? _cachedProgram;

  static Future<FragmentProgram?> sharedProgram() {
    return _cachedProgram ??= _loadProgram();
  }

  static Future<FragmentProgram?> _loadProgram() async {
    try {
      return await FragmentProgram.fromAsset('shaders/auth_minimal.frag');
    } catch (error, stackTrace) {
      debugPrint('[AuthShader] Unable to load shader asset: $error');
      debugPrintStack(stackTrace: stackTrace);
      return null;
    }
  }
}

class AuthShaderLayer extends StatelessWidget {
  const AuthShaderLayer({
    super.key,
    required this.program,
    required this.progress,
    this.intensity = 0.2,
  });

  final FragmentProgram program;
  final double progress;
  final double intensity;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: RepaintBoundary(
        child: CustomPaint(
          painter: _AuthShaderPainter(
            program: program,
            progress: progress,
            intensity: intensity,
          ),
          child: const SizedBox.expand(),
        ),
      ),
    );
  }
}

class AuthShaderFallbackLayer extends StatelessWidget {
  const AuthShaderFallbackLayer({
    super.key,
    required this.progress,
    this.intensity = 0.16,
  });

  final double progress;
  final double intensity;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: RepaintBoundary(
        child: CustomPaint(
          painter: _AuthShaderFallbackPainter(
            progress: progress,
            intensity: intensity,
          ),
          child: const SizedBox.expand(),
        ),
      ),
    );
  }
}

class _AuthShaderPainter extends CustomPainter {
  _AuthShaderPainter({
    required this.program,
    required this.progress,
    required this.intensity,
  });

  final FragmentProgram program;
  final double progress;
  final double intensity;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) {
      return;
    }

    final shader = program.fragmentShader()
      ..setFloat(0, size.width)
      ..setFloat(1, size.height)
      ..setFloat(2, progress * 6.28318530718 * _shaderMotionSpeed)
      ..setFloat(3, intensity);

    final paint = Paint()..shader = shader;
    canvas.drawRect(Offset.zero & size, paint);
  }

  @override
  bool shouldRepaint(covariant _AuthShaderPainter oldDelegate) {
    return oldDelegate.progress != progress ||
        oldDelegate.intensity != intensity ||
        oldDelegate.program != program;
  }
}

class _AuthShaderFallbackPainter extends CustomPainter {
  _AuthShaderFallbackPainter({
    required this.progress,
    required this.intensity,
  });

  final double progress;
  final double intensity;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) {
      return;
    }

    final phase = progress * 6.28318530718 * _shaderMotionSpeed;
    final glowAlpha = (0.03 + (0.06 * intensity)).clamp(0.0, 1.0).toDouble();
    final lineAlpha = (0.04 + (0.07 * intensity)).clamp(0.0, 1.0).toDouble();
    final lineColor = Colors.white.withValues(alpha: lineAlpha);

    final linePaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.6
      ..strokeCap = StrokeCap.round
      ..shader = LinearGradient(
        colors: [
          Colors.transparent,
          Colors.white.withValues(alpha: glowAlpha),
          lineColor,
          Colors.transparent,
        ],
        stops: const [0.0, 0.32, 0.62, 1.0],
      ).createShader(Offset.zero & size);

    const lineCount = 7;
    for (var i = 0; i < lineCount; i++) {
      final t = i / (lineCount - 1);
      final baseY = size.height * (0.18 + (t * 0.68));
      final sway = sin(phase + (i * 0.92)) * 13;
      final curveLift = cos((phase * 0.72) + (i * 1.18)) * 16;

      final path = Path()
        ..moveTo(-44, baseY + sway)
        ..quadraticBezierTo(
          size.width * 0.46,
          baseY + curveLift,
          size.width + 44,
          baseY + (sway * 0.58),
        );

      canvas.drawPath(path, linePaint);
    }

    final orbAlpha = (0.02 + (0.04 * intensity)).clamp(0.0, 1.0).toDouble();
    final orbPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          Colors.white.withValues(alpha: orbAlpha),
          Colors.transparent,
        ],
      ).createShader(
        Rect.fromCircle(
          center: Offset(
            size.width * 0.66,
            (size.height * 0.31) + (sin(phase * 0.45) * 22),
          ),
          radius: size.shortestSide * 0.58,
        ),
      );
    canvas.drawRect(Offset.zero & size, orbPaint);
  }

  @override
  bool shouldRepaint(covariant _AuthShaderFallbackPainter oldDelegate) {
    return oldDelegate.progress != progress ||
        oldDelegate.intensity != intensity;
  }
}
