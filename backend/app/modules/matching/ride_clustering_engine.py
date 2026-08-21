"""
Ride Clustering Engine — AI-Powered Carpooling Group Formation
==============================================================

This module implements REAL machine-learning-based ride clustering for the
Sylo Smart Carpooling system.

Architecture Decision: WHY DBSCAN?
-----------------------------------
Carpooling clustering is fundamentally a *density-based* problem:
  - We do NOT know how many groups will form at any time (unknown k → K-Means fails)
  - Rides that cannot be grouped (outliers) must be handled as solo trips (noise points)
  - Clusters are geographically irregular — DBSCAN handles arbitrary shapes

Algorithm: DBSCAN with a Custom Composite Metric
-------------------------------------------------
Standard DBSCAN uses Euclidean distance on coordinates. We go further:

  ride_distance(a, b) = sqrt(
      (haversine_pickup(a,b) / MAX_PICKUP_KM)²   ← pickup proximity
    + (haversine_dropoff(a,b) / MAX_DROP_KM)²     ← destination alignment
    + (|time_a - time_b| / MAX_TIME_MIN)²          ← time compatibility
  )

  This combines THREE physical meanings into one distance:
    1. How close are the pickup points?       (most important)
    2. Are they heading in the same direction? (moderate importance)
    3. Do they want to leave at similar times? (important for scheduling)

  DBSCAN eps is set in this normalized composite space.
  eps=1.0 groups rides that are simultaneously:
    - within ~1.4km pickup radius
    - heading to destinations within ~5.7km of each other
    - departing within ~14 minutes

Hyper-Parameters (tunable via config):
  MAX_PICKUP_KM  = 2.0  km   (pickup proximity threshold for grouping)
  MAX_DROP_KM    = 8.0  km   (dropoff direction similarity threshold)
  MAX_TIME_MIN   = 20.0 min  (departure time window)
  MIN_SAMPLES    = 2         (min 2 users to form a carpool group)
  DBSCAN_EPS     = 1.0       (in normalized composite space)

Fallback Algorithm: K-Means with Elbow Method
----------------------------------------------
When DBSCAN produces too many noise points (> 50% of requests), the engine
falls back to K-Means with the elbow method to determine optimal k.

Authors: M. Mobeen Shoukat Ch & M. Shayan Khan (FYP — Sylo Carpooling)
Date: March 2026
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  HYPER-PARAMETER DEFAULTS  (override via ClusteringConfig)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MAX_PICKUP_KM: float = 2.0   # Rides within this range may share a pickup
DEFAULT_MAX_DROP_KM: float = 8.0     # Dropoff direction tolerance
DEFAULT_MAX_TIME_MIN: float = 20.0   # Departure window tolerance in minutes
DEFAULT_EPS: float = 1.0             # DBSCAN epsilon in composite normalized space
DEFAULT_MIN_SAMPLES: int = 2         # Minimum rides per cluster (2 = pair carpool)
DEFAULT_MAX_CLUSTER_SEATS: int = 6   # Max passengers per cluster (vehicle capacity)
DEFAULT_MAX_SEATS_PER_VEHICLE: int = 4   # Default vehicle capacity if unknown


# ─────────────────────────────────────────────────────────────────────────────
#  DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RideFeature:
    """
    Structured representation of one passenger ride request.

    All fields come directly from the `ride_requests` database table.
    """
    request_id: UUID
    passenger_id: UUID
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float
    departure_time: datetime       # Actual datetime — converted to minutes internally
    seats_needed: int
    max_budget: Optional[float] = None
    origin_address: str = ""
    destination_address: str = ""

    def departure_minutes(self) -> float:
        """Convert departure time to minutes since midnight (UTC) for vectorization."""
        return self.departure_time.hour * 60.0 + self.departure_time.minute + self.departure_time.second / 60.0


@dataclass
class RideCluster:
    """
    One output cluster produced by the clustering engine.

    A cluster represents a group of passengers who should share a vehicle.
    """
    cluster_label: int                     # DBSCAN label (≥0), or -1 if noise
    member_requests: List[RideFeature]     # Rides in this cluster
    centroid_pickup_lat: float = 0.0
    centroid_pickup_lng: float = 0.0
    centroid_dropoff_lat: float = 0.0
    centroid_dropoff_lng: float = 0.0
    departure_window_start: Optional[datetime] = None
    departure_window_end: Optional[datetime] = None
    total_seats_needed: int = 0
    is_singleton: bool = False             # True if only one passenger (no grouping)
    split_index: int = 0                   # For split clusters (overflow handling)

    @property
    def size(self) -> int:
        return len(self.member_requests)

    @property
    def request_ids(self) -> List[UUID]:
        return [r.request_id for r in self.member_requests]

    @property
    def passenger_ids(self) -> List[UUID]:
        return [r.passenger_id for r in self.member_requests]


@dataclass
class ClusteringConfig:
    """Tunable hyper-parameters for the clustering engine."""
    max_pickup_km: float = DEFAULT_MAX_PICKUP_KM
    max_drop_km: float = DEFAULT_MAX_DROP_KM
    max_time_min: float = DEFAULT_MAX_TIME_MIN
    dbscan_eps: float = DEFAULT_EPS
    dbscan_min_samples: int = DEFAULT_MIN_SAMPLES
    max_cluster_seats: int = DEFAULT_MAX_CLUSTER_SEATS
    max_seats_per_vehicle: int = DEFAULT_MAX_SEATS_PER_VEHICLE
    # Fallback to K-Means if DBSCAN noise ratio exceeds this threshold
    noise_fallback_threshold: float = 0.5


@dataclass
class ClusteringResult:
    """Complete output of one clustering run."""
    clusters: List[RideCluster]
    noise_requests: List[RideFeature]      # Solo passengers (no match found)
    algorithm_used: str = "dbscan"
    total_requests: int = 0
    total_clusters: int = 0
    noise_count: int = 0
    run_at: datetime = field(default_factory=datetime.utcnow)
    elapsed_ms: float = 0.0

    @property
    def match_rate(self) -> float:
        """Fraction of passengers successfully grouped."""
        if self.total_requests == 0:
            return 0.0
        grouped = sum(c.size for c in self.clusters if not c.is_singleton)
        return grouped / self.total_requests


# ─────────────────────────────────────────────────────────────────────────────
#  HAVERSINE DISTANCE  (pure Python — avoids dependency for inner loop)
# ─────────────────────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Accurate great-circle distance between two GPS points.

    Uses the Haversine formula — standard for sub-100km distances.
    Accuracy is well within 0.1% for distances relevant to carpooling.
    """
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOM DBSCAN DISTANCE METRIC
# ─────────────────────────────────────────────────────────────────────────────

def _make_ride_distance_fn(config: ClusteringConfig):
    """
    Factory that creates a closure capturing the config.

    Returned function signature: (a, b) -> float
    where a, b are numpy rows with shape (5,):
      [pickup_lat, pickup_lng, dropoff_lat, dropoff_lng, departure_minutes]

    Distance formula (Euclidean in normalized composite space):

        d = sqrt(
              (pickup_km / MAX_PICKUP_KM)²
            + (dropoff_km / MAX_DROP_KM)²
            + (|Δtime_min| / MAX_TIME_MIN)²
        )

    Geometric interpretation:
      - d < 1.0  →  rides are compatible for carpooling
      - d ≥ 1.0  →  rides are incompatible in at least one dimension
    """
    max_p = config.max_pickup_km
    max_d = config.max_drop_km
    max_t = config.max_time_min

    def ride_distance(a: np.ndarray, b: np.ndarray) -> float:
        pickup_km = _haversine_km(a[0], a[1], b[0], b[1])
        drop_km = _haversine_km(a[2], a[3], b[2], b[3])
        time_diff = abs(a[4] - b[4])

        # Normalize each dimension
        p_score = pickup_km / max_p
        d_score = drop_km / max_d
        t_score = time_diff / max_t

        # Euclidean distance in normalized composite space
        return math.sqrt(p_score ** 2 + d_score ** 2 + t_score ** 2)

    return ride_distance


# ─────────────────────────────────────────────────────────────────────────────
#  FEATURE MATRIX BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_feature_matrix(rides: List[RideFeature]) -> np.ndarray:
    """
    Convert list of RideFeature objects into a 2D numpy array.

    Shape: (N, 5)
    Columns: [pickup_lat, pickup_lng, dropoff_lat, dropoff_lng, departure_minutes]

    Note:
      - Coordinates are left in raw degrees (the distance metric handles km conversion)
      - Departure time is converted to minutes since midnight for comparability
      - This raw representation is used directly by the custom metric function
    """
    rows = []
    for r in rides:
        rows.append([
            r.pickup_lat,
            r.pickup_lng,
            r.dropoff_lat,
            r.dropoff_lng,
            r.departure_minutes(),
        ])
    return np.array(rows, dtype=np.float64)


# ─────────────────────────────────────────────────────────────────────────────
#  DBSCAN CLUSTERING  (primary algorithm)
# ─────────────────────────────────────────────────────────────────────────────

def _run_dbscan(
    feature_matrix: np.ndarray,
    config: ClusteringConfig,
) -> np.ndarray:
    """
    Run DBSCAN with the composite ride distance metric.

    Returns:
        labels array (length N). Label -1 = noise (solo passenger).

    DBSCAN parameters:
        eps = config.dbscan_eps (default 1.0 in composite normalized space)
        min_samples = config.dbscan_min_samples (default 2 → pairs allowed)
        metric = 'precomputed' (we pass the distance matrix)

    Why precomputed distance matrix:
        Sklearn DBSCAN with metric='precomputed' allows our custom haversine-based
        metric. We build the N×N matrix once — O(N²) which is acceptable for
        N < 5000 requests in a 5-minute batch window.
    """
    from sklearn.cluster import DBSCAN

    n = len(feature_matrix)

    # Build precomputed distance matrix using our custom metric
    dist_fn = _make_ride_distance_fn(config)
    dist_matrix = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(i + 1, n):
            d = dist_fn(feature_matrix[i], feature_matrix[j])
            dist_matrix[i, j] = d
            dist_matrix[j, i] = d

    # Run DBSCAN on the precomputed distance matrix
    dbscan = DBSCAN(
        eps=config.dbscan_eps,
        min_samples=config.dbscan_min_samples,
        metric="precomputed",
        algorithm="brute",   # Required when metric='precomputed'
        n_jobs=-1,           # Use all CPU cores
    )
    labels = dbscan.fit_predict(dist_matrix)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise = np.sum(labels == -1)
    logger.info(
        f"DBSCAN complete: {n_clusters} clusters, {n_noise} noise points "
        f"from {n} ride requests (eps={config.dbscan_eps}, "
        f"min_samples={config.dbscan_min_samples})"
    )
    return labels


# ─────────────────────────────────────────────────────────────────────────────
#  K-MEANS FALLBACK  (used when DBSCAN noise ratio is too high)
# ─────────────────────────────────────────────────────────────────────────────

def _optimal_k_elbow(feature_matrix: np.ndarray, max_k: int = 10) -> int:
    """
    Determine optimal number of clusters using the Elbow Method.

    Fits K-Means for k = 2..max_k and finds the 'elbow' where inertia
    improvement starts to diminish.

    Returns optimal k (minimum 2).
    """
    from sklearn.cluster import KMeans

    n = len(feature_matrix)
    max_k = min(max_k, n - 1, 15)
    if max_k < 2:
        return 1

    inertias: List[float] = []
    k_values = range(2, max_k + 1)

    for k in k_values:
        km = KMeans(n_clusters=k, random_state=42, n_init=5, max_iter=100)
        km.fit(feature_matrix)
        inertias.append(km.inertia_)

    if len(inertias) < 2:
        return 2

    # Elbow detection: find k where second derivative of inertia is maximum
    deltas = np.diff(inertias)
    second_deriv = np.diff(deltas)
    if len(second_deriv) > 0:
        elbow_idx = np.argmax(second_deriv)
        optimal_k = list(k_values)[elbow_idx + 1]
    else:
        optimal_k = 2

    logger.info(f"Elbow method selected k={optimal_k} from {n} samples")
    return optimal_k


def _run_kmeans_normalized(
    feature_matrix: np.ndarray,
    config: ClusteringConfig,
) -> np.ndarray:
    """
    K-Means fallback on normalized feature matrix.

    Normalizes coordinates using city-level min-max scaling before clustering
    so that lat/lng dimensions don't dominate over time.
    """
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import MinMaxScaler

    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(feature_matrix)

    k = _optimal_k_elbow(X_scaled)
    km = KMeans(n_clusters=k, random_state=42, n_init=10, max_iter=300)
    labels = km.fit_predict(X_scaled)

    n_clusters = len(set(labels))
    logger.info(f"K-Means fallback: {n_clusters} clusters from {len(feature_matrix)} requests")
    return labels


# ─────────────────────────────────────────────────────────────────────────────
#  CLUSTER POST-PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def _build_clusters_from_labels(
    rides: List[RideFeature],
    labels: np.ndarray,
    config: ClusteringConfig,
    algorithm: str,
) -> Tuple[List[RideCluster], List[RideFeature]]:
    """
    Convert raw DBSCAN/K-Means labels into structured RideCluster objects.

    Also splits clusters that exceed vehicle capacity.

    Returns:
        (clusters, noise_requests)
        - clusters: All valid carpooling groups (possibly split)
        - noise_requests: Solo passengers (label -1 from DBSCAN)
    """
    # Group rides by label
    label_to_rides: Dict[int, List[RideFeature]] = {}
    for ride, label in zip(rides, labels):
        label_to_rides.setdefault(int(label), []).append(ride)

    clusters: List[RideCluster] = []
    noise_requests: List[RideFeature] = []

    for label, group in label_to_rides.items():
        # DBSCAN noise points → solo rides
        if label == -1:
            noise_requests.extend(group)
            continue

        # Split group if total seats exceed max vehicle capacity
        sub_groups = _split_by_capacity(group, config.max_cluster_seats)

        for split_idx, sub_group in enumerate(sub_groups):
            total_seats = sum(r.seats_needed for r in sub_group)

            # Compute centroids
            p_lats = [r.pickup_lat for r in sub_group]
            p_lngs = [r.pickup_lng for r in sub_group]
            d_lats = [r.dropoff_lat for r in sub_group]
            d_lngs = [r.dropoff_lng for r in sub_group]
            times = [r.departure_time for r in sub_group]

            cluster = RideCluster(
                cluster_label=label,
                member_requests=sub_group,
                centroid_pickup_lat=float(np.mean(p_lats)),
                centroid_pickup_lng=float(np.mean(p_lngs)),
                centroid_dropoff_lat=float(np.mean(d_lats)),
                centroid_dropoff_lng=float(np.mean(d_lngs)),
                departure_window_start=min(times),
                departure_window_end=max(times),
                total_seats_needed=total_seats,
                is_singleton=(len(sub_group) == 1),
                split_index=split_idx,
            )
            clusters.append(cluster)

    logger.info(
        f"Post-processing ({algorithm}): "
        f"{len(clusters)} clusters, {len(noise_requests)} solo passengers"
    )
    return clusters, noise_requests


def _split_by_capacity(
    rides: List[RideFeature],
    max_seats: int,
) -> List[List[RideFeature]]:
    """
    Split a group of rides into sub-groups if total seats exceed vehicle capacity.

    Strategy: Greedy bin-packing (FIRST-FIT DECREASING)
      - Sort rides by seats_needed descending
      - Assign each ride to the first bin with remaining capacity

    Example:
        rides: [2, 2, 1, 1, 1] seats, max_seats=4
        bin 1: [2, 2]          → 4 seats total (full)
        bin 2: [1, 1, 1]       → 3 seats total

    Returns:
        List of sub-groups, each fitting within max_seats capacity
    """
    if not rides:
        return []

    # Sort descending by seats needed (First-Fit Decreasing heuristic)
    sorted_rides = sorted(rides, key=lambda r: r.seats_needed, reverse=True)

    bins: List[List[RideFeature]] = []
    bin_totals: List[int] = []

    for ride in sorted_rides:
        placed = False
        for i, (bin_rides, bin_total) in enumerate(zip(bins, bin_totals)):
            if bin_total + ride.seats_needed <= max_seats:
                bin_rides.append(ride)
                bin_totals[i] += ride.seats_needed
                placed = True
                break
        if not placed:
            bins.append([ride])
            bin_totals.append(ride.seats_needed)

    return bins


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN ENGINE CLASS
# ─────────────────────────────────────────────────────────────────────────────

class RideClusteringEngine:
    """
    Production-grade AI ride clustering engine for Sylo Smart Carpooling.

    Usage:
        engine = RideClusteringEngine(config=ClusteringConfig())
        result = engine.cluster(rides)

        for cluster in result.clusters:
            # Assign driver, create ride, notify passengers
            ...

        for solo in result.noise_requests:
            # Offer private ride to this passenger
            ...

    Algorithm Selection:
        Primary:  DBSCAN with composite distance metric (recommended)
        Fallback: K-Means with Elbow method (when DBSCAN noise > 50%)

    Thread Safety:
        The engine is stateless — safe for concurrent use.
    """

    def __init__(self, config: Optional[ClusteringConfig] = None):
        self.config = config or ClusteringConfig()
        logger.info(
            f"RideClusteringEngine initialized | "
            f"eps={self.config.dbscan_eps}, "
            f"max_pickup={self.config.max_pickup_km}km, "
            f"max_drop={self.config.max_drop_km}km, "
            f"time_window={self.config.max_time_min}min, "
            f"min_samples={self.config.dbscan_min_samples}"
        )

    def cluster(self, rides: List[RideFeature]) -> ClusteringResult:
        """
        Main entry point. Clusters a batch of ride requests.

        Args:
            rides: List of pending RideFeature objects from the database

        Returns:
            ClusteringResult with clusters and noise_requests

        Steps:
            1. Validate input
            2. Build feature matrix
            3. Run DBSCAN with composite metric
            4. Check noise ratio → fall back to K-Means if needed
            5. Post-process labels → RideCluster objects
            6. Split over-capacity clusters
            7. Return full result
        """
        import time
        start = time.perf_counter()

        total = len(rides)
        logger.info(f"Starting clustering on {total} ride requests")

        # Edge case: 0 rides
        if total == 0:
            return ClusteringResult(
                clusters=[], noise_requests=[], algorithm_used="none",
                total_requests=0, total_clusters=0, noise_count=0,
            )

        # Edge case: 1 ride → immediate singleton
        if total == 1:
            solo_cluster = RideCluster(
                cluster_label=0,
                member_requests=rides,
                centroid_pickup_lat=rides[0].pickup_lat,
                centroid_pickup_lng=rides[0].pickup_lng,
                centroid_dropoff_lat=rides[0].dropoff_lat,
                centroid_dropoff_lng=rides[0].dropoff_lng,
                departure_window_start=rides[0].departure_time,
                departure_window_end=rides[0].departure_time,
                total_seats_needed=rides[0].seats_needed,
                is_singleton=True,
            )
            return ClusteringResult(
                clusters=[solo_cluster], noise_requests=[],
                algorithm_used="singleton", total_requests=1,
                total_clusters=1, noise_count=0,
            )

        # Build feature matrix: (N, 5)
        X = build_feature_matrix(rides)

        # ── Primary: DBSCAN ──────────────────────────────────────────────────
        algorithm = "dbscan"
        try:
            labels = _run_dbscan(X, self.config)
        except ImportError:
            logger.error("scikit-learn not available. Install: pip install scikit-learn")
            raise
        except Exception as exc:
            logger.warning(f"DBSCAN failed ({exc}), falling back to K-Means")
            labels = _run_kmeans_normalized(X, self.config)
            algorithm = "kmeans_fallback"

        # ── Fallback: K-Means if too many noise points ────────────────────────
        if algorithm == "dbscan":
            noise_ratio = float(np.sum(labels == -1)) / total
            if noise_ratio > self.config.noise_fallback_threshold and total >= 4:
                logger.info(
                    f"DBSCAN noise ratio {noise_ratio:.1%} exceeds threshold "
                    f"{self.config.noise_fallback_threshold:.1%}. "
                    f"Falling back to K-Means."
                )
                labels = _run_kmeans_normalized(X, self.config)
                algorithm = "kmeans_fallback"

        # ── Post-process labels → RideCluster objects ────────────────────────
        clusters, noise_requests = _build_clusters_from_labels(
            rides, labels, self.config, algorithm
        )

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        result = ClusteringResult(
            clusters=clusters,
            noise_requests=noise_requests,
            algorithm_used=algorithm,
            total_requests=total,
            total_clusters=len(clusters),
            noise_count=len(noise_requests),
            elapsed_ms=elapsed_ms,
        )

        logger.info(
            f"Clustering complete in {elapsed_ms:.1f}ms | "
            f"algorithm={algorithm} | "
            f"{result.total_clusters} clusters | "
            f"{result.noise_count} solo | "
            f"match_rate={result.match_rate:.1%}"
        )
        return result

    def describe_cluster(self, cluster: RideCluster) -> str:
        """Human-readable description of a cluster for logging/debugging."""
        member_str = ", ".join(str(r.request_id)[:8] for r in cluster.member_requests)
        return (
            f"Cluster(label={cluster.cluster_label}, "
            f"size={cluster.size}, "
            f"seats={cluster.total_seats_needed}, "
            f"singleton={cluster.is_singleton}, "
            f"pickup=({cluster.centroid_pickup_lat:.4f},{cluster.centroid_pickup_lng:.4f}), "
            f"dropoff=({cluster.centroid_dropoff_lat:.4f},{cluster.centroid_dropoff_lng:.4f}), "
            f"window=[{cluster.departure_window_start},{cluster.departure_window_end}], "
            f"members=[{member_str}])"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  DRIVER ASSIGNMENT ENGINE
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DriverCandidate:
    """Available driver eligible for cluster assignment."""
    driver_id: UUID
    user_id: UUID
    current_lat: float
    current_lng: float
    vehicle_capacity: int
    available_seats: int
    rating: float = 4.0
    vehicle_id: Optional[UUID] = None
    vehicle_model: str = ""


@dataclass
class DriverAssignment:
    """Result of assigning a driver to a cluster."""
    cluster: RideCluster
    driver: DriverCandidate
    distance_to_centroid_km: float
    assignment_score: float      # Lower is better (distance × rating_weight)
    success: bool = True
    failure_reason: str = ""


def assign_drivers_to_clusters(
    clusters: List[RideCluster],
    available_drivers: List[DriverCandidate],
    config: Optional[ClusteringConfig] = None,
) -> Tuple[List[DriverAssignment], List[RideCluster]]:
    """
    Assign the best available driver to each cluster.

    Assignment Algorithm:
        For each cluster (sorted by total_seats_needed descending):
            1. Filter drivers with capacity >= cluster.total_seats_needed
            2. Calculate assignment_score for each eligible driver:
                   score = distance_km × (1 / rating_bonus)
                   rating_bonus = 1 + (driver.rating - 3.0) / 10.0
               Lower score = better (closer driver with higher rating wins)
            3. Assign driver with minimum score
            4. Remove assigned driver from pool (no double-assignment)

    Args:
        clusters: List of RideCluster objects from clustering engine
        available_drivers: List of DriverCandidate objects from DB
        config: Clustering config for capacity constraints

    Returns:
        (assignments, unassigned_clusters)
        - assignments: List of successful driver-cluster matches
        - unassigned_clusters: Clusters where no driver was available
    """
    cfg = config or ClusteringConfig()

    # Sort clusters: serve largest groups first (greedy — maximizes vehicle utilization)
    sorted_clusters = sorted(clusters, key=lambda c: c.total_seats_needed, reverse=True)

    # Mutable driver pool
    driver_pool = list(available_drivers)

    assignments: List[DriverAssignment] = []
    unassigned: List[RideCluster] = []

    for cluster in sorted_clusters:
        best_assignment: Optional[DriverAssignment] = None

        for driver in driver_pool:
            if driver.available_seats < cluster.total_seats_needed:
                continue  # Driver lacks capacity

            dist_km = _haversine_km(
                driver.current_lat, driver.current_lng,
                cluster.centroid_pickup_lat, cluster.centroid_pickup_lng,
            )

            # Rating bonus: higher-rated drivers get a small score reduction
            rating_bonus = 1.0 + max(0.0, (driver.rating - 3.0)) / 10.0
            score = dist_km / rating_bonus

            if best_assignment is None or score < best_assignment.assignment_score:
                best_assignment = DriverAssignment(
                    cluster=cluster,
                    driver=driver,
                    distance_to_centroid_km=dist_km,
                    assignment_score=score,
                )

        if best_assignment is not None:
            assignments.append(best_assignment)
            driver_pool.remove(best_assignment.driver)
            logger.info(
                f"Assigned driver {best_assignment.driver.driver_id} "
                f"to cluster {cluster.cluster_label} "
                f"({cluster.size} passengers, {cluster.total_seats_needed} seats, "
                f"distance={best_assignment.distance_to_centroid_km:.2f}km)"
            )
        else:
            unassigned.append(cluster)
            logger.warning(
                f"No driver available for cluster {cluster.cluster_label} "
                f"(needs {cluster.total_seats_needed} seats)"
            )

    logger.info(
        f"Driver assignment complete: {len(assignments)} assigned, "
        f"{len(unassigned)} unassigned"
    )
    return assignments, unassigned
