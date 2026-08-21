import asyncio
from sqlalchemy import text
from app.db.session import engine

async def fix():
    async with engine.begin() as conn:
        print("Fixing missing tables and columns...")

        # 1. user_profiles
        try:
            await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                id UUID PRIMARY KEY,
                user_id UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                bio TEXT,
                preferences JSONB,
                avatar_url VARCHAR,
                rating FLOAT DEFAULT 0.0,
                rides_given INTEGER DEFAULT 0,
                rides_taken INTEGER DEFAULT 0,
                emergency_contacts JSONB,
                gender VARCHAR(20),
                date_of_birth DATE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """))
            print("user_profiles created if missing.")
        except Exception as e: print(f"Error user_profiles: {e}")

        # 2. Add missing columns
        queries = [
            "ALTER TABLE user_verifications ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending';",
            "ALTER TABLE user_verifications ADD COLUMN IF NOT EXISTS doc_type VARCHAR(50);",
            "ALTER TABLE ride_bookings ADD COLUMN IF NOT EXISTS booked_seats INTEGER DEFAULT 1;",
            "ALTER TABLE ride_bookings ADD COLUMN IF NOT EXISTS total_price FLOAT DEFAULT 0.0;",
            "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS seats_reserved INTEGER DEFAULT 1;",
            "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS fare FLOAT DEFAULT 0.0;",
            "ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS time TIME;",
            "ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS start_point_lat FLOAT;",
            "ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS start_point_lng FLOAT;",
            "ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS end_point_lat FLOAT;",
            "ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS end_point_lng FLOAT;",
            "ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS seats_offered INTEGER;",
            "ALTER TABLE recurring_schedules ADD COLUMN IF NOT EXISTS base_price FLOAT;"
        ]

        for q in queries:
            try:
                await conn.execute(text(q))
                print(f"Executed: {q}")
            except Exception as e:
                print(f"Error on {q}: {e}")

        print("Done fixing db!")

if __name__ == "__main__":
    asyncio.run(fix())