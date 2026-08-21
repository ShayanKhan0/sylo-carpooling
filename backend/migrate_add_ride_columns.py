"""Add address and route metadata columns to rides table."""
import asyncio
from app.core.config import settings


async def run():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    
    engine = create_async_engine(settings.DB_URL)
    async with engine.begin() as conn:
        # Check existing columns
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'rides' ORDER BY ordinal_position"
        ))
        cols = [r[0] for r in result.fetchall()]
        print("Existing columns:", cols)
        
        # Add missing columns
        migrations = [
            ("start_point_address", "TEXT"),
            ("end_point_address", "TEXT"),
            ("estimated_duration_minutes", "INTEGER"),
            ("route_distance_km", "DOUBLE PRECISION"),
        ]
        
        for col_name, col_type in migrations:
            if col_name not in cols:
                await conn.execute(text(
                    f"ALTER TABLE rides ADD COLUMN {col_name} {col_type}"
                ))
                print(f"Added column: {col_name} ({col_type})")
            else:
                print(f"Column already exists: {col_name}")
    
    await engine.dispose()
    print("Migration complete!")


if __name__ == "__main__":
    asyncio.run(run())
