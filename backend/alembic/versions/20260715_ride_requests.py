"""Add ride_requests table for passenger-initiated ride requests

Revision ID: 20260715_ride_req
Revises: a1b2c3d4e5f6
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260715_ride_req'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create the enum type first
    ride_request_status = postgresql.ENUM(
        'pending', 'accepted', 'cancelled', 'expired',
        name='ride_request_status', create_type=True
    )
    ride_request_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'ride_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('passenger_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('origin', sa.Text(), nullable=False),
        sa.Column('origin_lat', sa.Float(), nullable=False),
        sa.Column('origin_lng', sa.Float(), nullable=False),
        sa.Column('destination', sa.Text(), nullable=False),
        sa.Column('destination_lat', sa.Float(), nullable=False),
        sa.Column('destination_lng', sa.Float(), nullable=False),
        sa.Column('seats_needed', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('max_budget', sa.Float(), nullable=True),
        sa.Column('departure_time', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('status', sa.Enum('pending', 'accepted', 'cancelled', 'expired',
                                     name='ride_request_status', create_type=False),
                  nullable=False, server_default='pending'),
        sa.Column('accepted_by_driver_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('ride_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('rides.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index('idx_rr_passenger', 'ride_requests', ['passenger_id'])
    op.create_index('idx_rr_status', 'ride_requests', ['status'])
    op.create_index('idx_rr_origin', 'ride_requests', ['origin_lat', 'origin_lng'])
    op.create_index('idx_rr_departure', 'ride_requests', ['departure_time'])


def downgrade() -> None:
    op.drop_table('ride_requests')
    op.execute("DROP TYPE IF EXISTS ride_request_status")
