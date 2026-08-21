"""Add DB-level guard to prevent overlapping driver ride windows.

Revision ID: 20260414_ride_overlap
Revises: 23e71247e8e0
Create Date: 2026-04-14 01:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260414_ride_overlap"
down_revision: Union[str, None] = "23e71247e8e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create trigger function that blocks overlapping active ride windows per driver."""
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.enforce_ride_time_overlap()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $fn$
        DECLARE
            conflict_ride_id uuid;
            new_duration integer;
            new_end timestamptz;
        BEGIN
            IF NEW.driver_id IS NULL OR NEW.departure_time IS NULL THEN
                RETURN NEW;
            END IF;

            IF LOWER(COALESCE(NEW.status::text, '')) NOT IN ('open', 'scheduled', 'in_progress', 'ongoing') THEN
                RETURN NEW;
            END IF;

            new_duration := COALESCE(
                NULLIF(NEW.estimated_duration_minutes, 0),
                NULLIF(CEIL((COALESCE(NEW.route_distance_km, 0)::numeric / 40.0) * 60), 0)::int,
                45
            );

            NEW.estimated_duration_minutes := new_duration;
            new_end := NEW.departure_time + make_interval(mins => new_duration);

            PERFORM pg_advisory_xact_lock(hashtext('ride-overlap:' || NEW.driver_id::text));

            SELECT r.id
            INTO conflict_ride_id
            FROM rides r
            WHERE r.driver_id = NEW.driver_id
              AND (TG_OP <> 'UPDATE' OR r.id <> NEW.id)
              AND LOWER(COALESCE(r.status::text, '')) IN ('open', 'scheduled', 'in_progress', 'ongoing')
              AND r.departure_time < new_end
              AND (
                    r.departure_time + make_interval(
                        mins => COALESCE(
                            NULLIF(r.estimated_duration_minutes, 0),
                            NULLIF(CEIL((COALESCE(r.route_distance_km, 0)::numeric / 40.0) * 60), 0)::int,
                            45
                        )
                    )
                  ) > NEW.departure_time
            LIMIT 1;

            IF conflict_ride_id IS NOT NULL THEN
                RAISE EXCEPTION
                    'Ride time overlaps with existing ride %',
                    conflict_ride_id
                USING ERRCODE = '23P01';
            END IF;

            RETURN NEW;
        END;
        $fn$;
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_enforce_ride_time_overlap ON rides;
        CREATE TRIGGER trg_enforce_ride_time_overlap
        BEFORE INSERT OR UPDATE OF driver_id, departure_time, estimated_duration_minutes, route_distance_km, status
        ON rides
        FOR EACH ROW
        EXECUTE FUNCTION public.enforce_ride_time_overlap();
        """
    )


def downgrade() -> None:
    """Drop trigger-based overlap guard."""
    op.execute("DROP TRIGGER IF EXISTS trg_enforce_ride_time_overlap ON rides;")
    op.execute("DROP FUNCTION IF EXISTS public.enforce_ride_time_overlap();")
