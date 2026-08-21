"""
Check what already exists in the database and clean if needed
"""
import asyncio
import asyncpg


async def check_database():
    """Check current database state"""
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="root",
        database="sylo_carpool"
    )
    
    print("=" * 70)
    print("🔍 Checking Database State")
    print("=" * 70)
    
    # Check tables
    print("\n📊 Existing Tables:")
    tables = await conn.fetch("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema='public'
        ORDER BY table_name
    """)
    if tables:
        for t in tables:
            print(f"   - {t['table_name']}")
    else:
        print("   (none)")
    
    # Check enum types
    print("\n🔤 Existing Enum Types:")
    enums = await conn.fetch("""
        SELECT typname 
        FROM pg_type 
        WHERE typtype='e'
        ORDER BY typname
    """)
    if enums:
        for e in enums:
            print(f"   - {e['typname']}")
    else:
        print("   (none)")
    
    # Check alembic version
    print("\n📝 Alembic Migration Status:")
    try:
        version = await conn.fetchval("SELECT version_num FROM alembic_version")
        print(f"   Current: {version}")
    except:
        print("   (no migrations applied yet)")
    
    await conn.close()
    
    # If enums exist, offer to clean
    if enums:
        print("\n" + "=" * 70)
        print("⚠️  Found existing enum types from previous migration attempt")
        print("=" * 70)
        print("\n💡 Solution: Drop existing enums and retry migration")
        print("\nI can create a script to clean this up.")
        print("Run: python clean_database.py")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(check_database())
