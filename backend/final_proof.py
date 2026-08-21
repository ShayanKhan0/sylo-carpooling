"""Quick check of table structures and final proof"""
import asyncio
import asyncpg

async def final_proof():
    conn = await asyncpg.connect(
        host="localhost", port=5432,
        user="postgres", password="root",
        database="sylo_carpool"
    )
    
    print("=" * 80)
    print("🎯 FINAL PROOF - DATA IS REAL IN POSTGRESQL")
    print("=" * 80)
    
    try:
        # Get all tables
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        print(f"\n✅ TOTAL TABLES: {len(tables)}")
        
        # Show wallet_transactions structure
        print("\n📋 wallet_transactions columns:")
        cols = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'wallet_transactions'
            ORDER BY ordinal_position
        """)
        for col in cols:
            print(f"   • {col['column_name']}: {col['data_type']}")
        
        # Query real data
        print("\n" + "=" * 80)
        print("📊 REAL DATA IN DATABASE (Not Hypothetical!)")
        print("=" * 80)
        
        users = await conn.fetch("SELECT * FROM users")
        print(f"\n👥 USERS ({len(users)} records):")
        for user in users:
            print(f"   • {user['full_name']} ({user['email']})")
            print(f"     Role: {user['role']}, Active: {user['is_active']}")
            print(f"     Created: {user['created_at']}")
        
        drivers = await conn.fetch("SELECT * FROM drivers")
        print(f"\n🚗 DRIVERS ({len(drivers)} records):")
        for driver in drivers:
            print(f"   • License: {driver['license_number']}")
            print(f"     Status: {driver['verification_status']}")
            print(f"     Available: {driver['is_available']}")
        
        wallets = await conn.fetch("SELECT * FROM wallets")
        print(f"\n💰 WALLETS ({len(wallets)} records):")
        for wallet in wallets:
            print(f"   • Balance: {wallet['balance']} PKR")
            print(f"     Created: {wallet['created_at']}")
        
        # Check other tables with data
        important_tables = [
            'users', 'drivers', 'vehicles', 'rides', 'bookings',
            'wallets', 'ratings', 'notifications', 'driver_profiles'
        ]
        
        print(f"\n📊 RECORD COUNTS:")
        for table in important_tables:
            try:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                status = "✅" if count > 0 else "⚪"
                print(f"   {status} {table:20s}: {count} records")
            except:
                pass
        
        print("\n" + "=" * 80)
        print("✅ PROOF COMPLETE!")
        print("=" * 80)
        print(f"\n🎉 You have {len(tables)} REAL tables in PostgreSQL")
        print(f"🎉 You have {len(users)} REAL users stored on disk")
        print(f"🎉 You have {len(drivers)} REAL drivers stored on disk")
        print(f"🎉 You have {len(wallets)} REAL wallets stored on disk")
        
        print(f"\n💡 VERIFY IN PGADMIN:")
        print(f"   1. Open pgAdmin 4")
        print(f"   2. PostgreSQL → Databases → sylo_carpool")
        print(f"   3. Schemas → public → Tables")
        print(f"   4. Right-click any table → 'View/Edit Data' → 'All Rows'")
        print(f"   5. You'll see THE ACTUAL DATA we just showed you!")
        
        print(f"\n✅ THIS IS 100% REAL - NOT HYPOTHETICAL!")
        print("=" * 80)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(final_proof())
