"""
Direct database setup - creates all tables and enums
This avoids Alembic/SQLAlchemy enum issues
"""
import asyncio
import asyncpg


async def setup_database():
    """Create all tables and enums directly"""
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="root",
        database="sylo_carpool"
    )
    
    print("=" * 70)
    print("🚀 Setting Up Database Schema")
    print("=" * 70)
    
    try:
        # 1. UUID extension
        print("\n1️⃣  Creating UUID extension...")
        await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        print("   ✅ UUID extension ready")
        
        # 2. Create enum types
        print("\n2️⃣  Creating enum types...")
        enums = [
            ("user_role", ['passenger', 'driver', 'admin']),
            ("driver_verification_status", ['pending', 'verified', 'rejected']),
            ("ride_status", ['open', 'in_progress', 'completed', 'cancelled']),
            ("booking_status", ['reserved', 'cancelled', 'completed']),
            ("transaction_type", ['topup', 'payout', 'ride']),
            ("transaction_status", ['pending', 'completed', 'failed']),
            ("verification_status", ['pending', 'verified', 'rejected']),
            ("flag_severity", ['low', 'medium', 'high']),
            ("flag_status", ['open', 'resolved', 'dismissed']),
        ]
        
        for enum_name, values in enums:
            values_str = "', '".join(values)
            try:
                await conn.execute(f"CREATE TYPE {enum_name} AS ENUM ('{values_str}')")
                print(f"   ✅ {enum_name}")
            except asyncpg.DuplicateObjectError:
                print(f"   ⚠️  {enum_name} already exists (skipping)")
        
        # 3. Create tables
        print("\n3️⃣  Creating tables...")
        
        # Users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                email VARCHAR(255) NOT NULL UNIQUE,
                phone VARCHAR(20),
                full_name VARCHAR(255) NOT NULL,
                cnic VARCHAR(255),
                role user_role NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)
        print("   ✅ users")
        
        # Drivers table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS drivers (
                user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                license_number VARCHAR(255),
                verification_status driver_verification_status NOT NULL DEFAULT 'pending',
                location_last_lat DOUBLE PRECISION,
                location_last_lng DOUBLE PRECISION,
                is_available BOOLEAN NOT NULL DEFAULT false,
                total_rides INTEGER NOT NULL DEFAULT 0,
                rating_avg NUMERIC(3, 2),
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)
        print("   ✅ drivers")
        
        # Vehicles table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vehicles (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                driver_id UUID NOT NULL REFERENCES drivers(user_id) ON DELETE CASCADE,
                make VARCHAR(100) NOT NULL,
                model VARCHAR(100) NOT NULL,
                year INTEGER NOT NULL,
                color VARCHAR(50),
                license_plate VARCHAR(50) NOT NULL UNIQUE,
                seats_available INTEGER NOT NULL,
                photos JSONB,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)
        print("   ✅ vehicles")
        
        # Rides table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rides (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                driver_id UUID NOT NULL REFERENCES drivers(user_id) ON DELETE CASCADE,
                vehicle_id UUID REFERENCES vehicles(id) ON DELETE SET NULL,
                start_point_lat DOUBLE PRECISION NOT NULL,
                start_point_lng DOUBLE PRECISION NOT NULL,
                end_point_lat DOUBLE PRECISION NOT NULL,
                end_point_lng DOUBLE PRECISION NOT NULL,
                departure_time TIMESTAMP WITH TIME ZONE NOT NULL,
                seats_available INTEGER NOT NULL,
                price_per_seat NUMERIC(10, 2) NOT NULL,
                status ride_status NOT NULL DEFAULT 'open',
                polyline TEXT,
                recurrence JSONB,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)
        print("   ✅ rides")
        
        # Bookings table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                ride_id UUID NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
                passenger_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                seats_booked INTEGER NOT NULL,
                total_price NUMERIC(10, 2) NOT NULL,
                status booking_status NOT NULL DEFAULT 'reserved',
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)
        print("   ✅ bookings")
        
        # Wallets table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                balance NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)
        print("   ✅ wallets")
        
        # Wallet transactions table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet_transactions (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                wallet_id UUID NOT NULL REFERENCES wallets(user_id) ON DELETE CASCADE,
                amount NUMERIC(12, 2) NOT NULL,
                transaction_type transaction_type NOT NULL,
                status transaction_status NOT NULL DEFAULT 'pending',
                provider_transaction_id VARCHAR(255),
                metadata JSONB,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)
        print("   ✅ wallet_transactions")
        
        # Verifications table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS verifications (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                cnic_front_url VARCHAR(500),
                cnic_back_url VARCHAR(500),
                license_front_url VARCHAR(500),
                license_back_url VARCHAR(500),
                selfie_url VARCHAR(500),
                cnic_number VARCHAR(255),
                full_name_on_cnic VARCHAR(255),
                face_match_score NUMERIC(5, 2),
                status verification_status NOT NULL DEFAULT 'pending',
                reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
                reviewed_at TIMESTAMP WITH TIME ZONE,
                rejection_reason TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)
        print("   ✅ verifications")
        
        # Telemetry points table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_points (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                ride_id UUID NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                speed DOUBLE PRECISION,
                bearing DOUBLE PRECISION,
                recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)
        print("   ✅ telemetry_points")
        
        # Ratings table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ratings (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                ride_id UUID NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
                rater_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                ratee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                score INTEGER NOT NULL CHECK (score >= 1 AND score <= 5),
                comment TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)
        print("   ✅ ratings")
        
        # Admin flags table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_flags (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                flagged_entity_type VARCHAR(50) NOT NULL,
                flagged_entity_id UUID NOT NULL,
                reported_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                reason TEXT NOT NULL,
                severity flag_severity NOT NULL,
                status flag_status NOT NULL DEFAULT 'open',
                reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
                reviewed_at TIMESTAMP WITH TIME ZONE,
                resolution_notes TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        """)
        print("   ✅ admin_flags")
        
        # 4. Create indexes
        print("\n4️⃣  Creating indexes...")
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
            "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)",
            "CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_drivers_verification_status ON drivers(verification_status)",
            "CREATE INDEX IF NOT EXISTS idx_drivers_is_available ON drivers(is_available)",
            "CREATE INDEX IF NOT EXISTS idx_drivers_location ON drivers(location_last_lat, location_last_lng)",
            "CREATE INDEX IF NOT EXISTS idx_drivers_rating_avg ON drivers(rating_avg)",
            "CREATE INDEX IF NOT EXISTS idx_vehicles_driver_id ON vehicles(driver_id)",
            "CREATE INDEX IF NOT EXISTS idx_vehicles_license_plate ON vehicles(license_plate)",
            "CREATE INDEX IF NOT EXISTS idx_rides_driver_id ON rides(driver_id)",
            "CREATE INDEX IF NOT EXISTS idx_rides_status ON rides(status)",
            "CREATE INDEX IF NOT EXISTS idx_rides_departure_time ON rides(departure_time)",
            "CREATE INDEX IF NOT EXISTS idx_rides_start_point ON rides(start_point_lat, start_point_lng)",
            "CREATE INDEX IF NOT EXISTS idx_rides_end_point ON rides(end_point_lat, end_point_lng)",
            "CREATE INDEX IF NOT EXISTS idx_rides_seats_available ON rides(seats_available)",
            "CREATE INDEX IF NOT EXISTS idx_bookings_ride_id ON bookings(ride_id)",
            "CREATE INDEX IF NOT EXISTS idx_bookings_passenger_id ON bookings(passenger_id)",
            "CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status)",
            "CREATE INDEX IF NOT EXISTS idx_wallet_transactions_wallet_id ON wallet_transactions(wallet_id)",
            "CREATE INDEX IF NOT EXISTS idx_wallet_transactions_type ON wallet_transactions(transaction_type)",
            "CREATE INDEX IF NOT EXISTS idx_wallet_transactions_status ON wallet_transactions(status)",
            "CREATE INDEX IF NOT EXISTS idx_wallet_transactions_created_at ON wallet_transactions(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_verifications_user_id ON verifications(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_verifications_status ON verifications(status)",
            "CREATE INDEX IF NOT EXISTS idx_telemetry_ride_id ON telemetry_points(ride_id)",
            "CREATE INDEX IF NOT EXISTS idx_telemetry_recorded_at ON telemetry_points(recorded_at)",
            "CREATE INDEX IF NOT EXISTS idx_telemetry_location ON telemetry_points(latitude, longitude)",
            "CREATE INDEX IF NOT EXISTS idx_ratings_ride_id ON ratings(ride_id)",
            "CREATE INDEX IF NOT EXISTS idx_ratings_rater_id ON ratings(rater_id)",
            "CREATE INDEX IF NOT EXISTS idx_ratings_ratee_id ON ratings(ratee_id)",
            "CREATE INDEX IF NOT EXISTS idx_ratings_score ON ratings(score)",
            "CREATE INDEX IF NOT EXISTS idx_admin_flags_entity ON admin_flags(flagged_entity_type, flagged_entity_id)",
            "CREATE INDEX IF NOT EXISTS idx_admin_flags_reported_by ON admin_flags(reported_by)",
            "CREATE INDEX IF NOT EXISTS idx_admin_flags_severity ON admin_flags(severity)",
            "CREATE INDEX IF NOT EXISTS idx_admin_flags_status ON admin_flags(status)",
        ]
        
        for idx_sql in indexes:
            await conn.execute(idx_sql)
        print(f"   ✅ Created {len(indexes)} indexes")
        
        # 5. Create Alembic version table and mark as migrated
        print("\n5️⃣  Setting up Alembic tracking...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS alembic_version (
                version_num VARCHAR(32) NOT NULL,
                CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
            )
        """)
        # Mark current revision
        await conn.execute("DELETE FROM alembic_version")
        await conn.execute("INSERT INTO alembic_version VALUES ('18cd3a19027b')")
        print("   ✅ Alembic tracking configured")
        
        print("\n" + "=" * 70)
        print("✅ DATABASE SETUP COMPLETE!")
        print("=" * 70)
        print(f"\n📊 Summary:")
        print(f"   • 9 enum types created")
        print(f"   • 11 tables created")
        print(f"   • {len(indexes)} indexes created")
        print(f"   • Foreign key constraints applied")
        print("\n💡 Next steps:")
        print("   1. Test connection: python test_db_connection.py")
        print("   2. Start backend: uvicorn app.main:app --reload")
        print("   3. Access API docs: http://localhost:8000/docs")
        print("=" * 70)
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(setup_database())
