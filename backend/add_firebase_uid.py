"""Add firebase_uid column to users table."""
import asyncio
import sys
sys.path.insert(0, '.')

async def add_column():
    from sqlalchemy import text
    from app.db.session import engine
    async with engine.begin() as conn:
        # Add firebase_uid column
        await conn.execute(text(
            'ALTER TABLE users ADD COLUMN IF NOT EXISTS firebase_uid VARCHAR(255) UNIQUE'
        ))
        print('firebase_uid column added successfully')
        
        # Create index on firebase_uid  
        await conn.execute(text(
            'CREATE INDEX IF NOT EXISTS ix_users_firebase_uid ON users (firebase_uid)'
        ))
        print('Index created on firebase_uid')
        
        # Make updated_at nullable (model says onupdate, so it can be null initially)
        await conn.execute(text(
            'ALTER TABLE users ALTER COLUMN updated_at DROP NOT NULL'
        ))
        print('updated_at made nullable')
        
        # Make phone nullable (some Firebase users might not have phone yet)
        await conn.execute(text(
            'ALTER TABLE users ALTER COLUMN phone DROP NOT NULL'
        ))
        print('phone made nullable')
        
        # Verify
        result = await conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name='users' ORDER BY ordinal_position"
        ))
        print('\n=== Updated users table ===')
        for row in result.fetchall():
            print(f'  {row[0]}: {row[1]}')

asyncio.run(add_column())
