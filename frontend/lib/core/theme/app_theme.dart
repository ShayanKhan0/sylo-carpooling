import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'app_colors.dart';

class AppTheme {
  AppTheme._();

  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,

      // Color Scheme
      colorScheme: ColorScheme.light(
        primary: AppColors.primary,
        secondary: AppColors.secondary,
        tertiary: AppColors.accent,
        surface: AppColors.surface,
        error: AppColors.error,
        onPrimary: AppColors.textOnPrimary,
        onSecondary: AppColors.textOnPrimary,
        onSurface: AppColors.textPrimary,
        onError: Colors.white,
      ),

      // Scaffold Background
      scaffoldBackgroundColor: AppColors.background,

      // AppBar Theme
      appBarTheme: AppBarTheme(
        elevation: 0,
        centerTitle: true,
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.textPrimary,
        systemOverlayStyle: SystemUiOverlayStyle.dark,
        iconTheme: IconThemeData(color: AppColors.textPrimary),
        titleTextStyle: TextStyle(
          color: AppColors.textPrimary,
          fontSize: 20,
          fontWeight: FontWeight.w600,
          fontFamily: 'Inter',
        ),
      ),

      // Text Theme
      textTheme: TextTheme(
        displayLarge: TextStyle(
          fontSize: 32,
          fontWeight: FontWeight.bold,
          color: AppColors.textPrimary,
          fontFamily: 'Inter',
        ),
        displayMedium: TextStyle(
          fontSize: 28,
          fontWeight: FontWeight.bold,
          color: AppColors.textPrimary,
          fontFamily: 'Inter',
        ),
        displaySmall: TextStyle(
          fontSize: 24,
          fontWeight: FontWeight.w600,
          color: AppColors.textPrimary,
          fontFamily: 'Inter',
        ),
        headlineMedium: TextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: AppColors.textPrimary,
          fontFamily: 'Inter',
        ),
        headlineSmall: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: AppColors.textPrimary,
          fontFamily: 'Inter',
        ),
        titleLarge: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: AppColors.textPrimary,
          fontFamily: 'Inter',
        ),
        bodyLarge: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.normal,
          color: AppColors.textPrimary,
          fontFamily: 'Inter',
        ),
        bodyMedium: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.normal,
          color: AppColors.textSecondary,
          fontFamily: 'Inter',
        ),
        bodySmall: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.normal,
          color: AppColors.textSecondary,
          fontFamily: 'Inter',
        ),
      ),

      // Elevated Button Theme — primary on surface
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primary, // Brand green
          foregroundColor: AppColors.textOnPrimary, // White text
          elevation: 0,
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            fontFamily: 'Inter',
          ),
        ),
      ),

      // Outlined Button Theme
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.textPrimary,
          side: BorderSide(color: AppColors.border, width: 1.5),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(14),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          textStyle: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            fontFamily: 'Inter',
          ),
        ),
      ),

      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: const Color(0xFF159A56),
          textStyle: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            fontFamily: 'Inter',
          ),
        ),
      ),

      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: const Color(0xFF052E1E),
          textStyle: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            fontFamily: 'Inter',
          ),
        ),
      ),

      dialogTheme: DialogThemeData(
        backgroundColor: AppColors.surface,
        titleTextStyle: TextStyle(
          color: AppColors.textPrimary,
          fontSize: 30,
          fontWeight: FontWeight.w800,
          fontFamily: 'Inter',
        ),
        contentTextStyle: TextStyle(
          color: AppColors.textSecondary,
          fontSize: 16,
          fontWeight: FontWeight.w500,
          fontFamily: 'Inter',
        ),
      ),

      // Input Decoration Theme
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.backgroundLight,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.primary, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.error),
        ),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        hintStyle: TextStyle(
          color: AppColors.textHint,
          fontSize: 14,
          fontFamily: 'Inter',
        ),
      ),

      // Card Theme
      cardTheme: CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        color: AppColors.surface,
        shadowColor: AppColors.shadow,
      ),

      // Icon Theme
      iconTheme: IconThemeData(
        color: AppColors.textPrimary,
        size: 24,
      ),

      // Divider Theme
      dividerTheme: DividerThemeData(
        color: AppColors.divider,
        thickness: 1,
        space: 1,
      ),

      // Bottom Navigation Bar
      bottomNavigationBarTheme: BottomNavigationBarThemeData(
        backgroundColor: Colors.white,
        selectedItemColor: AppColors.charcoal,
        unselectedItemColor: AppColors.textHint,
        type: BottomNavigationBarType.fixed,
        elevation: 8,
      ),

      // Floating Action Button
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: AppColors.primary,
        foregroundColor: AppColors.charcoal,
        elevation: 4,
      ),
    );
  }

  // ═══════════════════════════════════════════════════════════
  //  DARK THEME
  // ═══════════════════════════════════════════════════════════
  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: const ColorScheme.dark(
        primary: AppColors.primaryDark,
        secondary: AppColors.secondary,
        tertiary: AppColors.accent,
        surface: Color(0xFF1E1E1E),
        error: AppColors.error,
        onPrimary: Colors.white,
        onSecondary: Colors.white,
        onSurface: Color(0xFFF9FAFB),
        onError: Colors.white,
      ),
      scaffoldBackgroundColor: const Color(0xFF121212),
      appBarTheme: const AppBarTheme(
        elevation: 0,
        centerTitle: true,
        backgroundColor: Color(0xFF121212),
        foregroundColor: Color(0xFFE0E0E0),
        systemOverlayStyle: SystemUiOverlayStyle.light,
        iconTheme: IconThemeData(color: Color(0xFFE0E0E0)),
        titleTextStyle: TextStyle(
          color: Color(0xFFE0E0E0),
          fontSize: 20,
          fontWeight: FontWeight.w600,
          fontFamily: 'Inter',
        ),
      ),
      textTheme: const TextTheme(
        displayLarge: TextStyle(
            fontSize: 32,
            fontWeight: FontWeight.bold,
            color: Color(0xFFE0E0E0),
            fontFamily: 'Inter'),
        displayMedium: TextStyle(
            fontSize: 28,
            fontWeight: FontWeight.bold,
            color: Color(0xFFE0E0E0),
            fontFamily: 'Inter'),
        displaySmall: TextStyle(
            fontSize: 24,
            fontWeight: FontWeight.w600,
            color: Color(0xFFE0E0E0),
            fontFamily: 'Inter'),
        headlineMedium: TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.w600,
            color: Color(0xFFE0E0E0),
            fontFamily: 'Inter'),
        headlineSmall: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
            color: Color(0xFFE0E0E0),
            fontFamily: 'Inter'),
        titleLarge: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: Color(0xFFE0E0E0),
            fontFamily: 'Inter'),
        bodyLarge: TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.normal,
            color: Color(0xFFE0E0E0),
            fontFamily: 'Inter'),
        bodyMedium: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.normal,
            color: Color(0xFFB0B0B0),
            fontFamily: 'Inter'),
        bodySmall: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.normal,
            color: Color(0xFFB0B0B0),
            fontFamily: 'Inter'),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primaryDark,
          foregroundColor: Colors.white,
          elevation: 0,
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          textStyle: const TextStyle(
              fontSize: 16, fontWeight: FontWeight.w700, fontFamily: 'Inter'),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: const Color(0xFFF9FAFB),
          side: const BorderSide(color: Color(0xFF424242), width: 1.5),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          textStyle: const TextStyle(
              fontSize: 16, fontWeight: FontWeight.w600, fontFamily: 'Inter'),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AppColors.primary,
          textStyle: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            fontFamily: 'Inter',
          ),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: const Color(0xFF052E1E),
          textStyle: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w700,
            fontFamily: 'Inter',
          ),
        ),
      ),
      dialogTheme: const DialogThemeData(
        backgroundColor: Color(0xFF1E1E1E),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFF2D2D2D),
        border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: Color(0xFF424242))),
        enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: Color(0xFF424242))),
        focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide:
                const BorderSide(color: AppColors.primaryDark, width: 2)),
        errorBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(color: AppColors.error)),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        hintStyle: const TextStyle(
            color: Color(0xFF757575), fontSize: 14, fontFamily: 'Inter'),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        color: const Color(0xFF1E1E1E),
      ),
      iconTheme: const IconThemeData(color: Color(0xFFE0E0E0), size: 24),
      dividerTheme: const DividerThemeData(
          color: Color(0xFF424242), thickness: 1, space: 1),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: Color(0xFF1E1E1E),
        selectedItemColor: AppColors.primary,
        unselectedItemColor: Color(0xFF757575),
        type: BottomNavigationBarType.fixed,
        elevation: 8,
      ),
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        elevation: 4,
      ),
    );
  }
}
