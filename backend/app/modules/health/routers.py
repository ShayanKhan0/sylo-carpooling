"""
Module: Health Check
Purpose: Comprehensive health check and system status endpoints.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Provides endpoints for monitoring service health, dependencies, and system metrics.
       Used by load balancers, monitoring tools (Prometheus, Grafana), and alerting systems.
"""

import os
from pathlib import Path
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db, check_database_connection
from app.core.config import settings
from app.core.responses import success_response, error_response

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/")
async def healthz():
    """
    Basic health check endpoint for load balancers.

    Returns:
        dict: Service health status

    Notes:
        - Lightweight endpoint with minimal checks
        - Used by Kubernetes liveness probes, AWS ALB health checks, etc.
        - Should return 200 if service is running
    """
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
    }


@router.get("/ready")
async def readiness_check():
    """
    Readiness check endpoint for load balancers.
    Checks if service is ready to accept traffic.

    Returns:
        dict: Service readiness status

    Notes:
        - Used by Kubernetes readiness probes
        - Checks critical dependencies (database)
        - Returns 200 only if service can handle requests
    """
    # Check database connection
    db_healthy = await check_database_connection()
    
    if not db_healthy:
        return error_response(
            message="Service not ready - database unavailable",
            status_code=503
        )
    
    return {
        "status": "ok",
        "ready": True,
        "service": settings.APP_NAME,
    }


@router.get("/live")
async def liveness_check():
    """
    Liveness check endpoint - minimal health check.

    Returns:
        dict: Service liveness status

    Notes:
        - Used by Kubernetes liveness probes
        - Only checks if application process is running
        - Does not check dependencies
    """
    return {"status": "ok", "alive": True}


async def check_cache_status() -> str:
    """
    Check in-memory cache health.

    Returns:
        str: "ok", "error", or "not_configured"
    """
    try:
        from app.core.cache import get_cache_client
        client = get_cache_client()
        if client is not None:
            return "ok"
        return "not_configured"
    except Exception:
        return "error"


async def check_fcm_credentials() -> str:
    """
    Check if FCM credentials file exists and is readable.

    Returns:
        str: "ok", "error", or "not_configured"
    """
    try:
        if not settings.FCM_CREDENTIALS_PATH:
            return "not_configured"
        
        fcm_path = Path(settings.FCM_CREDENTIALS_PATH)
        if fcm_path.exists() and fcm_path.is_file():
            return "ok"
        else:
            return "error"
    except Exception:
        return "error"


@router.get("/detailed")
async def health_detailed():
    """
    Comprehensive health check with all component status.
    Checks database, cache, FCM credentials, and system metrics.

    Returns:
        dict: Detailed health status of all components

    Response Format:
        {
            "status": "ok" | "degraded" | "error",
            "service": "SmartCarpoolingApp",
            "version": "1.0.0",
            "environment": "production",
            "components": {
                "database": "ok" | "error" | "not_configured",
                "cache": "ok" | "error" | "not_configured",
                "fcm": "ok" | "error" | "not_configured"
            },
            "system": {
                "uptime_seconds": 12345,
                "log_level": "INFO"
            }
        }

    Notes:
        - Returns 200 with "degraded" status if non-critical components fail
        - Returns 503 if critical components (database) fail
        - Use for monitoring dashboards and alerting
    """
    health_status = {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "components": {},
    }

    # Check database (critical)
    db_status = "ok" if await check_database_connection() else "error"
    health_status["components"]["database"] = db_status
    
    if db_status == "error":
        health_status["status"] = "error"

    # Check cache (non-critical)
    cache_status = await check_cache_status()
    health_status["components"]["cache"] = cache_status
    
    if cache_status == "error":
        health_status["status"] = "degraded"

    # Check FCM credentials (non-critical)
    fcm_status = await check_fcm_credentials()
    health_status["components"]["fcm"] = fcm_status
    
    if fcm_status == "error" and health_status["status"] == "ok":
        health_status["status"] = "degraded"

    # Add system information
    health_status["system"] = {
        "log_level": settings.LOG_LEVEL,
        "debug_mode": settings.DEBUG,
    }

    # Return appropriate status code
    if health_status["status"] == "error":
        return error_response(
            message="Health check failed - critical component unavailable",
            status_code=503,
            details=health_status
        )
    
    return health_status


@router.get("/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    """
    Database-specific health check with connection details.

    Args:
        db: Database session dependency

    Returns:
        dict: Database connection status and metrics

    Notes:
        - Tests actual database query execution
        - Returns connection pool information
        - Use for database-specific monitoring
    """
    try:
        # Execute test query
        result = await db.execute(text("SELECT 1 as health_check"))
        result.scalar()
        
        return {
            "status": "ok",
            "database": "connected",
            "pool_size": 10,
            "max_overflow": 20,
        }
    except Exception as e:
        return error_response(
            message=f"Database health check failed: {str(e)}",
            status_code=503,
            error_code="DATABASE_ERROR"
        )
