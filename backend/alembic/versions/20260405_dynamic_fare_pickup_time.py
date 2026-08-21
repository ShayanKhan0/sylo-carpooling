"""Add dynamic fare + pickup time columns to bookings; create system_config table

Revision ID: 20260405_dynamic_fare
Revises: 20260405_ride_cluster
Create Date: 2026-04-05

Changes
-------
1. bookings table — new columns:
   - individual_fare         NUMERIC(10,2)  — this passenger's computed fare (PKR)
   - estimated_pickup_time   TIMESTAMPTZ    — pre-computed pickup ETA
   - segment_km              FLOAT          — route km from pickup to dropoff
   - pickup_pct              FLOAT          — position along route where pickup falls (0–1)
   - dropoff_pct             FLOAT          — position along route where dropoff falls (0–1)
   - pickup_route_km         FLOAT          — km along route to pickup
   - dropoff_route_km        FLOAT          — km along route to dropoff
   - rate_per_km_used        FLOAT          — PKR/km snapshot used at booking time

2. system_config table — new table for live pricing parameters
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# ── Revision identifiers ───────────────────────────────────────────────────────
revision = "20260405_dynamic_fare"
down_revision = "20260405_ride_cluster"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add new columns to bookings ────────────────────────────────────────
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "individual_fare",
                sa.Numeric(10, 2),
                nullable=True,
                comment="Per-passenger dynamic fare computed by proportional distance engine (PKR)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "estimated_pickup_time",
                sa.DateTime(timezone=True),
                nullable=True,
                comment="Pre-computed ETA for when driver reaches this passenger's pickup",
            )
        )
        batch_op.add_column(
            sa.Column(
                "segment_km",
                sa.Float(),
                nullable=True,
                comment="Route km this passenger travels (pickup → dropoff along driver route)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "pickup_pct",
                sa.Float(),
                nullable=True,
                comment="Fraction along route where pickup falls (0.0 = start, 1.0 = end)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "dropoff_pct",
                sa.Float(),
                nullable=True,
                comment="Fraction along route where dropoff falls (0.0 = start, 1.0 = end)",
            )
        )
        batch_op.add_column(
            sa.Column(
                "pickup_route_km",
                sa.Float(),
                nullable=True,
                comment="Km along route to pickup point",
            )
        )
        batch_op.add_column(
            sa.Column(
                "dropoff_route_km",
                sa.Float(),
                nullable=True,
                comment="Km along route to dropoff point",
            )
        )
        batch_op.add_column(
            sa.Column(
                "rate_per_km_used",
                sa.Float(),
                nullable=True,
                comment="PKR/km rate snapshot at booking creation time",
            )
        )
        batch_op.create_index(
            "idx_bookings_individual_fare",
            ["individual_fare"],
        )
        batch_op.create_index(
            "idx_bookings_estimated_pickup_time",
            ["estimated_pickup_time"],
        )

    # ── 2. Create system_config table ─────────────────────────────────────────
    op.create_table(
        "system_config",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_unique_constraint("uq_system_config_key", "system_config", ["key"])
    op.create_index("idx_system_config_key", "system_config", ["key"])

    # ── 3. Seed default system_config rows (Pakistan April 2026 prices) ───────
    op.execute(
        """
        INSERT INTO system_config (key, value, description) VALUES
            ('petrol_price_per_litre', '378.0',  'Current petrol price in PKR per litre'),
            ('fuel_avg_km_per_litre',  '12.0',   'Average fuel efficiency in km per litre'),
            ('platform_fee_pct',       '0.15',   'Platform fee fraction (0.15 = 15%)'),
            ('driver_margin_pct',      '0.15',   'Driver profit margin fraction (0.15 = 15%)'),
            ('min_fare_pkr',           '50.0',   'Minimum fare per booking in PKR'),
            ('base_fare_pkr',          '30.0',   'Flat base charge added to every booking in PKR'),
            ('avg_speed_kmh',          '40.0',   'Average driving speed in km/h for ETA calculation')
        ON CONFLICT (key) DO NOTHING;
        """
    )


def downgrade() -> None:
    # Remove system_config table
    op.drop_index("idx_system_config_key", table_name="system_config")
    op.drop_constraint("uq_system_config_key", "system_config", type_="unique")
    op.drop_table("system_config")

    # Remove added columns from bookings
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.drop_index("idx_bookings_estimated_pickup_time")
        batch_op.drop_index("idx_bookings_individual_fare")
        batch_op.drop_column("rate_per_km_used")
        batch_op.drop_column("dropoff_route_km")
        batch_op.drop_column("pickup_route_km")
        batch_op.drop_column("dropoff_pct")
        batch_op.drop_column("pickup_pct")
        batch_op.drop_column("segment_km")
        batch_op.drop_column("estimated_pickup_time")
        batch_op.drop_column("individual_fare")
