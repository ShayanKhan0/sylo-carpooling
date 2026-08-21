import asyncio
from app.db.session import get_db
from sqlalchemy import text

async def check_users():
    async for db in get_db():
        result = await db.execute(text('SELECT email, phone, role, is_active FROM users LIMIT 10'))
        users = result.fetchall()
        
        print("\n" + "="*60)
        print("EXISTING USERS IN DATABASE")
        print("="*60)
        
        if users:
            for i, u in enumerate(users, 1):
                print(f"\n{i}. Email: {u[0]}")
                print(f"   Phone: {u[1]}")
                print(f"   Role: {u[2]}")
                print(f"   Active: {u[3]}")
        else:
            print("\n❌ No users found in database!")
        
        print("\n" + "="*60)
        break

if __name__ == "__main__":
    asyncio.run(check_users())
