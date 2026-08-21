"""Check wallet table structure and insert test data"""
import asyncio
import asyncpg

async def test_wallet():
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="root",
        database="sylo_carpool"
    )
    
    try:
        # Check wallet table structure
        print("📊 Wallet Table Columns:")
        columns = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'wallets'
            ORDER BY ordinal_position
        """)
        for col in columns:
            print(f"   • {col['column_name']}: {col['data_type']}")
        
        # Check if we have test users
        users = await conn.fetch("SELECT id, email, full_name FROM users ORDER BY created_at DESC LIMIT 5")
        print(f"\n📋 Users in database ({len(users)} total):")
        for user in users:
            print(f"   • {user['full_name']} ({user['email']})")
            print(f"     ID: {user['id']}")
        
        # Try to insert wallet with correct structure
        if users:
            test_user_id = users[0]['id']
            print(f"\n📝 Attempting to create wallet for user: {test_user_id}")
            
            # Check if wallet exists
            existing = await conn.fetchval("SELECT COUNT(*) FROM wallets WHERE user_id = $1", test_user_id)
            if existing == 0:
                await conn.execute("""
                    INSERT INTO wallets (user_id, balance, currency)
                    VALUES ($1, $2, $3)
                """, test_user_id, 1000.50, "PKR")
                print("   ✅ Wallet created successfully!")
            else:
                print("   ⚠️  Wallet already exists")
            
            # Retrieve and display
            wallet = await conn.fetchrow("SELECT * FROM wallets WHERE user_id = $1", test_user_id)
            print(f"\n💰 WALLET DATA (Retrieved from PostgreSQL):")
            for key, value in wallet.items():
                print(f"   {key}: {value}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_wallet())
