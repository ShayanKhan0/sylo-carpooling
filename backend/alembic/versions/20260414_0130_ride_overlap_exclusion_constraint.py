"""Add exclusion constraint to prevent overlapping active ride windows per driver.

Revision ID: 20260414_ride_overlap_excl
Revises: 20260414_ride_overlap
Create Date: 2026-04-14 01:30:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260414_ride_overlap_excl"
down_revision: Union[str, None] = "20260414_ride_overlap"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create a GiST exclusion constraint for driver time-window overlap."""
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")

    op.execute(
        """
        DO $do$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'rides_no_driver_time_overlap'
            ) THEN
                ALTER TABLE rides
                ADD CONSTRAINT rides_no_driver_time_overlap
                EXCLUDE USING gist (
                    driver_id WITH =,
                    tstzrange(
                        departure_time,
                        departure_time + make_interval(
                            mins => COALESCE(
                                NULLIF(estimated_duration_minutes, 0),
                                NULLIF(CEIL((COALESCE(route_distance_km, 0)::numeric / 40.0) * 60), 0)::int,
                                45
                            )
                        ),
                        '[)'
                    ) WITH &&
                )
                WHERE (
                    driver_id IS NOT NULL
                    AND departure_time IS NOT NULL
                    AND LOWER(COALESCE(status::text, '')) IN ('open', 'scheduled', 'in_progress', 'ongoing')
                )
                DEFERRABLE INITIALLY IMMEDIATE;
            END IF;
        END;
        $do$;
        """
    )


def downgrade() -> None:
    """Drop exclusion constraint for overlap guard."""
    op.execute(
        """
        ALTER TABLE rides
        DROP CONSTRAINT IF EXISTS rides_no_driver_time_overlap;
        """
    )
