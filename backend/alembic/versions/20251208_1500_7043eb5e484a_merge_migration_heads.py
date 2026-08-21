"""Merge migration heads

Revision ID: 7043eb5e484a
Revises: 18cd3a19027b, prompt5_rides_scheduling
Create Date: 2025-12-08 15:00:26.729322

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7043eb5e484a'
down_revision: Union[str, None] = ('18cd3a19027b', 'prompt5_rides_scheduling')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
