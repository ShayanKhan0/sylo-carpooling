"""
Ride Cluster Service — Full Pipeline Orchestrator
==================================================

This service ties together every step of the AI carpooling pipeline:

    1. FETCH  — Pull pending ride_requests from PostgreSQL
    2. VECTOR — Build feature matrix (pickup, dropoff, time, seats)
    3. CLUSTER— Run DBSCAN (or K-Means fallback) via RideClusteringEngine
    4. ASSIGN — Match each cluster to the best available driver
    5. PERSIST— Create rides + bookings in the database
    6. NOTIFY — Push FCM/WebSocket notifications to all affected users

The service is designed to run either:
  a) On a periodic background scheduler (every 5 minutes via APScheduler)
  b) On-demand via the `/api/v2/matching/cluster/trigger` endpoint

Author: M. Mobeen Shoukat Ch & M. Shayan Khan (Sylo FYP)
Date: March 2026
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models.ride import Ride
from app.models.ride_request import RideRequest, RideRequestStatus
from app.models.booking import Booking
from app.models.enums import RideStatus
from app.modules.drivers.models import DriverProfile
from app.models.vehicle import Vehicle
from app.core.fare_calculator import calculate_fare
from app.core.fuel_price_engine import load_fuel_config, FuelPriceConfig
from app.core.dynamic_fare import (
    PassengerSegment,
    calculate_full_ride_fares,
    RideFareBreakdown,
)
from app.core.route_membership import check_route_membership, MembershipResult
from app.core.pickup_time_estimator import compute_all_pickup_times, PickupTimeResult

from .ride_clustering_engine import (
    RideClusteringEngine,
    RideFeature,
    RideCluster,
    ClusteringConfig,
    ClusteringResult,
    DriverCandidate,
    DriverAssignment,
    assign_drivers_to_clusters,
)
from .ride_cluster_schemas import (
    ClusterTriggerRequest,
    ClusterRunSummary,
    RideClusterPublic,
    ClusterMemberPublic,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 1: FETCH pending ride requests from DB
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_pending_ride_requests(
    db: AsyncSession,
    window_minutes: int = 60,
) -> List[RideFeature]:
    """
    Pull all PENDING ride requests whose departure_time is within the next
    `window_minutes` minutes from now.

    Args:
        db: Async SQLAlchemy session
        window_minutes: How far ahead to look for ride requests

    Returns:
        List of RideFeature objects ready for clustering
    """
    now = datetime.utcnow()
    window_end = now + timedelta(minutes=window_minutes)

    stmt = (
        select(RideRequest)
        .where(
            and_(
                RideRequest.status == RideRequestStatus.PENDING,
                RideRequest.departure_time >= now,
                RideRequest.departure_time <= window_end,
            )
        )
        .order_by(RideRequest.departure_time.asc())
    )
    result = await db.execute(stmt)
    requests = result.scalars().all()

    features: List[RideFeature] = []
    for r in requests:
        features.append(
            RideFeature(
                request_id=r.id,
                passenger_id=r.passenger_id,
                pickup_lat=r.origin_lat,
                pickup_lng=r.origin_lng,
                dropoff_lat=r.destination_lat,
                dropoff_lng=r.destination_lng,
                departure_time=r.departure_time,
                seats_needed=r.seats_needed,
                max_budget=r.max_budget,
                origin_address=r.origin or "",
                destination_address=r.destination or "",
            )
        )

    logger.info(
        f"Fetched {len(features)} pending ride requests "
        f"(window: now → +{window_minutes}min)"
    )
    return features


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 2: FETCH available drivers
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_available_drivers(db: AsyncSession) -> List[DriverCandidate]:
    """
    Fetch all active, verified drivers with their current vehicle capacity.

    In production this would pull real-time GPS locations from Redis geospatial
    index. For now we use the last telemetry point stored in the DB.

    Returns:
        List of DriverCandidate objects
    """
    # Query active verified drivers with their vehicles
    stmt = (
        select(DriverProfile)
        .where(
            and_(
                DriverProfile.is_verified == True,
                DriverProfile.status == "active",
            )
        )
        .limit(500)
    )
    result = await db.execute(stmt)
    drivers = result.scalars().all()

    candidates: List[DriverCandidate] = []
    for d in drivers:
        # Try to get driver's most recent GPS telemetry point
        driver_lat, driver_lng = await _get_driver_last_location(db, d.user_id)
        if driver_lat is None:
            # Driver has no location data — skip in real-time matching
            # (They can still receive requests through the request-accept flow)
            continue

        # Get vehicle capacity
        vehicle = await _get_driver_active_vehicle(db, d.user_id)
        capacity = vehicle.capacity if vehicle and hasattr(vehicle, 'capacity') else 4

        candidates.append(
            DriverCandidate(
                driver_id=d.user_id,
                user_id=d.user_id,
                current_lat=driver_lat,
                current_lng=driver_lng,
                vehicle_capacity=capacity,
                available_seats=capacity,  # Assume all seats available
                rating=float(d.rating or 4.0),
                vehicle_id=vehicle.id if vehicle else None,
                vehicle_model=f"{vehicle.make} {vehicle.model}" if vehicle else "",
            )
        )

    logger.info(f"Fetched {len(candidates)} available drivers with location data")
    return candidates


async def _get_driver_last_location(
    db: AsyncSession, driver_user_id: UUID
) -> Tuple[Optional[float], Optional[float]]:
    """Get driver's most recent GPS coordinates from telemetry."""
    try:
        from app.models.telemetry_point import TelemetryPoint
        stmt = (
            select(TelemetryPoint.latitude, TelemetryPoint.longitude)
            .where(TelemetryPoint.driver_id == driver_user_id)
            .order_by(TelemetryPoint.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        row = result.first()
        if row:
            return row[0], row[1]
    except Exception as e:
        logger.debug(f"Could not fetch location for driver {driver_user_id}: {e}")
    return None, None


async def _get_driver_active_vehicle(
    db: AsyncSession, driver_user_id: UUID
) -> Optional[Vehicle]:
    """Get driver's currently active vehicle."""
    try:
        stmt = (
            select(Vehicle)
            .where(
                and_(
                    Vehicle.driver_id == driver_user_id,
                    Vehicle.is_active == True,
                )
            )
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.debug(f"Could not fetch vehicle for driver {driver_user_id}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 3+4: CLUSTER + ASSIGN  (delegated to engine)
# ─────────────────────────────────────────────────────────────────────────────

def run_clustering_pipeline(
    rides: List[RideFeature],
    drivers: List[DriverCandidate],
    config: ClusteringConfig,
) -> Tuple[List[DriverAssignment], List[RideCluster], ClusteringResult]:
    """
    Run the full ML clustering + driver assignment pipeline synchronously.

    Args:
        rides: Pending ride request features
        drivers: Available driver candidates
        config: Clustering hyper-parameters

    Returns:
        (assignments, unassigned_clusters, clustering_result)
    """
    engine = RideClusteringEngine(config=config)
    result = engine.cluster(rides)

    if not result.clusters:
        logger.info("No clusters formed — all passengers are solo or no requests")
        return [], [], result

    assignments, unassigned = assign_drivers_to_clusters(
        result.clusters, drivers, config
    )

    # Solo passengers (DBSCAN noise) also need singleton clusters + driver assignment
    if result.noise_requests:
        singleton_assignments, singleton_unassigned = assign_drivers_to_clusters(
            [c for c in result.clusters if c.is_singleton],
            [d for d in drivers if d not in [a.driver for a in assignments]],
            config,
        )
        # Note: singletons are already included in result.clusters

    return assignments, unassigned, result


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 5: PERSIST — create rides + bookings in DB
# ─────────────────────────────────────────────────────────────────────────────

async def persist_cluster_as_ride(
    db: AsyncSession,
    assignment: DriverAssignment,
    fuel_config: Optional[FuelPriceConfig] = None,
) -> Optional[UUID]:
    """
    Create one Ride and N RideBookings from a driver-cluster assignment.

    Enhanced Flow (Modules 1-4 integrated):
        1. Load live fuel price config (Module 1)
        2. Route membership check per passenger (Module 3)
        3. Proportional dynamic fare per passenger (Module 2)
        4. Pre-compute pickup ETAs (Module 4)
        5. Persist Ride + Bookings with all new fields
        6. Update RideRequests → ACCEPTED

    Returns:
        UUID of the created Ride, or None on failure
    """
    cluster = assignment.cluster
    driver = assignment.driver

    try:
        from app.modules.matching.utils import calculate_distance

        # ── Step 1: Live fuel price config ────────────────────────────────
        if fuel_config is None:
            fuel_config = await load_fuel_config(db)

        route_km = calculate_distance(
            cluster.centroid_pickup_lat, cluster.centroid_pickup_lng,
            cluster.centroid_dropoff_lat, cluster.centroid_dropoff_lng,
        )
        total_route_km = max(route_km, 0.5)
        departure = (
            cluster.departure_window_start
            or datetime.utcnow() + timedelta(minutes=30)
        )
        encoded_polyline: Optional[str] = getattr(cluster, "encoded_polyline", None)

        # ── Step 2: Route membership + segment distances (Module 3) ───────
        passenger_segments: List[PassengerSegment] = []
        member_membership: Dict[str, MembershipResult] = {}

        for member in cluster.member_requests:
            if encoded_polyline:
                membership = check_route_membership(
                    pickup_lat=member.pickup_lat,
                    pickup_lng=member.pickup_lng,
                    dropoff_lat=member.dropoff_lat,
                    dropoff_lng=member.dropoff_lng,
                    passenger_departure_time=member.departure_time,
                    encoded_polyline=encoded_polyline,
                    ride_departure_time=departure,
                )
                if not membership.is_eligible:
                    logger.warning(
                        f"Passenger {member.passenger_id} failed membership: "
                        f"{membership.rejection_reason} — using straight-line fallback"
                    )
                    seg_km = calculate_distance(
                        member.pickup_lat, member.pickup_lng,
                        member.dropoff_lat, member.dropoff_lng,
                    )
                    membership = MembershipResult(
                        is_eligible=True,
                        pickup_pct=0.0,
                        dropoff_pct=min(seg_km / total_route_km, 1.0),
                        pickup_route_km=0.0,
                        dropoff_route_km=seg_km,
                        segment_km=seg_km,
                    )
            else:
                seg_km = calculate_distance(
                    member.pickup_lat, member.pickup_lng,
                    member.dropoff_lat, member.dropoff_lng,
                )
                membership = MembershipResult(
                    is_eligible=True,
                    pickup_pct=0.0,
                    dropoff_pct=min(seg_km / total_route_km, 1.0),
                    pickup_route_km=0.0,
                    dropoff_route_km=seg_km,
                    segment_km=seg_km,
                )

            member_membership[str(member.request_id)] = membership
            passenger_segments.append(
                PassengerSegment(
                    passenger_id=member.passenger_id,
                    request_id=member.request_id,
                    segment_km=max(membership.segment_km, 0.5),
                    seats_needed=member.seats_needed,
                    pickup_pct=membership.pickup_pct,
                    dropoff_pct=membership.dropoff_pct,
                )
            )

        # ── Step 3: Dynamic proportional fares (Module 2) ─────────────────
        fare_breakdown: RideFareBreakdown = calculate_full_ride_fares(
            passengers=passenger_segments,
            total_route_km=total_route_km,
            config=fuel_config,
        )
        fare_by_request: Dict[str, float] = {
            str(pf.request_id): pf.final_fare_pkr
            for pf in fare_breakdown.passenger_fares
        }
        avg_fare = fare_breakdown.total_collected_pkr / max(cluster.total_seats_needed, 1)
        price_per_seat = Decimal(str(round(avg_fare, 2)))

        # ── Step 4: Pre-compute pickup ETAs (Module 4) ────────────────────
        passengers_for_eta = [
            {
                "passenger_id": m.passenger_id,
                "request_id": m.request_id,
                "pickup_lat": m.pickup_lat,
                "pickup_lng": m.pickup_lng,
                "pickup_pct": member_membership[str(m.request_id)].pickup_pct,
                "pickup_route_km": member_membership[str(m.request_id)].pickup_route_km,
                "dropoff_lat": m.dropoff_lat,
                "dropoff_lng": m.dropoff_lng,
                "dropoff_pct": member_membership[str(m.request_id)].dropoff_pct,
                "dropoff_route_km": member_membership[str(m.request_id)].dropoff_route_km,
                "segment_km": member_membership[str(m.request_id)].segment_km,
            }
            for m in cluster.member_requests
        ]

        try:
            from app.core.config import settings as _settings
            gmaps_key = _settings.resolved_google_maps_key() or None
        except Exception:
            gmaps_key = None

        eta_by_request: Dict[str, PickupTimeResult] = await compute_all_pickup_times(
            passengers=passengers_for_eta,
            ride_departure_time=departure,
            route_start_lat=cluster.centroid_pickup_lat,
            route_start_lng=cluster.centroid_pickup_lng,
            config=fuel_config,
            google_maps_key=gmaps_key,
            use_google_api=False,
        )

        # ── Step 5: Create Ride ────────────────────────────────────────────
        new_ride = Ride(
            id=uuid.uuid4(),
            driver_id=driver.driver_id,
            vehicle_id=driver.vehicle_id,
            start_point_lat=cluster.centroid_pickup_lat,
            start_point_lng=cluster.centroid_pickup_lng,
            end_point_lat=cluster.centroid_dropoff_lat,
            end_point_lng=cluster.centroid_dropoff_lng,
            departure_time=departure,
            seats_available=driver.available_seats,
            price_per_seat=price_per_seat,
            status=RideStatus.OPEN,
            route_distance_km=total_route_km,
            polyline=encoded_polyline,
        )
        db.add(new_ride)
        await db.flush()

        # ── Step 6: Create Bookings + update RideRequests ──────────────────
        for member in cluster.member_requests:
            rid_str = str(member.request_id)
            membership = member_membership[rid_str]
            pf = next(
                (f for f in fare_breakdown.passenger_fares
                 if str(f.request_id) == rid_str),
                None,
            )
            eta_result = eta_by_request.get(rid_str)

            individual_fare = (
                Decimal(str(pf.final_fare_pkr))
                if pf else price_per_seat * member.seats_needed
            )
            estimated_pickup = eta_result.estimated_pickup_time if eta_result else departure

            booking = Booking(
                id=uuid.uuid4(),
                ride_id=new_ride.id,
                passenger_id=member.passenger_id,
                seats_reserved=member.seats_needed,
                fare=individual_fare,
                individual_fare=individual_fare,
                estimated_pickup_time=estimated_pickup,
                segment_km=membership.segment_km,
                pickup_pct=membership.pickup_pct,
                dropoff_pct=membership.dropoff_pct,
                pickup_route_km=membership.pickup_route_km,
                dropoff_route_km=membership.dropoff_route_km,
                rate_per_km_used=fuel_config.rate_per_km,
                status="confirmed",
            )
            db.add(booking)

            await db.execute(
                update(RideRequest)
                .where(RideRequest.id == member.request_id)
                .values(
                    status=RideRequestStatus.ACCEPTED,
                    accepted_by_driver_id=driver.driver_id,
                    ride_id=new_ride.id,
                    updated_at=datetime.utcnow(),
                )
            )

        await db.commit()
        logger.info(
            f"Created ride {new_ride.id} | cluster={cluster.cluster_label} | "
            f"driver={driver.driver_id} | {cluster.size} passengers | "
            f"total_collected={fare_breakdown.total_collected_pkr:.0f} PKR | "
            f"rate={fuel_config.rate_per_km:.2f} PKR/km"
        )
        return new_ride.id

    except Exception as exc:
        await db.rollback()
        logger.error(
            f"Failed to persist cluster {cluster.cluster_label}: {exc}",
            exc_info=True,
        )
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 6: NOTIFY passengers + driver
# ─────────────────────────────────────────────────────────────────────────────

async def notify_cluster_participants(
    db: AsyncSession,
    assignment: DriverAssignment,
    ride_id: UUID,
) -> None:
    """
    Send FCM push notifications to all passengers and the assigned driver.

    Notifications:
        - Passengers: "Your ride has been matched! Departs at HH:MM"
        - Driver:     "New carpooling ride assigned: N passengers"
    """
    try:
        from app.modules.notifications.notification_service import send_push_notification

        cluster = assignment.cluster
        departure_str = (
            cluster.departure_window_start.strftime("%H:%M")
            if cluster.departure_window_start
            else "soon"
        )

        # Notify each passenger
        for member in cluster.member_requests:
            await send_push_notification(
                db=db,
                user_id=member.passenger_id,
                title="Ride Matched! 🚗",
                body=(
                    f"Great news! You've been matched with "
                    f"{cluster.size - 1} other passenger(s). "
                    f"Departs at {departure_str}."
                ) if not cluster.is_singleton else (
                    f"Your ride is confirmed. Departs at {departure_str}."
                ),
                data={
                    "type": "ride_matched",
                    "ride_id": str(ride_id),
                    "cluster_size": str(cluster.size),
                },
            )

        # Notify driver
        await send_push_notification(
            db=db,
            user_id=assignment.driver.user_id,
            title="New Ride Assignment 📍",
            body=(
                f"You have a new carpooling ride with {cluster.total_seats_needed} "
                f"passengers. Pickup at {departure_str}."
            ),
            data={
                "type": "ride_assigned",
                "ride_id": str(ride_id),
                "passenger_count": str(cluster.size),
            },
        )

    except Exception as exc:
        # Notifications are non-critical — log but don't fail the pipeline
        logger.warning(f"Notification failed for cluster {assignment.cluster.cluster_label}: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN PIPELINE ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

async def run_full_clustering_pipeline(
    db: AsyncSession,
    request: ClusterTriggerRequest,
    run_id: Optional[str] = None,
) -> ClusterRunSummary:
    """
    Execute the complete AI carpooling pipeline end-to-end.

    Steps:
        1. Fetch pending ride requests from DB (within time window)
        2. Fetch available drivers
        3. Build feature matrix and run DBSCAN clustering
        4. Assign best driver to each cluster
        5. Persist rides + bookings (unless dry_run=True)
        6. Send notifications
        7. Return full summary

    Args:
        db: Async database session
        request: Clustering parameters from API or scheduler
        run_id: Optional identifier for this run (for idempotency)

    Returns:
        ClusterRunSummary with full results
    """
    import time
    start = time.perf_counter()
    run_id = run_id or str(uuid.uuid4())[:8]

    logger.info(
        f"[run_id={run_id}] Starting full clustering pipeline | "
        f"window={request.time_window_minutes}min | dry_run={request.dry_run}"
    )

    try:
        # ── Step 1: Fetch ride requests ────────────────────────────────────
        rides = await fetch_pending_ride_requests(
            db, window_minutes=request.time_window_minutes
        )
        if not rides:
            logger.info(f"[run_id={run_id}] No pending ride requests. Pipeline skipped.")
            return ClusterRunSummary(
                run_id=run_id,
                algorithm_used="none",
                total_requests_processed=0,
                total_clusters_formed=0,
                grouped_passengers=0,
                solo_passengers=0,
                match_rate_pct=0.0,
                elapsed_ms=0.0,
                run_at=datetime.utcnow(),
                dry_run=request.dry_run,
                clusters=[],
                status="skipped",
            )

        # ── Step 2: Fetch drivers ──────────────────────────────────────────
        drivers = await fetch_available_drivers(db)

        # ── Step 3+4: Cluster + Assign ─────────────────────────────────────
        config = ClusteringConfig(
            max_pickup_km=request.max_pickup_km,
            max_drop_km=request.max_drop_km,
            max_time_min=request.max_time_min,
            dbscan_eps=request.dbscan_eps,
            dbscan_min_samples=request.dbscan_min_samples,
        )
        assignments, unassigned_clusters, clustering_result = run_clustering_pipeline(
            rides, drivers, config
        )

        created_ride_ids: Dict[int, Optional[UUID]] = {}

        # ── Step 5: Persist (skip if dry_run) ─────────────────────────────
        if not request.dry_run:
            # Load fuel config once for all clusters in this run
            shared_fuel_config = await load_fuel_config(db)

            for assignment in assignments:
                ride_id = await persist_cluster_as_ride(
                    db, assignment, fuel_config=shared_fuel_config
                )
                created_ride_ids[assignment.cluster.cluster_label] = ride_id

                if ride_id:
                    await notify_cluster_participants(db, assignment, ride_id)

        # ── Step 7: Build summary ──────────────────────────────────────────
        grouped_count = sum(
            c.size for c in clustering_result.clusters if not c.is_singleton
        )
        solo_count = clustering_result.noise_count + sum(
            1 for c in clustering_result.clusters if c.is_singleton
        )

        cluster_publics = []
        for assignment in assignments:
            c = assignment.cluster
            ride_id = created_ride_ids.get(c.cluster_label)
            cluster_publics.append(
                RideClusterPublic(
                    cluster_label=c.cluster_label,
                    size=c.size,
                    total_seats_needed=c.total_seats_needed,
                    is_singleton=c.is_singleton,
                    centroid_pickup_lat=c.centroid_pickup_lat,
                    centroid_pickup_lng=c.centroid_pickup_lng,
                    centroid_dropoff_lat=c.centroid_dropoff_lat,
                    centroid_dropoff_lng=c.centroid_dropoff_lng,
                    departure_window_start=c.departure_window_start,
                    departure_window_end=c.departure_window_end,
                    members=[
                        ClusterMemberPublic(
                            request_id=m.request_id,
                            passenger_id=m.passenger_id,
                            pickup_lat=m.pickup_lat,
                            pickup_lng=m.pickup_lng,
                            dropoff_lat=m.dropoff_lat,
                            dropoff_lng=m.dropoff_lng,
                            departure_time=m.departure_time,
                            seats_needed=m.seats_needed,
                            origin_address=m.origin_address,
                            destination_address=m.destination_address,
                        )
                        for m in c.member_requests
                    ],
                    assigned_driver_id=assignment.driver.driver_id,
                    created_ride_id=ride_id,
                )
            )

        unassigned_publics = [
            RideClusterPublic(
                cluster_label=c.cluster_label,
                size=c.size,
                total_seats_needed=c.total_seats_needed,
                is_singleton=c.is_singleton,
                centroid_pickup_lat=c.centroid_pickup_lat,
                centroid_pickup_lng=c.centroid_pickup_lng,
                centroid_dropoff_lat=c.centroid_dropoff_lat,
                centroid_dropoff_lng=c.centroid_dropoff_lng,
                departure_window_start=c.departure_window_start,
                departure_window_end=c.departure_window_end,
                members=[
                    ClusterMemberPublic(
                        request_id=m.request_id,
                        passenger_id=m.passenger_id,
                        pickup_lat=m.pickup_lat,
                        pickup_lng=m.pickup_lng,
                        dropoff_lat=m.dropoff_lat,
                        dropoff_lng=m.dropoff_lng,
                        departure_time=m.departure_time,
                        seats_needed=m.seats_needed,
                        origin_address=m.origin_address,
                        destination_address=m.destination_address,
                    )
                    for m in c.member_requests
                ],
            )
            for c in unassigned_clusters
        ]

        elapsed_ms = (time.perf_counter() - start) * 1000.0

        summary = ClusterRunSummary(
            run_id=run_id,
            algorithm_used=clustering_result.algorithm_used,
            total_requests_processed=clustering_result.total_requests,
            total_clusters_formed=clustering_result.total_clusters,
            grouped_passengers=grouped_count,
            solo_passengers=solo_count,
            match_rate_pct=round(clustering_result.match_rate * 100, 1),
            elapsed_ms=round(elapsed_ms, 1),
            run_at=clustering_result.run_at,
            dry_run=request.dry_run,
            clusters=cluster_publics,
            unassigned_clusters=unassigned_publics,
            status="completed",
        )

        logger.info(
            f"[run_id={run_id}] Pipeline complete | "
            f"algorithm={clustering_result.algorithm_used} | "
            f"{len(assignments)} rides created | "
            f"match_rate={summary.match_rate_pct:.1f}% | "
            f"{elapsed_ms:.0f}ms"
        )
        return summary

    except Exception as exc:
        logger.error(
            f"[run_id={run_id}] Pipeline failed: {exc}",
            exc_info=True,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return ClusterRunSummary(
            run_id=run_id,
            algorithm_used="unknown",
            total_requests_processed=0,
            total_clusters_formed=0,
            grouped_passengers=0,
            solo_passengers=0,
            match_rate_pct=0.0,
            elapsed_ms=round(elapsed_ms, 1),
            run_at=datetime.utcnow(),
            dry_run=request.dry_run,
            clusters=[],
            status="error",
            error=str(exc),
        )
