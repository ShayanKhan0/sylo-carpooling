"""
COMPLETE DATABASE SETUP AND VERIFICATION
Creates ALL missing tables and tests REAL data insertion
"""
import asyncio
import asyncpg
from datetime import datetime, timedelta
import uuid

async def complete_database_setup():
    """Create all missing tables and test real data insertion"""
    
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="root",
        database="sylo_carpool"
    )
    
    print("=" * 80)
    print("🚀 COMPLETE DATABASE SETUP - REAL WORLD PROJECT")
    print("=" * 80)
    
    try:
        # 1. Check current tables
        print("\n📊 Step 1: Checking current tables...")
        tables_before = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        print(f"   Current tables: {len(tables_before)}")
        for table in tables_before:
            print(f"      • {table['tablename']}")
        
        # 2. Create ALL missing tables
        print("\n🔨 Step 2: Creating ALL missing tables...")
        
        # Create missing tables one by one
        missing_tables = [
            # Driver Profiles
            """CREATE TABLE IF NOT EXISTS driver_profiles (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                license_number VARCHAR(50),
                license_expiry DATE,
                vehicle_id UUID REFERENCES vehicles(id),
                is_verified BOOLEAN DEFAULT FALSE,
                verification_status driver_verification_status DEFAULT 'pending',
                verification_date TIMESTAMP WITH TIME ZONE,
                rating_average DECIMAL(3,2) DEFAULT 0.0,
                total_ratings INTEGER DEFAULT 0,
                total_rides INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # Ride Bookings
            """CREATE TABLE IF NOT EXISTS ride_bookings (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                ride_id UUID NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
                passenger_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                seats_reserved INTEGER NOT NULL DEFAULT 1,
                status booking_status DEFAULT 'reserved',
                booking_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                pickup_lat DOUBLE PRECISION,
                pickup_lng DOUBLE PRECISION,
                dropoff_lat DOUBLE PRECISION,
                dropoff_lng DOUBLE PRECISION,
                fare DECIMAL(10,2),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # Match Records
            """CREATE TABLE IF NOT EXISTS match_records (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                driver_id UUID NOT NULL REFERENCES drivers(user_id) ON DELETE CASCADE,
                passenger_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                ride_id UUID REFERENCES rides(id) ON DELETE CASCADE,
                match_score DECIMAL(5,2),
                status VARCHAR(20) DEFAULT 'pending',
                matched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # Match Preferences
            """CREATE TABLE IF NOT EXISTS match_preferences (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                preferred_gender VARCHAR(10),
                max_detour_minutes INTEGER DEFAULT 15,
                smoking_allowed BOOLEAN DEFAULT FALSE,
                music_allowed BOOLEAN DEFAULT TRUE,
                pets_allowed BOOLEAN DEFAULT FALSE,
                conversation_level VARCHAR(20) DEFAULT 'moderate',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # Notifications
            """CREATE TABLE IF NOT EXISTS notifications (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                type VARCHAR(50) DEFAULT 'info',
                is_read BOOLEAN DEFAULT FALSE,
                data JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                read_at TIMESTAMP WITH TIME ZONE
            )""",
            
            # Notification Tokens
            """CREATE TABLE IF NOT EXISTS notification_tokens (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token VARCHAR(255) NOT NULL UNIQUE,
                device_type VARCHAR(50),
                device_id VARCHAR(255),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # Incident Reports
            """CREATE TABLE IF NOT EXISTS incident_reports (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                ride_id UUID REFERENCES rides(id) ON DELETE SET NULL,
                reporter_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                reported_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                incident_type VARCHAR(50) NOT NULL,
                severity flag_severity DEFAULT 'medium',
                description TEXT,
                location_lat DOUBLE PRECISION,
                location_lng DOUBLE PRECISION,
                status flag_status DEFAULT 'open',
                resolved_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # Payouts
            """CREATE TABLE IF NOT EXISTS payouts (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                driver_id UUID NOT NULL REFERENCES drivers(user_id) ON DELETE CASCADE,
                amount DECIMAL(10,2) NOT NULL,
                status transaction_status DEFAULT 'pending',
                transaction_id VARCHAR(255),
                payment_method VARCHAR(50),
                payout_date TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # User Verifications
            """CREATE TABLE IF NOT EXISTS user_verifications (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                email_verified BOOLEAN DEFAULT FALSE,
                phone_verified BOOLEAN DEFAULT FALSE,
                identity_verified BOOLEAN DEFAULT FALSE,
                email_verified_at TIMESTAMP WITH TIME ZONE,
                phone_verified_at TIMESTAMP WITH TIME ZONE,
                identity_verified_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # Verification Attempts
            """CREATE TABLE IF NOT EXISTS verification_attempts (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                verification_type VARCHAR(20) NOT NULL,
                code VARCHAR(10),
                attempts INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 3,
                expires_at TIMESTAMP WITH TIME ZONE,
                verified_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # System Stats
            """CREATE TABLE IF NOT EXISTS system_stats (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                metric_name VARCHAR(100) NOT NULL,
                metric_value DECIMAL(15,2),
                metadata JSONB,
                recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # Log Entries
            """CREATE TABLE IF NOT EXISTS log_entries (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                level VARCHAR(20) NOT NULL,
                logger VARCHAR(100),
                message TEXT,
                module VARCHAR(100),
                function VARCHAR(100),
                line_number INTEGER,
                user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                request_id VARCHAR(100),
                metadata JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # Alerts
            """CREATE TABLE IF NOT EXISTS alerts (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                alert_type VARCHAR(50) NOT NULL,
                severity flag_severity DEFAULT 'low',
                title VARCHAR(255),
                message TEXT,
                is_dismissed BOOLEAN DEFAULT FALSE,
                dismissed_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # Recurring Schedules
            """CREATE TABLE IF NOT EXISTS recurring_schedules (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                is_driver BOOLEAN DEFAULT FALSE,
                start_lat DOUBLE PRECISION NOT NULL,
                start_lng DOUBLE PRECISION NOT NULL,
                end_lat DOUBLE PRECISION NOT NULL,
                end_lng DOUBLE PRECISION NOT NULL,
                start_address VARCHAR(500),
                end_address VARCHAR(500),
                departure_time TIME,
                days_of_week INTEGER[],
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # Telemetry Data
            """CREATE TABLE IF NOT EXISTS telemetry_data (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                ride_id UUID REFERENCES rides(id) ON DELETE CASCADE,
                driver_id UUID REFERENCES drivers(user_id) ON DELETE CASCADE,
                event_type VARCHAR(50),
                location_lat DOUBLE PRECISION,
                location_lng DOUBLE PRECISION,
                speed DECIMAL(5,2),
                acceleration DECIMAL(5,2),
                metadata JSONB,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )""",
            
            # Saved Addresses
            """CREATE TABLE IF NOT EXISTS saved_addresses (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                label VARCHAR(50) NOT NULL,
                address VARCHAR(500) NOT NULL,
                location_lat DOUBLE PRECISION,
                location_lng DOUBLE PRECISION,
                is_default BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )"""
        ]
        
        created_count = 0
        for table_sql in missing_tables:
            try:
                await conn.execute(table_sql)
                # Extract table name
                table_name = table_sql.split("TABLE IF NOT EXISTS ")[1].split(" (")[0].strip()
                print(f"   ✅ {table_name}")
                created_count += 1
            except Exception as e:
                print(f"   ⚠️  {str(e)[:100]}")
        
        print(f"\n   Created {created_count} new tables")
        
        # 3. Check all tables now
        print("\n📊 Step 3: Verifying all tables...")
        tables_after = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        print(f"   Total tables NOW: {len(tables_after)}")
        for i, table in enumerate(tables_after, 1):
            print(f"   {i:2d}. {table['tablename']}")
        
        # 4. TEST REAL DATA INSERTION
        print("\n" + "=" * 80)
        print("🧪 TESTING REAL DATA INSERTION (Not Hypothetical!)")
        print("=" * 80)
        
        # Create a test user
        test_user_id = str(uuid.uuid4())
        print(f"\n📝 Inserting TEST USER into database...")
        print(f"   User ID: {test_user_id}")
        
        await conn.execute("""
            INSERT INTO users (id, email, phone, full_name, cnic, role, password_hash, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, test_user_id, "test@realproject.com", "+923001234567", "Real Test User",
            "12345-1234567-1", "passenger", "hashed_password_here", True)
        
        print("   ✅ User inserted into PostgreSQL!")
        
        # Create a test driver
        test_driver_id = str(uuid.uuid4())
        print(f"\n📝 Inserting TEST DRIVER into database...")
        print(f"   Driver ID: {test_driver_id}")
        
        await conn.execute("""
            INSERT INTO users (id, email, phone, full_name, cnic, role, password_hash, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """, test_driver_id, "driver@realproject.com", "+923007654321", "Real Test Driver",
            "54321-7654321-1", "driver", "hashed_password_here", True)
        
        await conn.execute("""
            INSERT INTO drivers (user_id, license_number, verification_status, is_available)
            VALUES ($1, $2, $3, $4)
        """, test_driver_id, "LHR-123456", "verified", True)
        
        print("   ✅ Driver inserted into PostgreSQL!")
        
        # Create a test wallet
        wallet_id = str(uuid.uuid4())
        print(f"\n📝 Inserting TEST WALLET into database...")
        await conn.execute("""
            INSERT INTO wallets (id, user_id, balance, currency)
            VALUES ($1, $2, $3, $4)
        """, wallet_id, test_user_id, 500.00, "PKR")
        
        print("   ✅ Wallet inserted with balance: 500.00 PKR")
        
        # 5. VERIFY DATA IS ACTUALLY STORED
        print("\n" + "=" * 80)
        print("✅ VERIFYING DATA IS ACTUALLY STORED IN POSTGRESQL")
        print("=" * 80)
        
        # Query the data back
        print("\n🔍 Querying data from database...")
        
        user = await conn.fetchrow("SELECT * FROM users WHERE email = 'test@realproject.com'")
        print(f"\n📋 USER RECORD (Retrieved from PostgreSQL):")
        print(f"   ID: {user['id']}")
        print(f"   Email: {user['email']}")
        print(f"   Name: {user['full_name']}")
        print(f"   Phone: {user['phone']}")
        print(f"   Role: {user['role']}")
        print(f"   Active: {user['is_active']}")
        print(f"   Created: {user['created_at']}")
        
        driver = await conn.fetchrow("SELECT * FROM drivers WHERE user_id = $1", test_driver_id)
        print(f"\n📋 DRIVER RECORD (Retrieved from PostgreSQL):")
        print(f"   User ID: {driver['user_id']}")
        print(f"   License: {driver['license_number']}")
        print(f"   Status: {driver['verification_status']}")
        print(f"   Available: {driver['is_available']}")
        
        wallet = await conn.fetchrow("SELECT * FROM wallets WHERE user_id = $1", test_user_id)
        print(f"\n📋 WALLET RECORD (Retrieved from PostgreSQL):")
        print(f"   ID: {wallet['id']}")
        print(f"   Balance: {wallet['balance']} {wallet['currency']}")
        print(f"   User ID: {wallet['user_id']}")
        
        # Count total records
        user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        driver_count = await conn.fetchval("SELECT COUNT(*) FROM drivers")
        wallet_count = await conn.fetchval("SELECT COUNT(*) FROM wallets")
        
        print(f"\n📊 TOTAL RECORDS IN DATABASE:")
        print(f"   Users: {user_count}")
        print(f"   Drivers: {driver_count}")
        print(f"   Wallets: {wallet_count}")
        
        print("\n" + "=" * 80)
        print("✅ SUCCESS! DATA IS REALLY STORED IN POSTGRESQL")
        print("=" * 80)
        print("\n💡 You can verify this by:")
        print("   1. Opening pgAdmin")
        print("   2. Navigate to: sylo_carpool → Schemas → public → Tables")
        print("   3. Right-click 'users' table → View/Edit Data → All Rows")
        print("   4. You'll see the real test user we just created!")
        print("\n🎉 This is a REAL-WORLD database, not hypothetical!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(complete_database_setup())
