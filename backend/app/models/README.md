# Database Models Documentation

## Overview
This directory contains SQLAlchemy ORM models for the SmartCarpoolingApp backend. All models use async-compatible SQLAlchemy with PostgreSQL and asyncpg driver.

## Architecture

### Core Design Principles
- **UUID Primary Keys**: All tables use UUID (postgres UUID type) for primary keys
- **Timezone-aware Timestamps**: All timestamps use `TIMESTAMP WITH TIME ZONE`
- **Async-friendly**: Models designed for use with SQLAlchemy async engine
- **Type Safety**: Full type annotations using `Mapped[]` types

## Models Structure

### Authentication & Users
- **User** (`app/modules/auth/models.py`): Core user accounts with roles (passenger, driver, admin)
- **Driver** (`driver.py`): Driver-specific information with one-to-one relationship to User
- **Vehicle** (`vehicle.py`): Vehicle information owned by users

### Rides & Bookings
- **Ride** (`ride.py`): Ride offers with route, pricing, and status
- **Booking** (`booking.py`): Passenger reservations for rides

### Payments
- **Wallet** (`wallet.py`): User wallet for in-app payments
- **WalletTransaction** (`wallet_transaction.py`): Transaction history

### Verification & Safety
- **Verification** (`verification.py`): Document verification records (CNIC, license, etc.)
- **TelemetryPoint** (`telemetry_point.py`): Real-time location tracking during rides
- **Rating** (`rating.py`): User ratings and reviews

### Administration
- **AdminFlag** (`admin_flag.py`): Admin flagging system for content moderation

## Security Considerations

### Encrypted Fields
The following fields contain sensitive personal information and **MUST** be encrypted at rest:

#### User Model
- **`cnic`**: National identity card number
  - Storage: Encrypted string (max 50 chars)
  - Encryption: Use KMS (AWS KMS, Azure Key Vault, or similar)
  - Implementation: Application-level encryption before DB insert

#### Driver Model
- **`license_number`**: Driver's license number
  - Storage: Encrypted string (max 255 chars)
  - Encryption: Use KMS (AWS KMS, Azure Key Vault, or similar)
  - Implementation: Application-level encryption before DB insert

### Encryption Implementation Steps

1. **Choose KMS Provider**:
   ```python
   # AWS KMS example
   from aws_encryption_sdk import EncryptionSDKClient
   
   # Azure Key Vault example  
   from azure.keyvault.keys.crypto import CryptographyClient
   ```

2. **Create Encryption Service**:
   ```python
   # backend/app/core/encryption.py
   class EncryptionService:
       async def encrypt_field(self, plaintext: str) -> str:
           """Encrypt sensitive field using KMS"""
           pass
       
       async def decrypt_field(self, ciphertext: str) -> str:
           """Decrypt sensitive field using KMS"""
           pass
   ```

3. **Apply in CRUD Operations**:
   ```python
   # Before insert/update
   user.cnic = await encryption_service.encrypt_field(plaintext_cnic)
   
   # After select
   plaintext_cnic = await encryption_service.decrypt_field(user.cnic)
   ```

### TODO: Security Enhancements
- [ ] Implement KMS integration for field-level encryption
- [ ] Add encryption middleware for automatic encrypt/decrypt
- [ ] Set up key rotation policies
- [ ] Add audit logging for encrypted field access
- [ ] Implement RBAC for sensitive field access

## Spatial Data & PostGIS

### Current Implementation
The current implementation uses **latitude/longitude float columns** for geospatial data:

- **drivers.location_last_lat, location_last_lng**: Driver's last known location
- **rides.start_point_lat, start_point_lng**: Ride starting point
- **rides.end_point_lat, end_point_lng**: Ride destination
- **telemetry_points.latitude, longitude**: Real-time tracking points

**Indexes**: Composite B-tree indexes on (lat, lng) pairs for basic spatial queries.

### PostGIS Enhancement (Recommended for Production)

PostGIS provides advanced spatial features and better performance for geo-queries.

#### Installation Steps

1. **Enable PostGIS Extension**:
   ```sql
   -- Connect to your database
   CREATE EXTENSION IF NOT EXISTS postgis;
   CREATE EXTENSION IF NOT EXISTS postgis_topology;
   ```

2. **Install GeoAlchemy2**:
   ```bash
   pip install geoalchemy2
   ```

3. **Update Models** (example for Driver model):
   ```python
   from geoalchemy2 import Geography
   
   class Driver(Base):
       # Replace lat/lng columns with:
       location_last: Mapped[str] = mapped_column(
           Geography(geometry_type='POINT', srid=4326),
           nullable=True,
           comment="Last known location (PostGIS POINT)"
       )
   ```

4. **Create Spatial Index**:
   ```python
   # In model definition
   __table_args__ = (
       Index('idx_drivers_location_gist', 'location_last', 
             postgresql_using='gist'),
   )
   ```

5. **Create Migration**:
   ```bash
   alembic revision --autogenerate -m "add postgis support"
   alembic upgrade head
   ```

#### Spatial Query Examples

**Find nearby drivers**:
```python
from geoalchemy2.functions import ST_DWithin, ST_MakePoint

# Find drivers within 5km of user location
nearby_drivers = await db.execute(
    select(Driver)
    .where(
        ST_DWithin(
            Driver.location_last,
            ST_MakePoint(user_lng, user_lat, srid=4326).cast(Geography),
            5000  # 5km in meters
        )
    )
)
```

**Calculate distance**:
```python
from geoalchemy2.functions import ST_Distance

distance = ST_Distance(
    Driver.location_last,
    ST_MakePoint(dest_lng, dest_lat, srid=4326).cast(Geography)
)
```

### Migration Path

If you want to migrate from lat/lng to PostGIS:

1. Enable PostGIS extension
2. Add new geography columns
3. Populate from existing lat/lng: `UPDATE drivers SET location_last = ST_MakePoint(location_last_lng, location_last_lat)`
4. Create GIST indexes
5. Update application code
6. Test thoroughly
7. Drop old lat/lng columns

## Performance Optimization

### Existing Indexes

The schema includes indexes on:
- Primary keys (UUID)
- Foreign keys
- Frequently queried columns (email, phone, status fields)
- Composite indexes for geo queries (lat, lng pairs)
- Unique constraints (email, plate_number)

### Recommended Additional Indexes

**For Analytics**:
```sql
-- Time-series queries
CREATE INDEX idx_rides_created_at ON rides(created_at DESC);
CREATE INDEX idx_bookings_created_at ON bookings(created_at DESC);
CREATE INDEX idx_wallet_transactions_created_at ON wallet_transactions(created_at DESC);
```

**Partial Indexes** (for common filters):
```sql
-- Active rides only
CREATE INDEX idx_rides_active ON rides(start_time) 
WHERE status IN ('open', 'in_progress');

-- Verified drivers only
CREATE INDEX idx_drivers_verified ON drivers(user_id) 
WHERE verified = 'verified';
```

**For High-Volume Tables**:
- Consider table partitioning for `telemetry_points` (by date range)
- Consider archiving old `wallet_transactions` to separate tables
- Use connection pooling (already configured in `app/db/session.py`)

## Enum Types

All enums are defined in `enums.py`:

- `UserRole`: passenger, driver, admin
- `DriverVerificationStatus`: pending, verified, rejected
- `RideStatus`: open, in_progress, completed, cancelled
- `BookingStatus`: reserved, cancelled, completed
- `TransactionType`: topup, payout, ride
- `TransactionStatus`: pending, completed, failed
- `FlagSeverity`: low, medium, high
- `FlagStatus`: open, resolved, dismissed
- `VerificationStatus`: pending, verified, rejected

## Testing

Run model tests:
```bash
pytest backend/tests/test_db_models.py -v
```

## Alembic Migrations

### Generate Migration
```bash
cd backend
alembic revision --autogenerate -m "description of changes"
```

### Review and Edit
Always review autogenerated migrations before applying:
```bash
# Check the generated file in backend/alembic/versions/
```

### Apply Migration
```bash
alembic upgrade head
```

### Rollback
```bash
alembic downgrade -1  # Rollback one version
```

## Best Practices

1. **Always use async session**: Use `AsyncSession` from `app/db/session.py`
2. **Type safety**: Use `Mapped[Type]` for all columns
3. **Lazy loading**: Configure relationships appropriately for async context
4. **Indexes**: Add indexes for frequently queried columns
5. **Constraints**: Use database constraints (FK, unique, check) where appropriate
6. **Comments**: Add docstrings and column comments for clarity
7. **Encryption**: Encrypt sensitive fields at application level
8. **Testing**: Write tests for complex queries and relationships

## Resources

- [SQLAlchemy Async Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Alembic Documentation](https://alembic.sqlalchemy.org/en/latest/)
- [PostGIS Documentation](https://postgis.net/documentation/)
- [GeoAlchemy2 Documentation](https://geoalchemy-2.readthedocs.io/)
