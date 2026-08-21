"""Add Prompt 5 features: buffer_seats, booking.version, recurring_schedules

Revision ID: prompt5_rides_scheduling
Revises: 95241d562070
Create Date: 2025-12-08 15:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

# revision identifiers, used by Alembic.
revision = 'prompt5_rides_scheduling'
down_revision = '95241d562070'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Prompt 5 features to database."""
    
    # 1. Add buffer_seats to rides table
    op.add_column('rides', sa.Column(
        'buffer_seats',
        sa.Integer(),
        nullable=False,
        server_default='0',
        comment='Optional seats kept aside from immediate booking'
    ))
    
    # 2. Add version to bookings table (for optimistic concurrency)
    op.add_column('bookings', sa.Column(
        'version',
        sa.Integer(),
        nullable=False,
        server_default='0',
        comment='Version field for optimistic locking'
    ))
    
    # 3. Create recurring_schedules table
    op.create_table(
        'recurring_schedules',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('days_of_week', JSON, nullable=False, comment="List of days: ['Mon', 'Tue', 'Wed', ...]"),
        sa.Column('time', sa.Time(), nullable=False, comment='Time of day for ride (e.g., 08:00:00)'),
        sa.Column('start_point_lat', sa.Float(), nullable=False),
        sa.Column('start_point_lng', sa.Float(), nullable=False),
        sa.Column('start_point_address', sa.String(500), nullable=False),
        sa.Column('end_point_lat', sa.Float(), nullable=False),
        sa.Column('end_point_lng', sa.Float(), nullable=False),
        sa.Column('end_point_address', sa.String(500), nullable=False),
        sa.Column('polyline_main', sa.String(), nullable=True, comment='Encoded polyline for route'),
        sa.Column('seats_offered', sa.Integer(), nullable=False),
        sa.Column('base_price', sa.Float(), nullable=False),
        sa.Column('buffer_seats', sa.Integer(), nullable=False, server_default='0', comment='Optional seats kept aside'),
        sa.Column('start_date', sa.Date(), nullable=False, comment='Schedule becomes active from this date'),
        sa.Column('end_date', sa.Date(), nullable=False, comment='Schedule ends after this date'),
        sa.Column('recurrence_meta', JSON, nullable=True, comment='Additional metadata: {exclude_dates: [], preferences: {}}'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())
    )
    
    # 4. Create indexes for recurring_schedules
    op.create_index('idx_schedules_user_id', 'recurring_schedules', ['user_id'])
    op.create_index('idx_schedules_is_active', 'recurring_schedules', ['is_active'])
    op.create_index('idx_schedules_date_range', 'recurring_schedules', ['start_date', 'end_date'])
    op.create_index('idx_schedules_user_active', 'recurring_schedules', ['user_id', 'is_active'])


def downgrade() -> None:
    """Revert Prompt 5 features."""
    
    # Drop indexes
    op.drop_index('idx_schedules_user_active', 'recurring_schedules')
    op.drop_index('idx_schedules_date_range', 'recurring_schedules')
    op.drop_index('idx_schedules_is_active', 'recurring_schedules')
    op.drop_index('idx_schedules_user_id', 'recurring_schedules')
    
    # Drop table
    op.drop_table('recurring_schedules')
    
    # Remove columns
    op.drop_column('bookings', 'version')
    op.drop_column('rides', 'buffer_seats')
