import asyncio
from sqlalchemy import text
from app.db.session import get_db


async def main() -> None:
    async for db in get_db():
        await db.execute(
            text(
                "ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMP WITH TIME ZONE"
            )
        )
        await db.execute(
            text(
                "ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS is_revoked BOOLEAN DEFAULT false"
            )
        )
        await db.commit()
        print("OK")
        break


if __name__ == "__main__":
    asyncio.run(main())
