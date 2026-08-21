"""
Cluster Service

Background service for building and caching driver clusters.
Runs periodically to precompute spatial groupings for fast matching.

Performance:
- Cluster building: < 5s for 1000 drivers
- Cache lookup: < 5ms (Redis)
- Fallback: On-demand clustering if cache miss
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.matching import crud_new as crud
from app.modules.matching.cache import CacheManager
from app.modules.matching.ml_adapter import cluster_drivers, create_ml_adapter
from app.modules.matching.schemas_new import ClusterInfo, GeoPoint

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

CLUSTER_CACHE_TTL = getattr(settings, "CLUSTER_CACHE_TTL_SECONDS", 300)  # 5 minutes
DEFAULT_N_CLUSTERS = 10
CLUSTER_ALGORITHM = "kmeans"  # or "dbscan"


# ============================================================================
# REGION HASHING
# ============================================================================

def hash_region(lat: float, lng: float, radius_km: float) -> str:
    """
    Generate cache key for a geographic region.
    
    Args:
        lat, lng: Center point
        radius_km: Region radius
        
    Returns:
        Hash string for cache key
    """
    # Round to 2 decimal places for cache key consistency (~1km precision)
    lat_rounded = round(lat, 2)
    lng_rounded = round(lng, 2)
    radius_rounded = round(radius_km, 1)

    key_str = f"{lat_rounded}:{lng_rounded}:{radius_rounded}"
    return hashlib.md5(key_str.encode()).hexdigest()[:16]


# ============================================================================
# CLUSTER BUILDING
# ============================================================================

async def build_clusters_for_region(
    db: AsyncSession,
    center_lat: float,
    center_lng: float,
    radius_km: float,
    n_clusters: Optional[int] = None,
    algorithm: str = CLUSTER_ALGORITHM,
) -> List[ClusterInfo]:
    """
    Build clusters for drivers in a geographic region.
    
    Args:
        db: Database session
        center_lat, center_lng: Region center
        radius_km: Region radius
        n_clusters: Number of clusters (auto if None)
        algorithm: "kmeans" or "dbscan"
        
    Returns:
        List of ClusterInfo objects
    """
    # Get drivers in region
    candidates = await crud.find_nearby_drivers(
        db=db,
        lat=center_lat,
        lng=center_lng,
        radius_km=radius_km,
        min_seats=0,  # Include all drivers
    )

    if not candidates:
        logger.info("No drivers found in region for clustering")
        return []

    # Extract locations
    locations = [(c["driver_lat"], c["driver_lng"]) for c in candidates]
    driver_ids = [c["driver_id"] for c in candidates]

    # Auto-determine n_clusters
    if n_clusters is None:
        n_clusters = min(max(2, len(locations) // 10), 20)

    # Perform clustering
    labels, centroids = cluster_drivers(
        locations,
        algorithm=algorithm,
        n_clusters=n_clusters
    )

    # Build ClusterInfo objects
    clusters = []
    for cluster_id in range(len(centroids)):
        # Find drivers in this cluster
        cluster_driver_ids = [
            driver_ids[i] for i, label in enumerate(labels) if label == cluster_id
        ]

        if cluster_driver_ids:
            centroid_lat, centroid_lng = centroids[cluster_id]
            clusters.append(
                ClusterInfo(
                    cluster_id=cluster_id,
                    centroid=GeoPoint(lat=centroid_lat, lng=centroid_lng),
                    driver_ids=cluster_driver_ids,
                    size=len(cluster_driver_ids),
                )
            )

    logger.info(
        f"Built {len(clusters)} clusters for region ({center_lat}, {center_lng}) "
        f"with {len(candidates)} drivers"
    )

    return clusters


async def build_global_clusters(
    db: AsyncSession,
    n_clusters: int = DEFAULT_N_CLUSTERS,
    algorithm: str = CLUSTER_ALGORITHM,
) -> List[ClusterInfo]:
    """
    Build clusters for all active drivers globally.
    
    Used for periodic background refresh of cluster cache.
    
    Args:
        db: Database session
        n_clusters: Number of clusters
        algorithm: Clustering algorithm
        
    Returns:
        List of ClusterInfo objects
    """
    # Get all active driver locations
    locations_raw = await crud.get_all_active_driver_locations(db, limit=1000)

    if not locations_raw:
        logger.warning("No active drivers found for global clustering")
        return []

    # Fetch driver IDs (need to re-query with driver_id)
    # Simplified: use sequential IDs for demo
    # In production, join to get actual driver_ids
    locations = locations_raw
    n_drivers = len(locations)

    # Auto-adjust n_clusters
    n_clusters = min(n_clusters, max(2, n_drivers // 5))

    # Perform clustering
    labels, centroids = cluster_drivers(
        locations,
        algorithm=algorithm,
        n_clusters=n_clusters
    )

    # Build ClusterInfo (without driver_ids for global view)
    clusters = []
    for cluster_id, centroid in enumerate(centroids):
        cluster_size = np.sum(labels == cluster_id)
        centroid_lat, centroid_lng = centroid

        clusters.append(
            ClusterInfo(
                cluster_id=cluster_id,
                centroid=GeoPoint(lat=centroid_lat, lng=centroid_lng),
                driver_ids=[],  # Not included in global view
                size=int(cluster_size),
            )
        )

    logger.info(f"Built {len(clusters)} global clusters from {n_drivers} drivers")
    return clusters


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================

async def cache_clusters(
    cache: CacheManager,
    region_hash: str,
    clusters: List[ClusterInfo],
    ttl: int = CLUSTER_CACHE_TTL,
):
    """
    Cache cluster data for a region.
    
    Args:
        cache: Cache manager instance
        region_hash: Region identifier
        clusters: List of clusters to cache
        ttl: Cache TTL in seconds
    """
    cache_key = f"clusters:{region_hash}"

    # Serialize clusters
    clusters_data = [
        {
            "cluster_id": c.cluster_id,
            "centroid": {"lat": c.centroid.lat, "lng": c.centroid.lng},
            "driver_ids": [str(did) for did in c.driver_ids],
            "size": c.size,
        }
        for c in clusters
    ]

    await cache.set(cache_key, clusters_data, ttl=ttl)
    logger.info(f"Cached {len(clusters)} clusters for region {region_hash}")


async def get_cached_clusters(
    cache: CacheManager,
    region_hash: str,
) -> Optional[List[ClusterInfo]]:
    """
    Retrieve cached clusters for a region.
    
    Returns:
        List of ClusterInfo or None if cache miss
    """
    cache_key = f"clusters:{region_hash}"
    cached_data = await cache.get(cache_key)

    if not cached_data:
        return None

    # Deserialize
    clusters = [
        ClusterInfo(
            cluster_id=c["cluster_id"],
            centroid=GeoPoint(**c["centroid"]),
            driver_ids=[UUID(did) for did in c["driver_ids"]],
            size=c["size"],
        )
        for c in cached_data
    ]

    logger.debug(f"Cache hit for region {region_hash}: {len(clusters)} clusters")
    return clusters


async def get_or_build_clusters(
    db: AsyncSession,
    cache: CacheManager,
    center_lat: float,
    center_lng: float,
    radius_km: float,
    n_clusters: Optional[int] = None,
) -> Tuple[List[ClusterInfo], bool]:
    """
    Get clusters from cache or build if cache miss.
    
    Args:
        db: Database session
        cache: Cache manager
        center_lat, center_lng: Region center
        radius_km: Region radius
        n_clusters: Number of clusters (auto if None)
        
    Returns:
        (clusters, cache_hit) tuple
    """
    region_hash = hash_region(center_lat, center_lng, radius_km)

    # Try cache first
    clusters = await get_cached_clusters(cache, region_hash)
    if clusters:
        return clusters, True

    # Cache miss - build clusters
    logger.info(f"Cache miss for region {region_hash}, building clusters")
    clusters = await build_clusters_for_region(
        db, center_lat, center_lng, radius_km, n_clusters
    )

    # Cache results
    if clusters:
        await cache_clusters(cache, region_hash, clusters)

    return clusters, False


# ============================================================================
# PERIODIC REFRESH
# ============================================================================

async def refresh_global_clusters_task(
    db: AsyncSession,
    cache: CacheManager,
    n_clusters: int = DEFAULT_N_CLUSTERS,
):
    """
    Background task to refresh global cluster cache.
    
    Should be called by Celery/RQ periodically (e.g., every 5 minutes).
    
    Args:
        db: Database session
        cache: Cache manager
        n_clusters: Number of clusters
    """
    try:
        logger.info("Starting global cluster refresh")
        start_time = datetime.now()

        # Build global clusters
        clusters = await build_global_clusters(db, n_clusters=n_clusters)

        # Cache with special key "global"
        if clusters:
            await cache_clusters(cache, "global", clusters, ttl=CLUSTER_CACHE_TTL)

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"✅ Global cluster refresh complete: {len(clusters)} clusters in {elapsed:.2f}s"
        )

        return {"status": "success", "clusters": len(clusters), "elapsed_s": elapsed}

    except Exception as e:
        logger.error(f"Global cluster refresh failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


async def invalidate_region_cache(
    cache: CacheManager,
    center_lat: float,
    center_lng: float,
    radius_km: float,
):
    """
    Invalidate cached clusters for a region.
    
    Call when driver locations change significantly.
    
    Args:
        cache: Cache manager
        center_lat, center_lng: Region center
        radius_km: Region radius
    """
    region_hash = hash_region(center_lat, center_lng, radius_km)
    cache_key = f"clusters:{region_hash}"
    await cache.delete(cache_key)
    logger.info(f"Invalidated cache for region {region_hash}")


# ============================================================================
# CLUSTER UTILITIES
# ============================================================================

def find_nearest_cluster(
    lat: float,
    lng: float,
    clusters: List[ClusterInfo]
) -> Optional[ClusterInfo]:
    """
    Find cluster whose centroid is nearest to a point.
    
    Args:
        lat, lng: Query point
        clusters: List of clusters
        
    Returns:
        Nearest ClusterInfo or None
    """
    if not clusters:
        return None

    from app.modules.matching.service_new import haversine_distance

    min_distance = float("inf")
    nearest = None

    for cluster in clusters:
        distance = haversine_distance(
            lat, lng,
            cluster.centroid.lat, cluster.centroid.lng
        )
        if distance < min_distance:
            min_distance = distance
            nearest = cluster

    return nearest


async def get_drivers_in_cluster(
    db: AsyncSession,
    cluster: ClusterInfo
) -> List[dict]:
    """
    Get detailed driver information for all drivers in a cluster.
    
    Args:
        db: Database session
        cluster: ClusterInfo with driver_ids
        
    Returns:
        List of driver detail dicts
    """
    if not cluster.driver_ids:
        return []

    locations = await crud.get_driver_locations(db, cluster.driver_ids)

    return [
        {
            "driver_id": driver_id,
            "lat": lat,
            "lng": lng,
            "cluster_id": cluster.cluster_id,
        }
        for driver_id, lat, lng in locations
    ]
