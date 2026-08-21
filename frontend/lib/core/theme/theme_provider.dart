import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'app_colors.dart';

/// Manages light/dark theme state and persists the user's preference.
class ThemeProvider extends ChangeNotifier {
  static const String _key = 'theme_mode';

  ThemeMode _themeMode = ThemeMode.light;
  ThemeMode get themeMode => _themeMode;
  bool get isDark => _themeMode == ThemeMode.dark;

  ThemeProvider() {
    _load();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getString(_key);
    if (stored == 'dark') {
      _themeMode = ThemeMode.dark;
    } else {
      _themeMode = ThemeMode.light;
    }
    AppColors.isDark = isDark;
    notifyListeners();
  }

  Future<void> toggle() async {
    _themeMode = isDark ? ThemeMode.light : ThemeMode.dark;
    AppColors.isDark = isDark;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, isDark ? 'dark' : 'light');
  }

  Future<void> setMode(ThemeMode mode) async {
    _themeMode = mode;
    AppColors.isDark = isDark;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, mode == ThemeMode.dark ? 'dark' : 'light');
  }
}
