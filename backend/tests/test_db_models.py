"""
Test suite for database models.

Tests model definitions, constraints, relationships, and database connectivity.
"""

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.session import engine, AsyncSessionLocal
from app.core.config import settings

# Import all models to ensure they're registered
from app.modules.auth.models import User
from app.models.driver import Driver
from app.models.vehicle import Vehicle
from app.models.ride import Ride
from app.models.booking import Booking
from app.models.wallet import Wallet
from app.models.wallet_transaction import WalletTransaction
from app.models.verification import Verification
from app.models.telemetry_point import TelemetryPoint
from app.models.rating import Rating
from app.models.admin_flag import AdminFlag
from app.modules.analytics.models import DailyAggregate
from app.models.enums import (
    UserRole,
    DriverVerificationStatus,
    RideStatus,
    BookingStatus,
    TransactionType,
    TransactionStatus,
    VerificationStatus,
    FlagSeverity,
    FlagStatus,
)


class TestDatabaseModels:
    """Test database model definitions and metadata."""
    
    def test_all_tables_in_metadata(self):
        """Verify all expected tables are registered in SQLAlchemy metadata."""
        expected_tables = {
            'users',
            'drivers',
            'vehicles',
            'rides',
            'bookings',
            'wallets',
            'wallet_transactions',
            'verifications',
            'telemetry_points',
            'ratings',
            'admin_flags',
            'daily_aggregates',
        }
        
        actual_tables = set(Base.metadata.tables.keys())
        
        # Check all expected tables exist
        missing_tables = expected_tables - actual_tables
        assert not missing_tables, f"Missing tables in metadata: {missing_tables}"
        
        print(f"✓ All {len(expected_tables)} tables found in metadata")
    
    def test_all_enum_types_defined(self):
        """Verify all enum types are properly defined."""
        enum_types = [
            UserRole,
            DriverVerificationStatus,
            RideStatus,
            BookingStatus,
            TransactionType,
            TransactionStatus,
            VerificationStatus,
            FlagSeverity,
            FlagStatus,
        ]
        
        for enum_type in enum_types:
            assert hasattr(enum_type, '__members__'), f"{enum_type.__name__} is not a valid enum"
            assert len(enum_type.__members__) > 0, f"{enum_type.__name__} has no members"
        
        print(f"✓ All {len(enum_types)} enum types properly defined")
    
    def test_primary_keys_are_uuid(self):
        """Verify all tables use UUID primary keys."""
        for table_name, table in Base.metadata.tables.items():
            pk_columns = [col for col in table.columns if col.primary_key]
            assert len(pk_columns) > 0, f"Table {table_name} has no primary key"
            
            for pk_col in pk_columns:
                # Check if column type is UUID
                assert 'UUID' in str(pk_col.type), \
                    f"Table {table_name} primary key {pk_col.name} is not UUID: {pk_col.type}"
        
        print(f"✓ All {len(Base.metadata.tables)} tables use UUID primary keys")
    
    def test_timestamp_columns_exist(self):
        """Verify created_at/updated_at columns where expected."""
        tables_with_timestamps = [
            'users', 'vehicles', 'rides', 'bookings', 
            'wallets', 'wallet_transactions', 'verifications', 'ratings'
        ]
        
        for table_name in tables_with_timestamps:
            table = Base.metadata.tables.get(table_name)
            assert table is not None, f"Table {table_name} not found"
            
            column_names = [col.name for col in table.columns]
            assert 'created_at' in column_names, \
                f"Table {table_name} missing created_at column"
        
        print(f"✓ Timestamp columns verified for {len(tables_with_timestamps)} tables")
    
    def test_foreign_key_constraints(self):
        """Verify foreign key relationships are properly defined."""
        expected_fks = {
            'drivers': ['user_id'],
            'vehicles': ['owner_id'],
            'rides': ['driver_id'],
            'bookings': ['ride_id', 'passenger_id'],
            'wallets': ['user_id'],
            'wallet_transactions': ['wallet_id'],
            'verifications': ['user_id'],
            'telemetry_points': ['ride_id'],
            'ratings': ['ride_id', 'from_user', 'to_user'],
        }
        
        for table_name, expected_fk_cols in expected_fks.items():
            table = Base.metadata.tables.get(table_name)
            assert table is not None, f"Table {table_name} not found"
            
            fk_columns = []
            for fk in table.foreign_keys:
                fk_columns.append(fk.parent.name)
            
            for expected_fk_col in expected_fk_cols:
                assert expected_fk_col in fk_columns, \
                    f"Table {table_name} missing FK on {expected_fk_col}"
        
        print(f"✓ Foreign keys verified for {len(expected_fks)} tables")
    
    def test_unique_constraints(self):
        """Verify unique constraints on critical columns."""
        unique_constraints = {
            'users': ['email'],
            'vehicles': ['plate_number'],
            'drivers': ['user_id'],
            'wallets': ['user_id'],
        }
        
        for table_name, expected_unique_cols in unique_constraints.items():
            table = Base.metadata.tables.get(table_name)
            assert table is not None, f"Table {table_name} not found"
            
            # Check unique constraints
            unique_cols = set()
            for col in table.columns:
                if col.unique:
                    unique_cols.add(col.name)
            
            # Also check unique indexes
            for index in table.indexes:
                if index.unique and len(index.columns) == 1:
                    unique_cols.add(list(index.columns)[0].name)
            
            for expected_col in expected_unique_cols:
                assert expected_col in unique_cols, \
                    f"Table {table_name} missing unique constraint on {expected_col}"
        
        print(f"✓ Unique constraints verified for {len(unique_constraints)} tables")
    
    def test_indexes_on_foreign_keys(self):
        """Verify indexes exist on foreign key columns for performance."""
        for table_name, table in Base.metadata.tables.items():
            fk_columns = set()
            for fk in table.foreign_keys:
                fk_columns.add(fk.parent.name)
            
            indexed_columns = set()
            for col in table.columns:
                if col.index or col.primary_key or col.unique:
                    indexed_columns.add(col.name)
            
            for index in table.indexes:
                if len(index.columns) == 1:
                    indexed_columns.add(list(index.columns)[0].name)
            
            # Check if all FK columns are indexed
            for fk_col in fk_columns:
                assert fk_col in indexed_columns, \
                    f"Table {table_name} FK column {fk_col} should be indexed"
        
        print(f"✓ All foreign key columns are properly indexed")
    
    def test_sensitive_fields_have_comments(self):
        """Verify sensitive fields have encryption comments."""
        # Check drivers table for license_number comment
        drivers_table = Base.metadata.tables.get('drivers')
        assert drivers_table is not None
        
        license_col = drivers_table.columns.get('license_number')
        assert license_col is not None
        assert license_col.comment is not None, "license_number should have encryption comment"
        assert 'encrypt' in license_col.comment.lower(), \
            "license_number comment should mention encryption"
        
        print("✓ Sensitive fields have encryption comments")


class TestDatabaseConnection:
    """Test database connectivity and configuration."""
    
    @pytest.mark.asyncio
    async def test_database_connection(self):
        """Test that we can connect to the database."""
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(1))
                value = result.scalar()
                assert value == 1
            
            print("✓ Database connection successful")
        except Exception as e:
            pytest.fail(f"Database connection failed: {e}")
    
    @pytest.mark.asyncio
    async def test_database_tables_exist(self):
        """Test that all tables exist in the actual database."""
        expected_tables = [
            'users', 'drivers', 'vehicles', 'rides', 'bookings',
            'wallets', 'wallet_transactions', 'verifications',
            'telemetry_points', 'ratings', 'admin_flags'
        ]
        
        try:
            async with engine.connect() as conn:
                # Get inspector
                def get_table_names(connection):
                    inspector = inspect(connection)
                    return inspector.get_table_names()
                
                existing_tables = await conn.run_sync(get_table_names)
                
                for table_name in expected_tables:
                    assert table_name in existing_tables, \
                        f"Table {table_name} does not exist in database"
            
            print(f"✓ All {len(expected_tables)} tables exist in database")
        except Exception as e:
            pytest.fail(f"Failed to check database tables: {e}")
    
    @pytest.mark.asyncio
    async def test_enum_types_exist_in_database(self):
        """Test that PostgreSQL enum types exist in the database."""
        expected_enums = [
            'user_role',
            'driver_verification_status',
            'ride_status',
            'booking_status',
            'transaction_type',
            'transaction_status',
            'verification_status',
            'flag_severity',
            'flag_status',
        ]
        
        try:
            async with engine.connect() as conn:
                # Query PostgreSQL system catalog for enum types
                def get_enum_types(connection):
                    inspector = inspect(connection)
                    # Get all enum types from pg_type
                    result = connection.execute(
                        """
                        SELECT typname 
                        FROM pg_type 
                        WHERE typtype = 'e'
                        ORDER BY typname
                        """
                    )
                    return [row[0] for row in result]
                
                existing_enums = await conn.run_sync(get_enum_types)
                
                for enum_name in expected_enums:
                    assert enum_name in existing_enums, \
                        f"Enum type {enum_name} does not exist in database"
            
            print(f"✓ All {len(expected_enums)} enum types exist in database")
        except Exception as e:
            pytest.fail(f"Failed to check enum types: {e}")
    
    def test_database_url_configured(self):
        """Test that database URL is properly configured."""
        assert settings.DB_URL is not None, "DB_URL not configured"
        assert settings.DB_URL.startswith('postgresql'), \
            "DB_URL should use postgresql driver"
        assert 'asyncpg' in settings.DB_URL, \
            "DB_URL should use asyncpg for async support"
        
        print("✓ Database URL properly configured")


class TestModelRelationships:
    """Test SQLAlchemy relationships between models."""
    
    @pytest.mark.asyncio
    async def test_user_driver_relationship(self):
        """Test one-to-one relationship between User and Driver."""
        # This is a structural test - just verify relationship is defined
        assert hasattr(User, 'driver_profile'), \
            "User model should have driver_profile relationship"
        assert hasattr(Driver, 'user'), \
            "Driver model should have user relationship"
        
        print("✓ User-Driver relationship properly defined")
    
    @pytest.mark.asyncio
    async def test_driver_vehicle_relationship(self):
        """Test relationship between Driver and Vehicle."""
        assert hasattr(Driver, 'vehicle'), \
            "Driver model should have vehicle relationship"
        
        print("✓ Driver-Vehicle relationship properly defined")
    
    @pytest.mark.asyncio
    async def test_ride_relationships(self):
        """Test Ride model relationships."""
        assert hasattr(Ride, 'driver'), \
            "Ride model should have driver relationship"
        assert hasattr(Ride, 'bookings'), \
            "Ride model should have bookings relationship"
        
        print("✓ Ride relationships properly defined")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
