"""
Background task helpers executed with FastAPI's native scheduling utilities.

This package now exposes plain async functions that can be dispatched via
FastAPI's ``BackgroundTasks`` or the lightweight scheduler in
``app.core.background``. Celery is no longer required.
"""

__all__: list[str] = []
