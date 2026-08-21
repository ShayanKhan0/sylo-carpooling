"""Initial database schema with all tables

Revision ID: 95241d562070
Revises: 
Create Date: 2025-11-08 15:25:35.829552

This migration creates all 11 core tables for the SmartCarpoolingApp:
1. users - User accounts (passengers, drivers, admins)
2. drivers - Driver-specific information (one-to-one with users)
3. vehicles - Vehicle information
4. rides - Driver-created trips
5. bookings - Passenger ride reservations
6. wallets - User payment balances
7. wallet_transactions - Payment transaction history
8. verifications - Document verification (KYC)
9. telemetry_points - GPS tracking during rides
10. ratings - Bidirectional ratings
11. admin_flags - Generic flagging system

All tables use UUID primary keys and include created_at/updated_at timestamps.
Comprehensive indexing is applied for performance.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '95241d562070'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create UUID extension if not exists
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    # Create enum types (using DO block to check if exists)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE user_role AS ENUM ('passenger', 'driver', 'admin');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE driver_verification_status AS ENUM ('pending', 'verified', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE ride_status AS ENUM ('open', 'in_progress', 'completed', 'cancelled');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE booking_status AS ENUM ('reserved', 'cancelled', 'completed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE transaction_type AS ENUM ('topup', 'payout', 'ride');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE transaction_status AS ENUM ('pending', 'completed', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE verification_status AS ENUM ('pending', 'verified', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE flag_severity AS ENUM ('low', 'medium', 'high');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE flag_status AS ENUM ('open', 'resolved', 'dismissed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # 1. Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('cnic', sa.String(255), nullable=True, comment='Encrypted CNIC - TODO: integrate KMS encryption'),
        sa.Column('role', postgresql.ENUM('passenger', 'driver', 'admin', name='user_role', create_type=False), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_role', 'users', ['role'])
    op.create_index('idx_users_is_active', 'users', ['is_active'])
    
    # 2. Create vehicles table
    op.create_table(
        'vehicles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('plate_number', sa.String(50), nullable=False, unique=True),
        sa.Column('make', sa.String(100), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('seats_total', sa.Integer(), nullable=False),
        sa.Column('seats_available', sa.Integer(), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('photos', postgresql.JSON, nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_vehicles_plate_number', 'vehicles', ['plate_number'])
    op.create_index('idx_vehicles_owner_id', 'vehicles', ['owner_id'])
    
    # 3. Create drivers table (one-to-one with users)
    op.create_table(
        'drivers',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('license_number', sa.String(255), nullable=False, comment='Encrypted license number - TODO: integrate KMS encryption'),
        sa.Column('vehicle_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('vehicles.id', ondelete='SET NULL'), nullable=True),
        sa.Column('verified', postgresql.ENUM('pending', 'verified', 'rejected', name='driver_verification_status', create_type=False), nullable=False, server_default='pending'),
        sa.Column('rating_avg', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('rating_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('location_last_lat', sa.Float(), nullable=True, comment='Consider PostGIS POINT type for production'),
        sa.Column('location_last_lng', sa.Float(), nullable=True, comment='Consider PostGIS POINT type for production'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_drivers_user_id', 'drivers', ['user_id'])
    op.create_index('idx_drivers_vehicle_id', 'drivers', ['vehicle_id'])
    op.create_index('idx_drivers_verified', 'drivers', ['verified'])
    op.create_index('idx_drivers_rating_avg', 'drivers', ['rating_avg'])
    op.create_index('idx_drivers_location', 'drivers', ['location_last_lat', 'location_last_lng'])
    
    # 4. Create rides table
    op.create_table(
        'rides',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('driver_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('drivers.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('start_point_lat', sa.Float(), nullable=False),
        sa.Column('start_point_lng', sa.Float(), nullable=False),
        sa.Column('start_point_address', sa.Text(), nullable=False),
        sa.Column('end_point_lat', sa.Float(), nullable=False),
        sa.Column('end_point_lng', sa.Float(), nullable=False),
        sa.Column('end_point_address', sa.Text(), nullable=False),
        sa.Column('polyline_main', sa.Text(), nullable=True),
        sa.Column('polyline_alternates', postgresql.JSON, nullable=True),
        sa.Column('start_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('recurrence', postgresql.JSON, nullable=True),
        sa.Column('seats_offered', sa.Integer(), nullable=False),
        sa.Column('seats_booked', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('base_price', sa.DECIMAL(10, 2), nullable=False),
        sa.Column('status', postgresql.ENUM('open', 'in_progress', 'completed', 'cancelled', name='ride_status', create_type=False), nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_rides_driver_id', 'rides', ['driver_id'])
    op.create_index('idx_rides_start_time', 'rides', ['start_time'])
    op.create_index('idx_rides_status', 'rides', ['status'])
    op.create_index('idx_rides_driver_status', 'rides', ['driver_id', 'status'])
    op.create_index('idx_rides_status_start_time', 'rides', ['status', 'start_time'])
    op.create_index('idx_rides_start_point', 'rides', ['start_point_lat', 'start_point_lng'])
    op.create_index('idx_rides_end_point', 'rides', ['end_point_lat', 'end_point_lng'])
    
    # 5. Create bookings table
    op.create_table(
        'bookings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('ride_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('rides.id', ondelete='CASCADE'), nullable=False),
        sa.Column('passenger_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('seats_reserved', sa.Integer(), nullable=False),
        sa.Column('fare', sa.DECIMAL(10, 2), nullable=False),
        sa.Column('status', postgresql.ENUM('reserved', 'cancelled', 'completed', name='booking_status', create_type=False), nullable=False, server_default='reserved'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_bookings_ride_id', 'bookings', ['ride_id'])
    op.create_index('idx_bookings_passenger_id', 'bookings', ['passenger_id'])
    op.create_index('idx_bookings_status', 'bookings', ['status'])
    op.create_index('idx_bookings_created_at', 'bookings', ['created_at'])
    op.create_index('idx_bookings_ride_status', 'bookings', ['ride_id', 'status'])
    op.create_index('idx_bookings_passenger_status', 'bookings', ['passenger_id', 'status'])
    
    # 6. Create wallets table
    op.create_table(
        'wallets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('balance', sa.DECIMAL(10, 2), nullable=False, server_default='0.00'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_wallets_user_id', 'wallets', ['user_id'], unique=True)
    
    # 7. Create wallet_transactions table
    op.create_table(
        'wallet_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('wallet_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('wallets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('amount', sa.DECIMAL(10, 2), nullable=False),
        sa.Column('type', postgresql.ENUM('topup', 'payout', 'ride', name='transaction_type', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'completed', 'failed', name='transaction_status', create_type=False), nullable=False, server_default='pending'),
        sa.Column('metadata', postgresql.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_wallet_transactions_wallet_id', 'wallet_transactions', ['wallet_id'])
    op.create_index('idx_wallet_transactions_type', 'wallet_transactions', ['type'])
    op.create_index('idx_wallet_transactions_status', 'wallet_transactions', ['status'])
    op.create_index('idx_wallet_transactions_created_at', 'wallet_transactions', ['created_at'])
    op.create_index('idx_wallet_transactions_wallet_status', 'wallet_transactions', ['wallet_id', 'status'])
    op.create_index('idx_wallet_transactions_wallet_created', 'wallet_transactions', ['wallet_id', 'created_at'])
    
    # 8. Create verifications table
    op.create_table(
        'verifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_type', sa.String(50), nullable=False),
        sa.Column('document_url', sa.String(500), nullable=False),
        sa.Column('ocr_fields', postgresql.JSON, nullable=True),
        sa.Column('face_match_score', sa.Float(), nullable=True),
        sa.Column('status', postgresql.ENUM('pending', 'verified', 'rejected', name='verification_status', create_type=False), nullable=False, server_default='pending'),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_verifications_user_id', 'verifications', ['user_id'])
    op.create_index('idx_verifications_status', 'verifications', ['status'])
    op.create_index('idx_verifications_document_type', 'verifications', ['document_type'])
    op.create_index('idx_verifications_created_at', 'verifications', ['created_at'])
    op.create_index('idx_verifications_user_status', 'verifications', ['user_id', 'status'])
    
    # 9. Create telemetry_points table
    op.create_table(
        'telemetry_points',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('ride_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('rides.id', ondelete='CASCADE'), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('speed', sa.Float(), nullable=True),
        sa.Column('bearing', sa.Float(), nullable=True),
    )
    op.create_index('idx_telemetry_ride_id', 'telemetry_points', ['ride_id'])
    op.create_index('idx_telemetry_timestamp', 'telemetry_points', ['timestamp'])
    op.create_index('idx_telemetry_ride_timestamp', 'telemetry_points', ['ride_id', 'timestamp'])
    op.create_index('idx_telemetry_location', 'telemetry_points', ['latitude', 'longitude'])
    # Note: Consider table partitioning for telemetry_points by timestamp for large datasets
    
    # 10. Create ratings table
    op.create_table(
        'ratings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('ride_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('rides.id', ondelete='CASCADE'), nullable=False),
        sa.Column('from_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('to_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_ratings_ride_id', 'ratings', ['ride_id'])
    op.create_index('idx_ratings_from_user_id', 'ratings', ['from_user_id'])
    op.create_index('idx_ratings_to_user_id', 'ratings', ['to_user_id'])
    op.create_index('idx_ratings_created_at', 'ratings', ['created_at'])
    op.create_index('idx_ratings_ride_from_user', 'ratings', ['ride_id', 'from_user_id'])
    op.create_index('idx_ratings_to_user_rating', 'ratings', ['to_user_id', 'rating'])
    
    # 11. Create admin_flags table
    op.create_table(
        'admin_flags',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('object_type', sa.String(50), nullable=False),
        sa.Column('object_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('severity', postgresql.ENUM('low', 'medium', 'high', name='flag_severity', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM('open', 'resolved', 'dismissed', name='flag_status', create_type=False), nullable=False, server_default='open'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('idx_admin_flags_object_type', 'admin_flags', ['object_type'])
    op.create_index('idx_admin_flags_object_id', 'admin_flags', ['object_id'])
    op.create_index('idx_admin_flags_severity', 'admin_flags', ['severity'])
    op.create_index('idx_admin_flags_status', 'admin_flags', ['status'])
    op.create_index('idx_admin_flags_created_at', 'admin_flags', ['created_at'])
    op.create_index('idx_admin_flags_object', 'admin_flags', ['object_type', 'object_id'])
    op.create_index('idx_admin_flags_status_severity', 'admin_flags', ['status', 'severity'])
    op.create_index('idx_admin_flags_status_created', 'admin_flags', ['status', 'created_at'])


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign key constraints)
    op.drop_table('admin_flags')
    op.drop_table('ratings')
    op.drop_table('telemetry_points')
    op.drop_table('verifications')
    op.drop_table('wallet_transactions')
    op.drop_table('wallets')
    op.drop_table('bookings')
    op.drop_table('rides')
    op.drop_table('drivers')
    op.drop_table('vehicles')
    op.drop_table('users')
    
    # Drop enum types
    op.execute('DROP TYPE IF EXISTS flag_status')
    op.execute('DROP TYPE IF EXISTS flag_severity')
    op.execute('DROP TYPE IF EXISTS verification_status')
    op.execute('DROP TYPE IF EXISTS transaction_status')
    op.execute('DROP TYPE IF EXISTS transaction_type')
    op.execute('DROP TYPE IF EXISTS booking_status')
    op.execute('DROP TYPE IF EXISTS ride_status')
    op.execute('DROP TYPE IF EXISTS driver_verification_status')
    op.execute('DROP TYPE IF EXISTS user_role')
