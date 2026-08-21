"""Add missing priority and delivery_status columns to notifications table."""
import asyncio
import asyncpg

async def fix():
    conn = await asyncpg.connect("postgresql://postgres:root@localhost:5432/sylo_carpool")
    
    # Check existing columns
    cols = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'notifications'"
    )
    existing = {c["column_name"] for c in cols}
    print(f"Existing columns: {existing}")
    
    # Create enum types if they don't exist
    if "priority" not in existing:
        await conn.execute("""
            DO $$ BEGIN
                CREATE TYPE notificationpriorityenum AS ENUM ('low', 'normal', 'high');
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """)
        await conn.execute("""
            ALTER TABLE notifications 
            ADD COLUMN priority notificationpriorityenum NOT NULL DEFAULT 'normal'
        """)
        print("Added 'priority' column")
    else:
        print("'priority' column already exists")
    
    if "delivery_status" not in existing:
        await conn.execute("""
            DO $$ BEGIN
                CREATE TYPE deliverystatusenum AS ENUM ('pending', 'sent', 'failed', 'read');
            EXCEPTION WHEN duplicate_object THEN null;
            END $$;
        """)
        await conn.execute("""
            ALTER TABLE notifications 
            ADD COLUMN delivery_status deliverystatusenum NOT NULL DEFAULT 'pending'
        """)
        print("Added 'delivery_status' column")
    else:
        print("'delivery_status' column already exists")
    
    if "sent_at" not in existing:
        await conn.execute("ALTER TABLE notifications ADD COLUMN sent_at TIMESTAMP NULL")
        print("Added 'sent_at' column")
    
    if "read_at" not in existing:
        await conn.execute("ALTER TABLE notifications ADD COLUMN read_at TIMESTAMP NULL")
        print("Added 'read_at' column")
    
    if "meta_data" not in existing:
        await conn.execute("ALTER TABLE notifications ADD COLUMN meta_data JSONB NULL DEFAULT '{}'::jsonb")
        print("Added 'meta_data' column")
    
    # Create indexes if they don't exist
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_notifications_user_status 
        ON notifications (user_id, delivery_status)
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS ix_notifications_user_created 
        ON notifications (user_id, created_at)
    """)
    print("Indexes ensured")
    
    # Verify
    cols2 = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'notifications' ORDER BY ordinal_position"
    )
    print(f"Final columns: {[c['column_name'] for c in cols2]}")
    
    await conn.close()
    print("Done!")

asyncio.run(fix())
