"""
Fuel Price Engine — Module 1
============================

Reads live pricing parameters from the `system_config` table and computes
a dynamic rate_per_km that drives all per-passenger fare calculations.

Formula
-------
    fuel_cost_per_km  = petrol_price_per_litre / fuel_avg_km_per_litre
                      = 378 / 12  = 31.5  PKR/km  (at current prices)

    rate_per_km       = fuel_cost_per_km
                        × (1 + platform_fee_pct + driver_margin_pct)
                      = 31.5 × (1 + 0.15 + 0.15)
                      = 31.5 × 1.30
                      ≈ 40.95  PKR/km

When petrol prices change, an admin updates the DB row and every new fare
calculation automatically picks up the new value — no code change needed.

Author: M. Mobeen Shoukat Ch & M. Shayan Khan
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Hard-coded Pakistan defaults (used when DB row is missing) ────────────────
_DEFAULT_PETROL_PRICE: float = 378.0   # PKR / litre  (April 2026)
_DEFAULT_FUEL_AVG: float = 12.0        # km / litre
_DEFAULT_PLATFORM_FEE: float = 0.15    # 15 %
_DEFAULT_DRIVER_MARGIN: float = 0.15   # 15 %
_DEFAULT_MIN_FARE: float = 50.0        # PKR
_DEFAULT_BASE_FARE: float = 30.0       # PKR (flat charge per booking)
_DEFAULT_AVG_SPEED_KMH: float = 40.0   # km/h (city traffic ETA fallback)


@dataclass
class FuelPriceConfig:
    """
    Live pricing parameters loaded from system_config table.

    All values are stored at the time the object is created so the same
    FuelPriceConfig instance is consistent throughout a single pipeline run.
    """
    petrol_price_per_litre: float = _DEFAULT_PETROL_PRICE
    fuel_avg_km_per_litre: float = _DEFAULT_FUEL_AVG
    platform_fee_pct: float = _DEFAULT_PLATFORM_FEE
    driver_margin_pct: float = _DEFAULT_DRIVER_MARGIN
    min_fare_pkr: float = _DEFAULT_MIN_FARE
    base_fare_pkr: float = _DEFAULT_BASE_FARE
    avg_speed_kmh: float = _DEFAULT_AVG_SPEED_KMH

    # ── Derived ────────────────────────────────────────────────────────────
    @property
    def fuel_cost_per_km(self) -> float:
        """Raw fuel cost per km in PKR."""
        return self.petrol_price_per_litre / self.fuel_avg_km_per_litre

    @property
    def rate_per_km(self) -> float:
        """
        Final PKR/km charged to passengers after fees and margin.

            rate = (petrol / avg) × (1 + platform_fee + driver_margin)
        """
        return self.fuel_cost_per_km * (
            1.0 + self.platform_fee_pct + self.driver_margin_pct
        )

    def to_dict(self) -> dict:
        return {
            "petrol_price_per_litre": round(self.petrol_price_per_litre, 2),
            "fuel_avg_km_per_litre": round(self.fuel_avg_km_per_litre, 2),
            "platform_fee_pct": round(self.platform_fee_pct * 100, 1),
            "driver_margin_pct": round(self.driver_margin_pct * 100, 1),
            "min_fare_pkr": round(self.min_fare_pkr, 2),
            "base_fare_pkr": round(self.base_fare_pkr, 2),
            "avg_speed_kmh": round(self.avg_speed_kmh, 1),
            "fuel_cost_per_km": round(self.fuel_cost_per_km, 4),
            "rate_per_km": round(self.rate_per_km, 4),
        }


# ── DB helpers ─────────────────────────────────────────────────────────────────

_CONFIG_KEYS = {
    "petrol_price_per_litre": float,
    "fuel_avg_km_per_litre": float,
    "platform_fee_pct": float,
    "driver_margin_pct": float,
    "min_fare_pkr": float,
    "base_fare_pkr": float,
    "avg_speed_kmh": float,
}


async def load_fuel_config(db: AsyncSession) -> FuelPriceConfig:
    """
    Load all pricing parameters from system_config table.

    Falls back to hard-coded defaults for any missing key so the system
    never crashes even if the table has no rows yet.
    """
    try:
        from app.models.system_config import SystemConfig
        result = await db.execute(
            select(SystemConfig).where(
                SystemConfig.key.in_(list(_CONFIG_KEYS.keys()))
            )
        )
        rows = result.scalars().all()
        loaded: dict[str, float] = {}
        for row in rows:
            cast = _CONFIG_KEYS.get(row.key, str)
            try:
                loaded[row.key] = cast(row.value)
            except (ValueError, TypeError):
                logger.warning(
                    f"system_config row '{row.key}' has invalid value '{row.value}' — using default"
                )
    except Exception as exc:
        logger.warning(f"Could not load system_config from DB: {exc} — using defaults")
        loaded = {}

    return FuelPriceConfig(
        petrol_price_per_litre=loaded.get("petrol_price_per_litre", _DEFAULT_PETROL_PRICE),
        fuel_avg_km_per_litre=loaded.get("fuel_avg_km_per_litre", _DEFAULT_FUEL_AVG),
        platform_fee_pct=loaded.get("platform_fee_pct", _DEFAULT_PLATFORM_FEE),
        driver_margin_pct=loaded.get("driver_margin_pct", _DEFAULT_DRIVER_MARGIN),
        min_fare_pkr=loaded.get("min_fare_pkr", _DEFAULT_MIN_FARE),
        base_fare_pkr=loaded.get("base_fare_pkr", _DEFAULT_BASE_FARE),
        avg_speed_kmh=loaded.get("avg_speed_kmh", _DEFAULT_AVG_SPEED_KMH),
    )


async def upsert_config_key(
    db: AsyncSession,
    key: str,
    value: str,
    description: Optional[str] = None,
) -> None:
    """
    Create or update a single system_config row (admin use).

    Raises ValueError for unknown keys so typos are caught immediately.
    """
    if key not in _CONFIG_KEYS:
        raise ValueError(
            f"Unknown config key '{key}'. Valid keys: {list(_CONFIG_KEYS.keys())}"
        )
    # Validate that value casts correctly
    try:
        _CONFIG_KEYS[key](value)
    except (ValueError, TypeError):
        raise ValueError(f"Value '{value}' cannot be cast to {_CONFIG_KEYS[key].__name__} for key '{key}'")

    from app.models.system_config import SystemConfig
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(SystemConfig).values(
        key=key,
        value=str(value),
        description=description,
    ).on_conflict_do_update(
        index_elements=["key"],
        set_={"value": str(value), "description": description},
    )
    await db.execute(stmt)
    await db.commit()
    logger.info(f"system_config updated: {key} = {value}")


def get_default_config() -> FuelPriceConfig:
    """Return a FuelPriceConfig populated with hard-coded defaults (no DB needed)."""
    return FuelPriceConfig()
