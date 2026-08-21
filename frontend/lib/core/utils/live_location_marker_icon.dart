import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

/// Builds and caches a custom live-location marker used on web.
class LiveLocationMarkerIcon {
  static BitmapDescriptor? _cached;
  static Future<BitmapDescriptor>? _pending;

  static Future<BitmapDescriptor> forWeb() {
    if (!kIsWeb) {
      return Future.value(
        BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueAzure),
      );
    }

    if (_cached != null) {
      return Future.value(_cached!);
    }

    _pending ??= _build().then((icon) {
      _cached = icon;
      return icon;
    }).catchError((_) {
      return BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueAzure);
    });

    return _pending!;
  }

  static Future<BitmapDescriptor> _build() async {
    // Keep this compact and fully in-frame on web maps.
    const canvasSize = 48.0;
    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);

    const centerX = canvasSize / 2;

    final shadowPaint = Paint()
      ..color = Colors.black.withValues(alpha: 0.20)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);
    canvas.drawCircle(
      const Offset(centerX, canvasSize * 0.90),
      canvasSize * 0.09,
      shadowPaint,
    );

    final pinPath = Path()
      ..moveTo(centerX, canvasSize * 0.94)
      ..quadraticBezierTo(
        canvasSize * 0.14,
        canvasSize * 0.66,
        canvasSize * 0.20,
        canvasSize * 0.34,
      )
      ..arcToPoint(
        const Offset(canvasSize * 0.80, canvasSize * 0.34),
        radius: const Radius.circular(canvasSize * 0.34),
        clockwise: true,
      )
      ..quadraticBezierTo(
        canvasSize * 0.86,
        canvasSize * 0.66,
        centerX,
        canvasSize * 0.94,
      )
      ..close();

    final pinFill = Paint()..color = Colors.black;
    canvas.drawPath(pinPath, pinFill);

    // White user silhouette in the pin head.
    final iconPaint = Paint()..color = Colors.white;
    canvas.drawCircle(
      const Offset(centerX, canvasSize * 0.35),
      canvasSize * 0.07,
      iconPaint,
    );

    final shoulders = RRect.fromRectAndRadius(
      const Rect.fromLTRB(
        canvasSize * 0.37,
        canvasSize * 0.46,
        canvasSize * 0.63,
        canvasSize * 0.58,
      ),
      const Radius.circular(canvasSize * 0.03),
    );
    canvas.drawRRect(shoulders, iconPaint);

    final neck = RRect.fromRectAndRadius(
      const Rect.fromLTRB(
        canvasSize * 0.47,
        canvasSize * 0.40,
        canvasSize * 0.53,
        canvasSize * 0.46,
      ),
      const Radius.circular(canvasSize * 0.01),
    );
    canvas.drawRRect(neck, iconPaint);

    final image = await recorder
        .endRecording()
        .toImage(canvasSize.toInt(), canvasSize.toInt());
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);

    if (bytes == null) {
      return BitmapDescriptor.defaultMarkerWithHue(BitmapDescriptor.hueAzure);
    }

    return BitmapDescriptor.fromBytes(
      Uint8List.view(bytes.buffer),
    );
  }
}
