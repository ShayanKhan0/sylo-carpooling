import 'api_client.dart';

/// Service for AI ride clustering and matching endpoints.
class MatchingService {
  final ApiClient _client = ApiClient();

  // ── Trigger manual clustering run ────────────────────────────────────────
  Future<ClusterRunSummary> triggerClustering({
    int timeWindowMinutes = 60,
    double maxPickupKm = 2.0,
    double maxDropKm = 8.0,
    double maxTimeMin = 20.0,
    double dbscanEps = 1.0,
    int dbscanMinSamples = 2,
    bool dryRun = false,
  }) async {
    final resp = await _client.post(
      '/api/v2/matching/cluster/trigger'.replaceFirst('/api/v1', ''),
      data: {
        'time_window_minutes': timeWindowMinutes,
        'max_pickup_km': maxPickupKm,
        'max_drop_km': maxDropKm,
        'max_time_min': maxTimeMin,
        'dbscan_eps': dbscanEps,
        'dbscan_min_samples': dbscanMinSamples,
        'dry_run': dryRun,
      },
    );
    final data = resp.data['data'] as Map<String, dynamic>;
    return ClusterRunSummary.fromJson(data);
  }

  // ── Get last run status ───────────────────────────────────────────────────
  Future<Map<String, dynamic>?> getLastRunStatus() async {
    try {
      final resp = await _client.get('/api/v2/matching/cluster/status');
      return resp.data['data'] as Map<String, dynamic>?;
    } catch (_) {
      return null;
    }
  }

  // ── Get cluster status for a specific ride request ────────────────────────
  Future<RideRequestClusterStatus> getRequestClusterStatus(
      String requestId) async {
    final resp = await _client.get(
      '/api/v2/matching/cluster/request/$requestId',
    );
    final data = resp.data['data'] as Map<String, dynamic>;
    return RideRequestClusterStatus.fromJson(data);
  }

  // ── Get algorithm explanation ─────────────────────────────────────────────
  Future<Map<String, dynamic>> getAlgorithmExplanation() async {
    final resp = await _client.get('/api/v2/matching/cluster/explain');
    return resp.data['data'] as Map<String, dynamic>;
  }
}

// ── Data Models ──────────────────────────────────────────────────────────────

class ClusterRunSummary {
  final String runId;
  final String algorithmUsed;
  final int totalRequestsProcessed;
  final int totalClustersFormed;
  final int groupedPassengers;
  final int soloPassengers;
  final double matchRatePct;
  final double elapsedMs;
  final String status;
  final bool dryRun;
  final List<RideClusterInfo> clusters;
  final String? error;

  const ClusterRunSummary({
    required this.runId,
    required this.algorithmUsed,
    required this.totalRequestsProcessed,
    required this.totalClustersFormed,
    required this.groupedPassengers,
    required this.soloPassengers,
    required this.matchRatePct,
    required this.elapsedMs,
    required this.status,
    required this.dryRun,
    required this.clusters,
    this.error,
  });

  factory ClusterRunSummary.fromJson(Map<String, dynamic> j) =>
      ClusterRunSummary(
        runId: j['run_id'] as String? ?? '',
        algorithmUsed: j['algorithm_used'] as String? ?? '',
        totalRequestsProcessed:
            (j['total_requests_processed'] as num?)?.toInt() ?? 0,
        totalClustersFormed:
            (j['total_clusters_formed'] as num?)?.toInt() ?? 0,
        groupedPassengers: (j['grouped_passengers'] as num?)?.toInt() ?? 0,
        soloPassengers: (j['solo_passengers'] as num?)?.toInt() ?? 0,
        matchRatePct: (j['match_rate_pct'] as num?)?.toDouble() ?? 0.0,
        elapsedMs: (j['elapsed_ms'] as num?)?.toDouble() ?? 0.0,
        status: j['status'] as String? ?? '',
        dryRun: j['dry_run'] as bool? ?? false,
        clusters: ((j['clusters'] as List?) ?? [])
            .map((e) => RideClusterInfo.fromJson(e as Map<String, dynamic>))
            .toList(),
        error: j['error'] as String?,
      );
}

class RideClusterInfo {
  final int clusterLabel;
  final int size;
  final int totalSeatsNeeded;
  final bool isSingleton;
  final double centroidPickupLat;
  final double centroidPickupLng;
  final String? assignedDriverId;
  final String? createdRideId;
  final DateTime? departureWindowStart;
  final DateTime? departureWindowEnd;

  const RideClusterInfo({
    required this.clusterLabel,
    required this.size,
    required this.totalSeatsNeeded,
    required this.isSingleton,
    required this.centroidPickupLat,
    required this.centroidPickupLng,
    this.assignedDriverId,
    this.createdRideId,
    this.departureWindowStart,
    this.departureWindowEnd,
  });

  factory RideClusterInfo.fromJson(Map<String, dynamic> j) => RideClusterInfo(
        clusterLabel: (j['cluster_label'] as num?)?.toInt() ?? 0,
        size: (j['size'] as num?)?.toInt() ?? 0,
        totalSeatsNeeded: (j['total_seats_needed'] as num?)?.toInt() ?? 0,
        isSingleton: j['is_singleton'] as bool? ?? false,
        centroidPickupLat:
            (j['centroid_pickup_lat'] as num?)?.toDouble() ?? 0.0,
        centroidPickupLng:
            (j['centroid_pickup_lng'] as num?)?.toDouble() ?? 0.0,
        assignedDriverId: j['assigned_driver_id'] as String?,
        createdRideId: j['created_ride_id'] as String?,
        departureWindowStart: j['departure_window_start'] != null
            ? DateTime.tryParse(j['departure_window_start'] as String)
            : null,
        departureWindowEnd: j['departure_window_end'] != null
            ? DateTime.tryParse(j['departure_window_end'] as String)
            : null,
      );
}

class RideRequestClusterStatus {
  final String requestId;
  final String status;       // pending | matched | cancelled | expired
  final int? clusterLabel;
  final int? clusterSize;
  final String? assignedDriverId;
  final String? matchedRideId;
  final double? estimatedFare;
  final String message;

  const RideRequestClusterStatus({
    required this.requestId,
    required this.status,
    this.clusterLabel,
    this.clusterSize,
    this.assignedDriverId,
    this.matchedRideId,
    this.estimatedFare,
    required this.message,
  });

  factory RideRequestClusterStatus.fromJson(Map<String, dynamic> j) =>
      RideRequestClusterStatus(
        requestId: j['request_id'] as String? ?? '',
        status: j['status'] as String? ?? '',
        clusterLabel: (j['cluster_label'] as num?)?.toInt(),
        clusterSize: (j['cluster_size'] as num?)?.toInt(),
        assignedDriverId: j['assigned_driver_id'] as String?,
        matchedRideId: j['matched_ride_id'] as String?,
        estimatedFare: (j['estimated_fare'] as num?)?.toDouble(),
        message: j['message'] as String? ?? '',
      );

  bool get isMatched => status == 'matched';
  bool get isPending => status == 'pending';
}
