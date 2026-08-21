"""Create refresh_tokens table for Prompt 1 completion"""
import asyncio
from sqlalchemy import text
from app.db.session import engine


async def create_refresh_tokens_table():
    """Create the refresh_tokens table for JWT token management."""
    
    print("=" * 60)
    print("Creating refresh_tokens table...")
    print("=" * 60)
    
    async with engine.begin() as conn:
        # Create refresh_tokens table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id SERIAL PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token VARCHAR(500) NOT NULL UNIQUE,
                expires_at TIMESTAMP NOT NULL,
                revoked BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """))
        print("✅ Created refresh_tokens table")
        
        # Create index on user_id
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id 
            ON refresh_tokens(user_id);
        """))
        print("✅ Created index on user_id")
        
        # Create index on token
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token 
            ON refresh_tokens(token);
        """))
        print("✅ Created index on token")
        
        # Create index on expires_at
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at 
            ON refresh_tokens(expires_at);
        """))
        print("✅ Created index on expires_at")
        
        print()
        print("🎉 refresh_tokens table created successfully!")
        print()
        
    # Verify
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'refresh_tokens' 
            ORDER BY ordinal_position;
        """))
        
        columns = result.fetchall()
        print("Table structure:")
        for col_name, col_type in columns:
            print(f"  • {col_name:<20} {col_type}")
        
        print()
        print("✅ Verification complete - refresh_tokens table is ready!")


if __name__ == "__main__":
    asyncio.run(create_refresh_tokens_table())
