"""
SmartCarpoolingApp - FastAPI Application Entry Point

Production-ready backend with comprehensive middleware, error handling,
and monitoring capabilities.

Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Date: November 8, 2025
Version: 1.0.0
"""

import asyncio
import os
import certifi
import ssl
from pathlib import Path

# --- CRITICAL SSL FIX FOR WINDOWS FIREBASE ADMIN SDK ---
# Fix 1: Try using the certifi modern bundle
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# Fix 2: Unverified default context bypass for localhost dev Google verification checks
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context
# -------------------------------------------------------

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from sqlalchemy import text

from app.core.config import settings
from app.core.logger import setup_logging
from app.core.middleware import setup_middleware, setup_exception_handlers
from app.db.session import init_db, close_db, engine

# Register ALL models before any router imports so SQLAlchemy mappers resolve
import app.models  # noqa: F401  — triggers import of every model class

# Import routers
from app.modules.auth.routers import router as auth_router
from app.modules.health.routers import router as health_router
from app.modules.users.routers import router as users_router
from app.modules.drivers.routers import router as drivers_router
from app.modules.rides.routers import router as rides_router
from app.modules.matching.routers import router as matching_router
from app.modules.payments.routers import payments_router
# === VERIFICATION FUNCTIONALITY START ===
from app.modules.verification.routers import router as verification_router
# === VERIFICATION FUNCTIONALITY END ===
from app.modules.notifications.routers import router as notifications_router
from app.modules.admin.routers import router as admin_router
from app.modules.telemetry.routers import router as telemetry_router
from app.modules.admin_moderation.routers import router as admin_moderation_router
from app.modules.admin_payouts.routers import router as admin_payouts_router
from app.modules.admin_audit.routers import router as admin_audit_router
from app.modules.admin_sos.routers import router as admin_sos_router
from app.modules.help.routers import router as help_router


# Setup logging first
import logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    Handles database initialization, cache, and health checks.
    """
    # ========== STARTUP ==========
    logger.info("=" * 80)
    logger.info(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.APP_ENV}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info("=" * 80)
    
    # 1. Database initialization
    # DISABLED: Tables already created manually via recreate_tables.py
    # try:
    #     await init_db()
    #     logger.info("✅ Database tables initialized successfully")
    # except Exception as e:
    #     logger.warning(f"⚠️  Database initialization failed: {e}")
    #     logger.warning("Continuing without database connection...")
    logger.info("✅ Using existing database tables (init_db disabled)")
    
    # 2. Database connection health check (bounded — a bad DB_URL must not hang startup forever)
    async def _db_ping():
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(_db_ping(), timeout=8.0)
        logger.info("✅ Database connection verified")
    except asyncio.TimeoutError:
        logger.error(
            "❌ Database ping timed out after 8s — check DB_URL, firewall, and that PostgreSQL is running. "
            "API will start in degraded mode; /healthz should still respond once startup completes."
        )
    except Exception as e:
        logger.error(f"❌ Database connection check failed: {e}")
        logger.warning("Service starting with degraded functionality...")
    
    # 3. Initialize In-Memory Cache
    try:
        from app.core.cache import init_cache
        await init_cache()
        logger.info("✅ In-memory cache initialized successfully")
    except Exception as e:
        logger.warning(f"⚠️  Cache initialization failed: {e}")
        logger.warning("Continuing without cache (rate limiting and caching disabled)...")
    
    # 4. Initialize Firebase Admin SDK (required for /auth/login and /auth/register)
    try:
        from app.core.firebase_admin import initialize_firebase

        fb_app = initialize_firebase()
        if fb_app:
            logger.info("✅ Firebase Admin SDK initialized successfully")
        else:
            logger.warning(
                "⚠️  Firebase Admin SDK not initialized — set FCM_CREDENTIALS_PATH or "
                "GOOGLE_APPLICATION_CREDENTIALS to your service account JSON. "
                "Login/register will return 401 until configured."
            )
    except Exception as e:
        logger.warning(f"⚠️  Firebase Admin SDK initialization failed: {e}")
        logger.warning("Continuing without Firebase authentication...")
    
    # 5. Initialize Notifications Subscriber (WebSocket)
    try:
        from app.modules.notifications.subscriber import get_subscriber
        from app.modules.notifications.websocket_manager import get_websocket_manager
        
        websocket_manager = get_websocket_manager(
            heartbeat_interval=settings.NOTIFICATIONS_HEARTBEAT_INTERVAL
        )
        
        subscriber = await get_subscriber(
            websocket_manager=websocket_manager,
            channel_prefix=settings.NOTIFICATIONS_CHANNEL_PREFIX,
        )
        
        await subscriber.start()
        
        logger.info("✅ Notifications subscriber started (WebSocket)")
        logger.info(f"   🔔 Heartbeat interval: {settings.NOTIFICATIONS_HEARTBEAT_INTERVAL}s")
        logger.info(f"   📡 WebSocket endpoint: ws://localhost:8000/api/v2/notifications/ws/{{user_id}}")
    except Exception as e:
        logger.warning(f"⚠️  Notifications subscriber initialization failed: {e}")
        logger.warning("Continuing without real-time notifications...")
    
    # 6. Start AI Ride Clustering Scheduler (after a tick — avoids blocking the event loop during bind)
    async def _start_clustering_soon():
        try:
            await asyncio.sleep(0.05)
            from app.tasks.clustering_task import start_clustering_scheduler

            cluster_interval = getattr(settings, "CLUSTER_INTERVAL_MINUTES", 5)
            cluster_window = getattr(settings, "CLUSTER_WINDOW_MINUTES", 60)
            started = start_clustering_scheduler(
                interval_minutes=cluster_interval,
                window_minutes=cluster_window,
                max_pickup_km=getattr(settings, "CLUSTER_MAX_PICKUP_KM", 2.0),
                max_drop_km=getattr(settings, "CLUSTER_MAX_DROP_KM", 8.0),
                max_time_min=getattr(settings, "CLUSTER_MAX_TIME_MIN", 20.0),
                dbscan_eps=getattr(settings, "CLUSTER_EPS", 1.0),
                dbscan_min_samples=getattr(settings, "CLUSTER_MIN_SAMPLES", 2),
            )
            if started:
                logger.info(f"✅ AI Clustering scheduler started (every {cluster_interval}min)")
            else:
                logger.warning("⚠️  APScheduler not available — install: pip install apscheduler")
        except Exception as e:
            logger.warning(f"⚠️  AI Clustering scheduler failed to start: {e}")
            logger.warning(
                "Continuing without automatic clustering (use /api/v2/matching/cluster/trigger manually)"
            )

    asyncio.create_task(_start_clustering_soon())

    # 7. Log registered routes
    routes_count = len([route for route in app.routes if hasattr(route, "methods")])
    logger.info(f"✅ Registered {routes_count} API endpoints across 13 modules")
    
    logger.info("=" * 80)
    logger.info(f"🎉 {settings.APP_NAME} is ready to accept requests!")
    logger.info(f"📚 API Documentation: http://localhost:8000/docs")
    logger.info(f"❤️  Health Check: http://localhost:8000/healthz")
    logger.info(f"📊 Detailed Health: http://localhost:8000/api/v1/health/detailed")
    logger.info("=" * 80)
    
    yield
    
    # ========== SHUTDOWN ==========
    logger.info("=" * 80)
    logger.info(f"🛑 Shutting down {settings.APP_NAME}...")
    logger.info("=" * 80)
    
    # 0. Stop AI Clustering Scheduler
    try:
        from app.tasks.clustering_task import stop_clustering_scheduler
        stop_clustering_scheduler()
    except Exception as e:
        logger.warning(f"⚠️  Clustering scheduler cleanup failed: {e}")

    # 1. Stop Notifications Subscriber (Prompt 9)
    try:
        from app.modules.notifications.subscriber import _subscriber
        if _subscriber:
            await _subscriber.stop()
            logger.info("✅ Notifications subscriber stopped gracefully")
    except Exception as e:
        logger.warning(f"⚠️  Notifications subscriber cleanup failed: {e}")
    
    # 2. Close cache
    try:
        from app.core.cache import close_cache
        await close_cache()
        logger.info("\u2705 Cache closed gracefully")
    except Exception as e:
        logger.warning(f"\u26a0\ufe0f  Cache cleanup failed: {e}")
    
    # 3. Close database connections
    try:
        await close_db()
        logger.info("✅ Database connections closed gracefully")
    except Exception as e:
        logger.warning(f"⚠️  Database cleanup failed: {e}")
    
    logger.info("=" * 80)
    logger.info(f"👋 {settings.APP_NAME} shutdown complete")
    logger.info("=" * 80)


# Create FastAPI application with comprehensive metadata
app = FastAPI(
    title="SmartCarpoolingApp API",
    description=(
        "Production-ready backend for Smart Carpooling App (FastAPI + PostgreSQL + AI Modules)\n\n"
        "## Features\n"
        "- 🔐 JWT Authentication & Authorization\n"
        "- 👥 User & Driver Management\n"
        "- 🚗 Ride Booking & Matching\n"
        "- 💳 Payment Processing\n"
        "- 📱 Push Notifications (FCM)\n"
        "- 🔒 Document Verification\n"
        "- 🛡️ Safety AI & Anomaly Detection\n"
        "- 👨‍💼 Admin Dashboard & Analytics\n\n"
        "Built for universities, offices, and schools."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    contact={
        "name": "SmartCarpoolingApp Team",
        "email": settings.ADMIN_EMAIL,
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# Expose backend static files (verification uploads, etc.) for authenticated UI rendering.
_static_dir = Path(__file__).resolve().parents[1] / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


# Setup middleware (CORS, GZip, Security Headers, Logging, etc.)
setup_middleware(app)

# Setup exception handlers (HTTPException, ValidationError, etc.)
setup_exception_handlers(app)

# Setup Prometheus metrics (optional, graceful fallback)
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/healthz", "/metrics"],
        env_var_name="ENABLE_METRICS",
        inprogress_name="fastapi_inprogress",
        inprogress_labels=True,
    )
    
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=True)
    logger.info("✅ Prometheus metrics enabled at /metrics")
    
except ImportError:
    logger.warning("⚠️  prometheus-fastapi-instrumentator not installed. Metrics endpoint disabled.")
    logger.warning("   Install with: pip install prometheus-fastapi-instrumentator")
except Exception as e:
    logger.warning(f"⚠️  Failed to setup Prometheus metrics: {e}")


# ========== Register all API routers ==========
# Note: Order matters for route matching. More specific routes should come first.

# 1. Health & Monitoring (no auth required)
app.include_router(
    health_router,
    prefix="/api/v1",
    tags=["Health & Monitoring"]
)

# 2. Authentication (public endpoints)
app.include_router(
    auth_router,
    prefix="/api/v1",
    tags=["Authentication"]
)

# 2b. In-app Help & FAQ content (public endpoint)
app.include_router(
    help_router,
    prefix="/api/v1",
    tags=["Help"]
)

# 3. User Management (auth required)
app.include_router(
    users_router,
    prefix="/api/v1",
    tags=["Users"]
)

# 4. Driver Management (auth required)
app.include_router(
    drivers_router,
    prefix="/api/v1",
    tags=["Drivers"]
)

# 5. Ride Management (auth required)
app.include_router(
    rides_router,
    prefix="/api/v1",
    tags=["Rides"]
)

# 5b. Rides V2 - Prompt 5 (atomic booking, geo-search, schedules)
from app.modules.rides.routers_v2 import router as rides_v2_router
app.include_router(
    rides_v2_router,
    tags=["Rides V2 (Prompt 5)"]
)

# 6. Matching Engine (auth required)
app.include_router(
    matching_router,
    prefix="/api/v1",
    tags=["Matching Engine"]
)

# 6b. Matching Engine V2 - Prompt 6 (ML-powered matching)
from app.modules.matching.routers_new import router as matching_v2_router
app.include_router(
    matching_v2_router,
    prefix="/api/v2",
    tags=["Matching V2 (Prompt 6)"]
)

# 7. Payments (auth required)
app.include_router(
    payments_router,
    tags=["Payments"]
)

# 7b. Payments V2 - Prompt 10 (Pluggable Adapters: Easypaisa, JazzCash, Card)
from app.modules.payments.routers_prompt10 import payments_prompt10_router
app.include_router(
    payments_prompt10_router,
    tags=["Payments V2 (Prompt 10 - Adapters)"]
)

# 8. Verification & KYC (auth required)
# === VERIFICATION FUNCTIONALITY START ===
app.include_router(
    verification_router,
    prefix="/api/v1",
    tags=["Verification & KYC"]
)
# === VERIFICATION FUNCTIONALITY END ===

# 9. Notifications & Alerts (auth required)
app.include_router(
    notifications_router,
    prefix="/api/v1",
    tags=["Notifications & Alerts"]
)

# Note: V2 notifications removed — same router was registered twice.
# WebSocket and real-time features are already included in the v1 router.

# 10. Safety AI & Monitoring (auth required)
from app.modules.safety_ai.routers import router as safety_ai_router
app.include_router(
    safety_ai_router,
    prefix="/api/v1",
    tags=["Safety AI & Monitoring"]
)

# 11. Admin Panel (admin auth required)
app.include_router(
    admin_router,
    prefix="/api/v1",
    tags=["Admin Panel"]
)

# 11b. Admin Auth (admin-only login)
from app.modules.admin_auth.routers import router as admin_auth_router
app.include_router(
    admin_auth_router,
    prefix="/api/admin",
    tags=["Admin Auth"]
)

# 11c. Admin Moderation (admin-only)
app.include_router(
    admin_moderation_router,
    prefix="/api/admin",
    tags=["Admin Moderation (Prompt 12B)"]
)

# 11d. Admin Payouts (admin-only)
app.include_router(
    admin_payouts_router,
    prefix="/api/admin",
    tags=["Admin Payouts (Prompt 12C)"]
)

# 11e. Admin Audit Logs (admin-only)
app.include_router(
    admin_audit_router,
    prefix="/api/admin",
    tags=["Admin Audit (Prompt 12D)"]
)

# 11f. Admin SOS Monitoring (admin-only)
app.include_router(
    admin_sos_router,
    prefix="/api/admin",
    tags=["Admin SOS Monitoring"]
)

# 12. Telemetry Ingestion & Streaming (auth required)
app.include_router(
    telemetry_router,
    prefix="/api/v2",
    tags=["Telemetry"]
)

# 12b. Trips Workflow Orchestration (auth required)
from app.modules.trips.routers import router as trips_router
app.include_router(
    trips_router,
    tags=["Trips (Workflow)"]
)

# 13. Ratings System (auth required) - Prompt 11
from app.modules.ratings.routers import router as ratings_router
app.include_router(
    ratings_router,
    prefix="/api/v1",
    tags=["Ratings (Prompt 11)"]
)

# 14. History & Earnings (auth required) - Prompt 11B
from app.modules.history.routers import router as history_router
app.include_router(
    history_router,
    prefix="/api/v1",
    tags=["Trip History (Prompt 11B)"]
)

# 15. Driver Earnings & Reports (driver only) - Prompt 11C
from app.modules.earnings.routers import router as earnings_router
app.include_router(
    earnings_router,
    prefix="/api/v1/earnings",
    tags=["Driver Earnings (Prompt 11C)"]
)

# 16. Analytics & Reporting (admin only) - Prompt 11
# (Endpoints will be registered after Prompt 11D-1)
from app.modules.analytics.routers import router as analytics_router
app.include_router(
    analytics_router,
    prefix="/api/v1",
    tags=["Analytics (Prompt 11D-2)"]
)

# 17. In-app Chat (ride-scoped messaging)
from app.modules.chat.routers import router as chat_router
app.include_router(
    chat_router,
    prefix="/api/v1/chat",
    tags=["Chat"]
)

# 18. Maps Proxy (Google Maps API proxy for Flutter Web — avoids CORS)
from app.modules.maps.routers import router as maps_proxy_router
app.include_router(
    maps_proxy_router,
    tags=["Maps Proxy"]
)

# 19. AI Ride Clustering (DBSCAN + K-Means hybrid)
from app.modules.matching.ride_cluster_routers import router as ride_cluster_router
app.include_router(
    ride_cluster_router,
    prefix="/api/v2",
    tags=["AI Ride Clustering"]
)

# 20. Dynamic Pricing (Fuel Price Engine + Proportional Fare + Route Check + ETAs)
from app.modules.matching.dynamic_pricing_routers import router as dynamic_pricing_router
app.include_router(
    dynamic_pricing_router,
    prefix="/api/v2",
    tags=["Dynamic Pricing"]
)



# ========== Root & Health Endpoints ==========

@app.get("/")
async def root():
    """
    Root endpoint - API information and quick links.
    
    Returns:
        dict: API metadata with navigation links
        
    Example Response:
        {
            "status": "ok",
            "data": {
                "name": "SmartCarpoolingApp API",
                "version": "1.0.0",
                "environment": "production",
                "docs": "/docs",
                "redoc": "/redoc",
                "health": "/healthz",
                "api_base": "/api/v1"
            }
        }
    """
    return {
        "status": "ok",
        "data": {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV,
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
            "health": "/healthz",
            "health_detailed": "/api/v1/health/detailed",
            "api_base": "/api/v1",
        }
    }


@app.get("/healthz")
async def healthz():
    """
    Simple health check endpoint for load balancers.
    Lightweight check without database dependencies.
    
    Returns:
        dict: Service status
        
    Notes:
        - Use this for Kubernetes liveness probes
        - Use /api/v1/health/ready for readiness probes
        - Use /api/v1/health/detailed for full health status
    """
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
