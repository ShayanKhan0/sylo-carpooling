import asyncio
from sqlalchemy import text
from app.db.session import get_db


async def main() -> None:
    async for db in get_db():
        await db.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified boolean DEFAULT false"
            )
        )
        await db.commit()
        print("OK")
        break


if __name__ == "__main__":
    asyncio.run(main())
