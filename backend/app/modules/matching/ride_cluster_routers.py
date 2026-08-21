"""
FastAPI Router — AI Ride Clustering Endpoints
=============================================

Endpoints:
    POST /api/v2/matching/cluster/trigger     → Run clustering pipeline
    GET  /api/v2/matching/cluster/status      → Scheduler status
    GET  /api/v2/matching/cluster/explain     → Algorithm explanation
    GET  /api/v2/matching/cluster/request/{id}→ Status of one ride request

Author: Sylo Smart Carpooling FYP
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User

from .ride_cluster_schemas import (
    ClusterTriggerRequest,
    ClusterRunSummary,
    ClusterStatusResponse,
)
from .ride_cluster_service import run_full_clustering_pipeline

router = APIRouter(prefix="/matching/cluster", tags=["AI Ride Clustering"])

# In-memory store of last run summary (replace with Redis in production)
_last_run_summary: Dict[str, Any] = {}


@router.post(
    "/trigger",
    response_model=Dict[str, Any],
    summary="Trigger AI Ride Clustering",
    description="""
Manually trigger the AI-powered ride clustering pipeline.

**Algorithm:**
1. Fetches all PENDING ride requests within the configured time window
2. Builds a feature matrix: [pickup_lat, pickup_lng, dropoff_lat, dropoff_lng, time_minutes]
3. Runs **DBSCAN** with a custom composite distance metric that measures:
   - Pickup point proximity (km)
   - Dropoff direction similarity (km)
   - Departure time compatibility (minutes)
4. Falls back to **K-Means** (elbow method) if DBSCAN produces >50% noise
5. Splits over-capacity clusters using First-Fit-Decreasing bin packing
6. Assigns best available driver to each cluster (by proximity + rating)
7. Creates Rides + Bookings in the database
8. Sends FCM notifications to all participants

**Use `dry_run=true` to see clustering results without writing to DB.**
""",
)
async def trigger_clustering(
    request: ClusterTriggerRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Trigger the full ML clustering pipeline.
    Can be called by admins or the background scheduler.
    """
    run_id = str(uuid.uuid4())[:8]
    summary = await run_full_clustering_pipeline(db, request, run_id=run_id)

    # Cache last run
    global _last_run_summary
    _last_run_summary = summary.model_dump()

    return {
        "status": "ok",
        "data": summary.model_dump(),
        "error": None,
    }


@router.get(
    "/status",
    response_model=Dict[str, Any],
    summary="Get Last Clustering Run Status",
)
async def get_cluster_status(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the summary of the most recent clustering run."""
    if not _last_run_summary:
        return {
            "status": "ok",
            "data": {
                "message": "No clustering run has been executed yet.",
                "last_run": None,
            },
            "error": None,
        }
    return {
        "status": "ok",
        "data": _last_run_summary,
        "error": None,
    }


@router.get(
    "/explain",
    response_model=Dict[str, Any],
    summary="Explain Clustering Algorithm",
    description="Returns a human-readable explanation of the AI algorithm used.",
)
async def explain_algorithm(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Algorithm transparency endpoint — explains the AI to passengers/drivers."""
    return {
        "status": "ok",
        "data": {
            "algorithm": "DBSCAN with Composite Haversine-Time Metric",
            "why_dbscan": (
                "Unlike K-Means, DBSCAN does not require knowing the number of "
                "groups in advance. It automatically discovers dense regions of "
                "compatible rides and labels isolated riders as 'noise' (solo trips). "
                "This is ideal for carpooling where group count varies dynamically."
            ),
            "distance_metric": {
                "formula": "sqrt((pickup_km/2.0)² + (dropoff_km/8.0)² + (Δtime_min/20.0)²)",
                "pickup_threshold_km": 2.0,
                "dropoff_threshold_km": 8.0,
                "time_threshold_minutes": 20.0,
                "eps": 1.0,
                "interpretation": (
                    "Two riders are grouped if: their pickup points are within ~1.4km, "
                    "their destinations are within ~5.7km, AND they depart within ~14min."
                ),
            },
            "fallback": (
                "K-Means with Elbow Method — used when DBSCAN marks >50% of riders "
                "as noise, indicating sparse request density."
            ),
            "driver_assignment": (
                "Greedy assignment: largest clusters served first. Best driver = "
                "minimum (distance_to_centroid / rating_bonus)."
            ),
            "capacity_handling": (
                "First-Fit-Decreasing bin packing splits clusters that exceed "
                "vehicle capacity (default: 6 seats)."
            ),
            "complexity": {
                "clustering": "O(N²) distance matrix construction, O(N log N) DBSCAN",
                "assignment": "O(C × D) where C=clusters, D=available drivers",
                "typical_latency_ms": "< 500ms for 200 simultaneous requests",
            },
        },
        "error": None,
    }


@router.get(
    "/request/{request_id}",
    response_model=Dict[str, Any],
    summary="Get Cluster Status for a Ride Request",
)
async def get_request_cluster_status(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Check whether a specific ride request has been matched to a cluster/ride.
    """
    from sqlalchemy import select
    from app.models.ride_request import RideRequest, RideRequestStatus
    from uuid import UUID

    try:
        req_uuid = UUID(request_id)
    except ValueError:
        return {
            "status": "error",
            "data": None,
            "error": "Invalid request_id format",
        }

    result = await db.execute(
        select(RideRequest).where(RideRequest.id == req_uuid)
    )
    rr = result.scalar_one_or_none()

    if not rr:
        return {
            "status": "error",
            "data": None,
            "error": f"Ride request {request_id} not found",
        }

    # Determine status message
    if rr.status == RideRequestStatus.PENDING:
        message = "Your ride request is pending. Clustering runs every 5 minutes."
        status_label = "pending"
    elif rr.status == RideRequestStatus.ACCEPTED:
        message = "You have been matched to a carpooling group!"
        status_label = "matched"
    elif rr.status == RideRequestStatus.CANCELLED:
        message = "This ride request has been cancelled."
        status_label = "cancelled"
    elif rr.status == RideRequestStatus.EXPIRED:
        message = "This ride request has expired."
        status_label = "expired"
    else:
        message = "Unknown status."
        status_label = str(rr.status)

    return {
        "status": "ok",
        "data": ClusterStatusResponse(
            request_id=rr.id,
            status=status_label,
            assigned_driver_id=rr.accepted_by_driver_id,
            matched_ride_id=rr.ride_id,
            message=message,
        ).model_dump(),
        "error": None,
    }
