import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def main():
    engine = create_async_engine("postgresql+asyncpg://postgres:root@localhost:5432/sylo_carpool")
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT id, full_name, email, firebase_uid, role, is_active FROM users ORDER BY created_at DESC LIMIT 10")
        )
        rows = result.fetchall()
        for row in rows:
            print(row)
    await engine.dispose()

asyncio.run(main())
