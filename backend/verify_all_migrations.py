"""
COMPREHENSIVE MIGRATION VERIFICATION
=====================================
Deep scan to verify ALL migrations are practically applied to PostgreSQL database.
This is NOT hypothetical - this script proves every migration is real.

Author: SmartCarpoolingApp Team
Date: December 12, 2025
Purpose: Verify 100% of migrations are in real database, not hypothetical
"""

import asyncio
import asyncpg
from typing import Dict, List, Set


DATABASE_URL = "postgresql://postgres:root@localhost:5432/sylo_carpool"


# ALL EXPECTED TABLES FROM ALL MODELS AND MIGRATIONS
EXPECTED_TABLES = {
    # Core Auth & Users (from auth module + models)
    "users",
    "refresh_tokens",
    
    # Driver Models
    "drivers",
    "driver_profiles",
    "vehicles",
    
    # Ride & Booking Models
    "rides",
    "bookings",
    "ride_bookings",
    "recurring_schedules",
    
    # Payment Models
    "wallets",
    "wallet_transactions",
    
    # Matching Module
    "match_records",
    "match_preferences",
    
    # Notifications Module
    "notifications",
    "notification_tokens",
    
    # Verification Module
    "verifications",
    "user_verifications",
    "verification_attempts",
    
    # Safety & Monitoring
    "incident_reports",
    "telemetry_points",
    "telemetry_data",
    
    # Ratings & Reviews
    "ratings",
    
    # Admin & Flagging
    "admin_flags",
    
    # Analytics & Reporting
    "system_stats",
    "log_entries",
    "alerts",
    "daily_aggregates",
    "driver_earnings",
    
    # Payments Advanced
    "payouts",
    
    # User Features
    "saved_addresses",
    
    # System Tables
    "alembic_version"
}


# ALL MIGRATION FILES WE FOUND
MIGRATION_FILES = {
    "95241d562070": "initial_database_schema_with_all_tables.py",
    "18cd3a19027b": "create_all_tables_with_enums.py",
    "prompt5_rides_scheduling": "prompt5_rides_scheduling.py",
    "7043eb5e484a": "merge_migration_heads.py",
    "5a7b9c8ec4e7": "prompt_10_add_payment_intents_and_.py",
    "a2d5b0da3fb3": "prompt_10_add_payment_intents_and_.py (v2)",
    "ecee828ee6ee": "add_prompt_11_analytics_tables.py"
}


async def check_database_connection() -> bool:
    """Verify we can connect to real PostgreSQL database"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.close()
        print("✅ Successfully connected to PostgreSQL database: sylo_carpool")
        return True
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return False


async def get_all_tables() -> Set[str]:
    """Get ALL tables currently in PostgreSQL database"""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        query = """
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
            ORDER BY tablename
        """
        rows = await conn.fetch(query)
        tables = {row['tablename'] for row in rows}
        return tables
    finally:
        await conn.close()


async def get_all_enums() -> Dict[str, List[str]]:
    """Get ALL enum types in PostgreSQL database"""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        query = """
            SELECT t.typname as enum_name, e.enumlabel as enum_value
            FROM pg_type t 
            JOIN pg_enum e ON t.oid = e.enumtypid  
            JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
            WHERE n.nspname = 'public'
            ORDER BY t.typname, e.enumsortorder
        """
        rows = await conn.fetch(query)
        
        enums = {}
        for row in rows:
            enum_name = row['enum_name']
            enum_value = row['enum_value']
            if enum_name not in enums:
                enums[enum_name] = []
            enums[enum_name].append(enum_value)
        
        return enums
    finally:
        await conn.close()


async def get_alembic_version() -> str:
    """Get current Alembic migration version from database"""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        query = "SELECT version_num FROM alembic_version"
        row = await conn.fetchrow(query)
        return row['version_num'] if row else "No version found"
    finally:
        await conn.close()


async def get_table_row_counts() -> Dict[str, int]:
    """Get row count for each table"""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        tables = await get_all_tables()
        counts = {}
        
        for table in sorted(tables):
            if table == 'alembic_version':
                continue
            try:
                count = await conn.fetchval(f'SELECT COUNT(*) FROM "{table}"')
                counts[table] = count
            except Exception as e:
                counts[table] = f"Error: {e}"
        
        return counts
    finally:
        await conn.close()


async def verify_critical_columns() -> Dict[str, List[str]]:
    """Verify critical columns exist in key tables"""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        critical_tables = {
            "users": ["id", "email", "password_hash", "role", "full_name"],
            "drivers": ["user_id", "license_number", "verified", "rating_avg"],
            "rides": ["id", "driver_id", "start_point_lat", "start_point_lng", "status"],
            "bookings": ["id", "ride_id", "passenger_id", "status"],
            "wallets": ["user_id", "balance"],
            "wallet_transactions": ["id", "wallet_id", "amount", "transaction_type"],
            "driver_profiles": ["id", "user_id", "license_number", "is_verified"],
            "match_records": ["id", "ride_id", "driver_id", "passenger_id"],
            "notifications": ["id", "user_id", "message"],
            "recurring_schedules": ["id", "user_id", "days_of_week", "time"]
        }
        
        results = {}
        
        for table, expected_columns in critical_tables.items():
            query = """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'public' AND table_name = $1
                ORDER BY ordinal_position
            """
            rows = await conn.fetch(query, table)
            actual_columns = [row['column_name'] for row in rows]
            
            missing = [col for col in expected_columns if col not in actual_columns]
            results[table] = {
                "exists": len(actual_columns) > 0,
                "expected": expected_columns,
                "actual": actual_columns,
                "missing": missing,
                "status": "✅" if not missing and len(actual_columns) > 0 else "⚠️"
            }
        
        return results
    finally:
        await conn.close()


async def main():
    """Main verification routine"""
    print("=" * 80)
    print("🔍 DEEP MIGRATION VERIFICATION - REAL DATABASE SCAN")
    print("=" * 80)
    print()
    
    # Step 1: Connection Test
    print("📡 STEP 1: Testing Database Connection...")
    if not await check_database_connection():
        print("❌ Cannot proceed - database not accessible")
        return
    print()
    
    # Step 2: Get all actual tables
    print("📊 STEP 2: Scanning ALL Tables in PostgreSQL...")
    actual_tables = await get_all_tables()
    print(f"   Found {len(actual_tables)} tables in database")
    print()
    
    # Step 3: Compare expected vs actual
    print("🔎 STEP 3: Comparing Expected vs Actual Tables...")
    missing_tables = EXPECTED_TABLES - actual_tables
    extra_tables = actual_tables - EXPECTED_TABLES
    matching_tables = EXPECTED_TABLES & actual_tables
    
    print(f"   ✅ Matching tables: {len(matching_tables)}/{len(EXPECTED_TABLES)}")
    print(f"   ⚠️  Missing tables: {len(missing_tables)}")
    print(f"   ℹ️  Extra tables: {len(extra_tables)}")
    print()
    
    if missing_tables:
        print("   ⚠️  MISSING TABLES:")
        for table in sorted(missing_tables):
            print(f"      - {table}")
        print()
    
    if extra_tables:
        print("   ℹ️  EXTRA TABLES (not in expected list):")
        for table in sorted(extra_tables):
            print(f"      - {table}")
        print()
    
    # Step 4: Check Alembic version
    print("📌 STEP 4: Checking Alembic Migration Version...")
    version = await get_alembic_version()
    print(f"   Current version: {version}")
    print(f"   Expected latest: ecee828ee6ee")
    print(f"   Status: {'✅ UP TO DATE' if version == 'ecee828ee6ee' else '⚠️ NOT LATEST'}")
    print()
    
    # Step 5: Check enums
    print("🎨 STEP 5: Verifying Database Enums...")
    enums = await get_all_enums()
    print(f"   Found {len(enums)} enum types:")
    for enum_name, values in sorted(enums.items()):
        print(f"      • {enum_name}: {len(values)} values ({', '.join(values[:3])}...)")
    print()
    
    # Step 6: Row counts
    print("📈 STEP 6: Checking Table Row Counts...")
    counts = await get_table_row_counts()
    tables_with_data = {k: v for k, v in counts.items() if isinstance(v, int) and v > 0}
    print(f"   Tables with data: {len(tables_with_data)}")
    for table, count in sorted(tables_with_data.items()):
        print(f"      • {table}: {count} rows")
    print()
    
    # Step 7: Critical columns verification
    print("🔍 STEP 7: Verifying Critical Columns in Key Tables...")
    column_checks = await verify_critical_columns()
    for table, result in sorted(column_checks.items()):
        print(f"   {result['status']} {table}:")
        if result['exists']:
            print(f"      Columns: {len(result['actual'])} found")
            if result['missing']:
                print(f"      ⚠️  Missing: {', '.join(result['missing'])}")
        else:
            print(f"      ❌ Table does not exist!")
    print()
    
    # Final Summary
    print("=" * 80)
    print("📋 FINAL VERIFICATION SUMMARY")
    print("=" * 80)
    
    # Calculate completion percentage
    completion = (len(matching_tables) / len(EXPECTED_TABLES)) * 100
    
    print()
    print(f"🎯 Database: sylo_carpool (PostgreSQL)")
    print(f"📊 Tables Present: {len(actual_tables)} total")
    print(f"✅ Expected Tables Found: {len(matching_tables)}/{len(EXPECTED_TABLES)} ({completion:.1f}%)")
    print(f"🔢 Tables with Data: {len(tables_with_data)}")
    print(f"📌 Migration Version: {version}")
    print(f"🎨 Enum Types: {len(enums)}")
    print()
    
    if completion == 100 and version == "ecee828ee6ee" and len(tables_with_data) > 0:
        print("🎉 " + "=" * 76 + " 🎉")
        print("🎉 ✅ ALL MIGRATIONS VERIFIED AS REAL - NOT HYPOTHETICAL!")
        print("🎉 ✅ 100% OF EXPECTED TABLES EXIST IN POSTGRESQL DATABASE!")
        print("🎉 ✅ MIGRATION VERSION IS UP TO DATE!")
        print("🎉 ✅ REAL DATA EXISTS IN DATABASE!")
        print("🎉 " + "=" * 76 + " 🎉")
    else:
        print("⚠️  VERIFICATION INCOMPLETE:")
        if completion < 100:
            print(f"   • {len(missing_tables)} tables missing")
        if version != "ecee828ee6ee":
            print(f"   • Migration version not at latest")
        if len(tables_with_data) == 0:
            print(f"   • No data in any tables")
    
    print()
    print("=" * 80)
    print("🔍 ALL TABLES IN YOUR REAL POSTGRESQL DATABASE:")
    print("=" * 80)
    for i, table in enumerate(sorted(actual_tables), 1):
        count = counts.get(table, 0)
        count_str = f"({count} rows)" if isinstance(count, int) else "(system)"
        print(f"{i:2}. {table:35} {count_str}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
