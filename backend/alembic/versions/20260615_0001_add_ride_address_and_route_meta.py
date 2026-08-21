"""Add address and route metadata columns to rides table

Revision ID: a1b2c3d4e5f6
Revises: 8c1b2f3e4a5b
Create Date: 2026-06-15 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '8c1b2f3e4a5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add human-readable address columns and route metadata to rides."""
    op.add_column('rides', sa.Column('start_point_address', sa.Text(), nullable=True))
    op.add_column('rides', sa.Column('end_point_address', sa.Text(), nullable=True))
    op.add_column('rides', sa.Column('estimated_duration_minutes', sa.Integer(), nullable=True))
    op.add_column('rides', sa.Column('route_distance_km', sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove address and route metadata columns from rides."""
    op.drop_column('rides', 'route_distance_km')
    op.drop_column('rides', 'estimated_duration_minutes')
    op.drop_column('rides', 'end_point_address')
    op.drop_column('rides', 'start_point_address')
