"""Check all database tables"""
import asyncio
from sqlalchemy import text
from app.db.session import engine


async def list_tables():
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public' 
            ORDER BY tablename
        """))
        
        print("\n" + "="*50)
        print("DATABASE TABLES")
        print("="*50)
        for row in result:
            print(f"  • {row[0]}")
        print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(list_tables())
