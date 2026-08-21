import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../core/theme/app_colors.dart';
import '../../core/constants/app_constants.dart';
import '../auth/auth_design_tokens.dart';

/// Consistent loading indicator
class SyloLoader extends StatelessWidget {
  final String? message;
  const SyloLoader({super.key, this.message});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(
            width: 40,
            height: 40,
            child: CircularProgressIndicator(
              strokeWidth: 3,
              color: AppColors.primary,
            ),
          ),
          if (message != null) ...[
            const SizedBox(height: 16),
            Text(message!,
                style: TextStyle(color: AppColors.textSecondary, fontSize: 14)),
          ],
        ],
      ),
    );
  }
}

/// Empty state placeholder
class SyloEmpty extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final String? actionLabel;
  final VoidCallback? onAction;

  const SyloEmpty({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    this.actionLabel,
    this.onAction,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: AppColors.primary.withValues(alpha: 0.10),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, size: 56, color: AppColors.primaryDark),
          ),
          const SizedBox(height: 20),
          Text(title,
              style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textPrimary)),
          const SizedBox(height: 8),
          Text(subtitle,
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.textSecondary, fontSize: 14)),
          if (actionLabel != null && onAction != null) ...[
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: onAction,
              icon: const Icon(Icons.refresh),
              label: Text(actionLabel!),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.primary,
                foregroundColor: Colors.white,
                padding:
                    const EdgeInsets.symmetric(horizontal: 28, vertical: 14),
                shape: RoundedRectangleBorder(
                    borderRadius:
                        BorderRadius.circular(AppConstants.radiusLarge)),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Error state with retry
class SyloError extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;

  const SyloError({
    super.key,
    required this.message,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: AppColors.error.withValues(alpha: 0.10),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.error_outline,
                size: 56, color: AppColors.error),
          ),
          const SizedBox(height: 20),
          Text('Something went wrong',
              style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textPrimary)),
          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 40),
            child: Text(message,
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.textSecondary, fontSize: 14)),
          ),
          const SizedBox(height: 24),
          ElevatedButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh),
            label: const Text('Try Again'),
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.primary,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14),
              shape: RoundedRectangleBorder(
                  borderRadius:
                      BorderRadius.circular(AppConstants.radiusLarge)),
            ),
          ),
        ],
      ),
    );
  }
}

/// Ride card widget used on both dashboards
class RideCard extends StatelessWidget {
  final String from;
  final String to;
  final String subtitle;
  final String status;
  final Color statusColor;
  final String? price;
  final double? carbonSavedKg;
  final VoidCallback? onTap;

  const RideCard({
    super.key,
    required this.from,
    required this.to,
    required this.subtitle,
    required this.status,
    required this.statusColor,
    this.price,
    this.carbonSavedKg,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              AuthDesignTokens.slate800.withValues(alpha: 0.76),
              AuthDesignTokens.midnight.withValues(alpha: 0.82),
            ],
          ),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: AuthDesignTokens.white.withValues(alpha: 0.14),
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.24),
              blurRadius: 18,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color:
                            AuthDesignTokens.routeBlue.withValues(alpha: 0.14),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Icon(
                        Icons.directions_car_rounded,
                        color: AuthDesignTokens.routeBlue,
                        size: 20,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          subtitle,
                          style: GoogleFonts.inter(
                            color: AuthDesignTokens.white.withValues(
                              alpha: 0.76,
                            ),
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        if (price != null)
                          Text(
                            price!,
                            style: GoogleFonts.inter(
                              fontWeight: FontWeight.w800,
                              fontSize: 16,
                              color: AppColors.success,
                            ),
                          ),
                      ],
                    ),
                  ],
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: statusColor.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: statusColor.withValues(alpha: 0.3),
                    ),
                  ),
                  child: Text(
                    status.toUpperCase(),
                    style: GoogleFonts.inter(
                      color: statusColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 10,
                      letterSpacing: 0.5,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Column(
                  children: [
                    const Icon(Icons.circle,
                        size: 10, color: AuthDesignTokens.routeBlue),
                    Container(
                      width: 2,
                      height: 20,
                      color: AuthDesignTokens.white.withValues(alpha: 0.22),
                    ),
                    const Icon(Icons.location_on_rounded,
                        size: 12, color: AuthDesignTokens.brandAction),
                  ],
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        from,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: GoogleFonts.inter(
                          fontWeight: FontWeight.w700,
                          fontSize: 14,
                          color: AuthDesignTokens.white,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(
                        to,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: GoogleFonts.inter(
                          fontWeight: FontWeight.w700,
                          fontSize: 14,
                          color: AuthDesignTokens.white,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            if (carbonSavedKg != null && carbonSavedKg! > 0) ...[
              const SizedBox(height: 16),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                decoration: BoxDecoration(
                  color: AppColors.success.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: AppColors.success.withValues(alpha: 0.3),
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.eco_rounded,
                        size: 14, color: AppColors.success),
                    const SizedBox(width: 6),
                    Text(
                      '${carbonSavedKg!.toStringAsFixed(1)} kg CO\u2082 saved on this trip',
                      style: GoogleFonts.inter(
                        color: AppColors.success,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Stat tile used on dashboard home tabs
class StatTile extends StatelessWidget {
  final IconData icon;
  final String value;
  final String label;
  final Color color;

  const StatTile({
    super.key,
    required this.icon,
    required this.value,
    required this.label,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppConstants.paddingMedium),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AuthDesignTokens.slate800.withValues(alpha: 0.78),
            AuthDesignTokens.midnight.withValues(alpha: 0.84),
          ],
        ),
        borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
        border: Border.all(
          color: AuthDesignTokens.white.withValues(alpha: 0.4),
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.2),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.2),
              shape: BoxShape.circle,
              border: Border.all(color: color.withValues(alpha: 0.45)),
            ),
            child: Icon(icon, color: color, size: 20),
          ),
          const SizedBox(height: 8),
          Text(value,
              style: GoogleFonts.inter(
                fontSize: 19,
                fontWeight: FontWeight.w800,
                color: AuthDesignTokens.white,
              )),
          const SizedBox(height: 4),
          Text(label,
              style: GoogleFonts.inter(
                color: AuthDesignTokens.white.withValues(alpha: 0.82),
                fontSize: 11.5,
                fontWeight: FontWeight.w600,
              )),
        ],
      ),
    );
  }
}
