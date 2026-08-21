"""
Module: Drivers - CRUD Operations
Purpose: Async database operations for driver profiles and vehicle management.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: All operations use async SQLAlchemy with comprehensive error handling and logging.
"""

import logging
from datetime import datetime
from uuid import UUID
from typing import Optional, List
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.modules.drivers.models import DriverProfile
from app.models.vehicle import Vehicle
from app.modules.drivers.schemas import DriverProfileCreate, DriverProfileUpdate, VehicleCreate, VehicleUpdate

logger = logging.getLogger(__name__)


def _vehicle_owner_scope(user_id: UUID, driver_profile_id: Optional[UUID] = None):
    """Build a non-destructive ownership scope that supports legacy and canonical links."""
    predicates = [
        Vehicle.owner_id == user_id,
        Vehicle.driver_id == user_id,
    ]
    if driver_profile_id is not None:
        predicates.append(Vehicle.driver_id == driver_profile_id)
    return or_(*predicates)


def _vehicle_owned_by(vehicle: Vehicle, user_id: UUID, driver_profile_id: Optional[UUID] = None) -> bool:
    """Runtime ownership check for mixed-schema records."""
    if vehicle.owner_id == user_id or vehicle.driver_id == user_id:
        return True
    if driver_profile_id is not None and vehicle.driver_id == driver_profile_id:
        return True
    return False


# ============================================
# DRIVER PROFILE CRUD OPERATIONS
# ============================================

async def create_driver_profile(
    db: AsyncSession, 
    user_id: UUID, 
    data: DriverProfileCreate
) -> DriverProfile:
    """
    Create a new driver profile for a user.
    
    Args:
        db: Async database session
        user_id: UUID of the user becoming a driver
        data: DriverProfileCreate schema with license, CNIC, etc.
    
    Returns:
        Created DriverProfile instance
    
    Raises:
        HTTPException 400: If driver profile already exists for this user
        HTTPException 500: On database errors
    
    Notes:
        - Initial status is 'pending' (awaiting verification)
        - is_verified defaults to False
        - Rating starts at 5.0, rides/earnings at 0
    """
    try:
        # Check if driver profile already exists
        result = await db.execute(
            select(DriverProfile).where(DriverProfile.user_id == user_id)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            logger.warning(f"Driver profile already exists for user_id={user_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Driver profile already exists for this user"
            )
        
        # Create new driver profile
        new_driver = DriverProfile(
            user_id=user_id,
            license_number=data.license_number,
            license_expiry=data.license_expiry,
            cnic_number=data.cnic_number,
            address=data.address
        )

        # Best-effort compatibility upsert for legacy `drivers` table.
        # Some environments keep rides.driver_id -> drivers.user_id FK.
        # Use savepoints so failures here do not poison the outer transaction.
        legacy_statements = [
            (
                """
                INSERT INTO drivers (user_id, license_number, verified, rating_avg, rating_count, created_at, updated_at)
                VALUES (
                    :user_id,
                    :license_number,
                    CAST(:verified_status AS driver_verification_status),
                    :rating_avg,
                    :rating_count,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (user_id) DO NOTHING
                """,
                {
                    "user_id": user_id,
                    "license_number": data.license_number,
                    "verified_status": "PENDING",
                    "rating_avg": 5.0,
                    "rating_count": 0,
                },
            ),
            (
                """
                INSERT INTO drivers (user_id, license_number, verified, rating_avg, rating_count, created_at, updated_at)
                VALUES (
                    :user_id,
                    :license_number,
                    CAST(:verified_status AS driver_verification_status),
                    :rating_avg,
                    :rating_count,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (user_id) DO NOTHING
                """,
                {
                    "user_id": user_id,
                    "license_number": data.license_number,
                    "verified_status": "pending",
                    "rating_avg": 5.0,
                    "rating_count": 0,
                },
            ),
            (
                """
                INSERT INTO drivers (user_id, license_number, verified, rating_avg, rating_count, created_at, updated_at)
                VALUES (:user_id, :license_number, :verified, :rating_avg, :rating_count, NOW(), NOW())
                ON CONFLICT (user_id) DO NOTHING
                """,
                {
                    "user_id": user_id,
                    "license_number": data.license_number,
                    "verified": False,
                    "rating_avg": 5.0,
                    "rating_count": 0,
                },
            ),
            (
                """
                INSERT INTO drivers (user_id, license_number)
                VALUES (:user_id, :license_number)
                ON CONFLICT (user_id) DO NOTHING
                """,
                {
                    "user_id": user_id,
                    "license_number": data.license_number,
                },
            ),
            (
                """
                INSERT INTO drivers (user_id)
                VALUES (:user_id)
                ON CONFLICT (user_id) DO NOTHING
                """,
                {"user_id": user_id},
            ),
        ]

        for sql_stmt, params in legacy_statements:
            try:
                async with db.begin_nested():
                    await db.execute(text(sql_stmt), params)
                break
            except Exception:
                continue
        else:
            logger.debug(
                "Legacy drivers upsert skipped for user_id=%s",
                user_id,
                exc_info=True,
            )
        
        db.add(new_driver)
        await db.commit()
        await db.refresh(new_driver)
        
        logger.info(f"Created driver profile for user_id={user_id}, driver_id={new_driver.id}")
        return new_driver
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating driver profile for user_id={user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create driver profile"
        )


async def get_driver_profile(db: AsyncSession, user_id: UUID) -> Optional[DriverProfile]:
    """
    Retrieve driver profile by user_id with all vehicles.
    
    Args:
        db: Async database session
        user_id: UUID of the user
    
    Returns:
        DriverProfile with vehicles loaded, or None if not found
    
    Notes:
        - Uses selectinload for efficient vehicle fetching
        - Returns None instead of raising exception if not found
    """
    try:
        result = await db.execute(
            select(DriverProfile)
            .options(selectinload(DriverProfile.vehicles))
            .where(DriverProfile.user_id == user_id)
        )
        driver = result.scalar_one_or_none()
        
        if driver:
            logger.debug(f"Retrieved driver profile for user_id={user_id}")
        else:
            logger.debug(f"No driver profile found for user_id={user_id}")
        
        return driver
        
    except Exception as e:
        logger.error(f"Error fetching driver profile for user_id={user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve driver profile"
        )


async def get_driver_profile_by_id(db: AsyncSession, driver_id: UUID) -> Optional[DriverProfile]:
    """
    Retrieve driver profile by driver_id with all vehicles.
    
    Args:
        db: Async database session
        driver_id: UUID of the driver profile
    
    Returns:
        DriverProfile with vehicles loaded, or None if not found
    """
    try:
        result = await db.execute(
            select(DriverProfile)
            .options(selectinload(DriverProfile.vehicles))
            .where(DriverProfile.id == driver_id)
        )
        return result.scalar_one_or_none()
        
    except Exception as e:
        logger.error(f"Error fetching driver profile by driver_id={driver_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve driver profile"
        )


async def update_driver_profile(
    db: AsyncSession, 
    user_id: UUID, 
    profile_update: DriverProfileUpdate
) -> DriverProfile:
    """
    Update driver profile fields.
    
    Args:
        db: Async database session
        user_id: UUID of the user
        profile_update: DriverProfileUpdate schema with updated fields
    
    Returns:
        Updated DriverProfile instance
    
    Raises:
        HTTPException 404: If driver profile not found
        HTTPException 500: On database errors
    
    Notes:
        - Only updates fields that are explicitly set (exclude_unset=True)
        - updated_at timestamp is automatically set by SQLAlchemy
    """
    try:
        driver = await get_driver_profile(db, user_id)
        
        if not driver:
            logger.warning(f"Driver profile not found for user_id={user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found"
            )
        
        # Update only provided fields
        update_data = profile_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(driver, field, value)
        
        await db.commit()
        await db.refresh(driver)
        
        logger.info(f"Updated driver profile for user_id={user_id}")
        return driver
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating driver profile for user_id={user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update driver profile"
        )


async def update_driver_status(db: AsyncSession, driver_id: UUID, new_status: str) -> DriverProfile:
    """
    Update driver account status (active/suspended/pending/inactive).
    
    Args:
        db: Async database session
        driver_id: UUID of the driver profile
        new_status: New status value
    
    Returns:
        Updated DriverProfile instance
    
    Raises:
        HTTPException 404: If driver not found
        HTTPException 500: On database errors
    
    Notes:
        - Used by admins for verification or suspension
        - Status changes logged for audit trail
    """
    try:
        driver = await get_driver_profile_by_id(db, driver_id)
        
        if not driver:
            logger.warning(f"Driver profile not found for driver_id={driver_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found"
            )
        
        old_status = driver.status
        driver.status = new_status
        
        await db.commit()
        await db.refresh(driver)
        
        logger.info(f"Updated driver status: driver_id={driver_id}, {old_status} -> {new_status}")
        return driver
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating driver status for driver_id={driver_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update driver status"
        )


async def update_driver_verification(
    db: AsyncSession, 
    driver_id: UUID, 
    is_verified: bool,
    cnic_verified: Optional[bool] = None
) -> DriverProfile:
    """
    Update driver verification status.
    
    Args:
        db: Async database session
        driver_id: UUID of the driver profile
        is_verified: Overall verification status
        cnic_verified: Optional CNIC verification status
    
    Returns:
        Updated DriverProfile instance
    
    Notes:
        - Called by admin/AI verification modules
        - Auto-updates status to 'active' if fully verified
    """
    try:
        driver = await get_driver_profile_by_id(db, driver_id)
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found"
            )
        
        driver.is_verified = is_verified
        if cnic_verified is not None:
            driver.cnic_verified = cnic_verified
        
        # Auto-activate if fully verified
        status_value = driver.status.value if hasattr(driver.status, "value") else str(driver.status)
        if is_verified and status_value.lower() == "pending":
            driver.status = "active"
        
        await db.commit()
        await db.refresh(driver)
        
        logger.info(f"Updated verification: driver_id={driver_id}, verified={is_verified}")
        return driver
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating verification for driver_id={driver_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update verification status"
        )


async def sync_identity_after_profile_update(
    db: AsyncSession,
    user_id: UUID,
    cnic_number: Optional[str] = None,
    license_number: Optional[str] = None,
    cnic_changed: bool = False,
    license_changed: bool = False,
) -> Optional[DriverProfile]:
    """
    Keep driver profile identity fields aligned with user profile updates.

    When CNIC or license changes, driver verification flags are reset and
    status is moved back to pending until updated documents are re-verified.
    """
    if not cnic_changed and not license_changed:
        return None

    try:
        driver = await get_driver_profile(db, user_id)
        if not driver:
            return None

        touched = False

        if cnic_changed and cnic_number is not None:
            normalized_cnic = cnic_number.strip()
            if normalized_cnic:
                driver.cnic_number = normalized_cnic
                touched = True
            driver.cnic_verified = False
            touched = True

        if license_changed and license_number is not None:
            normalized_license = license_number.strip()
            if normalized_license:
                driver.license_number = normalized_license
                touched = True

        if cnic_changed or license_changed:
            driver.is_verified = False
            driver.status = "pending"
            touched = True

        if not touched:
            return driver

        await db.commit()
        await db.refresh(driver)

        logger.info(
            "Driver identity synced for user_id=%s (cnic_changed=%s, license_changed=%s)",
            user_id,
            cnic_changed,
            license_changed,
        )
        return driver

    except Exception as e:
        await db.rollback()
        logger.error(
            "Error syncing driver identity after profile update for user_id=%s: %s",
            user_id,
            str(e),
        )
        return None


# ============================================
# VEHICLE CRUD OPERATIONS
# ============================================

async def add_vehicle(
    db: AsyncSession, 
    driver_id: UUID, 
    vehicle_data: VehicleCreate,
    driver_profile_id: Optional[UUID] = None,
) -> Vehicle:
    """
    Add a new vehicle to a driver's profile.
    
    Args:
        db: Async database session
        driver_id: UUID of the driver profile
        vehicle_data: VehicleCreate schema with vehicle details
    
    Returns:
        Created Vehicle instance
    
    Raises:
        HTTPException 400: If license plate or registration already exists
        HTTPException 500: On database errors
    
    Notes:
        - Checks for duplicate license plates and registration numbers
        - Does NOT enforce 3-vehicle limit (handled by service layer)
    """
    try:
        # Ensure legacy `drivers` FK target row exists before vehicle insert.
        try:
            async with db.begin_nested():
                await db.execute(
                    text(
                        """
                        INSERT INTO drivers (user_id)
                        VALUES (:user_id)
                        ON CONFLICT (user_id) DO NOTHING
                        """
                    ),
                    {"user_id": driver_id},
                )
        except Exception:
            try:
                profile_license = None
                if driver_profile_id is not None:
                    profile_result = await db.execute(
                        select(DriverProfile.license_number).where(DriverProfile.id == driver_profile_id)
                    )
                    profile_license = profile_result.scalar_one_or_none()

                async with db.begin_nested():
                    await db.execute(
                        text(
                            """
                            INSERT INTO drivers (user_id, license_number)
                            VALUES (:user_id, :license_number)
                            ON CONFLICT (user_id) DO NOTHING
                            """
                        ),
                        {
                            "user_id": driver_id,
                            "license_number": profile_license or "PENDING",
                        },
                    )
            except Exception:
                logger.debug(
                    "Legacy drivers pre-insert skipped for user_id=%s",
                    driver_id,
                    exc_info=True,
                )

        # Check for duplicate plate number
        normalized_plate = vehicle_data.plate_number.upper()
        current_year = datetime.now().year
        result = await db.execute(
            select(Vehicle).where(
                func.upper(func.coalesce(Vehicle.plate_number, Vehicle.license_plate)) == normalized_plate
            )
        )
        if result.scalar_one_or_none():
            logger.warning(f"Duplicate plate number: {vehicle_data.plate_number}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Vehicle with plate number {vehicle_data.plate_number} already exists"
            )
        
        # Legacy DB enforces vehicles.driver_id -> drivers.user_id FK.
        # Use the authenticated driver's user UUID for driver_id.
        new_vehicle = Vehicle(
            owner_id=driver_id,
            driver_id=driver_id,
            make=vehicle_data.make,
            model=vehicle_data.model,
            plate_number=normalized_plate,
            license_plate=normalized_plate,
            year=current_year,
            seats_total=vehicle_data.seats_total,
            seats_available=vehicle_data.seats_available,
            photos=vehicle_data.photos
        )
        
        db.add(new_vehicle)
        await db.commit()
        await db.refresh(new_vehicle)
        
        logger.info(f"Added vehicle: driver_id={driver_id}, vehicle_id={new_vehicle.id}")
        return new_vehicle
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error adding vehicle for driver_id={driver_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add vehicle"
        )


async def get_driver_vehicles(
    db: AsyncSession,
    driver_id: UUID,
    driver_profile_id: Optional[UUID] = None,
) -> List[Vehicle]:
    """
    Retrieve all vehicles for a driver.
    
    Args:
        db: Async database session
        driver_id: UUID of the driver profile
    
    Returns:
        List of Vehicle instances (empty list if none)
    
    Notes:
        - Ordered by created_at (newest first)
        - Includes both active and inactive vehicles
    """
    try:
        result = await db.execute(
            select(Vehicle)
            .where(_vehicle_owner_scope(driver_id, driver_profile_id))
            .order_by(Vehicle.created_at.desc())
        )
        vehicles = result.scalars().all()
        
        logger.debug(f"Retrieved {len(vehicles)} vehicles for driver_id={driver_id}")
        return list(vehicles)
        
    except Exception as e:
        logger.error(f"Error fetching vehicles for driver_id={driver_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve vehicles"
        )


async def get_vehicle_by_id(db: AsyncSession, vehicle_id: UUID) -> Optional[Vehicle]:
    """
    Retrieve a specific vehicle by ID.
    
    Args:
        db: Async database session
        vehicle_id: UUID of the vehicle
    
    Returns:
        Vehicle instance or None if not found
    """
    try:
        result = await db.execute(
            select(Vehicle).where(Vehicle.id == vehicle_id)
        )
        return result.scalar_one_or_none()
        
    except Exception as e:
        logger.error(f"Error fetching vehicle by vehicle_id={vehicle_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve vehicle"
        )


async def update_vehicle(
    db: AsyncSession, 
    driver_id: UUID, 
    vehicle_id: UUID, 
    vehicle_update: VehicleUpdate,
    driver_profile_id: Optional[UUID] = None,
) -> Vehicle:
    """
    Update vehicle details.
    
    Args:
        db: Async database session
        driver_id: UUID of the driver (for ownership verification)
        vehicle_id: UUID of the vehicle
        vehicle_update: VehicleUpdate schema with updated fields
    
    Returns:
        Updated Vehicle instance
    
    Raises:
        HTTPException 404: If vehicle not found or not owned by driver
        HTTPException 500: On database errors
    """
    try:
        vehicle = await get_vehicle_by_id(db, vehicle_id)
        
        if not vehicle or not _vehicle_owned_by(vehicle, driver_id, driver_profile_id):
            logger.warning(f"Vehicle not found or unauthorized: vehicle_id={vehicle_id}, driver_id={driver_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found or you don't own this vehicle"
            )
        
        # Update only provided fields
        update_data = vehicle_update.model_dump(exclude_unset=True)

        if not update_data:
            return vehicle

        if "plate_number" in update_data and update_data["plate_number"] is not None:
            normalized_plate = update_data["plate_number"].strip().upper()
            duplicate_result = await db.execute(
                select(Vehicle.id).where(
                    Vehicle.id != vehicle_id,
                    func.upper(func.coalesce(Vehicle.plate_number, Vehicle.license_plate)) == normalized_plate,
                )
            )
            if duplicate_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Vehicle with plate number {normalized_plate} already exists",
                )
            update_data["plate_number"] = normalized_plate
            update_data["license_plate"] = normalized_plate

        new_seats_total = update_data.get("seats_total", vehicle.seats_total)
        new_seats_available = update_data.get("seats_available", vehicle.seats_available)

        if new_seats_total is not None and new_seats_available is not None:
            if new_seats_available > new_seats_total:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Available seats cannot exceed total seats",
                )

        for field, value in update_data.items():
            setattr(vehicle, field, value)
        
        await db.commit()
        await db.refresh(vehicle)
        
        logger.info(f"Updated vehicle: vehicle_id={vehicle_id}, driver_id={driver_id}")
        return vehicle
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating vehicle_id={vehicle_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update vehicle"
        )


async def remove_vehicle(
    db: AsyncSession,
    driver_id: UUID,
    vehicle_id: UUID,
    driver_profile_id: Optional[UUID] = None,
) -> bool:
    """
    Delete a vehicle from driver's profile.
    
    Args:
        db: Async database session
        driver_id: UUID of the driver (for ownership verification)
        vehicle_id: UUID of the vehicle to delete
    
    Returns:
        True if deleted successfully
    
    Raises:
        HTTPException 404: If vehicle not found or not owned by driver
        HTTPException 500: On database errors
    
    Notes:
        - Permanently deletes vehicle record
        - Ownership is verified before deletion
    """
    try:
        vehicle = await get_vehicle_by_id(db, vehicle_id)
        
        if not vehicle or not _vehicle_owned_by(vehicle, driver_id, driver_profile_id):
            logger.warning(f"Vehicle not found or unauthorized: vehicle_id={vehicle_id}, driver_id={driver_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found or you don't own this vehicle"
            )
        
        await db.delete(vehicle)
        await db.commit()
        
        logger.info(f"Deleted vehicle: vehicle_id={vehicle_id}, driver_id={driver_id}")
        return True
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting vehicle_id={vehicle_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete vehicle"
        )


async def count_active_vehicles(
    db: AsyncSession,
    driver_id: UUID,
    driver_profile_id: Optional[UUID] = None,
) -> int:
    """
    Count active vehicles for a driver.
    
    Args:
        db: Async database session
        driver_id: UUID of the driver profile
    
    Returns:
        Number of active vehicles
    
    Notes:
        - Used by service layer to enforce 3-vehicle limit
        - Only counts vehicles with is_active=True
    """
    try:
        from sqlalchemy import func as sa_func
        result = await db.execute(
            select(sa_func.count(Vehicle.id))
            .where(_vehicle_owner_scope(driver_id, driver_profile_id))
            .where(or_(Vehicle.is_active.is_(True), Vehicle.is_active.is_(None)))
        )
        count = result.scalar() or 0
        
        logger.debug(f"Driver {driver_id} has {count} vehicles")
        return count
        
    except Exception as e:
        logger.error(f"Error counting active vehicles for driver_id={driver_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to count active vehicles"
        )


# Alias for backward compatibility
get_driver_by_user_id = get_driver_profile
