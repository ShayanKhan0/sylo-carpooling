import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart'
    show kIsWeb, defaultTargetPlatform, TargetPlatform, debugPrint;
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:provider/provider.dart';

import 'firebase_options.dart';
import 'core/theme/app_theme.dart';
import 'core/theme/app_colors.dart';
import 'core/theme/theme_provider.dart';
import 'core/services/auth_service.dart';
import 'core/services/api_client.dart';
import 'core/services/chat_sync_service.dart';
import 'core/services/notification_service.dart';
import 'core/services/notification_sync_service.dart';
import 'core/services/rating_service.dart';
import 'features/splash/splash_screen.dart';
import 'features/auth/signin_screen.dart';
import 'features/auth/signup_screen.dart';
import 'features/dashboard/passenger_dashboard_screen.dart';
import 'features/dashboard/driver_dashboard_screen.dart';
import 'features/notifications/notification_list_screen.dart';
import 'features/wallet/wallet_screen.dart';
import 'features/profile/profile_edit_screen.dart';
import 'features/verification/verification_screen.dart';
import 'features/rides/ride_detail_screen.dart';
import 'features/rides/ride_history_screen.dart';
import 'features/safety/sos_screen.dart';
import 'features/settings/help_faq_screen.dart';
import 'features/settings/terms_of_service_screen.dart';
import 'features/settings/privacy_policy_screen.dart';
import 'features/schedule/recurring_schedule_screen.dart';
import 'features/tracking/live_tracking_screen.dart';
import 'features/chat/chat_screen.dart';
import 'features/chat/chat_history_screen.dart';
import 'features/ratings/ratings_reviews_screen.dart';
import 'features/admin/admin_signin_screen.dart';
import 'features/admin/admin_dashboard_screen.dart';
import 'features/admin/admin_incident_detail_screen.dart';

final GlobalKey<NavigatorState> appNavigatorKey = GlobalKey<NavigatorState>();

@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  if (kIsWeb) {
    await Firebase.initializeApp(
        options: DefaultFirebaseOptions.currentPlatform);
  } else {
    await Firebase.initializeApp();
  }
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  if (kIsWeb) {
    await Firebase.initializeApp(
      options: DefaultFirebaseOptions.currentPlatform,
    );
  } else {
    await Firebase.initializeApp();
  }

  FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);
  await AuthService().init();

  runApp(
    ChangeNotifierProvider(
      create: (_) => ThemeProvider(),
      child: const SyloApp(),
    ),
  );
}

class SyloApp extends StatefulWidget {
  const SyloApp({super.key});

  @override
  State<SyloApp> createState() => _SyloAppState();
}

class _SyloAppState extends State<SyloApp> {
  StreamSubscription<RemoteMessage>? _foregroundSub;
  StreamSubscription<RemoteMessage>? _openedSub;
  final NotificationService _notificationService = NotificationService();
  final RatingService _ratingService = RatingService();
  Timer? _ratingPromptPollTimer;
  bool _ratingPromptPollBusy = false;
  final Set<String> _handledRatingPromptKeys = <String>{};

  bool _isDuplicateRatingError(Object error) {
    if (error is! DioException) return false;
    return extractError(error).toLowerCase().contains('already rated');
  }

  Future<void> _showAlreadyRatedPopup({String counterpartName = 'this user'}) async {
    final navContext = appNavigatorKey.currentContext;
    if (navContext == null) return;
    await showDialog<void>(
      context: navContext,
      builder: (ctx) => AlertDialog(
        title: const Text('Already Rated'),
        content: Text(
          'You have already rated $counterpartName for this ride.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _initFcmNavigationHooks();
    _startRatingPromptPolling();
  }

  @override
  void dispose() {
    _foregroundSub?.cancel();
    _openedSub?.cancel();
    _ratingPromptPollTimer?.cancel();
    super.dispose();
  }

  Map<String, String> _normalizedData(Map<String, dynamic> raw) {
    final data = <String, String>{};
    raw.forEach((key, value) {
      if (value == null) return;
      final text = value.toString();
      if (text.trim().isEmpty) return;
      data[key] = text;
    });
    return data;
  }

  String? _pick(Map<String, String> data, List<String> keys) {
    for (final key in keys) {
      final value = data[key];
      if (value != null && value.trim().isNotEmpty) {
        return value.trim();
      }
    }
    return null;
  }

  bool _isChatPayload(Map<String, String> data) {
    final event = _pick(data, const ['event', 'meta_event'])?.toLowerCase();
    if (event == 'chat_message') return true;
    return _pick(data, const ['thread_id', 'meta_thread_id']) != null;
  }

  bool _isRatingPromptPayload(Map<String, String> data) {
    final event = _pick(data, const ['event', 'meta_event'])?.toLowerCase();
    if (event == 'rating_prompt_required') return true;

    final roleContext =
        _pick(data, const ['role_context', 'meta_role_context'])?.toLowerCase();
    return roleContext == 'passenger_rates_driver' ||
        roleContext == 'driver_rates_passenger';
  }

  String? _ratingPromptKey(Map<String, String> data) {
    final rideId = _pick(data, const ['ride_id', 'meta_ride_id']) ?? '';
    final bookingId =
        _pick(data, const ['booking_id', 'meta_booking_id']) ?? '';
    final raterId = _pick(data, const ['rater_id', 'meta_rater_id']) ?? '';
    final rateeId = _pick(data, const ['ratee_id', 'meta_ratee_id']) ?? '';

    if (rideId.isEmpty || rateeId.isEmpty) {
      return null;
    }

    return '$rideId|$bookingId|$raterId|$rateeId';
  }

  Future<void> _markNotificationReadIfPresent(String? notificationId) async {
    final id = (notificationId ?? '').trim();
    if (id.isEmpty) return;

    try {
      await _notificationService.markAsRead(id);
    } catch (_) {
      // Keep UX resilient; unread badge can still recover on next refresh.
    }
  }

  Future<bool> _presentRatingPrompt(
    Map<String, String> data, {
    required bool openedFromTap,
  }) async {
    final rideId = _pick(data, const ['ride_id', 'meta_ride_id']);
    final rateeId = _pick(data, const ['ratee_id', 'meta_ratee_id']);
    if (rideId == null || rateeId == null) {
      return false;
    }

    final promptKey = _ratingPromptKey(data);
    if (promptKey == null || _handledRatingPromptKeys.contains(promptKey)) {
      return false;
    }

    final context = appNavigatorKey.currentContext;
    if (context == null) {
      return false;
    }

    _handledRatingPromptKeys.add(promptKey);

    final bookingId = _pick(data, const ['booking_id', 'meta_booking_id']);
    final counterpartName =
        _pick(data, const ['counterpart_name', 'meta_counterpart_name']) ??
            'this user';
    final notificationId =
        _pick(data, const ['notification_id', 'meta_notification_id']);

    int selectedRating = 5;
    final commentCtrl = TextEditingController();
    var submitted = false;

    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        var submitting = false;

        return StatefulBuilder(
          builder: (dialogContext, setDialogState) {
            return AlertDialog(
              title: Text('Rate $counterpartName'),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(5, (index) {
                      return IconButton(
                        onPressed: submitting
                            ? null
                            : () => setDialogState(() {
                                  selectedRating = index + 1;
                                }),
                        icon: Icon(
                          index < selectedRating
                              ? Icons.star_rounded
                              : Icons.star_outline_rounded,
                          color: AppColors.accent,
                          size: 34,
                        ),
                      );
                    }),
                  ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: commentCtrl,
                    maxLines: 3,
                    enabled: !submitting,
                    decoration: const InputDecoration(
                      labelText: 'Comment (optional)',
                      hintText: 'Share your feedback',
                    ),
                  ),
                ],
              ),
              actions: [
                TextButton(
                  onPressed: submitting
                      ? null
                      : () => Navigator.of(dialogContext).pop(),
                  child: const Text('Later'),
                ),
                ElevatedButton(
                  onPressed: submitting
                      ? null
                      : () async {
                          setDialogState(() {
                            submitting = true;
                          });

                          final comment = commentCtrl.text.trim();
                          try {
                            await _ratingService.createRating(
                              rideId: rideId,
                              rating: selectedRating,
                              toUserId: rateeId,
                              bookingId: bookingId,
                              comment: comment.isNotEmpty ? comment : null,
                            );
                            submitted = true;
                            appNavigatorKey.currentState?.pop();
                          } catch (e) {
                            if (_isDuplicateRatingError(e)) {
                              submitted = true;
                              if (dialogContext.mounted) {
                                appNavigatorKey.currentState?.pop();
                              }
                              await _showAlreadyRatedPopup(
                                counterpartName: counterpartName,
                              );
                              return;
                            }
                            if (dialogContext.mounted) {
                              setDialogState(() {
                                submitting = false;
                              });
                            }
                            debugPrint('Rating prompt submission failed: $e');
                          }
                        },
                  child: const Text('Submit'),
                ),
              ],
            );
          },
        );
      },
    );

    commentCtrl.dispose();

    if (submitted) {
      await _markNotificationReadIfPresent(notificationId);
      _refreshBadges();
    } else if (openedFromTap) {
      // User intentionally opened the push but decided to rate later.
      _refreshBadges();
    }

    return true;
  }

  Future<bool> _maybeHandleRatingPromptPayload(
    Map<String, String> data, {
    required bool openedFromTap,
  }) async {
    if (!_isRatingPromptPayload(data)) {
      return false;
    }
    return _presentRatingPrompt(data, openedFromTap: openedFromTap);
  }

  void _startRatingPromptPolling() {
    _ratingPromptPollTimer?.cancel();
    _ratingPromptPollTimer = Timer.periodic(
      const Duration(seconds: 8),
      (_) {
        unawaited(_pollUnreadRatingPrompts());
      },
    );
    unawaited(_pollUnreadRatingPrompts());
  }

  Future<void> _pollUnreadRatingPrompts() async {
    if (_ratingPromptPollBusy) {
      return;
    }

    _ratingPromptPollBusy = true;
    try {
      final loggedIn = await AuthService().isLoggedIn();
      if (!loggedIn) {
        return;
      }

      final result = await _notificationService.getMyNotifications(
        limit: 50,
        unreadOnly: true,
      );

      for (final notification in result.notifications) {
        final metadata = notification.metadata;
        if (metadata == null || metadata.isEmpty) {
          continue;
        }

        final data = _normalizedData(metadata);
        data.putIfAbsent('notification_id', () => notification.id);

        if (!_isRatingPromptPayload(data)) {
          continue;
        }

        final shown = await _maybeHandleRatingPromptPayload(
          data,
          openedFromTap: false,
        );

        // Present only one prompt at a time.
        if (shown) {
          break;
        }
      }
    } catch (_) {
      // Keep polling resilient against intermittent connectivity/auth refresh.
    } finally {
      _ratingPromptPollBusy = false;
    }
  }

  Map<String, dynamic> _chatRouteArgs(Map<String, String> data) {
    return {
      if (_pick(data, const ['thread_id', 'meta_thread_id']) != null)
        'threadId': _pick(data, const ['thread_id', 'meta_thread_id']),
      if (_pick(data, const ['ride_id', 'meta_ride_id']) != null)
        'rideId': _pick(data, const ['ride_id', 'meta_ride_id']),
      if (_pick(data, const ['booking_id', 'meta_booking_id']) != null)
        'bookingId': _pick(data, const ['booking_id', 'meta_booking_id']),
      if (_pick(data, const ['passenger_id', 'meta_passenger_id']) != null)
        'passengerId': _pick(data, const ['passenger_id', 'meta_passenger_id']),
      if (_pick(data, const ['sender_name', 'meta_sender_name']) != null)
        'counterpartName':
            _pick(data, const ['sender_name', 'meta_sender_name']),
    };
  }

  void _refreshBadges() {
    NotificationSyncService().refreshUnreadCount(force: true);
    ChatSyncService().refreshUnreadCount(force: true);
  }

  void _openChatFromPayload(Map<String, String> data) {
    final args = _chatRouteArgs(data);
    final threadId = (args['threadId'] ?? '').toString();
    final rideId = (args['rideId'] ?? '').toString();

    if (threadId.isEmpty && rideId.isEmpty) return;
    final nav = appNavigatorKey.currentState;
    if (nav == null) return;

    nav.pushNamed('/chat', arguments: args);
  }

  void _showForegroundChatSnack(Map<String, String> data) {
    final context = appNavigatorKey.currentContext;
    if (context == null) return;

    final sender =
        _pick(data, const ['sender_name', 'meta_sender_name']) ?? 'Someone';
    final body =
        _pick(data, const ['message', 'meta_message']) ?? 'sent a new message';

    final messenger = ScaffoldMessenger.maybeOf(context);
    if (messenger == null) return;

    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(
        content: Text('$sender: $body'),
        action: SnackBarAction(
          label: 'Open',
          onPressed: () => _openChatFromPayload(data),
        ),
      ),
    );
  }

  void _handleMessage(RemoteMessage message, {required bool openedFromTap}) {
    final data = _normalizedData(message.data);
    _refreshBadges();

    if (_isRatingPromptPayload(data)) {
      unawaited(
        _maybeHandleRatingPromptPayload(
          data,
          openedFromTap: openedFromTap,
        ),
      );
      return;
    }

    if (!_isChatPayload(data)) return;

    if (openedFromTap) {
      _openChatFromPayload(data);
      return;
    }
    _showForegroundChatSnack(data);
  }

  Future<void> _initFcmNavigationHooks() async {
    _foregroundSub = FirebaseMessaging.onMessage.listen(
      (message) => _handleMessage(message, openedFromTap: false),
    );
    _openedSub = FirebaseMessaging.onMessageOpenedApp.listen(
      (message) => _handleMessage(message, openedFromTap: true),
    );

    final initial = await FirebaseMessaging.instance.getInitialMessage();
    if (initial != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _handleMessage(initial, openedFromTap: true);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final themeProvider = Provider.of<ThemeProvider>(context);
    return MaterialApp(
      title: 'Sylo',
      debugShowCheckedModeBanner: false,
      navigatorKey: appNavigatorKey,
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: themeProvider.themeMode,
      home: const SplashScreenWrapper(),
      routes: {
        '/signin': (context) => const SignInScreen(),
        '/signup': (context) => const SignUpScreen(),
        '/passenger-dashboard': (context) => const PassengerDashboardScreen(),
        '/driver-dashboard': (context) => const DriverDashboardScreen(),
        '/notifications': (context) => const NotificationListScreen(),
        '/wallet': (context) => const WalletScreen(),
        '/profile-edit': (context) => const ProfileEditScreen(),
        '/verification': (context) => const VerificationScreen(),
        '/ride-history': (context) => const RideHistoryScreen(),
        '/chat-history': (context) => const ChatHistoryScreen(),
        '/help-faq': (context) => const HelpFaqScreen(),
        '/terms-of-service': (context) => const TermsOfServiceScreen(),
        '/privacy-policy': (context) => const PrivacyPolicyScreen(),
        '/recurring-schedule': (context) => const RecurringScheduleScreen(),
        '/ratings-reviews': (context) => const RatingsReviewsScreen(),
        '/admin-signin': (context) => const AdminSignInScreen(),
        '/admin-dashboard': (context) => const AdminDashboardScreen(),
        '/sos': (context) {
          final rideId = ModalRoute.of(context)?.settings.arguments as String?;
          return SOSScreen(rideId: rideId);
        },
      },
      onGenerateRoute: (settings) {
        if (settings.name == '/ride-detail') {
          final rideId = settings.arguments as String;
          return MaterialPageRoute(
            builder: (_) => RideDetailScreen(rideId: rideId),
          );
        }
        if (settings.name == '/live-tracking') {
          final args = settings.arguments as Map<String, dynamic>;
          return MaterialPageRoute(
            builder: (_) => LiveTrackingScreen(
              rideId: args['rideId'] as String,
              driverName: args['driverName'] as String?,
              bookingId: args['bookingId']?.toString(),
              passengerId: args['passengerId']?.toString(),
              pickupLocation: args['pickupLocation'],
              dropoffLocation: args['dropoffLocation'],
            ),
          );
        }
        if (settings.name == '/admin-incident-detail') {
          final args = settings.arguments;
          final incidentId = args is Map<String, dynamic>
              ? (args['incidentId']?.toString() ?? '')
              : (args?.toString() ?? '');
          final sosLabel = args is Map<String, dynamic>
              ? args['sosLabel']?.toString()
              : null;
          return MaterialPageRoute(
            builder: (_) => AdminIncidentDetailScreen(
              incidentId: incidentId,
              sosLabel: sosLabel,
            ),
          );
        }

        final rawName = settings.name ?? '';
        if (rawName == '/chat' || rawName.startsWith('/chat?')) {
          final args = settings.arguments is Map<String, dynamic>
              ? Map<String, dynamic>.from(
                  settings.arguments as Map<String, dynamic>)
              : <String, dynamic>{};

          final uri = Uri.tryParse(rawName);
          final query = uri?.queryParameters ?? const <String, String>{};

          final threadId = (args['threadId'] ?? query['threadId'])?.toString();
          final rideId = (args['rideId'] ?? query['rideId'])?.toString();
          final bookingId =
              (args['bookingId'] ?? query['bookingId'])?.toString();
          final passengerId =
              (args['passengerId'] ?? query['passengerId'])?.toString();
          final rideTitle =
              (args['rideTitle'] ?? query['rideTitle'])?.toString();
          final counterpartName =
              (args['counterpartName'] ?? query['counterpartName'])?.toString();

          return MaterialPageRoute(
            builder: (_) => ChatScreen(
              threadId: threadId,
              rideId: rideId,
              bookingId: bookingId,
              passengerId: passengerId,
              rideTitle: rideTitle,
              counterpartName: counterpartName,
            ),
          );
        }
        return null;
      },
    );
  }
}

class SplashScreenWrapper extends StatefulWidget {
  const SplashScreenWrapper({super.key});

  @override
  State<SplashScreenWrapper> createState() => _SplashScreenWrapperState();
}

class _SplashScreenWrapperState extends State<SplashScreenWrapper> {
  bool _isLoggedIn = false;
  String _userRole = 'passenger';
  bool _isLoading = true;

  String _fcmPlatform() {
    if (kIsWeb) return 'web';
    if (defaultTargetPlatform == TargetPlatform.iOS) return 'ios';
    return 'android';
  }

  @override
  void initState() {
    super.initState();
    _checkLoginStatus();
  }

  Future<void> _checkLoginStatus() async {
    var isLoggedIn = false;
    String role = 'passenger';
    try {
      isLoggedIn = await AuthService().isLoggedIn();
      role = (await AuthService().getUserRole()) ?? 'passenger';

      if (isLoggedIn) {
        _registerFcmToken();
      }
    } catch (_) {
      isLoggedIn = false;
      role = 'passenger';
    } finally {
      if (mounted) {
        setState(() {
          _isLoggedIn = isLoggedIn;
          _userRole = role;
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _registerFcmToken() async {
    try {
      final messaging = FirebaseMessaging.instance;
      final platform = _fcmPlatform();

      final settings = await messaging.requestPermission(
        alert: true,
        badge: true,
        sound: true,
      );

      if (settings.authorizationStatus == AuthorizationStatus.authorized ||
          settings.authorizationStatus == AuthorizationStatus.provisional) {
        final token = await messaging.getToken();
        if (token != null && token.isNotEmpty) {
          await NotificationService()
              .registerDeviceToken(deviceToken: token, platform: platform);
          debugPrint('FCM token registered for platform=$platform');
        } else {
          debugPrint('FCM token was null/empty for platform=$platform');
        }

        messaging.onTokenRefresh.listen(
          (newToken) async {
            if (newToken.isEmpty) {
              debugPrint('FCM token refresh returned empty token');
              return;
            }
            try {
              await NotificationService().registerDeviceToken(
                  deviceToken: newToken, platform: platform);
              debugPrint('FCM token refresh registered for platform=$platform');
            } catch (e) {
              debugPrint('FCM token refresh registration failed: $e');
            }
          },
          onError: (Object error) {
            debugPrint('FCM token refresh stream error: $error');
          },
        );
      } else {
        debugPrint(
          'FCM permission not granted: ${settings.authorizationStatus.name}',
        );
      }
    } catch (e) {
      debugPrint('FCM registration failed: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Scaffold(
        body: Center(
          child: CircularProgressIndicator(),
        ),
      );
    }

    return SplashScreen(isLoggedIn: _isLoggedIn, userRole: _userRole);
  }
}
