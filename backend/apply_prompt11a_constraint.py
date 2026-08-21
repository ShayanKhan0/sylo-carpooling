"""
Direct SQL migration for Prompt 11A unique constraint.
Run this script to add the unique constraint to the ratings table.
"""
import asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def apply_constraint():
    """Apply unique constraint directly to database."""
    engine = create_async_engine(settings.DB_URL)
    
    async with engine.begin() as conn:
        # Check if constraint already exists
        result = await conn.execute(sa.text("""
            SELECT 1 FROM pg_constraint 
            WHERE conname = 'uq_rating_ride_rater'
        """))
        
        exists = result.fetchone()
        
        if exists:
            print("✅ Constraint 'uq_rating_ride_rater' already exists")
        else:
            # Add unique constraint using actual database column names
            await conn.execute(sa.text("""
                ALTER TABLE ratings 
                ADD CONSTRAINT uq_rating_ride_rater 
                UNIQUE (ride_id, rater_id)
            """))
            print("✅ Constraint 'uq_rating_ride_rater' added successfully!")
            print("   (One rating per ride_id + rater_id combination)")
    
    await engine.dispose()
    print("✅ Prompt 11A database migration complete!")

if __name__ == "__main__":
    asyncio.run(apply_constraint())
