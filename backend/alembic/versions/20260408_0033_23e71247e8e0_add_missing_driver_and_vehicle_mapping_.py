"""Add missing driver and vehicle mapping columns

Revision ID: 23e71247e8e0
Revises: 20260405_dynamic_fare
Create Date: 2026-04-08 00:33:54.479263

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23e71247e8e0'
down_revision: Union[str, None] = '20260405_dynamic_fare'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing fields to `vehicles`
    op.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS owner_id UUID")
    op.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS plate_number VARCHAR(50)")
    op.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS seats_total INTEGER")
    op.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE")
    op.execute("ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS registration_verified BOOLEAN DEFAULT TRUE")
    
    # Add missing fields to `driver_profiles`
    op.execute("ALTER TABLE driver_profiles ADD COLUMN IF NOT EXISTS cnic_number VARCHAR(20) DEFAULT ''")
    op.execute("ALTER TABLE driver_profiles ADD COLUMN IF NOT EXISTS cnic_verified BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE driver_profiles ADD COLUMN IF NOT EXISTS address VARCHAR(255)")
    op.execute("ALTER TABLE driver_profiles ADD COLUMN IF NOT EXISTS rating FLOAT DEFAULT 5.0")
    op.execute("ALTER TABLE driver_profiles ADD COLUMN IF NOT EXISTS total_earnings FLOAT DEFAULT 0.0")
    op.execute("ALTER TABLE driver_profiles ADD COLUMN IF NOT EXISTS joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()")
    op.execute("ALTER TABLE driver_profiles ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'PENDING'")


def downgrade() -> None:
    pass
