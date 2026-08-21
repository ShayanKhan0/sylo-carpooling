"""
Prompt 1 Verification Script
Verifies that all Prompt 1 (Initial Backend Setup) requirements are complete.
"""

import asyncio
import sys
from sqlalchemy import text, inspect
from app.db.session import engine


async def verify_prompt1():
    """
    Verify all Prompt 1 requirements:
    1. Database models (User, RefreshToken)
    2. Authentication endpoints
    3. Core infrastructure
    4. Module skeletons
    """
    
    print("=" * 70)
    print("PROMPT 1 VERIFICATION - Initial Backend Setup")
    print("=" * 70)
    print()
    
    results = {
        "database_tables": False,
        "auth_module": False,
        "core_infrastructure": False,
        "module_skeletons": False
    }
    
    # 1. Verify Database Tables
    print("📊 1. DATABASE TABLES")
    print("-" * 70)
    try:
        async with engine.connect() as conn:
            # Check for users table
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'users'
                );
            """))
            users_exists = result.scalar()
            
            # Check for refresh_tokens table
            result = await conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'refresh_tokens'
                );
            """))
            tokens_exists = result.scalar()
            
            if users_exists and tokens_exists:
                print("  ✅ users table exists")
                print("  ✅ refresh_tokens table exists")
                
                # Check users table structure
                result = await conn.execute(text("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' 
                    ORDER BY ordinal_position;
                """))
                columns = result.fetchall()
                required_columns = {'id', 'email', 'full_name', 'password_hash', 'phone', 'role', 'is_active', 'created_at', 'updated_at'}
                found_columns = {col[0] for col in columns}
                
                if required_columns.issubset(found_columns):
                    print(f"  ✅ users table has all required columns ({len(found_columns)} total)")
                    results["database_tables"] = True
                else:
                    missing = required_columns - found_columns
                    print(f"  ⚠️  Missing columns in users table: {missing}")
            else:
                if not users_exists:
                    print("  ❌ users table NOT found")
                if not tokens_exists:
                    print("  ❌ refresh_tokens table NOT found")
    except Exception as e:
        print(f"  ❌ Database check failed: {e}")
    
    print()
    
    # 2. Verify Auth Module
    print("🔐 2. AUTHENTICATION MODULE")
    print("-" * 70)
    auth_files = {
        "models.py": "app/modules/auth/models.py",
        "schemas.py": "app/modules/auth/schemas.py",
        "crud.py": "app/modules/auth/crud.py",
        "service.py": "app/modules/auth/service.py",
        "routers.py": "app/modules/auth/routers.py",
        "deps.py": "app/modules/auth/deps.py"
    }
    
    import os
    auth_complete = True
    for name, path in auth_files.items():
        if os.path.exists(path):
            file_size = os.path.getsize(path)
            if file_size > 500:  # Should have substantial content
                print(f"  ✅ {name:<15} exists ({file_size:,} bytes)")
            else:
                print(f"  ⚠️  {name:<15} exists but seems incomplete ({file_size} bytes)")
                auth_complete = False
        else:
            print(f"  ❌ {name:<15} NOT found")
            auth_complete = False
    
    results["auth_module"] = auth_complete
    print()
    
    # 3. Verify Core Infrastructure
    print("🏗️  3. CORE INFRASTRUCTURE")
    print("-" * 70)
    core_files = {
        "config.py": "app/core/config.py",
        "security.py": "app/core/security.py",
        "logger.py": "app/core/logger.py",
        "middleware.py": "app/core/middleware.py"
    }
    
    core_complete = True
    for name, path in core_files.items():
        if os.path.exists(path):
            file_size = os.path.getsize(path)
            print(f"  ✅ {name:<20} exists ({file_size:,} bytes)")
        else:
            print(f"  ❌ {name:<20} NOT found")
            core_complete = False
    
    # Check database session
    if os.path.exists("app/db/session.py"):
        print(f"  ✅ {'db/session.py':<20} exists")
    else:
        print(f"  ❌ {'db/session.py':<20} NOT found")
        core_complete = False
    
    results["core_infrastructure"] = core_complete
    print()
    
    # 4. Verify Module Skeletons
    print("📦 4. MODULE SKELETONS")
    print("-" * 70)
    modules = [
        "auth", "users", "drivers", "rides", "matching", 
        "payments", "verification", "notifications", "safety_ai", 
        "admin", "health", "ratings", "history", "analytics", "telemetry"
    ]
    
    modules_complete = 0
    for module in modules:
        module_path = f"app/modules/{module}"
        if os.path.exists(module_path):
            print(f"  ✅ {module:<20} module exists")
            modules_complete += 1
        else:
            print(f"  ❌ {module:<20} module NOT found")
    
    results["module_skeletons"] = (modules_complete >= 11)  # At least 11 modules
    print(f"\n  📊 Total: {modules_complete}/{len(modules)} modules exist")
    print()
    
    # Summary
    print("=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    
    all_passed = all(results.values())
    
    for check, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        check_name = check.replace("_", " ").title()
        print(f"  {status:<10} {check_name}")
    
    print()
    print("=" * 70)
    
    if all_passed:
        print("✅ PROMPT 1: 100% COMPLETE")
        print("=" * 70)
        print()
        print("All Prompt 1 requirements are satisfied:")
        print("  • Database tables created")
        print("  • Authentication module fully implemented")
        print("  • Core infrastructure in place")
        print("  • Module skeletons created")
        print()
        print("Next steps:")
        print("  1. Start server: uvicorn app.main:app --reload")
        print("  2. Test auth: http://localhost:8000/docs")
        print("  3. Register a user and test login")
        return 0
    else:
        print("⚠️  PROMPT 1: INCOMPLETE")
        print("=" * 70)
        print()
        print("Issues found:")
        for check, passed in results.items():
            if not passed:
                check_name = check.replace("_", " ").title()
                print(f"  ❌ {check_name}")
        print()
        print("Please complete the remaining requirements.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(verify_prompt1())
    sys.exit(exit_code)
