"""
Script to create test users for app testing with verified status.
"""

import sys
import asyncio
from sqlalchemy import select, text
from app.db.session import get_db
import bcrypt
import uuid


async def create_test_user():
    """Create test passenger and driver users with verified status."""

    # Test user credentials (matches DB enum values: passenger, driver, admin)
    test_users = [
        {
            "email": "passenger@sylo.app",
            "password": "Test1234!",
            "phone": "+923001234567",
            "name": "Test Passenger",
            "role": "passenger",
        },
        {
            "email": "driver@sylo.app",
            "password": "Test1234!",
            "phone": "+923009876543",
            "name": "Test Driver",
            "role": "driver",
        },
    ]

    institution_id = "00000000-0000-0000-0000-000000000001"

    print("\n" + "="*60)
    print("Creating Test Users for Sylo App")
    print("="*60)
    
    async for db in get_db():
        try:
            table_check = text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            table_result = await db.execute(table_check)
            tables = {row[0] for row in table_result.fetchall()}
            has_profiles = "user_profiles" in tables
            has_verifications = "user_verifications" in tables

            for user in test_users:
                user_id = str(uuid.uuid4())
                password_hash = bcrypt.hashpw(
                    user["password"].encode("utf-8"),
                    bcrypt.gensalt()
                ).decode("utf-8")

                # Check if user already exists and delete
                check_sql = text("SELECT id FROM users WHERE email = :email")
                result = await db.execute(check_sql, {"email": user["email"]})
                existing = result.scalar_one_or_none()

                if existing:
                    print(f"\n⚠️  User already exists, deleting: {user['email']}")
                    delete_sql = text("DELETE FROM users WHERE email = :email")
                    await db.execute(delete_sql, {"email": user["email"]})
                    await db.commit()

                # Create User using raw SQL (without is_verified - it's in user_verifications table)
                insert_user_sql = text("""
                    INSERT INTO users (id, full_name, email, password_hash, phone, role, is_active, created_at)
                    VALUES (:id, :full_name, :email, :password_hash, :phone, :role, true, NOW())
                """)

                await db.execute(insert_user_sql, {
                    "id": user_id,
                    "full_name": user["name"],
                    "email": user["email"],
                    "password_hash": password_hash,
                    "phone": user["phone"],
                    "role": user["role"],
                })
                await db.commit()
                print(f"\n✅ User created successfully: {user['email']}")
                print(f"   User ID: {user_id}")

                # Create UserProfile (if table exists)
                if has_profiles:
                    insert_profile_sql = text("""
                        INSERT INTO user_profiles (user_id, institution_id, bio, emergency_contact_name, emergency_contact_phone, created_at)
                        VALUES (:user_id, :institution_id, :bio, :emergency_contact_name, :emergency_contact_phone, NOW())
                    """)

                    await db.execute(insert_profile_sql, {
                        "user_id": user_id,
                        "institution_id": institution_id,
                        "bio": f"{user['name']} for Sylo carpooling app",
                        "emergency_contact_name": "Emergency Contact",
                        "emergency_contact_phone": "+923009876543"
                    })
                    print("✅ User profile created!")
                else:
                    print("⚠️  Skipped user profile creation (table not found)")

                # Create UserVerification (if table exists)
                if has_verifications:
                    try:
                        insert_verification_sql = text("""
                            INSERT INTO user_verifications (user_id, email_verified, phone_verified, identity_verified, created_at)
                            VALUES (:user_id, true, true, true, NOW())
                        """)

                        await db.execute(insert_verification_sql, {
                            "user_id": user_id
                        })
                        await db.commit()
                        print("✅ User verification created (all verified)!")
                    except Exception as verification_error:
                        await db.rollback()
                        print(f"⚠️  Skipped user verification creation: {verification_error}")
                else:
                    print("⚠️  Skipped user verification creation (table not found)")
            
            # Commit all changes
            await db.commit()
            
            print("\n" + "="*60)
            print("✨ TEST USERS CREATED SUCCESSFULLY! ✨")
            print("="*60)
            for user in test_users:
                print(f"\n📧 Email:    {user['email']}")
                print(f"🔑 Password: {user['password']}")
                print(f"📱 Phone:    {user['phone']}")
                print(f"👤 Name:     {user['name']}")
                print(f"🎭 Role:     {user['role']}")
            print(f"\n💡 Use these credentials to login to the Sylo app!")
            print("="*60 + "\n")
            
            return True
            
        except Exception as e:
            await db.rollback()
            print(f"\n❌ Error creating test user: {str(e)}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    success = asyncio.run(create_test_user())
    sys.exit(0 if success else 1)
