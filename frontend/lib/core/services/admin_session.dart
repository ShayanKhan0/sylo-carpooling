class AdminSession {
  static String? _adminToken;

  static String? get token => _adminToken;
  static bool get isLoggedIn => (_adminToken ?? '').isNotEmpty;

  static void setToken(String? token) {
    _adminToken = token;
  }

  static void clear() {
    _adminToken = null;
  }
}
