"""Lightweight periodic task scheduler for FastAPI.

This module replaces the previous Celery-based worker/beat setup with a
simple, in-process scheduler that relies on ``asyncio``. Each task is
executed sequentially on the event loop with configurable intervals.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, List

logger = logging.getLogger(__name__)


@dataclass
class TaskSpec:
    """Metadata describing a periodic background task."""

    name: str
    interval_seconds: int
    coroutine_factory: Callable[[], Awaitable]


_periodic_tasks: List[asyncio.Task] = []
_task_specs: List[TaskSpec] | None = None


def _build_task_specs() -> List[TaskSpec]:
    """Lazily construct the periodic task specification list."""
    global _task_specs

    if _task_specs is not None:
        return _task_specs

    from app.tasks import ai_tasks, analytics_tasks, payment_tasks

    _task_specs = [
        TaskSpec(
            name="analytics.update_system_stats",
            interval_seconds=600,
            coroutine_factory=analytics_tasks.update_system_stats,
        ),
        TaskSpec(
            name="payments.process_pending_settlements",
            interval_seconds=300,
            coroutine_factory=payment_tasks.process_pending_settlements,
        ),
        TaskSpec(
            name="safety_ai.check_ride_anomalies",
            interval_seconds=1800,
            coroutine_factory=ai_tasks.check_ride_anomalies,
        ),
        TaskSpec(
            name="matching.refresh_driver_clusters",
            interval_seconds=300,
            coroutine_factory=analytics_tasks.refresh_driver_clusters_task,
        ),
    ]
    return _task_specs


async def _run_periodic_task(spec: TaskSpec):
    """Execute a coroutine periodically until cancelled."""
    logger.info(
        "⚙️  Starting periodic task %s (interval=%ss)", spec.name, spec.interval_seconds
    )
    try:
        while True:
            try:
                result = spec.coroutine_factory()
                if asyncio.iscoroutine(result):
                    await result
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Background task %s failed: %s", spec.name, exc)
            await asyncio.sleep(spec.interval_seconds)
    finally:
        logger.info("🛑 Periodic task %s stopped", spec.name)


async def start_background_tasks():
    """Create asyncio tasks for each registered periodic job."""
    if _periodic_tasks:
        logger.debug("Background tasks already running")
        return

    for spec in _build_task_specs():
        task = asyncio.create_task(_run_periodic_task(spec))
        _periodic_tasks.append(task)

    logger.info("✅ Started %d background tasks", len(_periodic_tasks))


async def stop_background_tasks():
    """Cancel and await all periodic tasks."""
    if not _periodic_tasks:
        return

    logger.info("🧹 Stopping %d background tasks", len(_periodic_tasks))

    for task in list(_periodic_tasks):
        task.cancel()

    for task in list(_periodic_tasks):
        try:
            await task
        except asyncio.CancelledError:
            pass

    _periodic_tasks.clear()


def get_background_status() -> dict:
    """Return diagnostic information for admin/health endpoints."""
    specs = _build_task_specs()
    return {
        "task_count": len(specs),
        "running": len(_periodic_tasks),
        "tasks": [spec.name for spec in specs],
    }
