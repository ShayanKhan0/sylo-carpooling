"""
Storage integrity audit for frontend-critical data.

Checks PostgreSQL schema/data readiness for:
- Ratings & reviews
- User profile fields (gender, DOB, verification flags)
- Verification records
- Ride history/bookings storage
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import text

from app.db.session import engine


@dataclass
class TableCheck:
    name: str
    required_columns: list[str]


TABLE_CHECKS = [
    TableCheck(
        name="users",
        required_columns=["id", "full_name", "email", "phone", "role", "is_verified"],
    ),
    TableCheck(
        name="user_profiles",
        required_columns=[
            "user_id",
            "gender",
            "date_of_birth",
            "organization_name",
            "organization_type",
            "cnic",
            "driving_license",
            "car_registration",
        ],
    ),
    TableCheck(
        name="user_verifications",
        required_columns=["user_id", "status", "doc_type", "created_at"],
    ),
    TableCheck(
        name="ratings",
        required_columns=["ride_id", "rater_id", "ratee_id", "score", "comment", "created_at"],
    ),
    TableCheck(
        name="rides",
        required_columns=["id", "driver_id", "departure_time", "status", "price_per_seat"],
    ),
    TableCheck(
        name="ride_bookings",
        required_columns=[
            "ride_id",
            "passenger_id",
            "status",
            "booking_time",
            "booked_seats",
            "total_price",
        ],
    ),
    TableCheck(
        name="bookings",
        required_columns=["ride_id", "passenger_id", "status", "seats_reserved", "fare"],
    ),
    TableCheck(
        name="recurring_schedules",
        required_columns=[
            "user_id",
            "days_of_week",
            "time",
            "start_point_lat",
            "start_point_lng",
            "end_point_lat",
            "end_point_lng",
            "seats_offered",
            "base_price",
        ],
    ),
]


async def table_exists(conn, table_name: str) -> bool:
    q = text(
        """
        SELECT EXISTS (
          SELECT 1
          FROM information_schema.tables
          WHERE table_schema='public' AND table_name=:table_name
        )
        """
    )
    return bool((await conn.execute(q, {"table_name": table_name})).scalar())


async def get_columns(conn, table_name: str) -> set[str]:
    q = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=:table_name
        """
    )
    rows = await conn.execute(q, {"table_name": table_name})
    return {r.column_name for r in rows}


async def count_rows(conn, table_name: str) -> int:
    q = text(f"SELECT COUNT(*) AS c FROM {table_name}")
    return int((await conn.execute(q)).scalar() or 0)


async def run_audit() -> int:
    print("=" * 90)
    print("POSTGRES STORAGE INTEGRITY AUDIT")
    print("=" * 90)

    failures: list[str] = []

    async with engine.connect() as conn:
        for check in TABLE_CHECKS:
            exists = await table_exists(conn, check.name)
            if not exists:
                failures.append(f"Missing table: {check.name}")
                print(f"[FAIL] {check.name}: table does not exist")
                continue

            cols = await get_columns(conn, check.name)
            missing = [c for c in check.required_columns if c not in cols]
            if missing:
                failures.append(f"{check.name} missing columns: {', '.join(missing)}")
                print(f"[FAIL] {check.name}: missing columns -> {', '.join(missing)}")
            else:
                print(f"[ OK ] {check.name}: required columns present")

            row_count = await count_rows(conn, check.name)
            print(f"      rows: {row_count}")

        # Cross checks for requested domains
        print("\nDomain checks")

        profile_with_gender = int(
            (
                await conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM user_profiles
                        WHERE gender IS NOT NULL
                        """
                    )
                )
            ).scalar()
            or 0
        )
        profile_with_dob = int(
            (
                await conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM user_profiles
                        WHERE date_of_birth IS NOT NULL
                        """
                    )
                )
            ).scalar()
            or 0
        )
        verified_users = int(
            (
                await conn.execute(text("SELECT COUNT(*) FROM users WHERE is_verified = TRUE"))
            ).scalar()
            or 0
        )
        rating_rows = int((await conn.execute(text("SELECT COUNT(*) FROM ratings"))).scalar() or 0)
        history_rows = int(
            (
                await conn.execute(
                    text(
                        """
                        SELECT
                          (SELECT COUNT(*) FROM ride_bookings) +
                          (SELECT COUNT(*) FROM bookings)
                        """
                    )
                )
            ).scalar()
            or 0
        )

        print(f"- user_profiles with gender: {profile_with_gender}")
        print(f"- user_profiles with date_of_birth: {profile_with_dob}")
        print(f"- users verified (is_verified=true): {verified_users}")
        print(f"- ratings rows: {rating_rows}")
        print(f"- total booking/history rows (ride_bookings + bookings): {history_rows}")

    print("\n" + "=" * 90)
    if failures:
        print("AUDIT RESULT: FAIL")
        for f in failures:
            print(f"- {f}")
        return 1

    print("AUDIT RESULT: PASS")
    print("All frontend-critical storage paths have required DB columns.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_audit()))
