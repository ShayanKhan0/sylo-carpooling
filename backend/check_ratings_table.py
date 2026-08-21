"""Check ratings table structure"""
import asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def check_table():
    engine = create_async_engine(settings.DB_URL)
    async with engine.begin() as conn:
        result = await conn.execute(sa.text("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'ratings'
            ORDER BY ordinal_position
        """))
        print("Ratings table columns:")
        for row in result:
            print(f"  - {row[0]}: {row[1]}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_table())
