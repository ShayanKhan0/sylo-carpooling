"""
Pydantic Schemas — Ride Clustering API
Author: Sylo Smart Carpooling
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ── Request Schemas ───────────────────────────────────────────────────────────

class ClusterTriggerRequest(BaseModel):
    """
    Manually trigger a clustering run.
    Useful for testing or admin-initiated re-clustering.
    """
    time_window_minutes: int = Field(
        default=60,
        ge=5, le=480,
        description="Aggregate ride requests within this many minutes from now",
    )
    max_pickup_km: float = Field(
        default=2.0, ge=0.5, le=10.0,
        description="Maximum pickup proximity for grouping (km)",
    )
    max_drop_km: float = Field(
        default=8.0, ge=1.0, le=30.0,
        description="Maximum dropoff direction similarity (km)",
    )
    max_time_min: float = Field(
        default=20.0, ge=5.0, le=60.0,
        description="Maximum departure time difference for grouping (minutes)",
    )
    dbscan_eps: float = Field(
        default=1.0, ge=0.1, le=5.0,
        description="DBSCAN epsilon in composite normalized space",
    )
    dbscan_min_samples: int = Field(
        default=2, ge=2, le=5,
        description="Minimum riders to form a cluster (2 = pairs allowed)",
    )
    dry_run: bool = Field(
        default=False,
        description="If true, compute clusters but do NOT create rides in DB",
    )

    model_config = ConfigDict(json_schema_extra={"example": {
        "time_window_minutes": 60,
        "max_pickup_km": 2.0,
        "max_drop_km": 8.0,
        "max_time_min": 20.0,
        "dbscan_eps": 1.0,
        "dbscan_min_samples": 2,
        "dry_run": False,
    }})


# ── Response Schemas ──────────────────────────────────────────────────────────

class ClusterMemberPublic(BaseModel):
    """One passenger member within a cluster."""
    request_id: UUID
    passenger_id: UUID
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float
    departure_time: datetime
    seats_needed: int
    origin_address: str = ""
    destination_address: str = ""


class RideClusterPublic(BaseModel):
    """Public representation of a formed ride cluster."""
    cluster_label: int
    size: int
    total_seats_needed: int
    is_singleton: bool
    centroid_pickup_lat: float
    centroid_pickup_lng: float
    centroid_dropoff_lat: float
    centroid_dropoff_lng: float
    departure_window_start: Optional[datetime]
    departure_window_end: Optional[datetime]
    members: List[ClusterMemberPublic]
    assigned_driver_id: Optional[UUID] = None
    created_ride_id: Optional[UUID] = None


class ClusterRunSummary(BaseModel):
    """Summary of one complete clustering run."""
    run_id: str
    algorithm_used: str
    total_requests_processed: int
    total_clusters_formed: int
    grouped_passengers: int
    solo_passengers: int
    match_rate_pct: float
    elapsed_ms: float
    run_at: datetime
    dry_run: bool
    clusters: List[RideClusterPublic]
    unassigned_clusters: List[RideClusterPublic] = []
    status: str = "completed"
    error: Optional[str] = None


class ClusterStatusResponse(BaseModel):
    """Status of a ride request in the matching system."""
    request_id: UUID
    status: str                        # pending | matched | solo_ride | no_driver
    cluster_label: Optional[int] = None
    cluster_size: Optional[int] = None
    assigned_driver_id: Optional[UUID] = None
    matched_ride_id: Optional[UUID] = None
    estimated_fare: Optional[float] = None
    message: str = ""
