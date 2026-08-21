// Sylo App Widget Tests

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:sylo/main.dart';

void main() {
  testWidgets('Sylo app smoke test', (WidgetTester tester) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const SyloApp());

    // Verify that the splash screen is shown initially
    expect(find.text('Sylo'), findsOneWidget);
  });

  testWidgets('SplashScreen widget test', (WidgetTester tester) async {
    // Test the splash screen wrapper
    await tester.pumpWidget(const MaterialApp(
      home: SplashScreenWrapper(),
    ));

    // Initially should show loading indicator
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });
}
