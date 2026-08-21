"""
ML Adapter Interface for Matching Engine

Pluggable ML interface with KMeans and DBSCAN implementations.
Designed for easy swap-in of production ML models.

Default: StubMLAdapter (sklearn KMeans)
Optional: DBSCANAdapter for density-based clustering
Future: Custom neural net adapters
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================================
# ABSTRACT INTERFACE
# ============================================================================

class MLAdapter(ABC):
    """
    Abstract base class for ML clustering algorithms.
    
    Implementations must provide:
    - fit(): Train on driver locations
    - predict(): Assign new points to clusters
    - get_cluster_centroids(): Return cluster centers
    """

    @abstractmethod
    def fit(self, features: np.ndarray) -> "MLAdapter":
        """
        Train clustering model on features.
        
        Args:
            features: Nx2 array of (lat, lng) coordinates
            
        Returns:
            self for method chaining
        """
        pass

    @abstractmethod
    def predict(self, features: np.ndarray) -> np.ndarray:
        """
        Predict cluster labels for new points.
        
        Args:
            features: Nx2 array of (lat, lng) coordinates
            
        Returns:
            Array of cluster labels (integers)
        """
        pass

    @abstractmethod
    def get_cluster_centroids(self) -> List[Tuple[float, float]]:
        """
        Get cluster centroid coordinates.
        
        Returns:
            List of (lat, lng) tuples for each cluster
        """
        pass

    @property
    @abstractmethod
    def n_clusters(self) -> int:
        """Number of clusters"""
        pass


# ============================================================================
# KMEANS IMPLEMENTATION (Default)
# ============================================================================

class StubMLAdapter(MLAdapter):
    """
    KMeans-based clustering adapter (sklearn).
    
    Good for:
    - Quick prototyping
    - Deterministic results (with random_state)
    - Known number of clusters
    
    Limitations:
    - Requires pre-defined k
    - Assumes spherical clusters
    
    Usage:
        adapter = StubMLAdapter(n_clusters=5)
        adapter.fit(driver_locations)
        labels = adapter.predict(new_locations)
    """

    def __init__(
        self,
        n_clusters: int = 5,
        random_state: int = 42,
        max_iter: int = 100
    ):
        """
        Initialize KMeans adapter.
        
        Args:
            n_clusters: Number of clusters to create
            random_state: Random seed for reproducibility
            max_iter: Maximum iterations for convergence
        """
        self._n_clusters = n_clusters
        self.random_state = random_state
        self.max_iter = max_iter
        self.model = None

        try:
            from sklearn.cluster import KMeans
            self.model = KMeans(
                n_clusters=n_clusters,
                random_state=random_state,
                max_iter=max_iter,
                n_init=10
            )
            logger.info(f"✅ StubMLAdapter initialized with KMeans (k={n_clusters})")
        except ImportError:
            logger.warning("sklearn not available, using fallback implementation")
            self.model = None

    def fit(self, features: np.ndarray) -> "StubMLAdapter":
        """Fit KMeans on driver locations"""
        if features.shape[0] < self._n_clusters:
            logger.warning(
                f"Only {features.shape[0]} samples for {self._n_clusters} clusters. "
                f"Adjusting n_clusters to {features.shape[0]}"
            )
            self._n_clusters = max(1, features.shape[0])
            if self.model:
                from sklearn.cluster import KMeans
                self.model = KMeans(
                    n_clusters=self._n_clusters,
                    random_state=self.random_state,
                    max_iter=self.max_iter
                )

        if self.model:
            self.model.fit(features)
        else:
            # Simple fallback: use first k points as centroids
            self._centroids = features[:self._n_clusters].copy()

        logger.info(f"KMeans fitted on {features.shape[0]} samples")
        return self

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Predict cluster labels"""
        if self.model:
            return self.model.predict(features)
        else:
            # Fallback: assign to nearest centroid
            labels = []
            for point in features:
                distances = np.linalg.norm(self._centroids - point, axis=1)
                labels.append(np.argmin(distances))
            return np.array(labels)

    def get_cluster_centroids(self) -> List[Tuple[float, float]]:
        """Get cluster centroids"""
        if self.model:
            centroids = self.model.cluster_centers_
        else:
            centroids = self._centroids

        return [(float(lat), float(lng)) for lat, lng in centroids]

    @property
    def n_clusters(self) -> int:
        return self._n_clusters


# ============================================================================
# DBSCAN IMPLEMENTATION (Optional)
# ============================================================================

class DBSCANAdapter(MLAdapter):
    """
    DBSCAN (Density-Based Spatial Clustering) adapter.
    
    Good for:
    - Automatic cluster discovery
    - Arbitrary cluster shapes
    - Noise detection (outliers)
    
    Limitations:
    - No predict() method (must refit for new points)
    - Sensitive to eps and min_samples parameters
    
    Usage:
        adapter = DBSCANAdapter(eps=0.05, min_samples=3)
        adapter.fit(driver_locations)
        centroids = adapter.get_cluster_centroids()
    """

    def __init__(self, eps: float = 0.05, min_samples: int = 3):
        """
        Initialize DBSCAN adapter.
        
        Args:
            eps: Maximum distance between two samples to be neighbors
                 (in degrees, ~0.05° ≈ 5km at equator)
            min_samples: Minimum samples in neighborhood for core point
        """
        self.eps = eps
        self.min_samples = min_samples
        self.model = None
        self.labels_ = None
        self._centroids = None
        self._n_clusters = 0

        try:
            from sklearn.cluster import DBSCAN
            self.model = DBSCAN(eps=eps, min_samples=min_samples)
            logger.info(f"✅ DBSCANAdapter initialized (eps={eps}, min_samples={min_samples})")
        except ImportError:
            logger.error("sklearn required for DBSCAN. Install: pip install scikit-learn")
            raise

    def fit(self, features: np.ndarray) -> "DBSCANAdapter":
        """Fit DBSCAN on driver locations"""
        if self.model is None:
            raise RuntimeError("DBSCAN model not initialized (sklearn missing?)")

        self.labels_ = self.model.fit_predict(features)

        # Calculate centroids (excluding noise label -1)
        unique_labels = set(self.labels_)
        unique_labels.discard(-1)  # Remove noise
        self._n_clusters = len(unique_labels)

        centroids = []
        for label in sorted(unique_labels):
            cluster_points = features[self.labels_ == label]
            centroid = cluster_points.mean(axis=0)
            centroids.append(centroid)

        self._centroids = np.array(centroids) if centroids else np.empty((0, 2))

        logger.info(
            f"DBSCAN fitted: {self._n_clusters} clusters, "
            f"{np.sum(self.labels_ == -1)} noise points"
        )
        return self

    def predict(self, features: np.ndarray) -> np.ndarray:
        """
        DBSCAN does not support predict().
        
        Workaround: Assign to nearest cluster centroid.
        For production, consider using HDBSCAN which supports prediction.
        """
        if self._centroids is None or len(self._centroids) == 0:
            logger.warning("No clusters found, returning all -1 (noise)")
            return np.full(features.shape[0], -1)

        # Assign to nearest centroid
        labels = []
        for point in features:
            distances = np.linalg.norm(self._centroids - point, axis=1)
            labels.append(np.argmin(distances))

        return np.array(labels)

    def get_cluster_centroids(self) -> List[Tuple[float, float]]:
        """Get cluster centroids (excluding noise)"""
        if self._centroids is None or len(self._centroids) == 0:
            return []

        return [(float(lat), float(lng)) for lat, lng in self._centroids]

    @property
    def n_clusters(self) -> int:
        return self._n_clusters


# ============================================================================
# FACTORY
# ============================================================================

def create_ml_adapter(
    algorithm: str = "kmeans",
    **kwargs
) -> MLAdapter:
    """
    Factory function to create ML adapter.
    
    Args:
        algorithm: "kmeans" or "dbscan"
        **kwargs: Algorithm-specific parameters
        
    Returns:
        Configured MLAdapter instance
        
    Example:
        adapter = create_ml_adapter("kmeans", n_clusters=5)
        adapter = create_ml_adapter("dbscan", eps=0.05, min_samples=3)
    """
    algorithm = algorithm.lower()

    if algorithm == "kmeans":
        n_clusters = kwargs.get("n_clusters", 5)
        random_state = kwargs.get("random_state", 42)
        return StubMLAdapter(n_clusters=n_clusters, random_state=random_state)

    elif algorithm == "dbscan":
        eps = kwargs.get("eps", 0.05)
        min_samples = kwargs.get("min_samples", 3)
        return DBSCANAdapter(eps=eps, min_samples=min_samples)

    else:
        raise ValueError(f"Unknown algorithm: {algorithm}. Use 'kmeans' or 'dbscan'")


# ============================================================================
# CLUSTERING UTILITIES
# ============================================================================

def prepare_features(locations: List[Tuple[float, float]]) -> np.ndarray:
    """
    Convert list of (lat, lng) tuples to numpy array.
    
    Args:
        locations: List of (lat, lng) tuples
        
    Returns:
        Nx2 numpy array
    """
    return np.array(locations, dtype=np.float32)


def cluster_drivers(
    locations: List[Tuple[float, float]],
    algorithm: str = "kmeans",
    n_clusters: Optional[int] = None,
    **kwargs
) -> Tuple[np.ndarray, List[Tuple[float, float]]]:
    """
    Cluster driver locations using specified algorithm.
    
    Args:
        locations: List of (lat, lng) tuples
        algorithm: "kmeans" or "dbscan"
        n_clusters: Number of clusters (for kmeans)
        **kwargs: Additional algorithm parameters
        
    Returns:
        (labels, centroids) tuple
        - labels: Array of cluster assignments
        - centroids: List of (lat, lng) centroid coordinates
        
    Example:
        labels, centroids = cluster_drivers(
            driver_locations,
            algorithm="kmeans",
            n_clusters=5
        )
    """
    if len(locations) == 0:
        return np.array([]), []

    features = prepare_features(locations)

    # Auto-determine n_clusters if not provided
    if algorithm == "kmeans" and n_clusters is None:
        n_clusters = min(max(2, len(locations) // 10), 20)  # Heuristic
        logger.info(f"Auto n_clusters: {n_clusters} (from {len(locations)} drivers)")

    # Create and fit adapter
    adapter = create_ml_adapter(algorithm, n_clusters=n_clusters, **kwargs)
    adapter.fit(features)

    # Get results
    labels = adapter.predict(features)
    centroids = adapter.get_cluster_centroids()

    logger.info(
        f"Clustered {len(locations)} drivers into {adapter.n_clusters} clusters "
        f"using {algorithm.upper()}"
    )

    return labels, centroids
