"""add chat_messages table

Revision ID: 20260712_chat_messages
Revises: 
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '20260712_chat'
down_revision = None
branch_labels = ('chat',)
depends_on = None


def upgrade() -> None:
    op.create_table(
        'chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('ride_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('rides.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('sender_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_chat_ride_created', 'chat_messages', ['ride_id', 'created_at'])
    op.create_index('ix_chat_ride_unread', 'chat_messages', ['ride_id', 'is_read'])


def downgrade() -> None:
    op.drop_index('ix_chat_ride_unread', table_name='chat_messages')
    op.drop_index('ix_chat_ride_created', table_name='chat_messages')
    op.drop_table('chat_messages')
