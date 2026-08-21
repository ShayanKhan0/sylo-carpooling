import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:video_player/video_player.dart';

class SplashScreen extends StatefulWidget {
  final bool isLoggedIn;
  final String userRole;

  const SplashScreen({
    super.key,
    required this.isLoggedIn,
    this.userRole = 'passenger',
  });

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  static const String _videoAssetPath = 'assets/videos/splash_intro.mp4';

  VideoPlayerController? _videoController;
  Timer? _navigationTimer;
  bool _videoInitFailed = false;

  @override
  void initState() {
    super.initState();
    _initializeVideoSplash();
  }

  Future<void> _initializeVideoSplash() async {
    final controller = VideoPlayerController.asset(_videoAssetPath);
    _videoController = controller;

    try {
      await controller.initialize();
      await controller.setLooping(true);
      await controller.setVolume(0);
      await controller.play();
    } catch (_) {
      _videoInitFailed = true;
    }

    if (mounted) {
      setState(() {});
    }

    _navigationTimer = Timer(const Duration(seconds: 5), _navigateNext);
  }

  void _navigateNext() {
    if (!mounted) return;

    if (widget.isLoggedIn) {
      final route = widget.userRole == 'driver'
          ? '/driver-dashboard'
          : '/passenger-dashboard';
      Navigator.of(context).pushReplacementNamed(route);
      return;
    }

    Navigator.of(context).pushReplacementNamed('/signin');
  }

  @override
  void dispose() {
    _navigationTimer?.cancel();
    _videoController?.dispose();
    super.dispose();
  }

  Widget _buildVideoBody() {
    final controller = _videoController;
    if (controller != null && controller.value.isInitialized) {
      final size = controller.value.size;
      return FittedBox(
        fit: BoxFit.cover,
        child: SizedBox(
          width: size.width,
          height: size.height,
          child: VideoPlayer(controller),
        ),
      );
    }

    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const CircularProgressIndicator(color: Colors.white),
          if (_videoInitFailed) ...[
            const SizedBox(height: 16),
            const Text(
              'Loading splash video...',
              style: TextStyle(color: Colors.white70),
            ),
          ],
        ],
      ),
    );
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
      backgroundColor: Colors.black,
      body: SafeArea(
        top: false,
        bottom: false,
        child: SizedBox.expand(child: _buildVideoBody()),
      ),
    );
  }
}
