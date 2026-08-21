"""List all database models that should exist"""
from app.db.base import Base

print("=" * 80)
print("ALL TABLES DEFINED IN MODELS (Should exist in database)")
print("=" * 80)

tables = sorted(Base.metadata.tables.keys())
print(f"\n✅ Total models defined: {len(tables)}")

print("\n📋 Complete list of tables:")
for i, table in enumerate(tables, 1):
    print(f"  {i}. {table}")

print("\n" + "=" * 80)
