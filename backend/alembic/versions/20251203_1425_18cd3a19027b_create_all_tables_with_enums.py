"""Create all tables with enums

Revision ID: 18cd3a19027b
Revises: 95241d562070
Create Date: 2025-12-03 14:25:54.965148

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18cd3a19027b'
down_revision: Union[str, None] = None  # First migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all database tables, enums, and indexes using raw SQL to avoid SQLAlchemy enum issues"""
    
    # Create UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    
    # Create all enum types using raw SQL
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
                CREATE TYPE user_role AS ENUM ('passenger', 'driver', 'admin');
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'driver_verification_status') THEN
                CREATE TYPE driver_verification_status AS ENUM ('pending', 'verified', 'rejected');
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'ride_status') THEN
                CREATE TYPE ride_status AS ENUM ('open', 'in_progress', 'completed', 'cancelled');
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'booking_status') THEN
                CREATE TYPE booking_status AS ENUM ('reserved', 'cancelled', 'completed');
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'transaction_type') THEN
                CREATE TYPE transaction_type AS ENUM ('topup', 'payout', 'ride');
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'transaction_status') THEN
                CREATE TYPE transaction_status AS ENUM ('pending', 'completed', 'failed');
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'verification_status') THEN
                CREATE TYPE verification_status AS ENUM ('pending', 'verified', 'rejected');
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'flag_severity') THEN
                CREATE TYPE flag_severity AS ENUM ('low', 'medium', 'high');
            END IF;
            
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'flag_status') THEN
                CREATE TYPE flag_status AS ENUM ('open', 'resolved', 'dismissed');
            END IF;
        END $$;
    """)
    
    # Create tables using raw SQL (avoids SQLAlchemy's automatic enum creation)
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email VARCHAR(255) NOT NULL UNIQUE,
            phone VARCHAR(20),
            full_name VARCHAR(255) NOT NULL,
            cnic VARCHAR(255),  -- Encrypted
            role user_role NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
        CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS drivers (
            user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            license_number VARCHAR(255),  -- Encrypted
            verification_status driver_verification_status NOT NULL DEFAULT 'pending',
            location_last_lat DOUBLE PRECISION,
            location_last_lng DOUBLE PRECISION,
            is_available BOOLEAN NOT NULL DEFAULT false,
            total_rides INTEGER NOT NULL DEFAULT 0,
            rating_avg NUMERIC(3, 2),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_drivers_verification_status ON drivers(verification_status);
        CREATE INDEX IF NOT EXISTS idx_drivers_is_available ON drivers(is_available);
        CREATE INDEX IF NOT EXISTS idx_drivers_location ON drivers(location_last_lat, location_last_lng);
        CREATE INDEX IF NOT EXISTS idx_drivers_rating_avg ON drivers(rating_avg);
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS vehicles (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            driver_id UUID NOT NULL REFERENCES drivers(user_id) ON DELETE CASCADE,
            make VARCHAR(100) NOT NULL,
            model VARCHAR(100) NOT NULL,
            year INTEGER NOT NULL,
            color VARCHAR(50),
            license_plate VARCHAR(50) NOT NULL UNIQUE,
            seats_available INTEGER NOT NULL,
            photos JSONB,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_vehicles_driver_id ON vehicles(driver_id);
        CREATE INDEX IF NOT EXISTS idx_vehicles_license_plate ON vehicles(license_plate);
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS rides (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            driver_id UUID NOT NULL REFERENCES drivers(user_id) ON DELETE CASCADE,
            vehicle_id UUID REFERENCES vehicles(id) ON DELETE SET NULL,
            start_point_lat DOUBLE PRECISION NOT NULL,
            start_point_lng DOUBLE PRECISION NOT NULL,
            end_point_lat DOUBLE PRECISION NOT NULL,
            end_point_lng DOUBLE PRECISION NOT NULL,
            departure_time TIMESTAMP WITH TIME ZONE NOT NULL,
            seats_available INTEGER NOT NULL,
            price_per_seat NUMERIC(10, 2) NOT NULL,
            status ride_status NOT NULL DEFAULT 'open',
            polyline TEXT,
            recurrence JSONB,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_rides_driver_id ON rides(driver_id);
        CREATE INDEX IF NOT EXISTS idx_rides_status ON rides(status);
        CREATE INDEX IF NOT EXISTS idx_rides_departure_time ON rides(departure_time);
        CREATE INDEX IF NOT EXISTS idx_rides_start_point ON rides(start_point_lat, start_point_lng);
        CREATE INDEX IF NOT EXISTS idx_rides_end_point ON rides(end_point_lat, end_point_lng);
        CREATE INDEX IF NOT EXISTS idx_rides_seats_available ON rides(seats_available);
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            ride_id UUID NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
            passenger_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            seats_booked INTEGER NOT NULL,
            total_price NUMERIC(10, 2) NOT NULL,
            status booking_status NOT NULL DEFAULT 'reserved',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_bookings_ride_id ON bookings(ride_id);
        CREATE INDEX IF NOT EXISTS idx_bookings_passenger_id ON bookings(passenger_id);
        CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            balance NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            wallet_id UUID NOT NULL REFERENCES wallets(user_id) ON DELETE CASCADE,
            amount NUMERIC(12, 2) NOT NULL,
            transaction_type transaction_type NOT NULL,
            status transaction_status NOT NULL DEFAULT 'pending',
            provider_transaction_id VARCHAR(255),
            metadata JSONB,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_wallet_transactions_wallet_id ON wallet_transactions(wallet_id);
        CREATE INDEX IF NOT EXISTS idx_wallet_transactions_type ON wallet_transactions(transaction_type);
        CREATE INDEX IF NOT EXISTS idx_wallet_transactions_status ON wallet_transactions(status);
        CREATE INDEX IF NOT EXISTS idx_wallet_transactions_created_at ON wallet_transactions(created_at);
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS verifications (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            cnic_front_url VARCHAR(500),
            cnic_back_url VARCHAR(500),
            license_front_url VARCHAR(500),
            license_back_url VARCHAR(500),
            selfie_url VARCHAR(500),
            cnic_number VARCHAR(255),
            full_name_on_cnic VARCHAR(255),
            face_match_score NUMERIC(5, 2),
            status verification_status NOT NULL DEFAULT 'pending',
            reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at TIMESTAMP WITH TIME ZONE,
            rejection_reason TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_verifications_user_id ON verifications(user_id);
        CREATE INDEX IF NOT EXISTS idx_verifications_status ON verifications(status);
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS telemetry_points (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            ride_id UUID NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            speed DOUBLE PRECISION,
            bearing DOUBLE PRECISION,
            recorded_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_telemetry_ride_id ON telemetry_points(ride_id);
        CREATE INDEX IF NOT EXISTS idx_telemetry_recorded_at ON telemetry_points(recorded_at);
        CREATE INDEX IF NOT EXISTS idx_telemetry_location ON telemetry_points(latitude, longitude);
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            ride_id UUID NOT NULL REFERENCES rides(id) ON DELETE CASCADE,
            rater_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            ratee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            score INTEGER NOT NULL CHECK (score >= 1 AND score <= 5),
            comment TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_ratings_ride_id ON ratings(ride_id);
        CREATE INDEX IF NOT EXISTS idx_ratings_rater_id ON ratings(rater_id);
        CREATE INDEX IF NOT EXISTS idx_ratings_ratee_id ON ratings(ratee_id);
        CREATE INDEX IF NOT EXISTS idx_ratings_score ON ratings(score);
    """)
    
    op.execute("""
        CREATE TABLE IF NOT EXISTS admin_flags (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            flagged_entity_type VARCHAR(50) NOT NULL,
            flagged_entity_id UUID NOT NULL,
            reported_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            reason TEXT NOT NULL,
            severity flag_severity NOT NULL,
            status flag_status NOT NULL DEFAULT 'open',
            reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            reviewed_at TIMESTAMP WITH TIME ZONE,
            resolution_notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_admin_flags_entity ON admin_flags(flagged_entity_type, flagged_entity_id);
        CREATE INDEX IF NOT EXISTS idx_admin_flags_reported_by ON admin_flags(reported_by);
        CREATE INDEX IF NOT EXISTS idx_admin_flags_severity ON admin_flags(severity);
        CREATE INDEX IF NOT EXISTS idx_admin_flags_status ON admin_flags(status);
    """)


def downgrade() -> None:
    """Drop all tables and enums"""
    op.execute('DROP TABLE IF EXISTS admin_flags CASCADE;')
    op.execute('DROP TABLE IF EXISTS ratings CASCADE;')
    op.execute('DROP TABLE IF EXISTS telemetry_points CASCADE;')
    op.execute('DROP TABLE IF EXISTS verifications CASCADE;')
    op.execute('DROP TABLE IF EXISTS wallet_transactions CASCADE;')
    op.execute('DROP TABLE IF EXISTS wallets CASCADE;')
    op.execute('DROP TABLE IF EXISTS bookings CASCADE;')
    op.execute('DROP TABLE IF EXISTS rides CASCADE;')
    op.execute('DROP TABLE IF EXISTS vehicles CASCADE;')
    op.execute('DROP TABLE IF EXISTS drivers CASCADE;')
    op.execute('DROP TABLE IF EXISTS users CASCADE;')
    
    op.execute('DROP TYPE IF EXISTS flag_status;')
    op.execute('DROP TYPE IF EXISTS flag_severity;')
    op.execute('DROP TYPE IF EXISTS verification_status;')
    op.execute('DROP TYPE IF EXISTS transaction_status;')
    op.execute('DROP TYPE IF EXISTS transaction_type;')
    op.execute('DROP TYPE IF EXISTS booking_status;')
    op.execute('DROP TYPE IF EXISTS ride_status;')
    op.execute('DROP TYPE IF EXISTS driver_verification_status;')
    op.execute('DROP TYPE IF EXISTS user_role;')
