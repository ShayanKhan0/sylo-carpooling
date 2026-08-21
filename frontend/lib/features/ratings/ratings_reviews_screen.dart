import 'dart:convert';

import 'package:flutter/material.dart';

import '../../core/constants/app_constants.dart';
import '../../core/models/rating_model.dart';
import '../../core/services/auth_service.dart';
import '../../core/services/rating_service.dart';
import '../../core/theme/app_colors.dart';

class RatingsReviewsScreen extends StatefulWidget {
  const RatingsReviewsScreen({super.key});

  @override
  State<RatingsReviewsScreen> createState() => _RatingsReviewsScreenState();
}

class _RatingsReviewsScreenState extends State<RatingsReviewsScreen> {
  final _ratingService = RatingService();

  bool _isLoading = true;
  String? _error;
  RatingStats? _stats;
  List<Rating> _ratings = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final userId = await AuthService().getUserId();
      if (userId == null || userId.isEmpty) {
        setState(() {
          _error = 'Could not read current user.';
          _isLoading = false;
        });
        return;
      }

      final stats = await _ratingService.getStats(userId);
      final listRes = await _ratingService.getUserRatings(userId, pageSize: 25);

      if (!mounted) return;
      setState(() {
        _stats = stats;
        _ratings = listRes.ratings;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'Failed to load ratings.';
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      appBar: AppBar(
        title: const Text('Ratings & Reviews'),
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(_error!, style: const TextStyle(color: AppColors.error)),
            const SizedBox(height: 12),
            ElevatedButton(onPressed: _load, child: const Text('Retry')),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _buildStatsCard(),
          const SizedBox(height: 16),
          Text(
            'Ratings Received',
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            ),
          ),
          const SizedBox(height: 10),
          if (_ratings.isEmpty)
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.border),
              ),
              child: const Text('No ratings yet.'),
            )
          else
            ..._ratings.map(_buildReviewCard),
        ],
      ),
    );
  }

  Widget _buildStatsCard() {
    final stats = _stats;
    if (stats == null) return const SizedBox.shrink();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.star_rounded, color: AppColors.warning),
              const SizedBox(width: 8),
              Text(
                stats.weightedAverage.toStringAsFixed(1),
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary,
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '(${stats.totalRatings} ratings)',
                style: TextStyle(color: AppColors.textSecondary),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _metricChip('5★', stats.fiveStar),
              _metricChip('4★', stats.fourStar),
              _metricChip('3★', stats.threeStar),
              _metricChip('2★', stats.twoStar),
              _metricChip('1★', stats.oneStar),
            ],
          ),
        ],
      ),
    );
  }

  Widget _metricChip(String label, int value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.backgroundLight,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: AppColors.border),
      ),
      child: Text('$label: $value'),
    );
  }

  Widget _buildReviewCard(Rating r) {
    final reviewerName = (r.fromUserName ?? '').trim().isNotEmpty
        ? r.fromUserName!.trim()
        : 'Anonymous User';
    final initials = _initials(reviewerName);
    final commentText =
        (r.comment ?? '').trim().isNotEmpty ? r.comment!.trim() : 'No comment';
    final provider = _profileImageProvider(r.fromUserProfilePhoto);
    final stars = r.rating.clamp(0, 5);

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              CircleAvatar(
                radius: 22,
                backgroundColor: AppColors.primary.withValues(alpha: 0.12),
                backgroundImage: provider,
                child: provider == null
                    ? Text(
                        initials,
                        style: const TextStyle(
                          color: AppColors.primary,
                          fontWeight: FontWeight.bold,
                          fontSize: 14,
                        ),
                      )
                    : null,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      reviewerName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 14,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _minutesAgoLabel(r.createdAt),
                      style: TextStyle(
                        color: AppColors.textSecondary,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: AppColors.warning.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(
                      Icons.star_rounded,
                      color: AppColors.warning,
                      size: 16,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      stars.toDouble().toStringAsFixed(1),
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        color: AppColors.textPrimary,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: List.generate(5, (index) {
              final filled = index < stars;
              return Icon(
                filled ? Icons.star_rounded : Icons.star_border_rounded,
                size: 18,
                color: filled ? AppColors.warning : AppColors.border,
              );
            }),
          ),
          const SizedBox(height: 10),
          Text(
            commentText,
            style: TextStyle(
              color: AppColors.textPrimary,
              fontSize: 13,
              fontStyle: commentText == 'No comment'
                  ? FontStyle.italic
                  : FontStyle.normal,
            ),
          ),
        ],
      ),
    );
  }

  String _minutesAgoLabel(String? rawDateTime) {
    if (rawDateTime == null || rawDateTime.trim().isEmpty) {
      return 'Unknown time';
    }

    final parsed = DateTime.tryParse(rawDateTime.trim());
    if (parsed == null) {
      return 'Unknown time';
    }

    final local = parsed.isUtc ? parsed.toLocal() : parsed;
    final diffMinutes = DateTime.now().difference(local).inMinutes;

    if (diffMinutes <= 0) {
      return 'Just now';
    }

    return '$diffMinutes min ago';
  }

  String _initials(String name) {
    final parts = name
        .trim()
        .split(RegExp(r'\s+'))
        .where((part) => part.isNotEmpty)
        .toList();

    if (parts.isEmpty) {
      return '?';
    }

    if (parts.length == 1) {
      return parts.first.substring(0, 1).toUpperCase();
    }

    final first = parts.first.substring(0, 1).toUpperCase();
    final last = parts.last.substring(0, 1).toUpperCase();
    return '$first$last';
  }

  String _apiOrigin() {
    final parsed = Uri.tryParse(AppConstants.baseUrl);
    if (parsed == null || !parsed.hasScheme || parsed.host.isEmpty) {
      return '';
    }

    final portPart = parsed.hasPort ? ':${parsed.port}' : '';
    return '${parsed.scheme}://${parsed.host}$portPart';
  }

  String? _resolveProfilePhotoUrl(String? rawPhoto) {
    final value = (rawPhoto ?? '').trim();
    if (value.isEmpty || value.startsWith('data:image/')) {
      return null;
    }

    final normalized = value.replaceAll('\\', '/');
    if (normalized.startsWith('http://') || normalized.startsWith('https://')) {
      return normalized;
    }

    final origin = _apiOrigin();
    if (origin.isEmpty) {
      return null;
    }

    if (normalized.startsWith('/')) {
      return '$origin$normalized';
    }
    if (normalized.startsWith('static/')) {
      return '$origin/$normalized';
    }
    if (normalized.startsWith('uploads/')) {
      return '$origin/static/$normalized';
    }

    return '$origin/$normalized';
  }

  ImageProvider? _profileImageProvider(String? rawPhoto) {
    final value = (rawPhoto ?? '').trim();
    if (value.isEmpty) {
      return null;
    }

    if (value.startsWith('data:image/')) {
      try {
        final parts = value.split(',');
        if (parts.length >= 2) {
          return MemoryImage(base64Decode(parts[1]));
        }
      } catch (_) {
        return null;
      }
      return null;
    }

    final photoUrl = _resolveProfilePhotoUrl(value);
    if (photoUrl == null || photoUrl.isEmpty) {
      return null;
    }

    return NetworkImage(photoUrl);
  }
}
