"""Add unique constraint for Prompt 11A ratings (simple version)

Revision ID: prompt11a_unique
Revises: ecee828ee6ee
Create Date: 2025-12-19 23:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'prompt11a_unique'
down_revision: Union[str, None] = 'ecee828ee6ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint for (ride_id, from_user_id) in ratings table."""
    # Check if constraint already exists
    conn = op.get_bind()
    result = conn.execute(sa.text("""
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_rating_ride_from_user'
    """))
    
    if result.fetchone() is None:
        op.create_unique_constraint(
            'uq_rating_ride_from_user',
            'ratings',
            ['ride_id', 'from_user_id']
        )


def downgrade() -> None:
    """Remove unique constraint from ratings table."""
    op.drop_constraint('uq_rating_ride_from_user', 'ratings', type_='unique')
