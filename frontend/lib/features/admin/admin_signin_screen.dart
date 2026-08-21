import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/services/admin_auth_service.dart';
import '../auth/auth_design_tokens.dart';

class AdminSignInScreen extends StatefulWidget {
  const AdminSignInScreen({super.key});

  @override
  State<AdminSignInScreen> createState() => _AdminSignInScreenState();
}

class _AdminSignInScreenState extends State<AdminSignInScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  final _auth = AdminAuthService();
  bool _busy = false;
  bool _obscure = true;
  String? _credentialError;

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }

  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _credentialError = null;
    });
    try {
      await _auth.login(
        email: _emailCtrl.text.trim(),
        password: _passwordCtrl.text,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacementNamed('/admin-dashboard');
    } on DioException catch (e) {
      if (!mounted) return;
      final message = extractAdminError(e);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: Colors.red.shade700,
          behavior: SnackBarBehavior.floating,
        ),
      );
      setState(() => _credentialError = message);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Unable to sign in right now. Please try again.'),
          backgroundColor: Colors.red.shade700,
          behavior: SnackBarBehavior.floating,
        ),
      );
      setState(() => _credentialError = 'Unable to sign in right now.');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final border = OutlineInputBorder(
      borderRadius: BorderRadius.circular(15),
      borderSide: const BorderSide(color: AuthDesignTokens.cardBorder),
    );

    return Scaffold(
      backgroundColor: AuthDesignTokens.midnight,
      body: Container(
        decoration: const BoxDecoration(gradient: AuthDesignTokens.pageGradient),
        child: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 430),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Container(
                  padding: const EdgeInsets.fromLTRB(18, 22, 18, 18),
                  decoration: BoxDecoration(
                    color: AuthDesignTokens.white.withValues(alpha: 0.95),
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(
                      color: AuthDesignTokens.cardBorder.withValues(alpha: 0.75),
                    ),
                  ),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Align(
                          alignment: Alignment.centerLeft,
                          child: IconButton(
                            onPressed: () => Navigator.of(context).pushReplacementNamed('/signin'),
                            tooltip: 'Back',
                            icon: const Icon(Icons.arrow_back_rounded, size: 20),
                          ),
                        ),
                        Text(
                          'SYLO',
                          textAlign: TextAlign.center,
                          style: GoogleFonts.playfairDisplay(
                            fontSize: 38,
                            fontWeight: FontWeight.w900,
                            color: AuthDesignTokens.brandDeep,
                            letterSpacing: 4.4,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Admin Portal',
                          textAlign: TextAlign.center,
                          style: GoogleFonts.inter(
                            fontSize: 22,
                            fontWeight: FontWeight.w700,
                            color: AuthDesignTokens.textPrimary,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'Sign in with your admin account',
                          textAlign: TextAlign.center,
                          style: GoogleFonts.inter(
                            fontSize: 13,
                            fontWeight: FontWeight.w500,
                            color: AuthDesignTokens.textMuted,
                          ),
                        ),
                        const SizedBox(height: 16),
                        if (_credentialError != null)
                          Container(
                            margin: const EdgeInsets.only(bottom: 12),
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: Colors.red.withValues(alpha: 0.08),
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                color: Colors.red.withValues(alpha: 0.35),
                              ),
                            ),
                            child: Text(
                              _credentialError!,
                              style: GoogleFonts.inter(
                                color: Colors.red.shade700,
                                fontWeight: FontWeight.w600,
                                fontSize: 12.5,
                              ),
                            ),
                          ),
                        TextFormField(
                          controller: _emailCtrl,
                          keyboardType: TextInputType.emailAddress,
                          onChanged: (_) {
                            if (_credentialError != null) {
                              setState(() => _credentialError = null);
                            }
                          },
                          decoration: InputDecoration(
                            labelText: 'Admin Email',
                            prefixIcon: const Icon(Icons.mail_outline_rounded),
                            errorText: _credentialError != null ? ' ' : null,
                            border: border,
                            enabledBorder: border,
                            focusedBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(15),
                              borderSide: const BorderSide(
                                color: AuthDesignTokens.brandAction,
                                width: 2,
                              ),
                            ),
                          ),
                          validator: (v) => (v == null || !v.contains('@'))
                              ? 'Enter a valid email'
                              : null,
                        ),
                        const SizedBox(height: 12),
                        TextFormField(
                          controller: _passwordCtrl,
                          obscureText: _obscure,
                          onChanged: (_) {
                            if (_credentialError != null) {
                              setState(() => _credentialError = null);
                            }
                          },
                          decoration: InputDecoration(
                            labelText: 'Password',
                            prefixIcon: const Icon(Icons.lock_outline_rounded),
                            suffixIcon: IconButton(
                              icon: Icon(
                                _obscure ? Icons.visibility : Icons.visibility_off,
                              ),
                              onPressed: () => setState(() => _obscure = !_obscure),
                            ),
                            errorText: _credentialError != null ? ' ' : null,
                            border: border,
                            enabledBorder: border,
                            focusedBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(15),
                              borderSide: const BorderSide(
                                color: AuthDesignTokens.brandAction,
                                width: 2,
                              ),
                            ),
                          ),
                          validator: (v) => (v == null || v.length < 8)
                              ? 'Password must be at least 8 characters'
                              : null,
                        ),
                        const SizedBox(height: 14),
                        SizedBox(
                          width: double.infinity,
                          height: 52,
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              gradient: const LinearGradient(
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                                colors: [
                                  AuthDesignTokens.brandDeep,
                                  AuthDesignTokens.midnight,
                                ],
                              ),
                              borderRadius: BorderRadius.circular(15),
                              border: Border.all(
                                color:
                                    AuthDesignTokens.routeBlue.withValues(alpha: 0.96),
                                width: 1.4,
                              ),
                            ),
                            child: ElevatedButton(
                              onPressed: _busy ? null : _login,
                              style: ElevatedButton.styleFrom(
                                backgroundColor: Colors.transparent,
                                shadowColor: Colors.transparent,
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(15),
                                ),
                              ),
                              child: _busy
                                  ? const SizedBox(
                                      height: 20,
                                      width: 20,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                        valueColor: AlwaysStoppedAnimation<Color>(
                                          Colors.white,
                                        ),
                                      ),
                                    )
                                  : Text(
                                      'Sign In as Admin',
                                      style: GoogleFonts.inter(
                                        color: Colors.white,
                                        fontWeight: FontWeight.w700,
                                        fontSize: 15,
                                      ),
                                    ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
