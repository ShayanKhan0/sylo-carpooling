"""Quick debug script to check auth tables and test flow."""
import asyncio
import sys
sys.path.insert(0, '.')

async def main():
    from sqlalchemy import text
    from app.db.session import engine
    
    async with engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' ORDER BY table_name"
        ))
        tables = [row[0] for row in result.fetchall()]
        print("=== Tables in DB ===")
        for t in tables:
            print(f"  - {t}")
        
        # Check users table structure
        if 'users' in tables:
            result = await conn.execute(text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name='users' ORDER BY ordinal_position"
            ))
            print("\n=== Users table columns ===")
            for row in result.fetchall():
                print(f"  {row[0]}: {row[1]} (nullable={row[2]})")
            
            # Count users
            result = await conn.execute(text("SELECT COUNT(*) FROM users"))
            count = result.scalar()
            print(f"\n=== User count: {count} ===")
            
            if count > 0:
                result = await conn.execute(text(
                    "SELECT id, email, firebase_uid, role, is_active FROM users LIMIT 5"
                ))
                print("\n=== Recent users ===")
                for row in result.fetchall():
                    print(f"  id={row[0]}, email={row[1]}, fb_uid={row[2]}, role={row[3]}, active={row[4]}")
        else:
            print("\n!!! 'users' table NOT FOUND !!!")
        
        # Check refresh_tokens
        if 'refresh_tokens' in tables:
            print("\n=== refresh_tokens table exists ===")
        else:
            print("\n!!! 'refresh_tokens' table NOT FOUND !!!")
        
        # Check user_profiles
        if 'user_profiles' in tables:
            print("\n=== user_profiles table exists ===")
        else:
            print("\n!!! 'user_profiles' table NOT FOUND !!!")
        
        # Check wallets
        if 'wallets' in tables:
            print("\n=== wallets table exists ===")
        else:
            print("\n!!! 'wallets' table NOT FOUND !!!")

asyncio.run(main())
