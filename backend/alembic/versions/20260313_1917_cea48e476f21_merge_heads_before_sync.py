"""Merge heads before sync

Revision ID: cea48e476f21
Revises: ecb1dd94e6f8, 20260712_chat, 20260715_ride_req
Create Date: 2026-03-13 19:17:38.847376

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cea48e476f21'
down_revision: Union[str, None] = ('ecb1dd94e6f8', '20260712_chat', '20260715_ride_req')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
