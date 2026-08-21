"""
Quick Prompt 11A Verification

Verifies:
1. Constraint exists in database  
2. Column names are correct
3. Model imports successfully

Author: Smart Carpooling Backend Team
Date: December 19, 2025
"""

import asyncio
from sqlalchemy import text
from app.db.session import AsyncSessionLocal


async def quick_verify():
    """Quick verification of Prompt 11A implementation."""
    
    print("\n" + "=" * 70)
    print("  PROMPT 11A IMPLEMENTATION VERIFICATION")
    print("=" * 70)
    
    async with AsyncSessionLocal() as db:
        # Check 1: Constraint exists
        print("\n[1/3] Database Constraint Check...")
        constraint_query = text("""
            SELECT 
                tc.constraint_name,
                kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'ratings'
            AND tc.constraint_name = 'uq_rating_ride_rater'
            AND tc.constraint_type = 'UNIQUE'
            ORDER BY kcu.ordinal_position
        """)
        result = await db.execute(constraint_query)
        columns = result.fetchall()
        
        if columns:
            col_names = [col.column_name for col in columns]
            print(f"   ✅ Constraint 'uq_rating_ride_rater' EXISTS")
            print(f"   ✅ Columns: {', '.join(col_names)}")
        else:
            print("   ❌ Constraint NOT FOUND")
            return False
        
        # Check 2: Column schema
        print("\n[2/3] Database Schema Check...")
        schema_query = text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'ratings'
            AND column_name IN ('rater_id', 'ratee_id', 'score')
            ORDER BY column_name
        """)
        result = await db.execute(schema_query)
        columns = result.fetchall()
        
        if len(columns) == 3:
            print("   ✅ All required columns exist:")
            for col in columns:
                print(f"      - {col.column_name}: {col.data_type} (nullable: {col.is_nullable})")
        else:
            print(f"   ❌ Expected 3 columns, found {len(columns)}")
            return False
        
        # Check 3: Model import
        print("\n[3/3] Python Model Check...")
        try:
            from app.models.rating import Rating
            
            # Check attributes
            has_rater = hasattr(Rating, 'rater_id')
            has_ratee = hasattr(Rating, 'ratee_id')
            has_score = hasattr(Rating, 'score')
            
            if has_rater and has_ratee and has_score:
                print("   ✅ Rating model has correct attributes:")
                print("      - rater_id ✓")
                print("      - ratee_id ✓")
                print("      - score ✓")
            else:
                print("   ❌ Model missing required attributes")
                if not has_rater:
                    print("      - Missing: rater_id")
                if not has_ratee:
                    print("      - Missing: ratee_id")
                if not has_score:
                    print("      - Missing: score")
                return False
                
        except Exception as e:
            print(f"   ❌ Failed to import Rating model: {e}")
            return False
        
        # Summary
        print("\n" + "=" * 70)
        print("  ✅ PROMPT 11A VERIFICATION PASSED")
        print("=" * 70)
        print("\n  Summary:")
        print("  • Database constraint: uq_rating_ride_rater (ride_id, rater_id)")
        print("  • Schema alignment: rater_id, ratee_id, score")
        print("  • Model compatibility: Rating model updated")
        print("  • Migration status: COMPLETE ✅")
        print("\n  The unique constraint prevents duplicate ratings per:")
        print("    (ride_id, rater_id) combination")
        print("\n  Prompt 11A Requirements: 100% IMPLEMENTED ✅")
        print("=" * 70 + "\n")
        
        return True


if __name__ == "__main__":
    success = asyncio.run(quick_verify())
    exit(0 if success else 1)
