import 'dart:convert';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../constants/app_constants.dart';
import 'auth_service.dart';

class AuthMessageException implements Exception {
  final String message;
  const AuthMessageException(this.message);

  @override
  String toString() => message;
}

/// Service that bridges Firebase Authentication with the FastAPI backend.
///
/// Flow:
///   1. User signs in/up via Firebase (email+password).
///   2. Firebase returns an ID token.
///   3. This service sends the ID token to the backend.
///   4. Backend verifies the token, creates/finds the user, returns a JWT.
///   5. The backend JWT is stored locally for all future API calls.
class FirebaseAuthService {
  static final FirebaseAuthService _instance = FirebaseAuthService._internal();
  factory FirebaseAuthService() => _instance;
  FirebaseAuthService._internal();

  final FirebaseAuth _auth = FirebaseAuth.instance;

  void _log(String message) {
    debugPrint('[FirebaseAuthService] $message');
  }

  String _apiUnavailableMessage() {
    return 'Cannot reach the backend at ${AppConstants.baseUrl}. ${AppConstants.apiConnectionHelp}';
  }

  AuthMessageException _friendlyNetworkException(dynamic e) {
    final raw = e.toString().toLowerCase();

    if (raw.contains('failed to fetch') ||
        raw.contains('clientexception') ||
        raw.contains('socketexception') ||
        raw.contains('xmlhttprequest')) {
      return AuthMessageException(_apiUnavailableMessage());
    }

    if (raw.contains('timeout')) {
      return AuthMessageException(
        'Request timed out while contacting ${AppConstants.baseUrl}. ${AppConstants.apiConnectionHelp}',
      );
    }

    return const AuthMessageException(
      'Authentication failed. Please try again.',
    );
  }

  String _extractDetailFromResponseBody(String body, String fallbackMessage) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map) {
        final detail = decoded['detail'] ?? decoded['error']?['detail'];
        if (detail is String && detail.trim().isNotEmpty) {
          return detail;
        }
        if (detail is List && detail.isNotEmpty) {
          return detail.first.toString();
        }
      }
    } catch (_) {
      _log('Failed to parse error body as JSON');
    }

    return fallbackMessage;
  }

  // ─────────────────────────────────────────────────────────
  //  Email / Password — Sign Up
  // ─────────────────────────────────────────────────────────
  Future<Map<String, dynamic>> signUpWithEmail({
    required String email,
    required String password,
    required String fullName,
    required String phone,
    String role = 'passenger',
  }) async {
    _log('signUpWithEmail started for email=$email role=$role');
    UserCredential credential;

    // 1. Create user in Firebase (or sign in if already exists from a prior partial signup)
    try {
      credential = await _auth.createUserWithEmailAndPassword(
        email: email,
        password: password,
      );
      _log(
          'Firebase createUserWithEmailAndPassword succeeded for email=$email');
      await credential.user!.updateDisplayName(fullName);
    } on FirebaseAuthException catch (e) {
      _log('Firebase signup error code=${e.code} message=${e.message}');
      if (e.code == 'email-already-in-use') {
        // User exists in Firebase but may not be in backend DB (partial failure).
        // Sign in to Firebase to get a valid ID token.
        credential = await _auth.signInWithEmailAndPassword(
          email: email,
          password: password,
        );
        _log(
            'Email already in use; signed in existing Firebase user for email=$email');
      } else {
        rethrow;
      }
    }

    try {
      // 2. Get Firebase ID token
      final idToken = await credential.user!.getIdToken();
      _log(
          'Firebase ID token acquired for signup flow (uid=${credential.user?.uid})');

      // 3. Register in backend (profile data only — Firebase handles auth)
      final response = await http
          .post(
            Uri.parse('${AppConstants.baseUrl}/auth/register'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'firebase_id_token': idToken,
              'full_name': fullName,
              'phone': phone,
              'role': role,
            }),
          )
          .timeout(AppConstants.connectTimeout);

      _log(
          'Backend /auth/register responded status=${response.statusCode} body=${response.body}');

      // If backend says already registered, fall through to login
      if (response.statusCode != 201 && response.statusCode != 200) {
        final detail = _extractDetailFromResponseBody(
          response.body,
          'Registration failed',
        );

        if (detail.toLowerCase().contains('already registered') ||
            detail.toLowerCase().contains('already exists')) {
          // User exists in both Firebase and backend — just log them in
          _log(
              'Backend says already registered, falling through to signInWithEmail for email=$email');
          return await signInWithEmail(email: email, password: password);
        }

        throw AuthMessageException(detail);
      }

      // Don't save login data — user must sign in explicitly after signup
      _log('signUpWithEmail completed successfully for email=$email');
      return jsonDecode(response.body);
    } on AuthMessageException {
      rethrow;
    } catch (e) {
      throw _friendlyNetworkException(e);
    }
  }

  // ─────────────────────────────────────────────────────────
  //  Email / Password — Sign In
  // ─────────────────────────────────────────────────────────
  Future<Map<String, dynamic>> signInWithEmail({
    required String email,
    required String password,
  }) async {
    _log('signInWithEmail started for email=$email');
    // 1. Sign in with Firebase
    final credential = await _auth.signInWithEmailAndPassword(
      email: email,
      password: password,
    );
    _log(
        'Firebase signInWithEmailAndPassword succeeded for email=$email uid=${credential.user?.uid}');

    try {
      // 2. Get Firebase ID token
      final idToken = await credential.user!.getIdToken();
      _log('Firebase ID token acquired for login flow');

      // 3. Login to backend
      final response = await http
          .post(
            Uri.parse('${AppConstants.baseUrl}/auth/login'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'firebase_id_token': idToken,
            }),
          )
          .timeout(AppConstants.connectTimeout);

      _log(
          'Backend /auth/login responded status=${response.statusCode} body=${response.body}');

      if (response.statusCode != 200) {
        final detail = _extractDetailFromResponseBody(
          response.body,
          'Login failed',
        );
        throw AuthMessageException(detail);
      }

      final loginData = jsonDecode(response.body)['data'];

      // 4. Save backend tokens and role locally
      await AuthService().saveLoginData(
        accessToken: loginData['access_token'],
        refreshToken: loginData['refresh_token'],
        userId: loginData['user']['id'],
        userEmail: loginData['user']['email'],
        userRole: loginData['user']['role'],
      );

      _log(
          'signInWithEmail completed successfully for email=$email role=${loginData['user']['role']}');

      return jsonDecode(response.body);
    } on AuthMessageException {
      rethrow;
    } catch (e) {
      throw _friendlyNetworkException(e);
    }
  }

  // ─────────────────────────────────────────────────────────
  //  Forgot Password (Firebase handles reset email)
  // ─────────────────────────────────────────────────────────
  Future<void> sendPasswordResetEmail(String email) async {
    await _auth.sendPasswordResetEmail(email: email);
  }

  // ─────────────────────────────────────────────────────────
  //  Sign Out
  // ─────────────────────────────────────────────────────────
  Future<void> signOut() async {
    // Revoke backend refresh token
    final refreshToken = await AuthService().getRefreshToken();
    if (refreshToken != null) {
      try {
        await http.post(
          Uri.parse('${AppConstants.baseUrl}/auth/logout'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'refresh_token': refreshToken}),
        );
      } catch (_) {
        // Best-effort — don't block logout if backend call fails
      }
    }

    // Sign out from Firebase
    await _auth.signOut();

    // Clear local tokens
    await AuthService().logout();
  }

  // ─────────────────────────────────────────────────────────
  //  Helpers
  // ─────────────────────────────────────────────────────────
  User? get currentUser => _auth.currentUser;
  Stream<User?> get authStateChanges => _auth.authStateChanges();
}
