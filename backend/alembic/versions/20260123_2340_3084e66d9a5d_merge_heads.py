"""merge_heads

Revision ID: 3084e66d9a5d
Revises: prompt11a_unique
Create Date: 2026-01-23 23:40:34.100217

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3084e66d9a5d'
down_revision: Union[str, None] = 'prompt11a_unique'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
