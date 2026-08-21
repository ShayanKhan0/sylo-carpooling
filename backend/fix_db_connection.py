"""
Interactive script to fix database connection
"""
import asyncio
import asyncpg


async def test_connection(host, port, user, password, database):
    """Test connection with given credentials"""
    try:
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        version = await conn.fetchval('SELECT version()')
        await conn.close()
        return True, version
    except Exception as e:
        return False, str(e)


async def main():
    print("=" * 70)
    print("🔧 PostgreSQL Connection Troubleshooter")
    print("=" * 70)
    
    # Common configurations to test
    configs = [
        {"user": "postgres", "password": "postgres", "database": "smartcarpool_dev"},
        {"user": "postgres", "password": "admin", "database": "smartcarpool_dev"},
        {"user": "postgres", "password": "", "database": "smartcarpool_dev"},
        {"user": "postgres", "password": "postgres", "database": "postgres"},
    ]
    
    host = "localhost"
    port = 5432
    
    print(f"\n🔍 Testing connection to {host}:{port}...\n")
    
    for i, config in enumerate(configs, 1):
        print(f"{i}. Testing: user={config['user']}, database={config['database']}, password={'*' * len(config['password']) if config['password'] else '(empty)'}")
        
        success, result = await test_connection(
            host=host,
            port=port,
            user=config['user'],
            password=config['password'],
            database=config['database']
        )
        
        if success:
            print(f"   ✅ SUCCESS! Connection works!")
            print(f"   📋 PostgreSQL: {result[:60]}...")
            print(f"\n" + "=" * 70)
            print("✅ Working Configuration Found!")
            print("=" * 70)
            print(f"\n💡 Update your .env file with this DB_URL:")
            print(f"\nDB_URL=postgresql+asyncpg://{config['user']}:{config['password']}@{host}:{port}/{config['database']}")
            print("\n" + "=" * 70)
            return
        else:
            print(f"   ❌ Failed: {result[:60]}...")
        print()
    
    print("=" * 70)
    print("❌ None of the common configurations worked")
    print("=" * 70)
    print("\n💡 Manual Setup Required:")
    print("\n1. Find your PostgreSQL password:")
    print("   - Check pgAdmin if installed")
    print("   - Check installation notes")
    print("   - Try resetting password (see below)")
    print("\n2. Create database manually:")
    print("   - Open pgAdmin or SQL Shell")
    print("   - Run: CREATE DATABASE smartcarpool_dev;")
    print("\n3. Update .env file with correct credentials:")
    print("   DB_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/smartcarpool_dev")
    print("\n4. Re-run: python test_db_connection.py")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
