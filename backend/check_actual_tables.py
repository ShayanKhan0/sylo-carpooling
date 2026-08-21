"""Check current database state."""
import asyncio
from sqlalchemy import text
from app.db.session import engine

async def check_tables():
    """Check which tables exist in the database."""
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT tablename 
            FROM pg_catalog.pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename;
        """))
        
        tables = [row[0] for row in result]
        
        if tables:
            print(f"✅ Found {len(tables)} tables:")
            for table in tables:
                print(f"   - {table}")
        else:
            print("❌ No tables found in database!")

if __name__ == "__main__":
    asyncio.run(check_tables())
