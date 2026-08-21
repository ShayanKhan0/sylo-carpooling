"""
Background Task: AI Ride Clustering Scheduler
=============================================

Runs the DBSCAN/K-Means ride clustering pipeline on a configurable interval.

Design:
    - Uses APScheduler (AsyncIOScheduler) — no Celery or Redis needed
    - Runs every CLUSTER_INTERVAL_MINUTES minutes
    - Processes ride requests departing in the next CLUSTER_WINDOW_MINUTES
    - Gracefully handles DB unavailability (logs + skips run)
    - Each run is logged to ai_cluster_runs table for analytics

Configuration (set in .env):
    CLUSTER_INTERVAL_MINUTES   = 5    (how often clustering runs)
    CLUSTER_WINDOW_MINUTES     = 60   (how far ahead to look for requests)
    CLUSTER_MAX_PICKUP_KM      = 2.0
    CLUSTER_MAX_DROP_KM        = 8.0
    CLUSTER_MAX_TIME_MIN       = 20.0
    CLUSTER_EPS                = 1.0
    CLUSTER_MIN_SAMPLES        = 2

Author: Sylo Smart Carpooling FYP
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── APScheduler instance (module-level singleton) ─────────────────────────────
_scheduler = None


def get_scheduler():
    """Return (or create) the APScheduler singleton."""
    global _scheduler
    if _scheduler is None:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            _scheduler = AsyncIOScheduler()
            logger.info("APScheduler created")
        except ImportError:
            logger.warning(
                "apscheduler not installed. "
                "Clustering scheduler disabled. "
                "Install with: pip install apscheduler"
            )
    return _scheduler


# ─────────────────────────────────────────────────────────────────────────────
#  CORE TASK FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

async def run_clustering_job(
    interval_minutes: int = 5,
    window_minutes: int = 60,
    max_pickup_km: float = 2.0,
    max_drop_km: float = 8.0,
    max_time_min: float = 20.0,
    dbscan_eps: float = 1.0,
    dbscan_min_samples: int = 2,
) -> None:
    """
    Execute one clustering run. Called by APScheduler periodically.

    This function:
        1. Opens a fresh DB session
        2. Calls the full clustering pipeline
        3. Logs the summary to ai_cluster_runs table
        4. Closes the DB session

    Designed to be resilient — exceptions are caught and logged,
    never propagated (would kill the scheduler).
    """
    run_start = datetime.utcnow()
    logger.info(
        f"⏰ Scheduled clustering job starting at {run_start.strftime('%H:%M:%S')}"
    )

    try:
        from app.db.session import AsyncSessionLocal
        from app.modules.matching.ride_cluster_service import run_full_clustering_pipeline
        from app.modules.matching.ride_cluster_schemas import ClusterTriggerRequest

        trigger = ClusterTriggerRequest(
            time_window_minutes=window_minutes,
            max_pickup_km=max_pickup_km,
            max_drop_km=max_drop_km,
            max_time_min=max_time_min,
            dbscan_eps=dbscan_eps,
            dbscan_min_samples=dbscan_min_samples,
            dry_run=False,
        )

        async with AsyncSessionLocal() as db:
            summary = await run_full_clustering_pipeline(db, trigger)

            # Persist run summary to DB for audit trail
            await _log_cluster_run(db, summary)

        logger.info(
            f"✅ Scheduled clustering complete | "
            f"algorithm={summary.algorithm_used} | "
            f"{summary.total_clusters_formed} clusters | "
            f"{summary.grouped_passengers} grouped | "
            f"match_rate={summary.match_rate_pct:.1f}%"
        )

    except Exception as exc:
        logger.error(
            f"❌ Scheduled clustering job failed: {exc}",
            exc_info=True,
        )


async def _log_cluster_run(db, summary) -> None:
    """Persist a ClusterRunSummary to the ai_cluster_runs table."""
    try:
        from sqlalchemy import text
        await db.execute(
            text("""
                INSERT INTO ai_cluster_runs
                    (id, run_at, algorithm_used, total_requests,
                     total_clusters, grouped_passengers, solo_passengers,
                     match_rate_pct, elapsed_ms, dry_run, status, error_message)
                VALUES
                    (:id, :run_at, :algo, :total_req,
                     :total_cl, :grouped, :solo,
                     :match_rate, :elapsed, :dry_run, :status, :error)
            """),
            {
                "id": summary.run_id,
                "run_at": summary.run_at,
                "algo": summary.algorithm_used,
                "total_req": summary.total_requests_processed,
                "total_cl": summary.total_clusters_formed,
                "grouped": summary.grouped_passengers,
                "solo": summary.solo_passengers,
                "match_rate": summary.match_rate_pct,
                "elapsed": summary.elapsed_ms,
                "dry_run": summary.dry_run,
                "status": summary.status,
                "error": summary.error,
            },
        )
        await db.commit()
    except Exception as exc:
        logger.warning(f"Could not log cluster run to DB: {exc}")
        # Non-critical — don't raise


# ─────────────────────────────────────────────────────────────────────────────
#  SCHEDULER LIFECYCLE
# ─────────────────────────────────────────────────────────────────────────────

def start_clustering_scheduler(
    interval_minutes: int = 5,
    window_minutes: int = 60,
    max_pickup_km: float = 2.0,
    max_drop_km: float = 8.0,
    max_time_min: float = 20.0,
    dbscan_eps: float = 1.0,
    dbscan_min_samples: int = 2,
) -> bool:
    """
    Start the APScheduler for periodic ride clustering.

    Call this from main.py during application startup (lifespan context).

    Returns:
        True if scheduler started, False if APScheduler not available
    """
    scheduler = get_scheduler()
    if scheduler is None:
        return False

    # Add clustering job
    scheduler.add_job(
        run_clustering_job,
        trigger="interval",
        minutes=interval_minutes,
        kwargs={
            "interval_minutes": interval_minutes,
            "window_minutes": window_minutes,
            "max_pickup_km": max_pickup_km,
            "max_drop_km": max_drop_km,
            "max_time_min": max_time_min,
            "dbscan_eps": dbscan_eps,
            "dbscan_min_samples": dbscan_min_samples,
        },
        id="ride_clustering",
        replace_existing=True,
        misfire_grace_time=60,  # Allow 60 seconds leeway for missed runs
    )

    scheduler.start()
    logger.info(
        f"✅ Clustering scheduler started | "
        f"interval={interval_minutes}min | "
        f"window={window_minutes}min ahead | "
        f"eps={dbscan_eps} | min_samples={dbscan_min_samples}"
    )
    return True


def stop_clustering_scheduler() -> None:
    """Stop the APScheduler. Call during application shutdown."""
    scheduler = get_scheduler()
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("✅ Clustering scheduler stopped")
