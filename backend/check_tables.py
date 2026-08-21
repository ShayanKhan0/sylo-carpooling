"""Check actual database tables"""
import asyncio
from app.db.session import engine
from sqlalchemy import text

async def check_tables():
    print("=" * 80)
    print("CHECKING REAL DATABASE TABLES IN POSTGRESQL")
    print("=" * 80)

    try:
        async with engine.connect() as conn:
            # Get all tables in public schema
            result = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
            )
            tables = [row[0] for row in result.fetchall()]
            
            print(f"\n✅ Total tables found: {len(tables)}")
            
            if tables:
                print("\n📊 REAL TABLES in your PostgreSQL database:")
                for i, table in enumerate(tables, 1):
                    print(f"  {i}. {table}")
                
                # Count rows in each table
                print("\n📈 Row counts:")
                for table in tables:
                    try:
                        count_result = await conn.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
                        count = count_result.scalar()
                        print(f"  {table}: {count} rows")
                    except Exception as e:
                        print(f"  {table}: Error - {str(e)[:50]}")
            else:
                print("\n" + "="*80)
                print("❌ NO TABLES FOUND IN THE DATABASE!")
                print("="*80)
                print("\n⚠️  THIS IS A REAL ISSUE - Database tables were never created!")
                print("\nWhat this means:")
                print("  • Alembic migrations have NOT been run")
                print("  • The database schema was never created")
                print("  • All API endpoints are accessing an EMPTY database")
                print("\nWe need to:")
                print("  1. Run Alembic migrations to create all tables")
                print("  2. Or use setup_database.py to initialize the schema")
            
            # Check if alembic_version table exists
            if 'alembic_version' in tables:
                result = await conn.execute(text("SELECT version_num FROM alembic_version"))
                version = result.scalar()
                print(f"\n📌 Current Alembic migration version: {version}")
            else:
                print("\n⚠️ No alembic_version table - migrations have NEVER been run!")
                
    except Exception as e:
        print(f"\n❌ Error connecting to database: {e}")
        print("\nPossible issues:")
        print("1. PostgreSQL server is not running")
        print("2. Database 'SmartCarpoolingApp' doesn't exist")
        print("3. Database credentials in .env are incorrect")
        print("4. Connection string is wrong")

    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(check_tables())
