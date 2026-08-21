"""Recreate database tables with proper dependency order."""
import asyncio
from app.db.session import engine
from app.db.base import Base

async def recreate_tables():
    """Recreate all database tables."""
    async with engine.begin() as conn:
        # Drop all tables
        await conn.run_sync(Base.metadata.drop_all)
        print("✅ All tables dropped")
        
        # Create all tables with proper dependency order
        await conn.run_sync(Base.metadata.create_all)
        print("✅ All tables created successfully!")

if __name__ == "__main__":
    asyncio.run(recreate_tables())
