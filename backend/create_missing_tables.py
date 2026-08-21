"""
Create ALL missing database tables
This script will create the real tables in PostgreSQL
"""
import asyncio
from app.db.session import engine
from sqlalchemy import text


TABLES_SQL = """
-- ===================================================================
-- CREATING ALL MISSING TABLES FOR SMARTCARPOOLINGAPP
-- ===================================================================

-- 1. DRIVER PROFILES TABLE
CREATE TABLE IF NOT EXISTS driver_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    license_number VARCHAR(50),
    license_expiry DATE,
    vehicle_id INTEGER,
    is_verified BOOLEAN DEFAULT FALSE,
    verification_status VARCHAR(20) DEFAULT 'pending',
    verification_date TIMESTAMP,
    rating_average DECIMAL(3,2) DEFAULT 0.0,
    total_ratings INTEGER DEFAULT 0,
    total_rides INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. RIDE BOOKINGS TABLE  
CREATE TABLE IF NOT EXISTS ride_bookings (
    id SERIAL PRIMARY KEY,
    ride_id INTEGER NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
    passenger_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    seats_reserved INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(20) DEFAULT 'reserved',
    booking_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    pickup_location GEOGRAPHY(POINT, 4326),
    dropoff_location GEOGRAPHY(POINT, 4326),
    fare DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. MATCH RECORDS TABLE
CREATE TABLE IF NOT EXISTS match_records (
    id SERIAL PRIMARY KEY,
    driver_id INTEGER NOT NULL REFERENCES driver_profiles(id) ON DELETE CASCADE,
    passenger_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ride_id INTEGER REFERENCES rides(id) ON DELETE CASCADE,
    match_score DECIMAL(5,2),
    status VARCHAR(20) DEFAULT 'pending',
    matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. MATCH PREFERENCES TABLE
CREATE TABLE IF NOT EXISTS match_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    preferred_gender VARCHAR(10),
    max_detour_minutes INTEGER DEFAULT 15,
    smoking_allowed BOOLEAN DEFAULT FALSE,
    music_allowed BOOLEAN DEFAULT TRUE,
    pets_allowed BOOLEAN DEFAULT FALSE,
    conversation_level VARCHAR(20) DEFAULT 'moderate',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. NOTIFICATIONS TABLE
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    type VARCHAR(50) DEFAULT 'info',
    is_read BOOLEAN DEFAULT FALSE,
    data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP
);

-- 6. NOTIFICATION TOKENS TABLE
CREATE TABLE IF NOT EXISTS notification_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(255) NOT NULL UNIQUE,
    device_type VARCHAR(50),
    device_id VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. INCIDENT REPORTS TABLE
CREATE TABLE IF NOT EXISTS incident_reports (
    id SERIAL PRIMARY KEY,
    ride_id INTEGER REFERENCES rides(id) ON DELETE SET NULL,
    reporter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reported_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    incident_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) DEFAULT 'medium',
    description TEXT,
    location GEOGRAPHY(POINT, 4326),
    status VARCHAR(20) DEFAULT 'open',
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. PAYOUTS TABLE
CREATE TABLE IF NOT EXISTS payouts (
    id SERIAL PRIMARY KEY,
    driver_id INTEGER NOT NULL REFERENCES driver_profiles(id) ON DELETE CASCADE,
    amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    transaction_id VARCHAR(255),
    payment_method VARCHAR(50),
    payout_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 9. PAYMENT INTENTS TABLE
CREATE TABLE IF NOT EXISTS payment_intents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'PKR',
    status VARCHAR(20) DEFAULT 'pending',
    provider VARCHAR(50),
    provider_intent_id VARCHAR(255) UNIQUE,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. IDEMPOTENCY RECORDS TABLE
CREATE TABLE IF NOT EXISTS idempotency_records (
    id SERIAL PRIMARY KEY,
    idempotency_key VARCHAR(255) NOT NULL UNIQUE,
    request_hash VARCHAR(64),
    response_data JSONB,
    status_code INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

-- 11. USER VERIFICATIONS TABLE
CREATE TABLE IF NOT EXISTS user_verifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    email_verified BOOLEAN DEFAULT FALSE,
    phone_verified BOOLEAN DEFAULT FALSE,
    identity_verified BOOLEAN DEFAULT FALSE,
    email_verified_at TIMESTAMP,
    phone_verified_at TIMESTAMP,
    identity_verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 12. VERIFICATION ATTEMPTS TABLE
CREATE TABLE IF NOT EXISTS verification_attempts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    verification_type VARCHAR(20) NOT NULL,
    code VARCHAR(10),
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    expires_at TIMESTAMP,
    verified_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 13. SYSTEM STATS TABLE
CREATE TABLE IF NOT EXISTS system_stats (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(15,2),
    metadata JSONB,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 14. LOG ENTRIES TABLE
CREATE TABLE IF NOT EXISTS log_entries (
    id SERIAL PRIMARY KEY,
    level VARCHAR(20) NOT NULL,
    logger VARCHAR(100),
    message TEXT,
    module VARCHAR(100),
    function VARCHAR(100),
    line_number INTEGER,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    request_id VARCHAR(100),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 15. ALERTS TABLE
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) DEFAULT 'info',
    title VARCHAR(255),
    message TEXT,
    is_dismissed BOOLEAN DEFAULT FALSE,
    dismissed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 16. RECURRING SCHEDULES TABLE
CREATE TABLE IF NOT EXISTS recurring_schedules (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_driver BOOLEAN DEFAULT FALSE,
    start_location GEOGRAPHY(POINT, 4326) NOT NULL,
    end_location GEOGRAPHY(POINT, 4326) NOT NULL,
    start_address VARCHAR(500),
    end_address VARCHAR(500),
    departure_time TIME,
    days_of_week INTEGER[] DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 17. TELEMETRY DATA TABLE
CREATE TABLE IF NOT EXISTS telemetry_data (
    id SERIAL PRIMARY KEY,
    ride_id INTEGER REFERENCES rides(id) ON DELETE CASCADE,
    driver_id INTEGER REFERENCES driver_profiles(id) ON DELETE CASCADE,
    event_type VARCHAR(50),
    location GEOGRAPHY(POINT, 4326),
    speed DECIMAL(5,2),
    acceleration DECIMAL(5,2),
    metadata JSONB,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 18. SAVED ADDRESSES TABLE
CREATE TABLE IF NOT EXISTS saved_addresses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label VARCHAR(50) NOT NULL,
    address VARCHAR(500) NOT NULL,
    location GEOGRAPHY(POINT, 4326),
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ===================================================================
-- CREATE INDEXES FOR PERFORMANCE
-- ===================================================================

CREATE INDEX IF NOT EXISTS idx_driver_profiles_user_id ON driver_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_ride_bookings_ride_id ON ride_bookings(ride_id);
CREATE INDEX IF NOT EXISTS idx_ride_bookings_passenger_id ON ride_bookings(passenger_id);
CREATE INDEX IF NOT EXISTS idx_match_records_driver_id ON match_records(driver_id);
CREATE INDEX IF NOT EXISTS idx_match_records_passenger_id ON match_records(passenger_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_incident_reports_ride_id ON incident_reports(ride_id);
CREATE INDEX IF NOT EXISTS idx_payment_intents_user_id ON payment_intents(user_id);
CREATE INDEX IF NOT EXISTS idx_log_entries_level ON log_entries(level);
CREATE INDEX IF NOT EXISTS idx_log_entries_created_at ON log_entries(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_recurring_schedules_user_id ON recurring_schedules(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_addresses_user_id ON saved_addresses(user_id);

"""


async def create_missing_tables():
    """Create all missing tables in the real PostgreSQL database"""
    print("=" * 80)
    print("🚀 CREATING ALL MISSING TABLES IN POSTGRESQL")
    print("=" * 80)
    
    try:
        async with engine.begin() as conn:
            # Check current state
            result = await conn.execute(
                text("SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'")
            )
            before_count = result.scalar()
            print(f"\n📊 Tables before: {before_count}")
            
            # Execute the SQL to create all missing tables
            print("\n🔨 Creating missing tables...")
            await conn.execute(text(TABLES_SQL))
            
            # Check new state
            result = await conn.execute(
                text("SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public'")
            )
            after_count = result.scalar()
            print(f"📊 Tables after: {after_count}")
            print(f"✅ Created {after_count - before_count} new tables")
            
            # List all tables
            result = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
            )
            all_tables = [row[0] for row in result.fetchall()]
            
            print(f"\n📋 ALL TABLES NOW IN YOUR POSTGRESQL DATABASE ({len(all_tables)} total):")
            for i, table in enumerate(all_tables, 1):
                print(f"  {i}. {table}")
            
            print("\n" + "=" * 80)
            print("✅ SUCCESS! All tables created in your real PostgreSQL database")
            print("=" * 80)
            print("\nYou can now open pgAdmin and see all these tables!")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(create_missing_tables())
