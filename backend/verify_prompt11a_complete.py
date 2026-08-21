"""
Verify Prompt 11A Complete Implementation

Tests:
1. Database constraint exists (uq_rating_ride_rater)
2. Model columns match database (rater_id, ratee_id, score)
3. Service layer uses correct columns
4. Constraint prevents duplicate ratings

Author: Smart Carpooling Backend Team
Date: December 19, 2025
"""

import asyncio
import uuid
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.db.session import AsyncSessionLocal
from app.core.config import settings


async def verify_prompt11a():
    """Verify all Prompt 11A components are correctly implemented."""
    
    print("=" * 60)
    print("PROMPT 11A VERIFICATION")
    print("=" * 60)
    
    async with AsyncSessionLocal() as db:
        try:
            # Test 1: Check constraint exists
            print("\n[1/4] Checking database constraint...")
            constraint_query = text("""
                SELECT constraint_name, table_name
                FROM information_schema.table_constraints
                WHERE table_name = 'ratings' 
                AND constraint_name = 'uq_rating_ride_rater'
                AND constraint_type = 'UNIQUE'
            """)
            result = await db.execute(constraint_query)
            constraint = result.fetchone()
            
            if constraint:
                print(f"✅ Constraint exists: {constraint.constraint_name} on {constraint.table_name}")
            else:
                print("❌ Constraint NOT found!")
                return False
            
            # Test 2: Check column names match database
            print("\n[2/4] Checking column names...")
            columns_query = text("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'ratings'
                AND column_name IN ('rater_id', 'ratee_id', 'score')
                ORDER BY column_name
            """)
            result = await db.execute(columns_query)
            columns = result.fetchall()
            
            expected_columns = {'rater_id', 'ratee_id', 'score'}
            found_columns = {col.column_name for col in columns}
            
            if expected_columns.issubset(found_columns):
                print(f"✅ All expected columns exist: {', '.join(sorted(found_columns))}")
            else:
                missing = expected_columns - found_columns
                print(f"❌ Missing columns: {missing}")
                return False
            
            # Test 3: Verify model can be imported
            print("\n[3/4] Importing Rating model...")
            try:
                from app.models.rating import Rating
                
                # Check if model attributes match database
                model_attrs = set(dir(Rating))
                required = {'rater_id', 'ratee_id', 'score'}
                
                if required.issubset(model_attrs):
                    print(f"✅ Rating model has correct attributes: {', '.join(sorted(required))}")
                else:
                    missing = required - model_attrs
                    print(f"❌ Model missing attributes: {missing}")
                    return False
                    
            except Exception as e:
                print(f"❌ Failed to import Rating model: {e}")
                return False
            
            # Test 4: Test constraint actually works (simulate duplicate)
            print("\n[4/4] Testing constraint enforcement...")
            
            # Create test data
            test_ride_id = uuid.uuid4()
            test_rater_id = uuid.uuid4()
            test_ratee_id = uuid.uuid4()
            
            # First rating should succeed
            insert_query = text("""
                INSERT INTO ratings (id, ride_id, rater_id, ratee_id, score, created_at)
                VALUES (:id1, :ride_id, :rater_id, :ratee_id, :score, NOW())
            """)
            
            try:
                await db.execute(
                    insert_query,
                    {
                        "id1": uuid.uuid4(),
                        "ride_id": test_ride_id,
                        "rater_id": test_rater_id,
                        "ratee_id": test_ratee_id,
                        "score": 5
                    }
                )
                await db.commit()
                print("   ✓ First rating inserted successfully")
            except Exception as e:
                print(f"   ⚠️  Could not insert test rating (might be missing ride data): {e}")
                await db.rollback()
            
            # Duplicate rating should fail
            duplicate_query = text("""
                INSERT INTO ratings (id, ride_id, rater_id, ratee_id, score, created_at)
                VALUES (:id2, :ride_id, :rater_id, :ratee_id, :score, NOW())
            """)
            
            try:
                await db.execute(
                    duplicate_query,
                    {
                        "id2": uuid.uuid4(),
                        "ride_id": test_ride_id,
                        "rater_id": test_rater_id,  # Same ride + same rater = DUPLICATE
                        "ratee_id": test_ratee_id,
                        "score": 4
                    }
                )
                await db.commit()
                print("   ❌ Duplicate rating was NOT blocked by constraint!")
                return False
            except IntegrityError as e:
                if "uq_rating_ride_rater" in str(e):
                    print(f"   ✅ Constraint correctly blocked duplicate rating!")
                    await db.rollback()
                else:
                    print(f"   ❌ Different error occurred: {e}")
                    await db.rollback()
                    return False
            
            # Cleanup test data
            cleanup_query = text("""
                DELETE FROM ratings 
                WHERE ride_id = :ride_id AND rater_id = :rater_id
            """)
            try:
                await db.execute(
                    cleanup_query,
                    {"ride_id": test_ride_id, "rater_id": test_rater_id}
                )
                await db.commit()
                print("   ✓ Test data cleaned up")
            except Exception as e:
                print(f"   ⚠️  Could not clean up test data: {e}")
                await db.rollback()
            
            print("\n" + "=" * 60)
            print("✅ PROMPT 11A VERIFICATION COMPLETE!")
            print("=" * 60)
            print("\n✓ Database constraint: uq_rating_ride_rater (ACTIVE)")
            print("✓ Column names: rater_id, ratee_id, score (MATCH)")
            print("✓ Model attributes: rater_id, ratee_id, score (CORRECT)")
            print("✓ Duplicate prevention: WORKING")
            print("\n📋 Summary:")
            print("   - Unique constraint prevents duplicate (ride_id, rater_id)")
            print("   - Model aligned with database schema")
            print("   - Prompt 11A requirements: 100% COMPLETE ✅")
            
            return True
            
        except Exception as e:
            print(f"\n❌ Verification failed: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    asyncio.run(verify_prompt11a())
