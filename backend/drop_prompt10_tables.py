"""Drop and recreate Prompt 10 tables with correct schema."""
import asyncio
from sqlalchemy import text
from app.db.session import engine


async def fix_tables():
    """Drop and recreate tables."""
    async with engine.begin() as conn:
        await conn.execute(text('DROP TABLE IF EXISTS payment_intents CASCADE'))
        print('✅ Dropped payment_intents')
        
        await conn.execute(text('DROP TABLE IF EXISTS idempotency_records CASCADE'))
        print('✅ Dropped idempotency_records')
        
        print('\nRe-run check_prompt10_tables.py to recreate with correct schema')


if __name__ == "__main__":
    asyncio.run(fix_tables())
