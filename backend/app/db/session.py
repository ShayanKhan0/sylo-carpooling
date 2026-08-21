"""
Purpose: Database session management with async SQLAlchemy.
         Provides async database engine and session dependency for FastAPI.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 7, 2025
Notes: Uses asyncpg driver for PostgreSQL async operations.
       Session is managed via dependency injection for proper cleanup.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# Create async engine with optimized connection pooling for production
engine = create_async_engine(
    settings.DB_URL,
    echo=settings.DEBUG,  # Log SQL queries in debug mode
    pool_size=10,  # Base connection pool size
    max_overflow=20,  # Additional connections beyond pool_size
    pool_pre_ping=True,  # Verify connections before using (health check)
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_timeout=30,  # Timeout for getting connection from pool
    echo_pool=False,  # Don't log pool operations
    connect_args={
        # Fail fast if PostgreSQL is unreachable (otherwise connect can hang a long time)
        "timeout": 10,
        "server_settings": {
            "application_name": settings.APP_NAME
        }
    },
)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get database session.
    Automatically manages session lifecycle (create, commit, rollback, close).

    Yields:
        AsyncSession: Database session for queries

    Example:
        >>> @app.get("/users")
        >>> async def get_users(db: AsyncSession = Depends(get_db)):
        >>>     result = await db.execute(select(User))
        >>>     return result.scalars().all()

    Notes:
        - Use this as FastAPI dependency: Depends(get_db)
        - Session is automatically closed after request
        - Rolls back on exceptions to maintain data integrity
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {str(e)}")
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database tables.
    Creates all tables defined in models if they don't exist.

    Returns:
        None

    Notes:
        This should be called on application startup.
        In production, use Alembic migrations instead.
    """
    from app.db.base import Base
    
    # Import all models to ensure they're registered with Base.metadata
    # This ensures proper table creation order (dependencies)
    try:
        # Core models
        from app.modules.auth.models import User, RefreshToken
        from app.modules.users.models import UserProfile
        from app.models.driver import DriverProfile
        from app.models.vehicle import Vehicle
        from app.models.ride import Ride
        from app.models.booking import Booking
        from app.models.wallet import Wallet
        from app.models.wallet_transaction import WalletTransaction
        
        # Payment models (must import after Wallet and Ride)
        from app.modules.payments.models import Transaction, Payout, PaymentIntent
        
        # Other models
        from app.models.rating import Rating
        from app.models.flag import Flag
        from app.models.telemetry_point import TelemetryPoint
        from app.models.verification_document import VerificationDocument
        
        logger.info("All models imported successfully")
    except Exception as e:
        logger.warning(f"Some models could not be imported: {e}")
        logger.warning("Continuing with available models...")

    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized successfully")


async def close_db() -> None:
    """
    Close database connections and dispose engine.
    Should be called on application shutdown.

    Returns:
        None
    """
    await engine.dispose()
    logger.info("✅ Database connections closed")


async def check_database_connection() -> bool:
    """
    Check if database connection is healthy.
    
    Returns:
        True if database is reachable, False otherwise
    """
    try:
        from sqlalchemy import text
        
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"❌ Database health check failed: {e}")
        return False
