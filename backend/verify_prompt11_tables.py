"""Quick verification that Prompt 11 tables exist."""
import asyncio
from sqlalchemy import text
from app.db.session import engine


async def verify():
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('daily_aggregates', 'driver_earnings')
            ORDER BY table_name
        """))
        
        tables = [row[0] for row in result]
        
        print("\n" + "="*50)
        print("Prompt 11 Tables Verification")
        print("="*50)
        
        for table in tables:
            print(f"  ✅ {table}")
        
        if len(tables) == 2:
            print("\n✅ All Prompt 11 tables exist!")
        else:
            print(f"\n⚠️  Expected 2 tables, found {len(tables)}")
        
        print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(verify())
