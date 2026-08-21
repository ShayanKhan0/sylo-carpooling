"""
Clean database - drop all enum types and start fresh
"""
import asyncio
import asyncpg


async def clean_database():
    """Drop all enum types and tables to start fresh"""
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="postgres",
        password="root",
        database="sylo_carpool"
    )
    
    print("=" * 70)
    print("🧹 Cleaning Database")
    print("=" * 70)
    
    try:
        # Get all enum types
        enums = await conn.fetch("""
            SELECT typname 
            FROM pg_type 
            WHERE typtype='e'
            ORDER BY typname
        """)
        
        if enums:
            print(f"\n📋 Found {len(enums)} enum types to drop:")
            for e in enums:
                print(f"   - {e['typname']}")
            
            print("\n🗑️  Dropping enums...")
            for e in enums:
                try:
                    await conn.execute(f"DROP TYPE IF EXISTS {e['typname']} CASCADE")
                    print(f"   ✅ Dropped: {e['typname']}")
                except Exception as ex:
                    print(f"   ⚠️  Error dropping {e['typname']}: {ex}")
        
        # Get all tables
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema='public'
            AND table_type='BASE TABLE'
            ORDER BY table_name
        """)
        
        if tables:
            print(f"\n📋 Found {len(tables)} tables to drop:")
            for t in tables:
                print(f"   - {t['table_name']}")
            
            print("\n🗑️  Dropping tables...")
            for t in tables:
                try:
                    await conn.execute(f"DROP TABLE IF EXISTS {t['table_name']} CASCADE")
                    print(f"   ✅ Dropped: {t['table_name']}")
                except Exception as ex:
                    print(f"   ⚠️  Error dropping {t['table_name']}: {ex}")
        
        print("\n" + "=" * 70)
        print("✅ Database cleaned successfully!")
        print("=" * 70)
        print("\n💡 Next step: Run the migration")
        print("   Command: alembic upgrade head")
        print("=" * 70)
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(clean_database())
