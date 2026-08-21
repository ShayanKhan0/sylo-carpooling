"""Check if Prompt 10 tables exist and create them if needed."""
import asyncio
from sqlalchemy import text
from app.db.session import engine


async def check_and_create_tables():
    """Check if payment_intents and idempotency_records tables exist."""
    async with engine.begin() as conn:
        # Check existing tables
        result = await conn.execute(text("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname='public' 
            AND tablename IN ('payment_intents', 'idempotency_records')
        """))
        existing_tables = [row[0] for row in result]
        print(f"Existing Prompt 10 tables: {existing_tables}")
        
        if 'payment_intents' not in existing_tables:
            print("\nCreating payment_intents table...")
            
            # Create enums if they don't exist
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE paymentprovider AS ENUM ('easypaisa', 'jazzcash', 'card');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE paymentstatus AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'EXPIRED', 'REFUNDED');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))
            
            # Create payment_intents table
            await conn.execute(text("""
                CREATE TABLE payment_intents (
                    id SERIAL PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    provider paymentprovider NOT NULL,
                    intent_id VARCHAR(100) NOT NULL,
                    amount DECIMAL(10, 2) NOT NULL,
                    commission DECIMAL(10, 2) NOT NULL DEFAULT 0,
                    net_amount DECIMAL(10, 2) NOT NULL,
                    status paymentstatus NOT NULL DEFAULT 'PENDING',
                    provider_transaction_id VARCHAR(255),
                    provider_response JSONB,
                    redirect_url TEXT,
                    expires_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    extra_data JSONB,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Create indexes
            await conn.execute(text("CREATE UNIQUE INDEX idx_payment_intents_intent_id ON payment_intents(intent_id)"))
            await conn.execute(text("CREATE INDEX idx_payment_intents_user_status ON payment_intents(user_id, status)"))
            await conn.execute(text("CREATE INDEX idx_payment_intents_provider_tid ON payment_intents(provider_transaction_id)"))
            print("✅ payment_intents table created successfully")
        
        if 'idempotency_records' not in existing_tables:
            print("\nCreating idempotency_records table...")
            await conn.execute(text("""
                CREATE TABLE idempotency_records (
                    id SERIAL PRIMARY KEY,
                    idempotency_key VARCHAR(255) NOT NULL,
                    provider paymentprovider NOT NULL,
                    request_payload JSONB,
                    response_payload JSONB,
                    status_code INTEGER,
                    processed BOOLEAN NOT NULL DEFAULT false,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Create indexes
            await conn.execute(text("CREATE UNIQUE INDEX idx_idempotency_key ON idempotency_records(idempotency_key)"))
            await conn.execute(text("CREATE INDEX idx_idempotency_expires ON idempotency_records(expires_at)"))
            print("✅ idempotency_records table created successfully")
        
        print("\n✅ All Prompt 10 tables are ready!")


if __name__ == "__main__":
    asyncio.run(check_and_create_tables())
