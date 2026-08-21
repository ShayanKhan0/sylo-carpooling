"""
Matching Engine API Routers

REST endpoints for driver-passenger matching with ML-powered clustering.

Endpoints:
- POST /matching/request: Find matching drivers
- POST /matching/simulate: Simulate clustering (debug/testing)
"""

import logging
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.core.exceptions import NotFoundError, ValidationError
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User
from app.modules.matching import cluster_service, service_new
from app.modules.matching.cache import get_cache
from app.modules.matching.schemas_new import (
    ClusterInfo,
    GeoPoint,
    MatchingRequest,
    MatchingResponse,
    SimulateRequest,
    SimulateResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/matching", tags=["Matching"])


# ============================================================================
# MAIN MATCHING ENDPOINT
# ============================================================================

@router.post(
    "/request",
    response_model=MatchingResponse,
    summary="Find matching drivers",
    description="""
    Find drivers that match passenger's pickup/dropoff requirements.
    
    **Two-stage pipeline:**
    1. Spatial prefilter (PostGIS or bounding box)
    2. Ranking by match score (detour + driver quality + preferences)
    
    **Performance:** < 200ms typical
    
    **Match Score Components:**
    - Detour cost (weight: 0.5)
    - Driver quality (rating + seats) (weight: 0.3)
    - Preference match (weight: 0.2)
    
    **Rate Limiting:** Recommended to implement rate limiting middleware
    (e.g., slowapi or Redis-based token bucket) to prevent abuse.
    """
)
async def request_matching(
    request: MatchingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Find and rank matching drivers for a passenger.
    
    Returns list of candidates ordered by match_score (0-1, higher = better).
    """
    start_time = time.time()

    try:
        # Validate user exists and is active
        if not current_user or not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not active"
            )

        # Validate request user_id matches authenticated user
        if str(request.user_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot request matching for another user"
            )

        # Get cache instance
        cache = await get_cache()

        # Check if we can use cached clusters (future optimization)
        # For now, directly call matching service
        region_hash = cluster_service.hash_region(
            request.pickup.lat,
            request.pickup.lng,
            10.0  # Default radius
        )
        cache_hit = False

        # Try to get cached clusters first (optional fast path)
        # clusters = await cluster_service.get_cached_clusters(cache, region_hash)
        # cache_hit = clusters is not None

        # Run matching
        candidates = await service_new.match_drivers(
            db=db,
            request=request,
            explain=request.explain
        )

        elapsed_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Matching request completed: {len(candidates)} candidates "
            f"in {elapsed_ms:.1f}ms (cache_hit={cache_hit})"
        )

        return MatchingResponse(
            status="ok",
            candidates=candidates,
            total_candidates=len(candidates),
            query_time_ms=elapsed_ms,
            cache_hit=cache_hit,
        )

    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Matching request failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during matching"
        )


# ============================================================================
# SIMULATION ENDPOINT (DEBUG/TESTING)
# ============================================================================

@router.post(
    "/simulate",
    response_model=SimulateResponse,
    summary="Simulate driver clustering",
    description="""
    Generate synthetic driver data and perform clustering for visualization/testing.
    
    **Use cases:**
    - Test clustering algorithms
    - Generate visualization data for frontend
    - Verify ML adapter functionality
    - Unit test validation
    
    **Note:** Uses synthetic data, not real drivers from database.
    """
)
async def simulate_clustering(
    request: SimulateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Simulate clustering with synthetic driver data.
    
    Returns cluster information suitable for visualization.
    """
    try:
        # Generate synthetic driver locations
        import numpy as np
        from uuid import uuid4

        # Default region: Lahore, Pakistan
        if request.region_bounds:
            lat_min = request.region_bounds["lat_min"]
            lat_max = request.region_bounds["lat_max"]
            lng_min = request.region_bounds["lng_min"]
            lng_max = request.region_bounds["lng_max"]
        else:
            # Default: Lahore area
            lat_min, lat_max = 31.4, 31.6
            lng_min, lng_max = 74.2, 74.4

        # Generate random driver locations
        np.random.seed(42)  # Reproducible
        lats = np.random.uniform(lat_min, lat_max, request.num_drivers)
        lngs = np.random.uniform(lng_min, lng_max, request.num_drivers)
        locations = list(zip(lats, lngs))

        # Generate driver IDs
        driver_ids = [uuid4() for _ in range(request.num_drivers)]

        # Perform clustering
        from app.modules.matching.ml_adapter import cluster_drivers

        labels, centroids = cluster_drivers(
            locations,
            algorithm="kmeans",
            n_clusters=request.num_clusters
        )

        # Build cluster info
        clusters = []
        for cluster_id in range(len(centroids)):
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
            f"Simulation complete: {request.num_drivers} drivers, "
            f"{len(clusters)} clusters"
        )

        return SimulateResponse(
            status="ok",
            clusters=clusters,
            num_drivers=request.num_drivers,
            num_clusters=len(clusters),
            algorithm="KMeans",
        )

    except Exception as e:
        logger.error(f"Simulation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Simulation error: {str(e)}"
        )


# ============================================================================
# CLUSTER INFO ENDPOINT (Optional)
# ============================================================================

@router.get(
    "/clusters/global",
    response_model=List[ClusterInfo],
    summary="Get global driver clusters",
    description="""
    Get precomputed global driver clusters (if available in cache).
    
    Useful for:
    - Dashboard visualization
    - Driver distribution heatmaps
    - System monitoring
    """
)
async def get_global_clusters(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get global driver clusters from cache or build on-demand"""
    try:
        cache = await get_cache()

        # Try cache first
        clusters = await cluster_service.get_cached_clusters(cache, "global")

        if not clusters:
            # Build on-demand (might be slow)
            logger.info("Building global clusters on-demand")
            clusters = await cluster_service.build_global_clusters(db, n_clusters=10)

            # Cache results
            if clusters:
                await cluster_service.cache_clusters(cache, "global", clusters)

        return clusters

    except Exception as e:
        logger.error(f"Failed to get global clusters: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve clusters"
        )


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get(
    "/health",
    summary="Matching engine health check",
    description="Check if matching engine and dependencies are operational"
)
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check for matching engine"""
    try:
        # Check database
        from app.modules.matching import crud_new
        driver_count = await crud_new.get_active_drivers_count(db)

        # Check cache
        cache = await get_cache()
        cache_status = "redis" if cache.using_redis else "in-memory"

        # Check PostGIS
        has_postgis = await crud_new.check_postgis_available(db)
        spatial_engine = "PostGIS" if has_postgis else "BoundingBox"

        return {
            "status": "healthy",
            "active_drivers": driver_count,
            "cache": cache_status,
            "spatial_engine": spatial_engine,
            "timestamp": time.time(),
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": time.time(),
        }
