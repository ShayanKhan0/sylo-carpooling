import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/constants/app_constants.dart';
import '../../core/services/firebase_auth_service.dart';
import 'auth_design_tokens.dart';
import 'auth_shader_layer.dart';

class SignUpScreen extends StatefulWidget {
  const SignUpScreen({super.key});

  @override
  State<SignUpScreen> createState() => _SignUpScreenState();
}

class _SignUpScreenState extends State<SignUpScreen>
    with TickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  final _fullNameController = TextEditingController();
  final _emailController = TextEditingController();
  final _phoneController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();

  bool _isPasswordVisible = false;
  bool _isConfirmPasswordVisible = false;
  bool _isLoading = false;
  String _selectedRole = 'passenger';

  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;

  late AnimationController _syloController;
  late Animation<double> _syloGlow;

  @override
  void initState() {
    super.initState();
    _initAnimations();
  }

  void _initAnimations() {
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 840),
    );

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _animationController, curve: Curves.easeIn),
    );

    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.16),
      end: Offset.zero,
    ).animate(
      CurvedAnimation(parent: _animationController, curve: Curves.easeOutCubic),
    );

    _animationController.forward();

    _syloController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2300),
    );
    _syloGlow = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _syloController, curve: Curves.easeInOut),
    );
    _syloController.repeat(reverse: true);
  }

  @override
  void dispose() {
    _fullNameController.dispose();
    _emailController.dispose();
    _phoneController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _animationController.dispose();
    _syloController.dispose();
    super.dispose();
  }

  void _handleSignUp() async {
    if (_formKey.currentState!.validate()) {
      setState(() => _isLoading = true);

      try {
        await FirebaseAuthService().signUpWithEmail(
          email: _emailController.text.trim(),
          password: _passwordController.text,
          fullName: _fullNameController.text.trim(),
          phone: _phoneController.text.trim(),
          role: _selectedRole,
        );

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content:
                  const Text('Account created successfully! Please sign in.'),
              backgroundColor: Colors.green.shade700,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          );
          Navigator.of(context).pushReplacementNamed('/signin');
        }
      } catch (e, st) {
        debugPrint('[SignUpScreen] _handleSignUp error: $e');
        debugPrint('[SignUpScreen] stack: $st');
        if (mounted) {
          String message = e is Exception
              ? e.toString().replaceFirst('Exception: ', '')
              : e.toString();
          if (message.contains('email-already-in-use')) {
            message = 'This email is already registered. Please sign in.';
          } else if (message.contains('weak-password')) {
            message = 'Password is too weak. Use at least 6 characters.';
          } else if (message.contains('invalid-email')) {
            message = 'Invalid email address.';
          } else if (message.toLowerCase().contains('failed to fetch') ||
              message.toLowerCase().contains('clientexception') ||
              message.toLowerCase().contains('socketexception') ||
              message.toLowerCase().contains('timeout')) {
            message =
                'Cannot reach the backend at ${AppConstants.baseUrl}. ${AppConstants.apiConnectionHelp}';
          }

          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(message),
              backgroundColor: Colors.red.shade700,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          );
        }
      } finally {
        if (mounted) setState(() => _isLoading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.light,
      ),
    );

    return Scaffold(
      backgroundColor: AuthDesignTokens.midnight,
      body: LayoutBuilder(
        builder: (context, constraints) {
          final isPhone = constraints.maxWidth < 420;
          final isWide = constraints.maxWidth >= 980;
          final horizontalPadding = constraints.maxWidth < 480 ? 14.0 : 26.0;
          final verticalPadding = constraints.maxHeight < 760 ? 12.0 : 22.0;
          final contentMaxWidth = isWide ? 1140.0 : 540.0;

          return Stack(
            children: [
              const Positioned.fill(child: _AuthBackdrop()),
              const Positioned.fill(
                child: IgnorePointer(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: AuthDesignTokens.pageVeilGradient,
                    ),
                  ),
                ),
              ),
              SafeArea(
                child: SingleChildScrollView(
                  padding: EdgeInsets.fromLTRB(
                    horizontalPadding,
                    verticalPadding,
                    horizontalPadding,
                    verticalPadding + 12,
                  ),
                  child: ConstrainedBox(
                    constraints: BoxConstraints(
                      minHeight: constraints.maxHeight - (verticalPadding * 2),
                    ),
                    child: Center(
                      child: FadeTransition(
                        opacity: _fadeAnimation,
                        child: SlideTransition(
                          position: _slideAnimation,
                          child: ConstrainedBox(
                            constraints:
                                BoxConstraints(maxWidth: contentMaxWidth),
                            child: isWide
                                ? Row(
                                    children: [
                                      Expanded(
                                        child: _buildHeroRail(isPhone: isPhone),
                                      ),
                                      const SizedBox(width: 26),
                                      SizedBox(
                                        width: 470,
                                        child: _buildAuthCard(isPhone: isPhone),
                                      ),
                                    ],
                                  )
                                : Center(
                                    child: ConstrainedBox(
                                      constraints: const BoxConstraints(
                                        maxWidth: 500,
                                      ),
                                      child: _buildAuthCard(isPhone: isPhone),
                                    ),
                                  ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildHeroRail({required bool isPhone}) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(30),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
        child: Container(
          padding: const EdgeInsets.fromLTRB(24, 28, 24, 28),
          decoration: BoxDecoration(
            color: AuthDesignTokens.white.withValues(alpha: 0.06),
            border: Border.all(
              color: AuthDesignTokens.lineFog.withValues(alpha: 0.3),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                'Join the city route.',
                style: GoogleFonts.playfairDisplay(
                  fontSize: 48,
                  height: 1.05,
                  fontWeight: FontWeight.w800,
                  color: AuthDesignTokens.white,
                  letterSpacing: 0.45,
                ),
              ),
              const SizedBox(height: 14),
              Text(
                'Create your profile to ride, drive, and coordinate shared travel in seconds.',
                style: GoogleFonts.inter(
                  fontSize: 16,
                  height: 1.45,
                  fontWeight: FontWeight.w500,
                  color: AuthDesignTokens.white.withValues(alpha: 0.9),
                ),
              ),
              const SizedBox(height: 22),
              const Wrap(
                spacing: 10,
                runSpacing: 10,
                children: [
                  _RouteTag(
                      icon: Icons.badge_outlined, label: 'Fast Onboarding'),
                  _RouteTag(icon: Icons.hail_outlined, label: 'Ride or Drive'),
                  _RouteTag(
                    icon: Icons.verified_user_outlined,
                    label: 'Trusted Network',
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildAuthCard({required bool isPhone}) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(28),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 14, sigmaY: 14),
        child: Container(
          padding: EdgeInsets.fromLTRB(
            isPhone ? 16 : 24,
            isPhone ? 18 : 24,
            isPhone ? 16 : 24,
            isPhone ? 18 : 24,
          ),
          decoration: AuthDesignTokens.authCardDecoration(),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Align(
                child: Container(
                  height: 4,
                  width: 92,
                  decoration: BoxDecoration(
                    gradient: AuthDesignTokens.ctaGradient,
                    borderRadius: BorderRadius.circular(99),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              Align(
                alignment: Alignment.centerLeft,
                child: IconButton(
                  onPressed: () => Navigator.of(context).pop(),
                  icon: const Icon(Icons.arrow_back_ios_new),
                  color: AuthDesignTokens.brandAction,
                  style: IconButton.styleFrom(
                    backgroundColor:
                        AuthDesignTokens.white.withValues(alpha: 0.96),
                    side: BorderSide(
                      color:
                          AuthDesignTokens.brandAction.withValues(alpha: 0.24),
                    ),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 6),
              _buildHeader(isPhone: isPhone),
              SizedBox(height: isPhone ? 16 : 20),
              _buildSignUpForm(),
              SizedBox(height: isPhone ? 16 : 18),
              _buildRoleSelector(),
              SizedBox(height: isPhone ? 18 : 22),
              _buildSignUpButton(isPhone: isPhone),
              SizedBox(height: isPhone ? 18 : 22),
              _buildSignInLink(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader({required bool isPhone}) {
    return Column(
      children: [
        AnimatedBuilder(
          animation: _syloController,
          builder: (context, child) {
            return Transform.scale(
              scale: 1 + (0.012 * _syloGlow.value),
              child: Text(
                'SYLO',
                style: GoogleFonts.playfairDisplay(
                  fontSize: isPhone ? 36 : 44,
                  fontWeight: FontWeight.w900,
                  color: AuthDesignTokens.brandDeep,
                  letterSpacing: isPhone ? 3.6 : 4.4,
                  shadows: [
                    Shadow(
                      color: AuthDesignTokens.routeBlue
                          .withValues(alpha: 0.22 + (0.22 * _syloGlow.value)),
                      blurRadius: 18 + (12 * _syloGlow.value),
                    ),
                  ],
                ),
              ),
            );
          },
        ),
        const SizedBox(height: 8),
        Text(
          'Create Account',
          textAlign: TextAlign.center,
          style: GoogleFonts.inter(
            fontSize: isPhone ? 24 : 28,
            fontWeight: FontWeight.w700,
            color: AuthDesignTokens.textPrimary,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          'Start your shared mobility journey',
          textAlign: TextAlign.center,
          style: GoogleFonts.inter(
            fontSize: 14,
            fontWeight: FontWeight.w500,
            color: AuthDesignTokens.textMuted,
          ),
        ),
      ],
    );
  }

  InputDecoration _inputDecoration({
    required String label,
    required String hint,
    required IconData icon,
    Widget? suffixIcon,
  }) {
    final border = OutlineInputBorder(
      borderRadius: BorderRadius.circular(15),
      borderSide: const BorderSide(color: AuthDesignTokens.cardBorder),
    );

    return InputDecoration(
      labelText: label,
      hintText: hint,
      prefixIcon: Icon(icon, color: AuthDesignTokens.brandAction, size: 20),
      suffixIcon: suffixIcon,
      labelStyle: GoogleFonts.inter(
        color: AuthDesignTokens.textMuted,
        fontWeight: FontWeight.w500,
        fontSize: 14,
      ),
      floatingLabelStyle: GoogleFonts.inter(
        color: AuthDesignTokens.brandDeep,
        fontWeight: FontWeight.w600,
        fontSize: 14,
      ),
      hintStyle: GoogleFonts.inter(
        color: AuthDesignTokens.textMuted.withValues(alpha: 0.82),
        fontSize: 14,
      ),
      filled: true,
      fillColor: AuthDesignTokens.white.withValues(alpha: 0.985),
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: border,
      enabledBorder: border,
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(15),
        borderSide: const BorderSide(
          color: AuthDesignTokens.brandAction,
          width: 2,
        ),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(15),
        borderSide: const BorderSide(color: Colors.redAccent),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(15),
        borderSide: const BorderSide(color: Colors.redAccent, width: 2),
      ),
      errorStyle: GoogleFonts.inter(
        color: Colors.red.shade300,
        fontSize: 12,
        fontWeight: FontWeight.w500,
      ),
    );
  }

  Widget _buildSignUpForm() {
    return Form(
      key: _formKey,
      child: Column(
        children: [
          TextFormField(
            controller: _fullNameController,
            textCapitalization: TextCapitalization.words,
            cursorColor: AuthDesignTokens.brandAction,
            style: GoogleFonts.inter(
              color: AuthDesignTokens.textPrimary,
              fontWeight: FontWeight.w500,
              fontSize: 15,
            ),
            decoration: _inputDecoration(
              label: 'Full Name',
              hint: 'Enter your full name',
              icon: Icons.person_outline_rounded,
            ),
            validator: (value) {
              if (value == null || value.trim().isEmpty) {
                return 'Please enter your name';
              }
              if (value.trim().length < 2) {
                return 'Name must be at least 2 characters';
              }
              return null;
            },
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _emailController,
            keyboardType: TextInputType.emailAddress,
            cursorColor: AuthDesignTokens.brandAction,
            style: GoogleFonts.inter(
              color: AuthDesignTokens.textPrimary,
              fontWeight: FontWeight.w500,
              fontSize: 15,
            ),
            decoration: _inputDecoration(
              label: 'Email',
              hint: 'Enter your email',
              icon: Icons.mail_outline_rounded,
            ),
            validator: (value) {
              if (value == null || value.isEmpty) {
                return 'Please enter your email';
              }
              if (!value.contains('@') || !value.contains('.')) {
                return 'Please enter a valid email';
              }
              return null;
            },
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _phoneController,
            keyboardType: TextInputType.phone,
            cursorColor: AuthDesignTokens.brandAction,
            style: GoogleFonts.inter(
              color: AuthDesignTokens.textPrimary,
              fontWeight: FontWeight.w500,
              fontSize: 15,
            ),
            decoration: _inputDecoration(
              label: 'Phone Number',
              hint: '+923001234567',
              icon: Icons.phone_outlined,
            ),
            validator: (value) {
              if (value == null || value.isEmpty) {
                return 'Please enter your phone number';
              }
              final cleaned = value.replaceAll(RegExp(r'\s'), '');
              if (!RegExp(r'^\+\d{10,19}$').hasMatch(cleaned)) {
                return 'Use format: +923001234567';
              }
              return null;
            },
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _passwordController,
            obscureText: !_isPasswordVisible,
            cursorColor: AuthDesignTokens.brandAction,
            style: GoogleFonts.inter(
              color: AuthDesignTokens.textPrimary,
              fontWeight: FontWeight.w500,
              fontSize: 15,
            ),
            decoration: _inputDecoration(
              label: 'Password',
              hint: 'Create a password',
              icon: Icons.lock_outline_rounded,
              suffixIcon: IconButton(
                icon: Icon(
                  _isPasswordVisible ? Icons.visibility_off : Icons.visibility,
                  color: AuthDesignTokens.textMuted,
                ),
                onPressed: () {
                  setState(() => _isPasswordVisible = !_isPasswordVisible);
                },
              ),
            ),
            validator: (value) {
              if (value == null || value.isEmpty) {
                return 'Please enter a password';
              }
              if (value.length < 6) {
                return 'Password must be at least 6 characters';
              }
              return null;
            },
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _confirmPasswordController,
            obscureText: !_isConfirmPasswordVisible,
            cursorColor: AuthDesignTokens.brandAction,
            style: GoogleFonts.inter(
              color: AuthDesignTokens.textPrimary,
              fontWeight: FontWeight.w500,
              fontSize: 15,
            ),
            decoration: _inputDecoration(
              label: 'Confirm Password',
              hint: 'Re-enter your password',
              icon: Icons.lock_outline_rounded,
              suffixIcon: IconButton(
                icon: Icon(
                  _isConfirmPasswordVisible
                      ? Icons.visibility_off
                      : Icons.visibility,
                  color: AuthDesignTokens.textMuted,
                ),
                onPressed: () {
                  setState(() =>
                      _isConfirmPasswordVisible = !_isConfirmPasswordVisible);
                },
              ),
            ),
            validator: (value) {
              if (value == null || value.isEmpty) {
                return 'Please confirm your password';
              }
              if (value != _passwordController.text) {
                return 'Passwords do not match';
              }
              return null;
            },
          ),
        ],
      ),
    );
  }

  Widget _buildRoleSelector() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'I want to:',
          style: GoogleFonts.inter(
            color: AuthDesignTokens.textMuted,
            fontWeight: FontWeight.w600,
            fontSize: 14,
          ),
        ),
        const SizedBox(height: 10),
        LayoutBuilder(
          builder: (context, constraints) {
            final singleColumn = constraints.maxWidth < 300;
            if (singleColumn) {
              return Column(
                children: [
                  _buildRoleChip(
                    label: 'Ride',
                    icon: Icons.directions_car_outlined,
                    value: 'passenger',
                  ),
                  const SizedBox(height: 10),
                  _buildRoleChip(
                    label: 'Drive',
                    icon: Icons.drive_eta_outlined,
                    value: 'driver',
                  ),
                ],
              );
            }

            return Row(
              children: [
                Expanded(
                  child: _buildRoleChip(
                    label: 'Ride',
                    icon: Icons.directions_car_outlined,
                    value: 'passenger',
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _buildRoleChip(
                    label: 'Drive',
                    icon: Icons.drive_eta_outlined,
                    value: 'driver',
                  ),
                ),
              ],
            );
          },
        ),
      ],
    );
  }

  Widget _buildRoleChip({
    required String label,
    required IconData icon,
    required String value,
  }) {
    final isSelected = _selectedRole == value;
    return GestureDetector(
      onTap: () => setState(() => _selectedRole = value),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOutCubic,
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(
          color: isSelected
              ? AuthDesignTokens.brandAction.withValues(alpha: 0.14)
              : AuthDesignTokens.white,
          border: Border.all(
            color: isSelected
                ? AuthDesignTokens.brandAction
                : AuthDesignTokens.cardBorder,
            width: isSelected ? 2 : 1,
          ),
          borderRadius: BorderRadius.circular(14),
          boxShadow: [
            BoxShadow(
              color: isSelected
                  ? AuthDesignTokens.routeBlue.withValues(alpha: 0.18)
                  : AuthDesignTokens.midnight.withValues(alpha: 0.06),
              blurRadius: 14,
              offset: const Offset(0, 5),
            ),
          ],
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              icon,
              color: isSelected
                  ? AuthDesignTokens.brandAction
                  : AuthDesignTokens.textMuted,
              size: 20,
            ),
            const SizedBox(width: 8),
            Text(
              label,
              style: GoogleFonts.inter(
                fontSize: 14,
                fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                color: isSelected
                    ? AuthDesignTokens.brandAction
                    : AuthDesignTokens.textPrimary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSignUpButton({required bool isPhone}) {
    return AnimatedScale(
      scale: _isLoading ? 0.99 : 1,
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOutCubic,
      child: SizedBox(
        height: isPhone ? 52 : 58,
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                AuthDesignTokens.brandDeep,
                AuthDesignTokens.midnight,
              ],
              stops: [0.0, 1.0],
            ),
            borderRadius: BorderRadius.circular(15),
            border: Border.all(
              color: AuthDesignTokens.routeBlue.withValues(alpha: 0.96),
              width: 1.4,
            ),
            boxShadow: [
              BoxShadow(
                color: AuthDesignTokens.routeBlue.withValues(alpha: 0.24),
                blurRadius: 18,
                spreadRadius: -1,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: ElevatedButton(
            onPressed: _isLoading ? null : _handleSignUp,
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.transparent,
              disabledBackgroundColor: Colors.transparent,
              foregroundColor: AuthDesignTokens.white,
              shadowColor: Colors.transparent,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(15),
              ),
            ),
            child: _isLoading
                ? const SizedBox(
                    height: 22,
                    width: 22,
                    child: CircularProgressIndicator(
                      strokeWidth: 2.4,
                      valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                    ),
                  )
                : Text(
                    'Create Account',
                    style: GoogleFonts.inter(
                      fontSize: isPhone ? 15 : 16,
                      fontWeight: FontWeight.w700,
                      color: AuthDesignTokens.white,
                      letterSpacing: 0.22,
                    ),
                  ),
          ),
        ),
      ),
    );
  }

  Widget _buildSignInLink() {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text(
          'Already have an account? ',
          style: GoogleFonts.inter(
            color: AuthDesignTokens.textMuted,
            fontWeight: FontWeight.w500,
            fontSize: 14,
          ),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          style: TextButton.styleFrom(
            padding: EdgeInsets.zero,
            minimumSize: Size.zero,
            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          ),
          child: Text(
            'Sign In',
            style: GoogleFonts.inter(
              color: AuthDesignTokens.brandAction,
              fontWeight: FontWeight.w700,
              fontSize: 14,
              decoration: TextDecoration.underline,
              decorationColor: AuthDesignTokens.brandAction,
            ),
          ),
        ),
      ],
    );
  }
}

class _RouteTag extends StatelessWidget {
  final IconData icon;
  final String label;

  const _RouteTag({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: AuthDesignTokens.white.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: AuthDesignTokens.lineFog.withValues(alpha: 0.65),
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: AuthDesignTokens.sky400),
          const SizedBox(width: 7),
          Text(
            label,
            style: GoogleFonts.inter(
              color: AuthDesignTokens.white.withValues(alpha: 0.98),
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _AuthBackdrop extends StatefulWidget {
  const _AuthBackdrop();

  @override
  State<_AuthBackdrop> createState() => _AuthBackdropState();
}

class _AuthBackdropState extends State<_AuthBackdrop>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Future<FragmentProgram?> _shaderProgramFuture;

  @override
  void initState() {
    super.initState();
    _shaderProgramFuture = AuthShaderLoader.sharedProgram();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 9),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final wave = Curves.easeInOutSine.transform(_controller.value);
        final shaderProgress = _controller.value;
        final drift = ((wave * 2) - 1) * 16;
        final lineBoost = (0.86 + (0.22 * wave)).clamp(0.0, 1.0).toDouble();
        final orbAlpha = 0.12 + (0.08 * wave);

        return Container(
          decoration: const BoxDecoration(
            gradient: AuthDesignTokens.pageGradient,
          ),
          child: Stack(
            children: [
              Positioned.fill(
                child: FutureBuilder<FragmentProgram?>(
                  future: _shaderProgramFuture,
                  builder: (context, snapshot) {
                    final program = snapshot.data;
                    if (program == null) {
                      return AuthShaderFallbackLayer(
                        progress: shaderProgress,
                        intensity: 0.16,
                      );
                    }

                    return Stack(
                      children: [
                        AuthShaderLayer(
                          program: program,
                          progress: shaderProgress,
                          intensity: 0.2,
                        ),
                        AuthShaderFallbackLayer(
                          progress: shaderProgress,
                          intensity: 0.1,
                        ),
                      ],
                    );
                  },
                ),
              ),
              Positioned(
                top: -170 + drift,
                left: -120 + (drift * 0.35),
                child: _softOrb(
                  size: 330,
                  color: AuthDesignTokens.routeBlue.withValues(alpha: orbAlpha),
                ),
              ),
              Positioned(
                bottom: -170 - drift,
                right: -90 + (drift * 0.25),
                child: _softOrb(
                  size: 320,
                  color: AuthDesignTokens.brandAction
                      .withValues(alpha: (orbAlpha - 0.02).clamp(0.0, 1.0)),
                ),
              ),
              ..._routeLines(drift: drift, glow: lineBoost),
              ..._microLines(drift: drift, glow: lineBoost),
            ],
          ),
        );
      },
    );
  }

  static Widget _softOrb({required double size, required Color color}) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: RadialGradient(
          colors: [
            color,
            color.withValues(alpha: 0),
          ],
        ),
      ),
    );
  }

  List<Widget> _routeLines({required double drift, required double glow}) {
    return [
      _line(
        top: 112 + (drift * 0.25),
        left: -74,
        width: 320,
        angle: -0.16,
        alpha: 0.27 * glow,
      ),
      _line(
        top: 206 + (drift * 0.2),
        right: -60,
        width: 290,
        angle: 0.23,
        alpha: 0.22 * glow,
      ),
      _line(
        bottom: 222 - (drift * 0.15),
        left: -54,
        width: 290,
        angle: 0.12,
        alpha: 0.2 * glow,
      ),
      _line(
        bottom: 130 - (drift * 0.18),
        right: -60,
        width: 275,
        angle: -0.12,
        alpha: 0.2 * glow,
      ),
      _line(
        top: 372 + (drift * 0.3),
        left: -80,
        width: 340,
        angle: 0.05,
        alpha: 0.18 * glow,
      ),
    ];
  }

  List<Widget> _microLines({required double drift, required double glow}) {
    return [
      _line(
        top: 300 + (drift * 0.45),
        right: -40,
        width: 210,
        angle: -0.26,
        alpha: 0.14 * glow,
      ),
      _line(
        bottom: 330 - (drift * 0.42),
        left: -30,
        width: 180,
        angle: 0.26,
        alpha: 0.14 * glow,
      ),
      _line(
        bottom: 410 - (drift * 0.35),
        right: -20,
        width: 160,
        angle: -0.18,
        alpha: 0.13 * glow,
      ),
    ];
  }

  Widget _line({
    double? top,
    double? left,
    double? right,
    double? bottom,
    required double width,
    required double angle,
    required double alpha,
  }) {
    return Positioned(
      top: top,
      left: left,
      right: right,
      bottom: bottom,
      child: Transform.rotate(
        angle: angle,
        child: Container(
          width: width,
          height: 2,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(999),
            gradient: LinearGradient(
              colors: [
                AuthDesignTokens.sky400.withValues(alpha: 0),
                AuthDesignTokens.lineFog.withValues(alpha: alpha),
                AuthDesignTokens.routeBlue.withValues(alpha: alpha + 0.02),
                AuthDesignTokens.sky400.withValues(alpha: 0),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
