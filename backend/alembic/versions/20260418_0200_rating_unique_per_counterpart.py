"""Allow one rating per counterpart per ride

Revision ID: 20260418_0200_rate_unique_ctr
Revises: 20260715_ride_req
Create Date: 2026-04-18 02:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260418_0200_rate_unique_ctr"
down_revision: Union[str, None] = "20260715_ride_req"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_constraint_if_exists(name: str) -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_constraint
            WHERE conname = :name
            """
        ),
        {"name": name},
    )
    if result.fetchone() is not None:
        op.drop_constraint(name, "ratings", type_="unique")


def _create_constraint_if_missing(name: str, columns: list[str]) -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_constraint
            WHERE conname = :name
            """
        ),
        {"name": name},
    )
    if result.fetchone() is None:
        op.create_unique_constraint(name, "ratings", columns)


def upgrade() -> None:
    _drop_constraint_if_exists("uq_rating_ride_rater")
    _drop_constraint_if_exists("uq_rating_ride_from_user")
    _create_constraint_if_missing(
        "uq_rating_ride_rater_ratee",
        ["ride_id", "rater_id", "ratee_id"],
    )


def downgrade() -> None:
    _drop_constraint_if_exists("uq_rating_ride_rater_ratee")
    _create_constraint_if_missing(
        "uq_rating_ride_rater",
        ["ride_id", "rater_id"],
    )
