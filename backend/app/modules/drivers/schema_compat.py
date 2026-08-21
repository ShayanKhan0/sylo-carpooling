"""
Driver/vehicle schema compatibility helpers.

Adds missing columns and backfills data to bridge legacy and current
contracts without destructive schema operations.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_schema_ready = False
_schema_lock = asyncio.Lock()


async def ensure_driver_vehicle_schema_compat(db: AsyncSession) -> None:
    """Ensure driver/vehicle tables have both legacy and canonical fields."""
    global _schema_ready

    if _schema_ready:
        return

    async with _schema_lock:
        if _schema_ready:
            return

        statements = [
            # --- driver_profiles additive columns ---
            "ALTER TABLE IF EXISTS driver_profiles ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE IF EXISTS driver_profiles ADD COLUMN IF NOT EXISTS verification_status VARCHAR(32)",
            "ALTER TABLE IF EXISTS driver_profiles ADD COLUMN IF NOT EXISTS verification_date TIMESTAMPTZ",
            "ALTER TABLE IF EXISTS driver_profiles ADD COLUMN IF NOT EXISTS rating_average DOUBLE PRECISION",
            "ALTER TABLE IF EXISTS driver_profiles ADD COLUMN IF NOT EXISTS total_ratings INTEGER",
            "ALTER TABLE IF EXISTS driver_profiles ADD COLUMN IF NOT EXISTS vehicle_id UUID",
            "ALTER TABLE IF EXISTS driver_profiles ADD COLUMN IF NOT EXISTS cnic_number VARCHAR(20)",
            "ALTER TABLE IF EXISTS driver_profiles ADD COLUMN IF NOT EXISTS cnic_verified BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE IF EXISTS driver_profiles ADD COLUMN IF NOT EXISTS address VARCHAR(255)",
            "ALTER TABLE IF EXISTS driver_profiles ADD COLUMN IF NOT EXISTS rating DOUBLE PRECISION NOT NULL DEFAULT 5.0",
            "ALTER TABLE IF EXISTS driver_profiles ADD COLUMN IF NOT EXISTS total_earnings DOUBLE PRECISION NOT NULL DEFAULT 0.0",
            "ALTER TABLE IF EXISTS driver_profiles ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'pending'",
            "ALTER TABLE IF EXISTS driver_profiles ADD COLUMN IF NOT EXISTS joined_at TIMESTAMPTZ",
            # --- vehicles additive columns ---
            "ALTER TABLE IF EXISTS vehicles ADD COLUMN IF NOT EXISTS owner_id UUID",
            "ALTER TABLE IF EXISTS vehicles ADD COLUMN IF NOT EXISTS plate_number VARCHAR(50)",
            "ALTER TABLE IF EXISTS vehicles ADD COLUMN IF NOT EXISTS seats_total INTEGER",
            "ALTER TABLE IF EXISTS vehicles ADD COLUMN IF NOT EXISTS seats_available INTEGER",
            "ALTER TABLE IF EXISTS vehicles ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE IF EXISTS vehicles ADD COLUMN IF NOT EXISTS registration_verified BOOLEAN NOT NULL DEFAULT TRUE",
            "ALTER TABLE IF EXISTS vehicles ADD COLUMN IF NOT EXISTS license_plate VARCHAR(50)",
            "ALTER TABLE IF EXISTS vehicles ADD COLUMN IF NOT EXISTS driver_id UUID",
            "ALTER TABLE IF EXISTS vehicles ADD COLUMN IF NOT EXISTS year INTEGER",
            "ALTER TABLE IF EXISTS vehicles ADD COLUMN IF NOT EXISTS color VARCHAR(50)",
            # --- data backfill (legacy -> canonical) ---
            """
            UPDATE driver_profiles
            SET joined_at = COALESCE(joined_at, created_at, NOW())
            """,
            """
            UPDATE driver_profiles
            SET rating = COALESCE(rating, rating_average::double precision, 5.0)
            """,
            """
            UPDATE driver_profiles
            SET total_earnings = COALESCE(total_earnings, 0.0)
            """,
            """
            UPDATE driver_profiles
            SET status = CASE
                WHEN status IS NOT NULL AND status <> '' THEN status
                WHEN is_verified IS TRUE THEN 'active'
                WHEN verification_status::text = 'verified' THEN 'active'
                ELSE 'pending'
            END
            """,
            """
            UPDATE driver_profiles
            SET cnic_number = COALESCE(NULLIF(cnic_number, ''), 'N/A')
            WHERE cnic_number IS NULL OR cnic_number = ''
            """,
            """
            UPDATE vehicles
            SET owner_id = COALESCE(owner_id, driver_id)
            """,
            """
            UPDATE vehicles
            SET plate_number = COALESCE(plate_number, license_plate)
            """,
            """
            UPDATE vehicles
            SET seats_available = COALESCE(seats_available, 4)
            """,
            """
            UPDATE vehicles
            SET seats_total = GREATEST(
                COALESCE(seats_total, seats_available, 4),
                COALESCE(seats_available, 1)
            )
            """,
            """
            UPDATE vehicles
            SET is_active = COALESCE(is_active, TRUE),
                registration_verified = COALESCE(registration_verified, TRUE)
            """,
            # --- non-destructive indexes ---
            "CREATE INDEX IF NOT EXISTS idx_vehicles_owner_id ON vehicles(owner_id)",
            "CREATE INDEX IF NOT EXISTS idx_vehicles_plate_number ON vehicles(plate_number)",
        ]

        try:
            for sql in statements:
                await db.execute(text(sql))
            await db.commit()
            _schema_ready = True
            logger.info("Driver/vehicle schema compatibility check completed")
        except Exception:
            await db.rollback()
            logger.exception("Driver/vehicle schema compatibility check failed")
            raise
