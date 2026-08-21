"""
Manual migration script for Prompt 11 tables.

Creates DailyAggregate and DriverEarnings tables directly.

Run with: python create_prompt11_tables.py
"""

import asyncio
from sqlalchemy import text
from app.db.session import engine


async def create_prompt11_tables():
    """Create Prompt 11 analytics tables manually."""
    
    async with engine.begin() as conn:
        print("Creating Prompt 11 tables...")
        
        # Create daily_aggregates table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS daily_aggregates (
                id SERIAL PRIMARY KEY,
                date DATE NOT NULL,
                rides_count INTEGER NOT NULL DEFAULT 0,
                revenue_total DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                active_drivers INTEGER NOT NULL DEFAULT 0,
                active_passengers INTEGER NOT NULL DEFAULT 0,
                verification_failures INTEGER NOT NULL DEFAULT 0,
                region VARCHAR(100),
                avg_ride_distance FLOAT,
                avg_ride_duration INTEGER,
                surge_multiplier_avg FLOAT,
                cancellations_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_daily_aggregates_date_region UNIQUE (date, region)
            );
        """))
        print("✅ Created daily_aggregates table")
        
        # Create indexes for daily_aggregates
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_daily_aggregates_date ON daily_aggregates(date);
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_daily_aggregates_region ON daily_aggregates(region);
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_daily_aggregates_date_region ON daily_aggregates(date, region);
        """))
        print("✅ Created indexes for daily_aggregates")
        
        # Create driver_earnings table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS driver_earnings (
                id SERIAL PRIMARY KEY,
                driver_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                month VARCHAR(7) NOT NULL,
                total_earnings DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                commissions_paid DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                net_earnings DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                completed_rides INTEGER NOT NULL DEFAULT 0,
                total_distance_km FLOAT NOT NULL DEFAULT 0.0,
                total_duration_minutes INTEGER NOT NULL DEFAULT 0,
                avg_rating FLOAT,
                tips_received DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                bonuses DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_driver_earnings_driver_month UNIQUE (driver_id, month)
            );
        """))
        print("✅ Created driver_earnings table")
        
        # Create indexes for driver_earnings
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_driver_earnings_driver_id ON driver_earnings(driver_id);
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_driver_earnings_month ON driver_earnings(month);
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_driver_earnings_driver_month ON driver_earnings(driver_id, month);
        """))
        print("✅ Created indexes for driver_earnings")
        
        print("\n🎉 Prompt 11 tables created successfully!")
        print("\nTables created:")
        print("  - daily_aggregates (with 3 indexes)")
        print("  - driver_earnings (with 3 indexes)")


async def verify_tables():
    """Verify tables exist."""
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('daily_aggregates', 'driver_earnings')
            ORDER BY table_name;
        """))
        
        tables = [row[0] for row in result]
        
        print("\n✅ Verification:")
        print(f"   Found tables: {', '.join(tables)}")
        
        if len(tables) == 2:
            print("   ✅ All Prompt 11 tables exist!")
            return True
        else:
            print(f"   ⚠️  Missing tables: {set(['daily_aggregates', 'driver_earnings']) - set(tables)}")
            return False


if __name__ == "__main__":
    print("=" * 60)
    print("Prompt 11 Manual Migration")
    print("=" * 60)
    
    asyncio.run(create_prompt11_tables())
    asyncio.run(verify_tables())
    
    print("\n✅ Migration complete!")
    print("\nNext steps:")
    print("1. Restart your FastAPI server")
    print("2. Test endpoints at http://localhost:8000/docs")
    print("3. Check 'Ratings (Prompt 11)' section")
    print("4. Check 'History & Earnings (Prompt 11)' section")
    print("5. Check 'Analytics (Prompt 11)' section (requires admin)")
