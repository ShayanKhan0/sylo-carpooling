import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../core/services/api_client.dart';
import '../../core/services/verification_service.dart';
import '../../core/services/auth_service.dart';
import '../../core/theme/app_colors.dart';
import '../../core/constants/app_constants.dart';
import '../dashboard/home_design_system.dart';
import '../shared/widgets.dart';

// === VERIFICATION FUNCTIONALITY START ===
class VerificationScreen extends StatefulWidget {
  const VerificationScreen({super.key});

  @override
  State<VerificationScreen> createState() => _VerificationScreenState();
}

class _VerificationScreenState extends State<VerificationScreen> {
  final VerificationService _svc = VerificationService();
  static const int _aiProcessingCountdownSeconds = 5;
  static const String _identityResultsStoragePrefix =
      'verification_identity_results_v1_';
  Map<String, dynamic>? _status;
  final Map<String, Map<String, dynamic>> _identityResults = {};
  final Set<String> _identityLoadingDocs = <String>{};
  String? _currentUserId;
  bool _loading = true;
  String? _error;
  Timer? _processingTimer;
  int _processingSecondsRemaining = 0;
  static const Color _homeTextPrimary = Color(0xFF121915);
  static const Color _homeTextSecondary = Color(0xFF25352D);
  static const Color _innerCardDarkGreen = Color(0xFF174632);
  static const Color _innerCardDarkGreen2 = Color(0xFF1E5540);

  BoxDecoration _myRidesCardDecoration({
    double radius = 18,
    bool elevated = false,
    double borderAlpha = 0.56,
    double borderWidth = 1.1,
  }) {
    return BoxDecoration(
      borderRadius: BorderRadius.circular(radius),
      color: const Color(0xA2123E2A),
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          Color(0xD255E0A0),
          Color(0xB53ABF7C),
          Color(0xA13A7051),
        ],
        stops: [0.0, 0.5, 1.0],
      ),
      border: Border.all(
        color: const Color(0xFFD7FFE8).withValues(alpha: borderAlpha),
        width: borderWidth,
      ),
      boxShadow: [
        if (elevated)
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.24),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        BoxShadow(
          color: const Color(0xFF1ED760).withValues(alpha: 0.24),
          blurRadius: 32,
          spreadRadius: -8,
          offset: const Offset(-8, -6),
        ),
      ],
    );
  }

  BoxDecoration _innerDarkCardDecoration({double radius = 14}) {
    return BoxDecoration(
      borderRadius: BorderRadius.circular(radius),
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [_innerCardDarkGreen2, _innerCardDarkGreen],
      ),
      border: Border.all(
        color: const Color(0xFF8FFFC0).withValues(alpha: 0.24),
        width: 1.0,
      ),
      boxShadow: [
        BoxShadow(
          color: Colors.black.withValues(alpha: 0.18),
          blurRadius: 16,
          offset: const Offset(0, 6),
        ),
      ],
    );
  }

  Color _statusTextColor(String text, Color fallback) {
    final lower = text.toLowerCase();
    if (lower.contains('not uploaded') || lower.contains('unverified')) {
      return AppColors.error;
    }
    if (lower.contains('verified') || lower.contains('approved')) {
      return AppColors.primary;
    }
    return fallback;
  }

  String _identityResultsStorageKey(String userId) =>
      '$_identityResultsStoragePrefix$userId';

  Future<Map<String, Map<String, dynamic>>> _loadIdentityResultsForUser(
    String userId,
  ) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_identityResultsStorageKey(userId));
      if (raw == null || raw.trim().isEmpty) {
        return <String, Map<String, dynamic>>{};
      }

      final decoded = jsonDecode(raw);
      if (decoded is! Map) {
        await prefs.remove(_identityResultsStorageKey(userId));
        return <String, Map<String, dynamic>>{};
      }

      final parsed = <String, Map<String, dynamic>>{};
      for (final entry in decoded.entries) {
        final key = entry.key.toString();
        final value = entry.value;
        if (value is Map) {
          parsed[key] = Map<String, dynamic>.from(value);
        }
      }
      return parsed;
    } catch (_) {
      return <String, Map<String, dynamic>>{};
    }
  }

  Future<void> _saveIdentityResultsForCurrentUser() async {
    final userId = _currentUserId ?? await AuthService().getUserId();
    if (userId == null || userId.trim().isEmpty) {
      return;
    }

    _currentUserId = userId;
    final prefs = await SharedPreferences.getInstance();
    final storageKey = _identityResultsStorageKey(userId);

    if (_identityResults.isEmpty) {
      await prefs.remove(storageKey);
      return;
    }

    await prefs.setString(storageKey, jsonEncode(_identityResults));
  }

  @override
  void initState() {
    super.initState();
    _loadStatus();
  }

  @override
  void dispose() {
    _processingTimer?.cancel();
    super.dispose();
  }

  String _friendlyErrorMessage(
    Object error, {
    String fallback = 'Something went wrong. Please try again.',
  }) {
    if (error is DioException) {
      return extractError(error);
    }

    final raw = error.toString().trim();
    if (raw.isEmpty) return fallback;

    final lower = raw.toLowerCase();
    if (lower.contains('timeout') || lower.contains('timed out')) {
      return 'Request timed out. Please try again.';
    }
    if (lower.contains('dioexception')) {
      return 'Request failed. Please try again.';
    }

    const prefix = 'Exception: ';
    if (raw.startsWith(prefix)) {
      final cleaned = raw.substring(prefix.length).trim();
      if (cleaned.isNotEmpty) {
        return cleaned;
      }
    }

    return fallback;
  }

  bool _isInvalidDocumentFormatError(String message) {
    final lower = message.toLowerCase();
    return lower.contains('file type not allowed') ||
        lower.contains('content type not allowed') ||
        lower.contains('unsupported media type') ||
        lower.contains('invalid file type') ||
        lower.contains('invalid image format');
  }

  Future<void> _showInvalidDocumentFormatDialog() async {
    if (!mounted) return;

    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Invalid Document Format'),
        content: const Text(
          'Please upload the document in one of the required formats:\n'
          '- JPG / JPEG\n'
          '- PNG\n'
          '- PDF\n\n'
          'Maximum file size: 10 MB.',
        ),
        actions: [
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primary,
              foregroundColor: Colors.white,
            ),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }

  Future<void> _showVerificationIssueDialog({
    required String title,
    required String message,
  }) async {
    if (!mounted) return;

    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
          side: BorderSide(
            color: AppColors.primary.withValues(alpha: 0.25),
          ),
        ),
        title: Row(
          children: [
            const Icon(Icons.info_outline_rounded, color: AppColors.primary),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                title,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
            ),
          ],
        ),
        content: Text(
          message,
          style: const TextStyle(height: 1.35),
        ),
        actions: [
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primary,
              foregroundColor: Colors.white,
            ),
            child: const Text('Got it'),
          ),
        ],
      ),
    );
  }

  Future<void> _loadStatus() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final userId = await AuthService().getUserId();
      if (userId == null) throw Exception('Not logged in');

      if (_currentUserId != userId) {
        _currentUserId = userId;
        final restoredIdentityResults =
            await _loadIdentityResultsForUser(userId);
        _identityResults
          ..clear()
          ..addAll(restoredIdentityResults);
      }

      final status = await _svc.getStatus(userId);
      final readyInSeconds =
          (status['analysis_ready_in_seconds'] as num?)?.toInt() ?? 0;

      final requiredDocs = (status['required_documents'] as List?)
              ?.map((item) => item.toString())
              .where((item) => item.isNotEmpty)
              .toList() ??
          const <String>['cnic', 'selfie'];
      final verifications =
          (status['verifications'] as Map?)?.cast<String, dynamic>() ??
              <String, dynamic>{};
      final latestDocumentPaths =
          (status['latest_document_paths'] as Map?)?.cast<String, dynamic>() ??
              <String, dynamic>{};
      final hasPathSyncData = latestDocumentPaths.isNotEmpty;
      final identityDocsForStatus = requiredDocs.contains('driving_license')
          ? const <String>{'cnic', 'driving_license'}
          : const <String>{'cnic'};

      final syncedIdentityResults =
          Map<String, Map<String, dynamic>>.from(_identityResults);
      syncedIdentityResults.removeWhere(
        (docType, _) => !identityDocsForStatus.contains(docType),
      );

      for (final docType in identityDocsForStatus) {
        final docStatus = verifications[docType]?.toString() ?? 'not_uploaded';

        if (docStatus == 'not_uploaded') {
          syncedIdentityResults.remove(docType);
          continue;
        }

        if (!hasPathSyncData) {
          continue;
        }

        final existingResult = syncedIdentityResults[docType];
        if (existingResult == null) {
          continue;
        }

        final latestPath = latestDocumentPaths[docType]?.toString() ?? '';
        final resultPath = existingResult['document_path']?.toString() ?? '';
        if (latestPath.isEmpty ||
            resultPath.isEmpty ||
            latestPath != resultPath) {
          syncedIdentityResults.remove(docType);
        }
      }

      final hasMissingRequiredDocs = requiredDocs.any((docType) {
        final docStatus = verifications[docType]?.toString() ?? 'not_uploaded';
        return docStatus == 'not_uploaded';
      });

      if (readyInSeconds > 0 && !hasMissingRequiredDocs) {
        _startProcessingCountdown(readyInSeconds);
      } else {
        _stopProcessingCountdown();
      }

      setState(() {
        _status = status;
        _identityResults
          ..clear()
          ..addAll(syncedIdentityResults);
        _identityLoadingDocs.removeWhere(
          (docType) => !_identityResults.containsKey(docType),
        );
        _loading = false;
      });

      await _saveIdentityResultsForCurrentUser();
    } catch (e) {
      setState(() {
        _error = _friendlyErrorMessage(
          e,
          fallback: 'Unable to load verification status. Please try again.',
        );
        _loading = false;
      });
    }
  }

  void _startProcessingCountdown(int seconds) {
    final safeSeconds = seconds < 0 ? 0 : seconds;
    _processingTimer?.cancel();
    if (mounted) {
      setState(() {
        _processingSecondsRemaining = safeSeconds;
      });
    } else {
      _processingSecondsRemaining = safeSeconds;
    }

    if (safeSeconds == 0) return;

    _processingTimer =
        Timer.periodic(const Duration(seconds: 1), (timer) async {
      if (!mounted) {
        timer.cancel();
        return;
      }

      if (_processingSecondsRemaining <= 1) {
        timer.cancel();
        setState(() {
          _processingSecondsRemaining = 0;
        });
        await _loadStatus();
        return;
      }

      setState(() {
        _processingSecondsRemaining -= 1;
      });
    });
  }

  void _stopProcessingCountdown() {
    _processingTimer?.cancel();
    _processingTimer = null;
    _processingSecondsRemaining = 0;
  }

  Future<void> _runIdentityDataVerification(String docType) async {
    if (_identityLoadingDocs.contains(docType)) return;

    setState(() {
      _identityLoadingDocs.add(docType);
    });

    try {
      final result = await _svc.verifyIdentityData(documentType: docType);

      if (!mounted) return;
      final passed = result['check_status']?.toString() == 'passed';
      final message = result['message']?.toString() ??
          'Identity Data Verification completed.';

      setState(() {
        _identityResults[docType] = result;
        _identityLoadingDocs.remove(docType);
      });
      await _saveIdentityResultsForCurrentUser();
      await _loadStatus();
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: passed ? AppColors.success : AppColors.error,
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _identityLoadingDocs.remove(docType);
      });
      final message = _friendlyErrorMessage(
        e,
        fallback:
            'Unable to run identity verification right now. Please try again.',
      );
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
      );
    }
  }

  final ImagePicker _picker = ImagePicker();

  Future<void> _uploadDocument(String docType) async {
    try {
      // Show source picker (camera or gallery)
      final source = await showModalBottomSheet<ImageSource>(
        context: context,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
        ),
        builder: (ctx) => SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('Upload ${_docTypeLabel(docType)}',
                    style: const TextStyle(
                        fontSize: 18, fontWeight: FontWeight.bold)),
                const SizedBox(height: 4),
                Text(_docTypeHint(docType),
                    style: TextStyle(
                        color: AppColors.textSecondary, fontSize: 13)),
                const SizedBox(height: 16),
                if (!kIsWeb)
                  ListTile(
                    leading: const Icon(Icons.camera_alt_rounded,
                        color: AppColors.primary),
                    title: const Text('Take a Photo'),
                    onTap: () => Navigator.pop(ctx, ImageSource.camera),
                  ),
                ListTile(
                  leading: const Icon(Icons.photo_library_rounded,
                      color: AppColors.primary),
                  title: const Text(kIsWeb
                      ? 'Choose the Document'
                      : 'Choose the Document from Gallery'),
                  onTap: () => Navigator.pop(ctx, ImageSource.gallery),
                ),
              ],
            ),
          ),
        ),
      );

      if (source == null) return;

      final preserveDetailForOcr =
          docType == 'cnic' || docType == 'driving_license';
      final maxWidth = preserveDetailForOcr ? null : 1920.0;
      final maxHeight = preserveDetailForOcr ? null : 1920.0;
      final imageQuality = preserveDetailForOcr ? 100 : 85;

      XFile? pickedFile = await _picker.pickImage(
        source: source,
        maxWidth: maxWidth,
        maxHeight: maxHeight,
        imageQuality: imageQuality,
      );

      if (pickedFile == null) return;

      while (true) {
        final currentFile = pickedFile;
        if (currentFile == null) return;

        // Show preview and confirm
        final fileBytes = await currentFile.readAsBytes();

        if (!mounted) return;

        final confirmed = await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: Text('Upload ${_docTypeLabel(docType)}'),
            content: SizedBox(
              width: double.maxFinite,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    height: 200,
                    width: double.maxFinite,
                    child: ClipRRect(
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusMedium),
                      child: Image.memory(
                        fileBytes,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => const ColoredBox(
                          color: Color(0xFFF1F3F5),
                          child: Center(
                            child: Icon(Icons.broken_image_outlined),
                          ),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text('Does this image look clear and readable?',
                      style: TextStyle(
                          color: AppColors.textSecondary, fontSize: 13)),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('Retake'),
              ),
              ElevatedButton(
                onPressed: () => Navigator.pop(ctx, true),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppColors.primary,
                  foregroundColor: Colors.white,
                ),
                child: const Text('Upload'),
              ),
            ],
          ),
        );

        if (confirmed == true) {
          break;
        }

        // If dismissed, leave upload flow. Retake (false) reopens picker.
        if (confirmed == null || !mounted) {
          return;
        }

        pickedFile = await _picker.pickImage(
          source: source,
          maxWidth: maxWidth,
          maxHeight: maxHeight,
          imageQuality: imageQuality,
        );

        if (pickedFile == null) {
          return;
        }
      }

      if (!mounted || pickedFile == null) return;
      final selectedFile = pickedFile;

      // Upload with loading indicator
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (_) => const Center(child: CircularProgressIndicator()),
      );

      try {
        await _svc.uploadDocument(
          documentType: docType,
          imageFile: selectedFile,
        );
        if (mounted) {
          Navigator.of(context, rootNavigator: true).pop(); // dismiss loader
          if (docType == 'cnic' || docType == 'driving_license') {
            setState(() {
              _identityResults.remove(docType);
            });
            await _saveIdentityResultsForCurrentUser();
            if (!mounted) return;
          }
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Document uploaded for verification!'),
              backgroundColor: AppColors.success,
            ),
          );
        }
        await _loadStatus();
        if (mounted && _allRequiredDocsUploaded()) {
          _startProcessingCountdown(_aiProcessingCountdownSeconds);
        }
      } catch (e) {
        if (mounted) {
          Navigator.of(context, rootNavigator: true).pop(); // dismiss loader
          final message = _friendlyErrorMessage(
            e,
            fallback: 'Upload failed. Please try again.',
          );
          if (_isInvalidDocumentFormatError(message)) {
            await _showInvalidDocumentFormatDialog();
          } else {
            await _showVerificationIssueDialog(
              title: 'Upload Issue',
              message: message,
            );
          }
        }
      }
    } catch (e) {
      if (!mounted) return;
      final message = _friendlyErrorMessage(
        e,
        fallback: 'Could not open document picker. Please try again.',
      );
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
      );
    }
  }

  Future<void> _deleteDocument(String docType) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Delete ${_docTypeLabel(docType)}?'),
        content: const Text(
          'This removes the uploaded image so you can upload a new one.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.error,
              foregroundColor: Colors.white,
            ),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );

    try {
      await _svc.deleteDocument(documentType: docType);
      if (!mounted) return;
      Navigator.of(context, rootNavigator: true).pop();
      if (docType == 'cnic' || docType == 'driving_license') {
        setState(() {
          _identityResults.remove(docType);
        });
        await _saveIdentityResultsForCurrentUser();
        if (!mounted) return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${_docTypeLabel(docType)} deleted.'),
          backgroundColor: AppColors.info,
        ),
      );
      await _loadStatus();
    } catch (e) {
      if (!mounted) return;
      Navigator.of(context, rootNavigator: true).pop();
      final message = _friendlyErrorMessage(
        e,
        fallback: 'Delete failed. Please try again.',
      );
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
      );
    }
  }

  String _docTypeLabel(String type) {
    switch (type) {
      case 'cnic':
        return 'CNIC';
      case 'driving_license':
        return 'Driving License';
      case 'vehicle_registration':
        return 'Vehicle Registration';
      case 'selfie':
        return 'Selfie';
      case 'insurance':
        return 'Insurance';
      default:
        return type.replaceAll('_', ' ');
    }
  }

  String _docTypeHint(String type) {
    switch (type) {
      case 'cnic':
        return 'Take a clear photo of your CNIC card (front side).';
      case 'driving_license':
        return 'Upload your valid driving license.';
      case 'vehicle_registration':
        return 'Upload your vehicle registration document.';
      case 'selfie':
        return 'Take a selfie for face verification.';
      case 'insurance':
        return 'Upload your vehicle insurance document.';
      default:
        return 'Upload a clear image.';
    }
  }

  IconData _docTypeIcon(String type) {
    switch (type) {
      case 'cnic':
        return Icons.credit_card_rounded;
      case 'driving_license':
        return Icons.badge_rounded;
      case 'vehicle_registration':
        return Icons.directions_car_rounded;
      case 'selfie':
        return Icons.face_rounded;
      case 'insurance':
        return Icons.shield_rounded;
      default:
        return Icons.description_rounded;
    }
  }

  List<String> _requiredDocumentTypes() {
    final requiredDocs = (_status?['required_documents'] as List?)
            ?.map((item) => item.toString())
            .where((item) => item.isNotEmpty)
            .toList() ??
        <String>[];

    if (requiredDocs.isNotEmpty) {
      return requiredDocs;
    }

    return const ['cnic', 'selfie'];
  }

  List<String> _missingRequiredDocumentTypes() {
    final missingDocs = (_status?['missing_documents'] as List?)
            ?.map((item) => item.toString())
            .where((item) => item.isNotEmpty)
            .toList() ??
        <String>[];

    if (missingDocs.isNotEmpty) {
      return missingDocs;
    }

    final requiredDocs = _requiredDocumentTypes();
    if (requiredDocs.isEmpty) {
      return <String>[];
    }

    final verifications =
        (_status?['verifications'] as Map?)?.cast<String, dynamic>() ?? {};

    return requiredDocs.where((docType) {
      final docStatus = verifications[docType]?.toString() ?? 'not_uploaded';
      return docStatus == 'not_uploaded';
    }).toList();
  }

  String _formatDocTypeList(List<String> docTypes) {
    final labels = docTypes.map(_docTypeLabel).toList();

    if (labels.isEmpty) {
      return 'required documents';
    }

    if (labels.length == 1) {
      return labels.first;
    }

    if (labels.length == 2) {
      return '${labels[0]} and ${labels[1]}';
    }

    final leading = labels.sublist(0, labels.length - 1).join(', ');
    return '$leading and ${labels.last}';
  }

  bool _isPassengerVerificationFlow() {
    final required = _requiredDocumentTypes().toSet();
    return required.length == 2 &&
        required.contains('cnic') &&
        required.contains('selfie');
  }

  bool _isDriverVerificationFlow() {
    final required = _requiredDocumentTypes().toSet();
    return required.length == 3 &&
        required.contains('cnic') &&
        required.contains('driving_license') &&
        required.contains('selfie');
  }

  List<String> _driverProblemDocumentTypes() {
    if (!_isDriverVerificationFlow()) {
      return <String>[];
    }

    final fromApi = (_status?['driver_failed_documents'] as List?)
            ?.map((item) => item.toString())
            .where((item) =>
                item == 'cnic' || item == 'driving_license' || item == 'selfie')
            .toList() ??
        <String>[];

    if (fromApi.isNotEmpty) {
      return fromApi;
    }

    final verifications =
        (_status?['verifications'] as Map?)?.cast<String, dynamic>() ?? {};
    final rawVerifications =
        (_status?['raw_verifications'] as Map?)?.cast<String, dynamic>() ?? {};

    const trackedDocs = ['cnic', 'driving_license'];
    final rejectedDriverFaceDocs = trackedDocs.where((docType) {
      final rawStatus = rawVerifications[docType]?.toString() ?? '';
      final mappedStatus = verifications[docType]?.toString() ?? '';
      return rawStatus == 'rejected' || mappedStatus == 'rejected';
    }).toList();

    if (rejectedDriverFaceDocs.length == trackedDocs.length) {
      return const ['selfie'];
    }

    return rejectedDriverFaceDocs;
  }

  bool _allRequiredDocsUploaded() {
    final requiredDocs = _requiredDocumentTypes();
    if (requiredDocs.isEmpty) return false;

    final verifications =
        (_status?['verifications'] as Map?)?.cast<String, dynamic>() ?? {};

    return requiredDocs.every((docType) {
      final docStatus = verifications[docType]?.toString() ?? 'not_uploaded';
      return docStatus != 'not_uploaded';
    });
  }

  List<String> _identityDocumentTypes() {
    if (_isDriverVerificationFlow()) {
      return const ['cnic', 'driving_license'];
    }
    if (_isPassengerVerificationFlow()) {
      return const ['cnic'];
    }

    final required = _requiredDocumentTypes().toSet();
    if (required.contains('cnic')) {
      return const ['cnic'];
    }
    return const <String>[];
  }

  String _identityStepStatus(String docType) {
    if (_identityLoadingDocs.contains(docType)) {
      return 'processing';
    }

    final verifications =
        (_status?['verifications'] as Map?)?.cast<String, dynamic>() ?? {};
    final isUploaded = verifications[docType]?.toString() != 'not_uploaded';
    if (!isUploaded) {
      return 'not_uploaded';
    }

    final result = _identityResults[docType];
    final checkStatus = result?['check_status']?.toString() ?? 'not_run';
    if (checkStatus == 'passed') {
      return 'passed';
    }
    if (checkStatus == 'failed') {
      return 'failed';
    }

    return 'not_run';
  }

  Map<String, dynamic> _identityOverallStatusMeta() {
    final identityDocs = _identityDocumentTypes();
    if (identityDocs.isEmpty) {
      return {
        'title': 'Not Available',
        'hint': 'Identity Data Verification is not required for this account.',
        'color': AppColors.textHint,
        'icon': Icons.info_outline_rounded,
      };
    }

    final cnicStatus = _identityStepStatus('cnic');

    if (identityDocs.length == 1) {
      if (cnicStatus == 'passed') {
        return {
          'title': 'Verified',
          'hint': 'CNIC number check is verified.',
          'color': AppColors.success,
          'icon': Icons.verified_rounded,
        };
      }

      if (cnicStatus == 'failed') {
        return {
          'title': 'Unverified: CNIC',
          'hint': 'Please re-verify CNIC.',
          'color': AppColors.error,
          'icon': Icons.cancel_rounded,
        };
      }

      if (cnicStatus == 'processing') {
        return {
          'title': 'In Progress',
          'hint': 'CNIC verification is running. Please wait for completion.',
          'color': AppColors.accent,
          'icon': Icons.hourglass_top_rounded,
        };
      }

      if (cnicStatus == 'not_uploaded') {
        return {
          'title': 'Pending CNIC Upload',
          'hint': 'Please upload CNIC first, then run CNIC Number Match.',
          'color': AppColors.info,
          'icon': Icons.assignment_late_rounded,
        };
      }

      return {
        'title': 'Pending CNIC Verification',
        'hint': 'Please do CNIC Number Match.',
        'color': AppColors.info,
        'icon': Icons.assignment_late_rounded,
      };
    }

    final licenseStatus = _identityStepStatus('driving_license');

    final cnicPassed = cnicStatus == 'passed';
    final licensePassed = licenseStatus == 'passed';

    if (cnicPassed && licensePassed) {
      return {
        'title': 'Verified',
        'hint': 'Both CNIC and Driving License number checks are verified.',
        'color': AppColors.success,
        'icon': Icons.verified_rounded,
      };
    }

    final failedDocs = <String>[];
    if (cnicStatus == 'failed') {
      failedDocs.add('cnic');
    }
    if (licenseStatus == 'failed') {
      failedDocs.add('driving_license');
    }

    if (failedDocs.isNotEmpty) {
      return {
        'title': failedDocs.length == 1
            ? 'Unverified: ${_docTypeLabel(failedDocs.first)}'
            : 'Unverified: ${_formatDocTypeList(failedDocs)}',
        'hint': failedDocs.length == 1
            ? 'Please re-verify ${_docTypeLabel(failedDocs.first)}.'
            : 'Please re-verify ${_formatDocTypeList(failedDocs)}.',
        'color': AppColors.error,
        'icon': Icons.cancel_rounded,
      };
    }

    final anyProcessing =
        cnicStatus == 'processing' || licenseStatus == 'processing';
    if (anyProcessing) {
      return {
        'title': 'In Progress',
        'hint': 'Identity verification is running. Please wait for completion.',
        'color': AppColors.accent,
        'icon': Icons.hourglass_top_rounded,
      };
    }

    if (cnicPassed && !licensePassed) {
      return {
        'title': 'Pending Step 2',
        'hint': 'Step 1 is verified. Please do Step 2 (Driving License).',
        'color': AppColors.info,
        'icon': Icons.assignment_late_rounded,
      };
    }

    if (!cnicPassed && licensePassed) {
      return {
        'title': 'Pending Step 1',
        'hint': 'Step 2 is verified. Please do Step 1 (CNIC) first.',
        'color': AppColors.info,
        'icon': Icons.assignment_late_rounded,
      };
    }

    return {
      'title': 'Not Started',
      'hint': 'Firstly verify Step 1 (CNIC) and Step 2 (Driving License).',
      'color': AppColors.info,
      'icon': Icons.assignment_late_rounded,
    };
  }

  Widget _buildVerificationSectionCard({
    required ThemeData theme,
    required String title,
    required IconData icon,
    required Widget child,
    String? sectionStatusText,
    Color? sectionStatusColor,
    bool initiallyExpanded = false,
  }) {
    return HomeDesignSystem.frostLayer(
      blur: 10,
      radius: 18,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        decoration: _myRidesCardDecoration(
          radius: 18,
          elevated: false,
          borderAlpha: 0.62,
          borderWidth: 1.2,
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(18),
        child: Theme(
          data: theme.copyWith(dividerColor: Colors.transparent),
          child: ExpansionTile(
            initiallyExpanded: initiallyExpanded,
            tilePadding:
                const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
            childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
            leading: Icon(icon, color: const Color(0xFF0B3D24)),
            title: Row(
              children: [
                Expanded(
                  child: Text(
                    title,
                    style: GoogleFonts.inter(
                      color: _homeTextPrimary,
                      fontWeight: FontWeight.w800,
                      fontSize: 17,
                    ),
                  ),
                ),
                if (sectionStatusText != null)
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: (sectionStatusColor ?? AppColors.textHint)
                          .withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(
                        color: (sectionStatusColor ?? AppColors.textHint)
                            .withValues(alpha: 0.30),
                      ),
                    ),
                    child: Text(
                      sectionStatusText,
                      style: TextStyle(
                        color: sectionStatusColor ?? AppColors.textHint,
                        fontSize: 11.5,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
              ],
            ),
            subtitle: Text(
              'Tap to view details',
              style: GoogleFonts.inter(
                color: _homeTextSecondary.withValues(alpha: 0.86),
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
            children: [child],
          ),
        ),
      ),
    ));
  }

  Widget _buildIdentityDataVerificationWidget(ThemeData theme) {
    final identityDocs = _identityDocumentTypes();
    final isPassengerIdentityOnly =
        identityDocs.length == 1 && identityDocs.first == 'cnic';

    final statusMeta = _identityOverallStatusMeta();
    final statusColor = statusMeta['color'] as Color;
    final statusIcon = statusMeta['icon'] as IconData;
    final statusText = statusMeta['title'] as String;
    final statusHint = statusMeta['hint'] as String;
    final visibleStatusTextColor = _statusTextColor(statusText, statusColor);

    return Column(
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(20),
          decoration: _innerDarkCardDecoration(radius: AppConstants.radiusLarge),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: statusColor.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: Icon(statusIcon, color: statusColor, size: 32),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Verification Status',
                      style: GoogleFonts.inter(
                        fontSize: 13,
                        color: Colors.white.withValues(alpha: 0.78),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      statusText,
                      style: GoogleFonts.inter(
                        fontSize: 20,
                        fontWeight: FontWeight.w800,
                        color: visibleStatusTextColor,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      statusHint,
                      style: GoogleFonts.inter(
                        color: Colors.white.withValues(alpha: 0.78),
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        if (identityDocs.contains('cnic'))
          _buildIdentityVerificationActionTile(
            theme: theme,
            docType: 'cnic',
            title: isPassengerIdentityOnly
                ? 'CNIC Number Match'
                : 'Step 1: CNIC Number Match',
            subtitle:
                'Use uploaded CNIC image. The system extracts the CNIC number and matches it with Personal Info.',
            actionLabel: 'Use uploaded CNIC image',
          ),
        if (identityDocs.contains('cnic') &&
            identityDocs.contains('driving_license'))
          const SizedBox(height: 10),
        if (identityDocs.contains('driving_license'))
          _buildIdentityVerificationActionTile(
            theme: theme,
            docType: 'driving_license',
            title: 'Step 2: Driving License Number Match',
            subtitle:
                'Use uploaded Driving License image. The system extracts the license number and matches it with Personal Info.',
            actionLabel: 'Use uploaded License image',
          ),
      ],
    );
  }

  Widget _buildIdentityVerificationActionTile({
    required ThemeData theme,
    required String docType,
    required String title,
    required String subtitle,
    required String actionLabel,
  }) {
    final isRunning = _identityLoadingDocs.contains(docType);
    final result = _identityResults[docType];
    final verifications =
        (_status?['verifications'] as Map?)?.cast<String, dynamic>() ?? {};
    final isUploaded = verifications[docType]?.toString() != 'not_uploaded';
    final checkStatus = result?['check_status']?.toString() ?? 'not_run';

    Color statusColor;
    String statusText;
    if (isRunning) {
      statusColor = AppColors.accent;
      statusText = 'Processing...';
    } else if (!isUploaded) {
      statusColor = AppColors.error;
      statusText = 'Not uploaded';
    } else if (checkStatus == 'passed') {
      statusColor = AppColors.success;
      statusText = 'Verified';
    } else if (checkStatus == 'failed') {
      statusColor = AppColors.error;
      statusText = 'Unverified';
    } else {
      statusColor = AppColors.textHint;
      statusText = 'Not run';
    }
    statusColor = _statusTextColor(statusText, statusColor);

    final profileNumber = result?['profile_number']?.toString() ?? '';
    final extractedNumber = result?['extracted_number']?.toString() ?? '';
    final message = result?['message']?.toString() ?? '';

    return HomeDesignSystem.frostLayer(
      blur: 8,
      radius: 14,
      child: Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: _innerDarkCardDecoration(radius: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: GoogleFonts.inter(
              color: Colors.white,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            subtitle,
            style: GoogleFonts.inter(
              color: Colors.white.withValues(alpha: 0.78),
              fontSize: 12.5,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: Text(
                  statusText,
                  style: TextStyle(
                    color: statusColor,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
              OutlinedButton(
                onPressed: (isRunning || !isUploaded)
                    ? null
                    : () => _runIdentityDataVerification(docType),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.primary,
                  disabledForegroundColor: AppColors.primary,
                  side: const BorderSide(color: AppColors.primary),
                  textStyle: GoogleFonts.inter(
                    fontWeight: FontWeight.w700,
                    fontSize: 13.5,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius:
                        BorderRadius.circular(AppConstants.radiusSmall),
                  ),
                ),
                child: Text(
                  isRunning
                      ? 'Checking...'
                      : (isUploaded ? actionLabel : 'Upload first'),
                ),
              ),
            ],
          ),
          if (result != null) ...[
            const SizedBox(height: 10),
            if (message.isNotEmpty)
              Text(
                message,
                style: GoogleFonts.inter(
                  color: Colors.white.withValues(alpha: 0.78),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            if (profileNumber.isNotEmpty || extractedNumber.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                'Profile: ${profileNumber.isEmpty ? '-' : profileNumber}',
                style: GoogleFonts.inter(
                  color: Colors.white.withValues(alpha: 0.75),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
              Text(
                'Extracted: ${extractedNumber.isEmpty ? '-' : extractedNumber}',
                style: GoogleFonts.inter(
                  color: Colors.white.withValues(alpha: 0.75),
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ],
        ],
      ),
    ));
  }

  Widget _buildFaceVerificationWidget(
    ThemeData theme,
    bool isPassengerFlow,
    bool isDriverFlow,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildStatusCard(theme),
        const SizedBox(height: 16),
        Text(
          'Documents',
          style: theme.textTheme.titleMedium
              ?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 12),
        if (isPassengerFlow || isDriverFlow) ...[
          Container(
            margin: const EdgeInsets.only(bottom: 12),
            padding: const EdgeInsets.all(12),
            decoration:
                _innerDarkCardDecoration(radius: AppConstants.radiusMedium),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.tips_and_updates_outlined,
                    color: AppColors.info, size: 18),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    isDriverFlow
                        ? 'Upload order is flexible. For driver verification, upload CNIC, driving license, and selfie in any order. AI processing starts after all 3 are uploaded.'
                        : 'Upload order is flexible. You can upload selfie or CNIC first. Face matching starts automatically after both are uploaded.',
                    style: GoogleFonts.inter(
                      color: Colors.white.withValues(alpha: 0.84),
                      fontSize: 12.5,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
        ..._requiredDocumentTypes().map((docType) => _docTile(docType, theme)),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: _innerDarkCardDecoration(radius: AppConstants.radiusMedium),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.info_outline_rounded, color: AppColors.info),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Secure Verification',
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          color: Colors.white,
                        )),
                    const SizedBox(height: 4),
                    Text(
                      'Documents are verified using automated document and face checks. '
                      'Upload all required documents shown above, then processing takes about 5 seconds before final status.',
                      style: GoogleFonts.inter(
                        color: Colors.white.withValues(alpha: 0.84),
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isPassengerFlow = _isPassengerVerificationFlow();
    final isDriverFlow = _isDriverVerificationFlow();
    final showIdentitySection = _identityDocumentTypes().isNotEmpty;

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: _loading
          ? const SyloLoader(message: 'Loading verification status…')
          : _error != null
              ? SyloError(message: _error!, onRetry: _loadStatus)
              : RefreshIndicator(
                  color: AppColors.primary,
                  onRefresh: _loadStatus,
                  child: Stack(
                    children: [
                      HomeDesignSystem.driverHomeSoftWhiteBackground(),
                      SafeArea(
                        child: ListView(
                          padding: const EdgeInsets.all(AppConstants.paddingMedium),
                          children: [
                            HomeDesignSystem.frostLayer(
                              blur: 10,
                              radius: 20,
                              child: Container(
                                padding: const EdgeInsets.fromLTRB(14, 10, 10, 10),
                                decoration: _myRidesCardDecoration(
                                  radius: 20,
                                  elevated: false,
                                  borderAlpha: 0.58,
                                  borderWidth: 1.15,
                                ),
                                child: Row(
                                  children: [
                                    Material(
                                      color: Colors.transparent,
                                      child: InkWell(
                                        borderRadius: BorderRadius.circular(12),
                                        onTap: () => Navigator.maybePop(context),
                                        child: Container(
                                          width: 34,
                                          height: 34,
                                          decoration: BoxDecoration(
                                            shape: BoxShape.circle,
                                            color: const Color(0xFF1ED760)
                                                .withValues(alpha: 0.18),
                                            border: Border.all(
                                              color: const Color(0xFF22E082)
                                                  .withValues(alpha: 0.8),
                                              width: 1.2,
                                            ),
                                          ),
                                          child: const Icon(
                                            Icons.arrow_back_rounded,
                                            size: 18,
                                            color: Color(0xFF0B3D24),
                                          ),
                                        ),
                                      ),
                                    ),
                                    const SizedBox(width: 10),
                                    Expanded(
                                      child: Text(
                                        'Verification',
                                        style: GoogleFonts.inter(
                                          fontSize: 26,
                                          fontWeight: FontWeight.w900,
                                          color: _homeTextPrimary,
                                          letterSpacing: 0.1,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                            const SizedBox(height: 12),
                            _buildVerificationSectionCard(
                              theme: theme,
                              title: 'Face Verification',
                              icon: Icons.face_retouching_natural_outlined,
                              initiallyExpanded: true,
                              child: _buildFaceVerificationWidget(
                                theme,
                                isPassengerFlow,
                                isDriverFlow,
                              ),
                            ),
                            if (showIdentitySection)
                              _buildVerificationSectionCard(
                                theme: theme,
                                title: 'Identity Data Verification',
                                icon: Icons.badge_outlined,
                                child: _buildIdentityDataVerificationWidget(theme),
                              ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
    );
  }

  Widget _buildStatusCard(ThemeData theme) {
    final verifications =
        (_status?['verifications'] as Map?)?.cast<String, dynamic>() ?? {};
    final missingRequiredDocs = _missingRequiredDocumentTypes();
    final driverProblemDocs = _driverProblemDocumentTypes();
    final overallStatus = _status?['overall_status']?.toString() ??
        ((_status?['overall_verified'] == true)
            ? 'verified'
            : (verifications.isEmpty ? 'pending' : 'under_review'));
    final showCountdown =
        _processingSecondsRemaining > 0 && missingRequiredDocs.isEmpty;

    Color statusColor;
    IconData statusIcon;
    String statusText;

    if (showCountdown) {
      statusColor = AppColors.accent;
      statusIcon = Icons.hourglass_top_rounded;
      statusText = 'AI is Processing... $_processingSecondsRemaining';
    } else {
      switch (overallStatus) {
        case 'approved':
        case 'verified':
          statusColor = AppColors.success;
          statusIcon = Icons.verified_rounded;
          statusText = 'Verified';
          break;
        case 'under_review':
        case 'in_review':
          statusColor = AppColors.accent;
          statusIcon = Icons.hourglass_top_rounded;
          statusText = 'In Review';
          break;
        case 'processing':
        case 'pending':
          if (missingRequiredDocs.isNotEmpty) {
            statusColor = AppColors.info;
            statusIcon = Icons.assignment_late_rounded;
            statusText =
                'Waiting for ${_formatDocTypeList(missingRequiredDocs)}';
          } else {
            statusColor = AppColors.accent;
            statusIcon = Icons.hourglass_top_rounded;
            statusText = 'AI is Processing';
          }
          break;
        case 'rejected':
          statusColor = AppColors.error;
          statusIcon = Icons.cancel_rounded;
          if (driverProblemDocs.isNotEmpty) {
            statusText = 'Unverified: ${_formatDocTypeList(driverProblemDocs)}';
          } else {
            statusText = 'Unverified';
          }
          break;
        default:
          statusColor = AppColors.textSecondary;
          statusIcon = Icons.upload_rounded;
          statusText = 'Not Submitted';
      }
    }
    statusColor = _statusTextColor(statusText, statusColor);

    return HomeDesignSystem.frostLayer(
      blur: 8,
      radius: 16,
      child: Container(
      padding: const EdgeInsets.all(20),
      decoration: _innerDarkCardDecoration(radius: AppConstants.radiusLarge),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: statusColor.withValues(alpha: 0.15),
              shape: BoxShape.circle,
            ),
            child: Icon(statusIcon, color: statusColor, size: 32),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Verification Status',
                    style: GoogleFonts.inter(
                      fontSize: 13,
                      color: Colors.white.withValues(alpha: 0.78),
                      fontWeight: FontWeight.w600,
                    )),
                const SizedBox(height: 4),
                Text(statusText,
                    style: GoogleFonts.inter(
                        fontSize: 20,
                        fontWeight: FontWeight.w800,
                        color: statusColor)),
                if (overallStatus == 'rejected' &&
                    driverProblemDocs.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    'Please delete and re-upload ${_formatDocTypeList(driverProblemDocs)}.',
                    style: GoogleFonts.inter(
                      color: Colors.white.withValues(alpha: 0.78),
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
                if (_status?['score'] != null) ...[
                  const SizedBox(height: 4),
                  Text(
                      'Confidence Score: ${(_status!['score'] as num).toStringAsFixed(1)}%',
                      style: GoogleFonts.inter(
                        color: Colors.white.withValues(alpha: 0.78),
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      )),
                ],
              ],
            ),
          ),
        ],
      ),
    ));
  }

  Widget _docTile(String docType, ThemeData theme) {
    // Support both payload shapes:
    // 1) documents: [{document_type, status, ...}]
    // 2) verifications: {cnic: verified, driving_license: pending, ...}
    final docs = _status?['documents'] as List? ?? [];
    final doc = docs.cast<Map<String, dynamic>?>().firstWhere(
          (d) => d?['document_type'] == docType,
          orElse: () => null,
        );

    final verifications =
        (_status?['verifications'] as Map?)?.cast<String, dynamic>() ?? {};
    final missingRequiredDocs = _missingRequiredDocumentTypes();

    final mappedStatus = verifications[docType]?.toString();
    final hasUploadedStatus =
        mappedStatus != null && mappedStatus != 'not_uploaded';
    final isUploaded = doc != null || hasUploadedStatus;
    String docStatus =
        doc?['status']?.toString() ?? mappedStatus ?? 'not_uploaded';

    final overallStatus = _status?['overall_status']?.toString() ?? '';
    final driverProblemDocs = _driverProblemDocumentTypes();
    final isSelfieRootCauseForDriver = _isDriverVerificationFlow() &&
        overallStatus == 'rejected' &&
        driverProblemDocs.length == 1 &&
        driverProblemDocs.first == 'selfie';

    if (isSelfieRootCauseForDriver) {
      if (docType == 'selfie') {
        docStatus = 'rejected';
      } else if (docType == 'cnic' || docType == 'driving_license') {
        docStatus = 'verified';
      }
    }

    final isWaitingForMissingDocs =
        (docStatus == 'processing' || docStatus == 'pending') &&
            isUploaded &&
            missingRequiredDocs.isNotEmpty &&
            !missingRequiredDocs.contains(docType);

    final showCountdownForDoc = _processingSecondsRemaining > 0 &&
        missingRequiredDocs.isEmpty &&
        isUploaded;

    if (showCountdownForDoc) {
      docStatus = 'processing';
    }

    Color statusColor;
    String statusText;
    switch (docStatus) {
      case 'approved':
      case 'verified':
        statusColor = Colors.white;
        statusText = 'Approved';
        break;
      case 'processing':
        if (isWaitingForMissingDocs) {
          statusColor = AppColors.info;
          statusText = 'Waiting for ${_formatDocTypeList(missingRequiredDocs)}';
        } else {
          statusColor = AppColors.accent;
          statusText = 'AI is Processing';
        }
        break;
      case 'pending':
        if (isWaitingForMissingDocs) {
          statusColor = AppColors.info;
          statusText = 'Waiting for ${_formatDocTypeList(missingRequiredDocs)}';
          break;
        }
        statusColor = AppColors.accent;
        statusText = 'In Review';
        break;
      case 'under_review':
      case 'in_review':
        statusColor = AppColors.accent;
        statusText = 'In Review';
        break;
      case 'rejected':
        statusColor = AppColors.error;
        statusText = 'Unverified';
        break;
      case 'expired':
        statusColor = AppColors.error;
        statusText = 'Expired';
        break;
      default:
        statusColor = AppColors.error;
        statusText = 'Not Uploaded';
    }
    statusColor = _statusTextColor(statusText, statusColor);

    final modeConfig = (_status?['mode'] as Map?)?.cast<String, dynamic>() ??
        <String, dynamic>{};
    final allowReuploadAlways = modeConfig['allow_reupload_always'] == true;
    final isDriverSelfieDoc =
        _isDriverVerificationFlow() && docType == 'selfie';
    final isCountdownActive =
        _processingSecondsRemaining > 0 && missingRequiredDocs.isEmpty;

    final canUpload = allowReuploadAlways ||
        ((!isCountdownActive) &&
            (!isUploaded || docStatus == 'rejected' || docStatus == 'expired'));
    final canDelete = isUploaded && !isDriverSelfieDoc;

    return HomeDesignSystem.frostLayer(
      blur: 8,
      radius: 14,
      child: Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: _innerDarkCardDecoration(radius: 14),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: statusColor.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(AppConstants.radiusSmall),
            ),
            child: Icon(_docTypeIcon(docType), color: statusColor, size: 22),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _docTypeLabel(docType),
                  style: GoogleFonts.inter(
                    color: Colors.white,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  statusText,
                  style: GoogleFonts.inter(
                    color: statusColor,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
          if (canUpload || canDelete)
            Wrap(
              spacing: 6,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                if (canUpload)
                  OutlinedButton(
                    onPressed: () => _uploadDocument(docType),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.primary,
                      disabledForegroundColor: AppColors.primary,
                      side: const BorderSide(color: AppColors.primary),
                      textStyle: GoogleFonts.inter(
                        fontWeight: FontWeight.w700,
                        fontSize: 13,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius:
                            BorderRadius.circular(AppConstants.radiusSmall),
                      ),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 14, vertical: 6),
                    ),
                    child: Text(isUploaded ? 'Re-upload' : 'Upload',
                        style: const TextStyle(fontSize: 13)),
                  ),
                if (canDelete)
                  IconButton(
                    tooltip: 'Delete image',
                    onPressed: () => _deleteDocument(docType),
                    style: IconButton.styleFrom(
                      foregroundColor: AppColors.error,
                    ),
                    icon: const Icon(Icons.delete_outline_rounded),
                  ),
              ],
            )
          else
            Icon(
              (docStatus == 'approved' || docStatus == 'verified')
                  ? Icons.check_circle_rounded
                  : Icons.hourglass_top_rounded,
              color: statusColor,
            ),
        ],
      ),
    ));
  }
}
// === VERIFICATION FUNCTIONALITY END ===
