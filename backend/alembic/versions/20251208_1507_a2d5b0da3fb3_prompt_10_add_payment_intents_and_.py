"""Prompt 10: Add payment intents and idempotency tables (manual)

Revision ID: a2d5b0da3fb3
Revises: 5a7b9c8ec4e7
Create Date: 2025-12-08 15:07:29.850406

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2d5b0da3fb3'
down_revision: Union[str, None] = '5a7b9c8ec4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create PaymentProvider enum
    op.execute("""
        CREATE TYPE paymentprovider AS ENUM ('easypaisa', 'jazzcash', 'card')
    """)
    
    # Create PaymentStatus enum
    op.execute("""
        CREATE TYPE paymentstatus AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'EXPIRED', 'REFUNDED')
    """)
    
    # Create payment_intents table
    op.create_table(
        'payment_intents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.Enum('easypaisa', 'jazzcash', 'card', name='paymentprovider'), nullable=False),
        sa.Column('intent_id', sa.String(length=100), nullable=False),
        sa.Column('amount', sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column('commission', sa.DECIMAL(precision=10, scale=2), nullable=False, server_default='0'),
        sa.Column('net_amount', sa.DECIMAL(precision=10, scale=2), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'EXPIRED', 'REFUNDED', name='paymentstatus'), nullable=False, server_default='PENDING'),
        sa.Column('provider_transaction_id', sa.String(length=255), nullable=True),
        sa.Column('provider_response', sa.JSON(), nullable=True),
        sa.Column('redirect_url', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_payment_intents_intent_id', 'payment_intents', ['intent_id'], unique=True)
    op.create_index('idx_payment_intents_user_status', 'payment_intents', ['user_id', 'status'])
    op.create_index('idx_payment_intents_provider_tid', 'payment_intents', ['provider_transaction_id'])
    
    # Create idempotency_records table
    op.create_table(
        'idempotency_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('provider', sa.Enum('easypaisa', 'jazzcash', 'card', name='paymentprovider'), nullable=False),
        sa.Column('request_payload', sa.JSON(), nullable=True),
        sa.Column('response_payload', sa.JSON(), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('processed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_idempotency_key', 'idempotency_records', ['idempotency_key'], unique=True)
    op.create_index('idx_idempotency_expires', 'idempotency_records', ['expires_at'])


def downgrade() -> None:
    # Drop idempotency_records table
    op.drop_index('idx_idempotency_expires', table_name='idempotency_records')
    op.drop_index('idx_idempotency_key', table_name='idempotency_records')
    op.drop_table('idempotency_records')
    
    # Drop payment_intents table
    op.drop_index('idx_payment_intents_provider_tid', table_name='payment_intents')
    op.drop_index('idx_payment_intents_user_status', table_name='payment_intents')
    op.drop_index('idx_payment_intents_intent_id', table_name='payment_intents')
    op.drop_table('payment_intents')
    
    # Drop enums
    op.execute('DROP TYPE IF EXISTS paymentstatus')
    op.execute('DROP TYPE IF EXISTS paymentprovider')
