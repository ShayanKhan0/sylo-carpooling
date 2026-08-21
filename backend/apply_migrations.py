"""
Apply Prompt 11A database migrations.
"""
import sys
from alembic.config import Config
from alembic import command

def main():
    cfg = Config('alembic.ini')
    
    print("Applying all pending migrations...")
    try:
        command.upgrade(cfg, 'head')
        print("✅ All migrations applied successfully!")
        print("✅ Prompt 11A unique constraint is now in the database")
        return 0
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
