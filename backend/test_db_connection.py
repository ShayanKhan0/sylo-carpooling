"""
Test PostgreSQL database connection
"""
import asyncio
from sqlalchemy import text
from app.core.config import settings
from app.db.session import get_db


async def test_database_connection():
    """Test database connectivity and basic queries"""
    print("=" * 60)
    print("🔍 Testing PostgreSQL Database Connection")
    print("=" * 60)
    
    try:
        print(f"\n📋 Database URL: {settings.DB_URL.split('@')[1] if '@' in settings.DB_URL else 'Hidden'}")
        
        # Get database session
        async for db in get_db():
            print("\n✅ Database connection established successfully!")
            
            # Test 1: Get PostgreSQL version
            print("\n1️⃣ Testing PostgreSQL Version...")
            result = await db.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"   ✅ PostgreSQL Version: {version[:80]}...")
            
            # Test 2: Check if tables exist
            print("\n2️⃣ Checking Database Tables...")
            result = await db.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema='public' 
                ORDER BY table_name
            """))
            tables = result.fetchall()
            
            if tables:
                print(f"   ✅ Found {len(tables)} tables:")
                for table in tables:
                    print(f"      - {table[0]}")
            else:
                print("   ⚠️  No tables found. Run migrations: alembic upgrade head")
            
            # Test 3: Check enum types
            print("\n3️⃣ Checking Enum Types...")
            result = await db.execute(text("""
                SELECT typname 
                FROM pg_type 
                WHERE typtype='e' 
                ORDER BY typname
            """))
            enums = result.fetchall()
            
            if enums:
                print(f"   ✅ Found {len(enums)} enum types:")
                for enum in enums:
                    print(f"      - {enum[0]}")
            else:
                print("   ⚠️  No enum types found. Run migrations first.")
            
            # Test 4: Check indexes
            print("\n4️⃣ Checking Indexes...")
            result = await db.execute(text("""
                SELECT COUNT(*) 
                FROM pg_indexes 
                WHERE schemaname='public'
            """))
            index_count = result.scalar()
            print(f"   ✅ Found {index_count} indexes")
            
            # Test 5: Check alembic migration version
            print("\n5️⃣ Checking Migration Status...")
            try:
                result = await db.execute(text("SELECT version_num FROM alembic_version"))
                version_num = result.scalar()
                if version_num:
                    print(f"   ✅ Current migration: {version_num}")
                else:
                    print("   ⚠️  No migrations applied yet")
            except Exception as e:
                print(f"   ⚠️  Alembic version table not found. Run: alembic upgrade head")
            
            print("\n" + "=" * 60)
            print("✅ Database Connection Test PASSED!")
            print("=" * 60)
            print("\n💡 Next Steps:")
            if not tables or len(tables) <= 1:
                print("   1. Apply migrations: alembic upgrade head")
            print("   2. Start the backend: uvicorn app.main:app --reload")
            print("   3. Access API docs: http://localhost:8000/docs")
            print("=" * 60)
            
            break
            
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ Database Connection FAILED!")
        print("=" * 60)
        print(f"\n🔴 Error: {str(e)}")
        print("\n💡 Troubleshooting:")
        print("   1. Check if PostgreSQL is running: net start postgresql-x64-13")
        print("   2. Verify .env file has correct DB_URL")
        print("   3. Check database exists: psql -U postgres -c '\\l'")
        print("   4. Verify connection string format:")
        print("      DB_URL=postgresql+asyncpg://user:password@localhost:5432/carpooling_db")
        print("=" * 60)
        return False
    
    return True


if __name__ == "__main__":
    asyncio.run(test_database_connection())
