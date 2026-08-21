"""
Test connection to different databases
"""
import asyncio
import asyncpg


async def test_db(password, database):
    """Test connection to a specific database"""
    try:
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password=password,
            database=database
        )
        version = await conn.fetchval('SELECT version()')
        
        # List all databases
        databases = await conn.fetch('SELECT datname FROM pg_database WHERE datistemplate = false')
        
        await conn.close()
        return True, version, [db['datname'] for db in databases]
    except Exception as e:
        return False, str(e), None


async def main():
    print("=" * 70)
    print("🔍 Database Explorer")
    print("=" * 70)
    
    # Try common passwords with default 'postgres' database
    passwords = ["Admin@123", "Admin123", "postgres", "admin", "password", "admin123", ""]
    
    for password in passwords:
        print(f"\nTrying password: '{password if password else '(empty)'}'")
        success, result, databases = await test_db(password, "postgres")
        
        if success:
            print(f"   ✅ CONNECTION SUCCESSFUL!")
            print(f"\n📋 PostgreSQL Version: {result[:60]}...")
            print(f"\n📊 Available Databases:")
            for db in databases:
                marker = "✅" if db == "smartcarpool_dev" else "  "
                print(f"   {marker} {db}")
            
            print("\n" + "=" * 70)
            print("✅ SUCCESS! Password Found!")
            print("=" * 70)
            print(f"\nCorrect Password: '{password}'")
            
            if "smartcarpool_dev" in databases:
                print(f"\n✅ Database 'smartcarpool_dev' exists!")
                from urllib.parse import quote_plus
                encoded = quote_plus(password) if password else password
                print(f"\n💾 Update your .env file:")
                print(f"\nDB_URL=postgresql+asyncpg://postgres:{encoded}@localhost:5432/smartcarpool_dev")
            else:
                print(f"\n⚠️  Database 'smartcarpool_dev' does NOT exist yet.")
                print(f"   Create it first, then update .env")
            
            print("=" * 70)
            return
        else:
            print(f"   ❌ {result[:60]}...")


if __name__ == "__main__":
    asyncio.run(main())
