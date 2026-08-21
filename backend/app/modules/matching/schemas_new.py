"""
Pydantic Schemas for Matching Engine

Request and response models for matching API endpoints.
All schemas include validation, examples, and comprehensive documentation.
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, ConfigDict


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class GeoPoint(BaseModel):
    """Geographic coordinate"""
    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lng: float = Field(..., ge=-180, le=180, description="Longitude")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "lat": 31.4697,
                "lng": 74.2728
            }
        }
    )


class TimeWindow(BaseModel):
    """Time window for ride matching"""
    start: datetime = Field(..., description="Window start time")
    end: datetime = Field(..., description="Window end time")

    @field_validator("end")
    @classmethod
    def validate_time_range(cls, end: datetime, info) -> datetime:
        """Ensure end is after start"""
        if "start" in info.data and end <= info.data["start"]:
            raise ValueError("end must be after start")
        return end

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "start": "2025-12-09T08:00:00+05:00",
                "end": "2025-12-09T09:00:00+05:00"
            }
        }
    )


class MatchingPreferences(BaseModel):
    """User preferences for driver matching"""
    max_detour_minutes: int = Field(
        default=15,
        ge=0,
        le=60,
        description="Maximum acceptable detour time in minutes"
    )
    min_driver_rating: float = Field(
        default=3.0,
        ge=0.0,
        le=5.0,
        description="Minimum acceptable driver rating"
    )
    preferred_vehicle_types: Optional[List[str]] = Field(
        default=None,
        description="Preferred vehicle types (sedan, suv, hatchback, etc.)"
    )
    max_price: Optional[Decimal] = Field(
        default=None,
        ge=0,
        description="Maximum acceptable fare"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "max_detour_minutes": 10,
                "min_driver_rating": 4.0,
                "preferred_vehicle_types": ["sedan", "suv"],
                "max_price": 500.00
            }
        }
    )


class MatchingRequest(BaseModel):
    """
    Request to find matching drivers for a passenger.
    
    Two-stage pipeline:
    1. Spatial prefilter (PostGIS or bounding box)
    2. Ranking by match score (detour + driver quality + preferences)
    """
    user_id: UUID = Field(..., description="Passenger user ID")
    pickup: GeoPoint = Field(..., description="Pickup location")
    dropoff: GeoPoint = Field(..., description="Dropoff location")
    time_window: Optional[TimeWindow] = Field(
        default=None,
        description="Optional time window for ride"
    )
    preferences: MatchingPreferences = Field(
        default_factory=MatchingPreferences,
        description="Matching preferences"
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of candidates to return"
    )
    explain: bool = Field(
        default=False,
        description="Include score breakdown for debugging"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "pickup": {"lat": 31.4697, "lng": 74.2728},
                "dropoff": {"lat": 31.5204, "lng": 74.3587},
                "time_window": {
                    "start": "2025-12-09T08:00:00+05:00",
                    "end": "2025-12-09T09:00:00+05:00"
                },
                "preferences": {
                    "max_detour_minutes": 10,
                    "min_driver_rating": 4.0,
                    "max_price": 500.00
                },
                "limit": 10,
                "explain": False
            }
        }
    )


class SimulateRequest(BaseModel):
    """Request to simulate clustering with sample data"""
    num_drivers: int = Field(
        default=20,
        ge=5,
        le=200,
        description="Number of drivers to simulate"
    )
    num_clusters: int = Field(
        default=5,
        ge=2,
        le=20,
        description="Number of clusters to create"
    )
    region_bounds: Optional[dict] = Field(
        default=None,
        description="Geographic bounds {lat_min, lat_max, lng_min, lng_max}"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "num_drivers": 50,
                "num_clusters": 5,
                "region_bounds": {
                    "lat_min": 31.4,
                    "lat_max": 31.6,
                    "lng_min": 74.2,
                    "lng_max": 74.4
                }
            }
        }
    )


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class ScoreBreakdown(BaseModel):
    """Detailed breakdown of match score components"""
    detour_cost: float = Field(..., ge=0, le=1, description="Normalized detour cost (0=best)")
    rating_score: float = Field(..., ge=0, le=1, description="Driver rating component")
    seats_score: float = Field(..., ge=0, le=1, description="Seat availability component")
    preference_score: float = Field(..., ge=0, le=1, description="Preference match component")
    
    detour_weight: float = Field(..., description="Weight applied to detour_cost")
    driver_weight: float = Field(..., description="Weight applied to driver score")
    preference_weight: float = Field(..., description="Weight applied to preferences")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detour_cost": 0.3,
                "rating_score": 0.9,
                "seats_score": 1.0,
                "preference_score": 0.8,
                "detour_weight": 0.5,
                "driver_weight": 0.3,
                "preference_weight": 0.2
            }
        }
    )


class MatchCandidate(BaseModel):
    """A single matched driver candidate"""
    driver_id: UUID = Field(..., description="Driver's user ID")
    ride_id: UUID = Field(..., description="Associated ride ID")
    match_score: float = Field(
        ...,
        ge=0,
        le=1,
        description="Overall match score (0-1, higher is better)"
    )
    estimated_detour_minutes: float = Field(
        ...,
        ge=0,
        description="Estimated additional time for driver"
    )
    eta_to_pickup_minutes: float = Field(
        ...,
        ge=0,
        description="Estimated time to reach pickup location"
    )
    fare_estimate: Decimal = Field(..., ge=0, description="Estimated fare")
    driver_rating: float = Field(..., ge=0, le=5, description="Driver's average rating")
    seats_available: int = Field(..., ge=0, description="Available seats")
    route_overlap_percentage: float = Field(
        ...,
        ge=0,
        le=100,
        description="Percentage of route overlap"
    )
    
    # Optional explainability
    score_breakdown: Optional[ScoreBreakdown] = Field(
        default=None,
        description="Detailed score breakdown (if explain=true)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "driver_id": "987e6543-e21b-12d3-a456-426614174000",
                "ride_id": "456e7890-e21b-12d3-a456-426614174000",
                "match_score": 0.85,
                "estimated_detour_minutes": 5.2,
                "eta_to_pickup_minutes": 3.5,
                "fare_estimate": 250.00,
                "driver_rating": 4.5,
                "seats_available": 3,
                "route_overlap_percentage": 75.0
            }
        }
    )


class MatchingResponse(BaseModel):
    """Response containing matched driver candidates"""
    status: str = Field(default="ok", description="Response status")
    candidates: List[MatchCandidate] = Field(
        ...,
        description="Matched drivers ordered by match_score desc"
    )
    total_candidates: int = Field(..., description="Total candidates found")
    query_time_ms: float = Field(..., description="Query execution time in milliseconds")
    cache_hit: bool = Field(default=False, description="Whether clusters were cached")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "candidates": [
                    {
                        "driver_id": "987e6543-e21b-12d3-a456-426614174000",
                        "ride_id": "456e7890-e21b-12d3-a456-426614174000",
                        "match_score": 0.85,
                        "estimated_detour_minutes": 5.2,
                        "eta_to_pickup_minutes": 3.5,
                        "fare_estimate": 250.00,
                        "driver_rating": 4.5,
                        "seats_available": 3,
                        "route_overlap_percentage": 75.0
                    }
                ],
                "total_candidates": 1,
                "query_time_ms": 145.3,
                "cache_hit": True
            }
        }
    )


class ClusterInfo(BaseModel):
    """Information about a driver cluster"""
    cluster_id: int = Field(..., description="Cluster identifier")
    centroid: GeoPoint = Field(..., description="Cluster centroid coordinates")
    driver_ids: List[UUID] = Field(..., description="Drivers in this cluster")
    size: int = Field(..., description="Number of drivers in cluster")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "cluster_id": 0,
                "centroid": {"lat": 31.5, "lng": 74.3},
                "driver_ids": [
                    "123e4567-e89b-12d3-a456-426614174001",
                    "123e4567-e89b-12d3-a456-426614174002"
                ],
                "size": 2
            }
        }
    )


class SimulateResponse(BaseModel):
    """Response from cluster simulation"""
    status: str = Field(default="ok")
    clusters: List[ClusterInfo] = Field(..., description="Computed clusters")
    num_drivers: int = Field(..., description="Total drivers in simulation")
    num_clusters: int = Field(..., description="Number of clusters created")
    algorithm: str = Field(..., description="Clustering algorithm used")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "clusters": [
                    {
                        "cluster_id": 0,
                        "centroid": {"lat": 31.5, "lng": 74.3},
                        "driver_ids": [
                            "123e4567-e89b-12d3-a456-426614174001"
                        ],
                        "size": 1
                    }
                ],
                "num_drivers": 50,
                "num_clusters": 5,
                "algorithm": "KMeans"
            }
        }
    )
