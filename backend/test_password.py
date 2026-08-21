"""
Interactive password tester
"""
import asyncio
import asyncpg
from urllib.parse import quote_plus


async def test_password(password):
    """Test a specific password"""
    try:
        # URL encode the password
        encoded_password = quote_plus(password)
        
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user="postgres",
            password=password,  # Use raw password for connection
            database="smartcarpool_dev"
        )
        version = await conn.fetchval('SELECT version()')
        await conn.close()
        return True, version, encoded_password
    except Exception as e:
        return False, str(e), None


async def main():
    print("=" * 70)
    print("🔐 PostgreSQL Password Tester")
    print("=" * 70)
    
    # Test the password you provided
    passwords_to_test = [
        "Admin@123",
        "Admin123",
        "admin@123",
        "admin123",
        "postgres",
        "Admin",
    ]
    
    print("\n🔍 Testing passwords...\n")
    
    for password in passwords_to_test:
        print(f"Testing: '{password}'")
        success, result, encoded = await test_password(password)
        
        if success:
            print(f"   ✅ SUCCESS!\n")
            print("=" * 70)
            print("✅ Correct Password Found!")
            print("=" * 70)
            print(f"\nPassword: {password}")
            print(f"URL-encoded: {encoded}")
            print(f"\n💾 Add this to your .env file:")
            print(f"\nDB_URL=postgresql+asyncpg://postgres:{encoded}@localhost:5432/smartcarpool_dev")
            print("\n" + "=" * 70)
            return
        else:
            print(f"   ❌ {result[:50]}...\n")
    
    print("=" * 70)
    print("❌ None of the passwords worked")
    print("=" * 70)
    print("\n💡 Please try manually:")
    print("1. Open pgAdmin and check your saved password")
    print("2. Or try connecting with a PostgreSQL client")
    print("3. Enter the exact password when you find it")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
