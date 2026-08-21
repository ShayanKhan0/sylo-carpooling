from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


ACTIVE_BOOKING_STATUSES = {"reserved", "confirmed", "booked"}


async def _ensure_ride_overlap_trigger(db: AsyncSession) -> bool:
    trigger_exists = await db.execute(
        text(
            """
            SELECT 1
            FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = 'rides'
              AND t.tgname = 'trg_enforce_ride_time_overlap'
              AND NOT t.tgisinternal
            LIMIT 1
            """
        )
    )
    if trigger_exists.scalar_one_or_none():
        return False

    await db.execute(
        text(
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
    )

    await db.execute(
        text(
            """
            CREATE TRIGGER trg_enforce_ride_time_overlap
            BEFORE INSERT OR UPDATE OF driver_id, departure_time, estimated_duration_minutes, route_distance_km, status
            ON rides
            FOR EACH ROW
            EXECUTE FUNCTION public.enforce_ride_time_overlap()
            """
        )
    )
    return True


async def _get_table_columns(
    db: AsyncSession, table_name: str
) -> dict[str, dict[str, str | None]]:
    result = await db.execute(
        text(
            """
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return {
        row.column_name: {"data_type": row.data_type, "udt_name": row.udt_name}
        for row in result
    }


async def ensure_rides_schema_compat(db: AsyncSession) -> None:
    if db.info.get("rides_schema_compat_done"):
        return

    changed = False

    rides_columns = await _get_table_columns(db, "rides")
    if rides_columns:
        ride_adds: list[str] = []
        if "start_point_address" not in rides_columns:
            ride_adds.append("ADD COLUMN start_point_address VARCHAR(500)")
        if "end_point_address" not in rides_columns:
            ride_adds.append("ADD COLUMN end_point_address VARCHAR(500)")
        if "estimated_duration_minutes" not in rides_columns:
            ride_adds.append("ADD COLUMN estimated_duration_minutes INTEGER")
        if "route_distance_km" not in rides_columns:
            ride_adds.append("ADD COLUMN route_distance_km DOUBLE PRECISION")
        if "route_plan_version" not in rides_columns:
            ride_adds.append("ADD COLUMN route_plan_version INTEGER NOT NULL DEFAULT 0")
        if "route_selected_key" not in rides_columns:
            ride_adds.append("ADD COLUMN route_selected_key VARCHAR(64)")
        if "route_alternatives" not in rides_columns:
            ride_adds.append("ADD COLUMN route_alternatives JSONB")

        if ride_adds:
            await db.execute(text(f"ALTER TABLE rides {', '.join(ride_adds)}"))
            changed = True

        # Best-effort backfill from legacy ride schema variants.
        if "origin" in rides_columns:
            await db.execute(
                text(
                    """
                    UPDATE rides
                    SET start_point_address = COALESCE(start_point_address, origin)
                    WHERE origin IS NOT NULL
                    """
                )
            )
            changed = True

        if "destination" in rides_columns:
            await db.execute(
                text(
                    """
                    UPDATE rides
                    SET end_point_address = COALESCE(end_point_address, destination)
                    WHERE destination IS NOT NULL
                    """
                )
            )
            changed = True

        if "estimated_duration" in rides_columns:
            await db.execute(
                text(
                    """
                    UPDATE rides
                    SET estimated_duration_minutes = COALESCE(estimated_duration_minutes, estimated_duration)
                    WHERE estimated_duration IS NOT NULL
                    """
                )
            )
            changed = True

        if "distance_km" in rides_columns:
            await db.execute(
                text(
                    """
                    UPDATE rides
                    SET route_distance_km = COALESCE(route_distance_km, distance_km)
                    WHERE distance_km IS NOT NULL
                    """
                )
            )
            changed = True

        if await _ensure_ride_overlap_trigger(db):
            changed = True

    recurring_columns = await _get_table_columns(db, "recurring_schedules")
    if recurring_columns:
        days_meta = recurring_columns.get("days_of_week")
        if days_meta and days_meta.get("data_type") not in {"json", "jsonb"}:
            await db.execute(
                text(
                    """
                    ALTER TABLE recurring_schedules
                    ALTER COLUMN days_of_week TYPE JSONB
                    USING to_jsonb(days_of_week)
                    """
                )
            )
            changed = True

        recurring_adds: list[str] = []
        if "time" not in recurring_columns:
            recurring_adds.append('ADD COLUMN "time" TIME')
        if "start_point_lat" not in recurring_columns:
            recurring_adds.append("ADD COLUMN start_point_lat DOUBLE PRECISION")
        if "start_point_lng" not in recurring_columns:
            recurring_adds.append("ADD COLUMN start_point_lng DOUBLE PRECISION")
        if "start_point_address" not in recurring_columns:
            recurring_adds.append("ADD COLUMN start_point_address VARCHAR(500)")
        if "end_point_lat" not in recurring_columns:
            recurring_adds.append("ADD COLUMN end_point_lat DOUBLE PRECISION")
        if "end_point_lng" not in recurring_columns:
            recurring_adds.append("ADD COLUMN end_point_lng DOUBLE PRECISION")
        if "end_point_address" not in recurring_columns:
            recurring_adds.append("ADD COLUMN end_point_address VARCHAR(500)")
        if "polyline_main" not in recurring_columns:
            recurring_adds.append("ADD COLUMN polyline_main TEXT")
        if "seats_offered" not in recurring_columns:
            recurring_adds.append("ADD COLUMN seats_offered INTEGER NOT NULL DEFAULT 1")
        if "base_price" not in recurring_columns:
            recurring_adds.append("ADD COLUMN base_price NUMERIC(10,2) NOT NULL DEFAULT 0")
        if "buffer_seats" not in recurring_columns:
            recurring_adds.append("ADD COLUMN buffer_seats INTEGER NOT NULL DEFAULT 0")
        if "start_date" not in recurring_columns:
            recurring_adds.append("ADD COLUMN start_date DATE NOT NULL DEFAULT CURRENT_DATE")
        if "end_date" not in recurring_columns:
            recurring_adds.append("ADD COLUMN end_date DATE NOT NULL DEFAULT (CURRENT_DATE + 365)")
        if "recurrence_meta" not in recurring_columns:
            recurring_adds.append("ADD COLUMN recurrence_meta JSONB")

        if recurring_adds:
            await db.execute(text(f"ALTER TABLE recurring_schedules {', '.join(recurring_adds)}"))
            changed = True

        if "departure_time" in recurring_columns:
            await db.execute(
                text(
                    'UPDATE recurring_schedules SET "time" = COALESCE("time", departure_time) WHERE departure_time IS NOT NULL'
                )
            )
            changed = True
        if "start_lat" in recurring_columns:
            await db.execute(
                text(
                    "UPDATE recurring_schedules SET start_point_lat = COALESCE(start_point_lat, start_lat) WHERE start_lat IS NOT NULL"
                )
            )
            changed = True
        if "start_lng" in recurring_columns:
            await db.execute(
                text(
                    "UPDATE recurring_schedules SET start_point_lng = COALESCE(start_point_lng, start_lng) WHERE start_lng IS NOT NULL"
                )
            )
            changed = True
        if "end_lat" in recurring_columns:
            await db.execute(
                text(
                    "UPDATE recurring_schedules SET end_point_lat = COALESCE(end_point_lat, end_lat) WHERE end_lat IS NOT NULL"
                )
            )
            changed = True
        if "end_lng" in recurring_columns:
            await db.execute(
                text(
                    "UPDATE recurring_schedules SET end_point_lng = COALESCE(end_point_lng, end_lng) WHERE end_lng IS NOT NULL"
                )
            )
            changed = True
        if "start_address" in recurring_columns:
            await db.execute(
                text(
                    "UPDATE recurring_schedules SET start_point_address = COALESCE(start_point_address, start_address) WHERE start_address IS NOT NULL"
                )
            )
            changed = True
        if "end_address" in recurring_columns:
            await db.execute(
                text(
                    "UPDATE recurring_schedules SET end_point_address = COALESCE(end_point_address, end_address) WHERE end_address IS NOT NULL"
                )
            )
            changed = True

    # Passenger recurring-booking subscriptions table.
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS recurring_schedule_subscriptions (
                id UUID PRIMARY KEY,
                schedule_id UUID NOT NULL REFERENCES recurring_schedules(id) ON DELETE CASCADE,
                passenger_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                overlap_start_date DATE NOT NULL,
                overlap_end_date DATE NOT NULL,
                departure_window_start TIME NOT NULL,
                departure_window_end TIME NOT NULL,
                seats_reserved INTEGER NOT NULL DEFAULT 1,
                pickup_lat DOUBLE PRECISION,
                pickup_lng DOUBLE PRECISION,
                pickup_address VARCHAR(500),
                pickup_place_id VARCHAR(191),
                dropoff_lat DOUBLE PRECISION,
                dropoff_lng DOUBLE PRECISION,
                dropoff_address VARCHAR(500),
                dropoff_place_id VARCHAR(191),
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                cancellation_reason VARCHAR(255),
                cancelled_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_recurring_subscriptions_schedule_status
            ON recurring_schedule_subscriptions (schedule_id, status)
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS idx_recurring_subscriptions_passenger_status
            ON recurring_schedule_subscriptions (passenger_id, status)
            """
        )
    )
    changed = True

    booking_columns = await _get_table_columns(db, "ride_bookings")
    if booking_columns:
        booking_adds: list[str] = []
        if "booked_seats" not in booking_columns:
            booking_adds.append("ADD COLUMN booked_seats INTEGER NOT NULL DEFAULT 1")
        if "total_price" not in booking_columns:
            booking_adds.append("ADD COLUMN total_price DOUBLE PRECISION NOT NULL DEFAULT 0")
        if "payment_status" not in booking_columns:
            booking_adds.append("ADD COLUMN payment_status VARCHAR(20) NOT NULL DEFAULT 'pending'")
        if "cancellation_time" not in booking_columns:
            booking_adds.append("ADD COLUMN cancellation_time TIMESTAMP WITH TIME ZONE")
        if "cancellation_reason" not in booking_columns:
            booking_adds.append("ADD COLUMN cancellation_reason VARCHAR(255)")
        if "pickup_lat" not in booking_columns:
            booking_adds.append("ADD COLUMN pickup_lat DOUBLE PRECISION")
        if "pickup_lng" not in booking_columns:
            booking_adds.append("ADD COLUMN pickup_lng DOUBLE PRECISION")
        if "pickup_address" not in booking_columns:
            booking_adds.append("ADD COLUMN pickup_address VARCHAR(500)")
        if "pickup_place_id" not in booking_columns:
            booking_adds.append("ADD COLUMN pickup_place_id VARCHAR(191)")
        if "dropoff_lat" not in booking_columns:
            booking_adds.append("ADD COLUMN dropoff_lat DOUBLE PRECISION")
        if "dropoff_lng" not in booking_columns:
            booking_adds.append("ADD COLUMN dropoff_lng DOUBLE PRECISION")
        if "dropoff_address" not in booking_columns:
            booking_adds.append("ADD COLUMN dropoff_address VARCHAR(500)")
        if "dropoff_place_id" not in booking_columns:
            booking_adds.append("ADD COLUMN dropoff_place_id VARCHAR(191)")
        if "segment_km" not in booking_columns:
            booking_adds.append("ADD COLUMN segment_km DOUBLE PRECISION")
        if "pickup_stop_order" not in booking_columns:
            booking_adds.append("ADD COLUMN pickup_stop_order INTEGER")
        if "dropoff_stop_order" not in booking_columns:
            booking_adds.append("ADD COLUMN dropoff_stop_order INTEGER")
        if "planned_pickup_eta" not in booking_columns:
            booking_adds.append("ADD COLUMN planned_pickup_eta TIMESTAMP WITH TIME ZONE")
        if "planned_dropoff_eta" not in booking_columns:
            booking_adds.append("ADD COLUMN planned_dropoff_eta TIMESTAMP WITH TIME ZONE")
        if "actual_pickup_time" not in booking_columns:
            booking_adds.append("ADD COLUMN actual_pickup_time TIMESTAMP WITH TIME ZONE")
        if "actual_dropoff_time" not in booking_columns:
            booking_adds.append("ADD COLUMN actual_dropoff_time TIMESTAMP WITH TIME ZONE")
        if "route_plan_version" not in booking_columns:
            booking_adds.append("ADD COLUMN route_plan_version INTEGER NOT NULL DEFAULT 0")
        if "recurring_subscription_id" not in booking_columns:
            booking_adds.append(
                "ADD COLUMN recurring_subscription_id UUID REFERENCES recurring_schedule_subscriptions(id) ON DELETE SET NULL"
            )

        if booking_adds:
            await db.execute(text(f"ALTER TABLE ride_bookings {', '.join(booking_adds)}"))
            changed = True

        if "seats_reserved" in booking_columns:
            await db.execute(
                text(
                    "UPDATE ride_bookings SET booked_seats = COALESCE(booked_seats, seats_reserved, 1)"
                )
            )
            changed = True
        if "fare" in booking_columns:
            await db.execute(
                text(
                    "UPDATE ride_bookings SET total_price = COALESCE(total_price, fare, 0)"
                )
            )
            changed = True

        await db.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_ride_bookings_recurring_subscription_id
                ON ride_bookings (recurring_subscription_id)
                """
            )
        )
        changed = True

    if changed:
        await db.commit()

    db.info["rides_schema_compat_done"] = True