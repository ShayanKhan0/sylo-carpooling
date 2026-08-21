"""Add admin audit logs and payout admin fields

Revision ID: 8c1b2f3e4a5b
Revises: 3084e66d9a5d
Create Date: 2026-01-23 23:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8c1b2f3e4a5b'
down_revision: Union[str, None] = '3084e66d9a5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create admin_audit_logs table
    op.create_table(
        'admin_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('admin_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action_type', sa.String(length=100), nullable=False),
        sa.Column('target_entity', sa.String(length=100), nullable=False),
        sa.Column('target_id', sa.String(length=100), nullable=True),
        sa.Column('meta_data', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_admin_audit_action_type', 'admin_audit_logs', ['action_type'], unique=False)
    op.create_index('idx_admin_audit_target_entity', 'admin_audit_logs', ['target_entity'], unique=False)
    op.create_index('idx_admin_audit_created_at', 'admin_audit_logs', ['created_at'], unique=False)
    op.create_index('ix_admin_audit_logs_admin_id', 'admin_audit_logs', ['admin_id'], unique=False)
    op.create_index('ix_admin_audit_logs_target_id', 'admin_audit_logs', ['target_id'], unique=False)

    # Add admin fields to payouts
    with op.batch_alter_table('payouts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('admin_id', postgresql.UUID(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column('admin_action', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('admin_action_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_payouts_admin_id', ['admin_id'], unique=False)
        batch_op.create_foreign_key('payouts_admin_id_fkey', 'users', ['admin_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    with op.batch_alter_table('payouts', schema=None) as batch_op:
        batch_op.drop_constraint('payouts_admin_id_fkey', type_='foreignkey')
        batch_op.drop_index('ix_payouts_admin_id')
        batch_op.drop_column('admin_action_at')
        batch_op.drop_column('admin_action')
        batch_op.drop_column('admin_id')

    op.drop_index('ix_admin_audit_logs_target_id', table_name='admin_audit_logs')
    op.drop_index('ix_admin_audit_logs_admin_id', table_name='admin_audit_logs')
    op.drop_index('idx_admin_audit_created_at', table_name='admin_audit_logs')
    op.drop_index('idx_admin_audit_target_entity', table_name='admin_audit_logs')
    op.drop_index('idx_admin_audit_action_type', table_name='admin_audit_logs')
    op.drop_table('admin_audit_logs')
