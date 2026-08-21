import asyncio
from sqlalchemy import text
from app.db.session import engine
from app.db.base import Base

# Import all models to ensure metadata has them
import app.models

async def sync():
    async with engine.begin() as conn:
        # 1. Create missing tables (e.g. user_profiles)
        print("Creating missing tables...")
        await conn.run_sync(Base.metadata.create_all)
        
        # 2. Add missing columns using ALTER TABLE if they do not exist
        print("Adding missing columns to user_verifications...")
        try:
            await conn.execute(text("ALTER TABLE user_verifications ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending';"))
            await conn.execute(text("ALTER TABLE user_verifications ADD COLUMN IF NOT EXISTS doc_type VARCHAR(50);"))
        except Exception as e: print(f"Error user_verifications: {e}")
            
        print("Adding missing columns to ride_bookings...")
        try:
            await conn.execute(text("ALTER TABLE ride_bookings ADD COLUMN IF NOT EXISTS booked_seats INTEGER DEFAULT 1;"))
            await conn.execute(text("ALTER TABLE ride_bookings ADD COLUMN IF NOT EXISTS total_price FLOAT DEFAULT 0.0;"))
        except Exception as e: print(f"Error ride_bookings: {e}")

        print("Adding missing columns to bookings...")
        try:
            await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS seats_reserved INTEGER DEFAULT 1;"))
            await conn.execute(text("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS fare FLOAT DEFAULT 0.0;"))
        except Exception as e: print(f"Error bookings: {e}")

        print("Adding missing columns to recurring_schedules...")
        try:
            await conn.execute(text("ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS time TIME;"))
            await conn.execute(text("ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS start_point_lat FLOAT;"))
            await conn.execute(text("ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS start_point_lng FLOAT;"))
            await conn.execute(text("ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS end_point_lat FLOAT;"))
            await conn.execute(text("ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS end_point_lng FLOAT;"))
            await conn.execute(text("ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS seats_offered INTEGER;"))
            await conn.execute(text("ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS base_price FLOAT;"))
        except Exception as e: print(f"Error recurring_schedules: {e}")

        print("Database sync complete.")

if __name__ == "__main__":
    asyncio.run(sync())