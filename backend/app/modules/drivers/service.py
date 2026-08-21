"""
Module: Drivers - Service Layer
Purpose: Business logic for driver registration, vehicle management, verification, and earnings.
Author: M. Mobeen Shoukat Ch & M. Shayan Khan
Date: November 7, 2025
Notes: Handles validation, limits enforcement, verification hooks, and standardized response formatting.
"""

import logging
import json
from uuid import UUID
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.modules.drivers import crud
from app.modules.drivers.schemas import (
    DriverProfileCreate, DriverProfileUpdate, DriverProfilePublic,
    VehicleCreate, VehicleUpdate, VehiclePublic,
    DriverStatsPublic, DriverStatusUpdate
)
from app.modules.drivers.schema_compat import ensure_driver_vehicle_schema_compat
from app.modules.auth import crud as auth_crud
from app.modules.verification import crud as verification_crud
from app.modules.verification.models import DocumentTypeEnum, VerificationStatusEnum

logger = logging.getLogger(__name__)

# Configuration constants (TODO: Move to settings)
MAX_ACTIVE_VEHICLES = 3
MIN_RATING_FOR_RIDES = 3.0


# ============================================
# HELPER FUNCTIONS
# ============================================

def _is_ride_eligible(driver, vehicle_count: int = 0) -> bool:
    """
    Determine if driver is eligible to accept rides.
    
    Criteria:
    - Driver must be verified (is_verified=True)
    - Driver status must be 'active'
    - Must have at least one vehicle
    - Rating must be >= 3.0
    """
    if not driver.is_verified:
        return False
    
    status_value = driver.status.value if hasattr(driver.status, "value") else str(driver.status)
    if status_value.lower() != "active":
        return False
    
    if driver.rating < MIN_RATING_FOR_RIDES:
        return False
    
    return vehicle_count > 0


def _format_response(data: Any = None, error: Optional[str] = None) -> Dict[str, Any]:
    """
    Format standardized API response.
    
    Args:
        data: Response payload (None if error)
        error: Error message (None if success)
    
    Returns:
        Dict with {status, data, error} structure
    """
    if error:
        return {
            "status": "error",
            "data": None,
            "error": error
        }
    return {
        "status": "ok",
        "data": data,
        "error": None
    }


def _safe_parse_verification_metadata(metadata_raw: Optional[str]) -> Dict[str, Any]:
    if not metadata_raw:
        return {}

    try:
        parsed = json.loads(metadata_raw)
    except (TypeError, ValueError):
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _is_identity_check_passed(metadata_raw: Optional[str], expected_doc_path: Optional[str]) -> bool:
    metadata = _safe_parse_verification_metadata(metadata_raw)
    identity_meta = metadata.get("identity_data_verification")
    if not isinstance(identity_meta, dict):
        return False

    stored_doc_path = str(identity_meta.get("document_path") or "").strip()
    latest_doc_path = str(expected_doc_path or "").strip()
    if stored_doc_path and latest_doc_path and stored_doc_path != latest_doc_path:
        return False

    status_value = str(identity_meta.get("check_status") or "").strip().lower()
    return status_value in {"passed", "pass", "verified", "approved", "success", "match"}


async def _has_required_driver_verifications(db: AsyncSession, user_id: UUID) -> bool:
    """Return True when required driver docs and identity checks are both verified."""
    try:
        records = await verification_crud.get_user_verifications(db, user_id)
    except Exception:
        return False

    latest_by_doc: Dict[str, Any] = {}
    for verification in records:
        # get_user_verifications returns newest-first; keep first seen per doc type.
        latest_by_doc.setdefault(verification.doc_type.value, verification)

    required_docs = {
        DocumentTypeEnum.CNIC.value,
        DocumentTypeEnum.DRIVING_LICENSE.value,
        DocumentTypeEnum.SELFIE.value,
    }
    identity_required_docs = {
        DocumentTypeEnum.CNIC.value,
        DocumentTypeEnum.DRIVING_LICENSE.value,
    }

    for doc in required_docs:
        verification = latest_by_doc.get(doc)
        if verification is None:
            return False

        if verification.status.value != VerificationStatusEnum.VERIFIED.value:
            return False

        if doc in identity_required_docs and not _is_identity_check_passed(
            verification.meta_data,
            verification.doc_path,
        ):
            return False

    return True


# ============================================
# DRIVER PROFILE SERVICES
# ============================================

async def register_driver_service(
    db: AsyncSession,
    user_id: UUID,
    driver_data: DriverProfileCreate
) -> Dict[str, Any]:
    """
    Register a new driver or upgrade existing user to driver role.
    
    Business Logic:
    - Checks if user exists
    - Creates driver profile with initial status 'pending'
    - Auto-sets rating to 5.0, rides/earnings to 0
    - Verification starts as False (requires admin/AI approval)
    
    Args:
        db: Async database session
        user_id: UUID of the user
        driver_data: DriverProfileCreate schema
    
    Returns:
        Standardized response with created driver profile
    
    Raises:
        HTTPException 404: If user not found
        HTTPException 400: If already registered as driver
    """
    try:
        await ensure_driver_vehicle_schema_compat(db)

        # Verify user exists
        user = await auth_crud.get_user_by_id(db, user_id)
        if not user:
            logger.warning(f"User not found: user_id={user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Create driver profile
        driver = await crud.create_driver_profile(db, user_id, driver_data)

        # Re-read with eager vehicles to avoid lazy-loading issues
        driver = await crud.get_driver_profile(db, user_id) or driver
        
        logger.info(f"Registered new driver: user_id={user_id}, driver_id={driver.id}")
        
        return _format_response(
            data=DriverProfilePublic.model_validate(driver).model_dump()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in register_driver_service: {str(e)}")
        return _format_response(error="Failed to register driver")


async def get_driver_profile_service(
    db: AsyncSession,
    user_id: UUID
) -> Dict[str, Any]:
    """
    Get driver profile with all vehicles and eligibility status.
    
    Args:
        db: Async database session
        user_id: UUID of the user
    
    Returns:
        Standardized response with driver profile, vehicles, and is_ride_eligible flag
    
    Raises:
        HTTPException 404: If driver profile not found
    """
    try:
        await ensure_driver_vehicle_schema_compat(db)

        driver = await crud.get_driver_profile(db, user_id)
        
        if not driver:
            logger.warning(f"Driver profile not found: user_id={user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found. Please register as a driver first."
            )

        # Keep driver profile verification state in sync with KYC document status.
        kyc_verified = await _has_required_driver_verifications(db, user_id)
        if kyc_verified:
            if not driver.is_verified:
                driver.is_verified = True
                if driver.status in (None, "pending"):
                    driver.status = "active"
                await db.commit()
                await db.refresh(driver)
        else:
            if driver.is_verified:
                driver.is_verified = False
                if driver.status in (None, "active"):
                    driver.status = "pending"
                await db.commit()
                await db.refresh(driver)
        
        # Compute ride eligibility
        vehicle_count = await crud.count_active_vehicles(db, driver.user_id, driver.id)
        is_eligible = _is_ride_eligible(driver, vehicle_count)
        
        response_data = {
            "profile": DriverProfilePublic.model_validate(driver).model_dump(),
            "is_ride_eligible": is_eligible
        }
        
        return _format_response(data=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_driver_profile_service: {str(e)}")
        return _format_response(error="Failed to retrieve driver profile")


async def update_driver_profile_service(
    db: AsyncSession,
    user_id: UUID,
    profile_update: DriverProfileUpdate
) -> Dict[str, Any]:
    """
    Update driver profile fields.
    
    Args:
        db: Async database session
        user_id: UUID of the user
        profile_update: DriverProfileUpdate schema
    
    Returns:
        Standardized response with updated driver profile
    
    Raises:
        HTTPException 404: If driver profile not found
    """
    try:
        await ensure_driver_vehicle_schema_compat(db)

        driver = await crud.update_driver_profile(db, user_id, profile_update)
        
        logger.info(f"Updated driver profile: user_id={user_id}")
        
        return _format_response(
            data=DriverProfilePublic.model_validate(driver).model_dump()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_driver_profile_service: {str(e)}")
        return _format_response(error="Failed to update driver profile")


async def update_driver_status_service(
    db: AsyncSession,
    user_id: UUID,
    status_update: DriverStatusUpdate
) -> Dict[str, Any]:
    """
    Update driver account status.
    
    Args:
        db: Async database session
        user_id: UUID of the user
        status_update: DriverStatusUpdate schema
    
    Returns:
        Standardized response with updated driver profile
    
    Notes:
        - Can be used by driver to set 'inactive' (pause services)
        - Admin can set 'suspended' or 'active'
    """
    try:
        await ensure_driver_vehicle_schema_compat(db)

        driver = await crud.get_driver_profile(db, user_id)
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found"
            )
        
        updated_driver = await crud.update_driver_status(db, driver.id, status_update.status)
        
        logger.info(f"Updated driver status: user_id={user_id}, status={status_update.status}")
        
        return _format_response(
            data=DriverProfilePublic.model_validate(updated_driver).model_dump()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_driver_status_service: {str(e)}")
        return _format_response(error="Failed to update driver status")


async def get_driver_stats_service(
    db: AsyncSession,
    user_id: UUID
) -> Dict[str, Any]:
    """
    Get driver performance statistics summary.
    
    Returns:
    - Rating
    - Total rides completed
    - Total earnings
    - Number of active vehicles
    - Ride eligibility status
    
    Args:
        db: Async database session
        user_id: UUID of the user
    
    Returns:
        Standardized response with DriverStatsPublic data
    
    Raises:
        HTTPException 404: If driver profile not found
    """
    try:
        await ensure_driver_vehicle_schema_compat(db)

        driver = await crud.get_driver_profile(db, user_id)
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found"
            )
        
        # Count vehicles via crud
        vehicle_count = await crud.count_active_vehicles(db, driver.user_id, driver.id)

        # Keep driver stats earnings aligned with the Earnings module logic.
        total_earnings = float(driver.total_earnings or 0)
        try:
            from app.modules.earnings import crud as earnings_crud

            _, lifetime_gross, _ = await earnings_crud.get_lifetime_rides_earnings(
                db, driver.user_id
            )
            total_earnings = float(lifetime_gross or 0)
        except Exception:
            logger.warning(
                "Falling back to driver_profiles.total_earnings in get_driver_stats_service",
                exc_info=True,
            )
        
        stats = DriverStatsPublic(
            driver_id=driver.id,
            rating=driver.rating,
            total_rides=driver.total_rides,
            total_earnings=total_earnings,
            active_vehicles=vehicle_count,
            is_ride_eligible=_is_ride_eligible(driver, vehicle_count),
            status=driver.status
        )
        
        return _format_response(data=stats.model_dump())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_driver_stats_service: {str(e)}")
        return _format_response(error="Failed to retrieve driver stats")


# ============================================
# VEHICLE MANAGEMENT SERVICES
# ============================================

async def add_vehicle_service(
    db: AsyncSession,
    user_id: UUID,
    vehicle_data: VehicleCreate
) -> Dict[str, Any]:
    """
    Add a new vehicle to driver's profile.
    
    Business Logic:
    - Enforces MAX_ACTIVE_VEHICLES limit (default: 3)
    - Validates license plate and registration uniqueness
    - Initial verification status is False
    - Vehicle is active by default
    
    Args:
        db: Async database session
        user_id: UUID of the user
        vehicle_data: VehicleCreate schema
    
    Returns:
        Standardized response with created vehicle
    
    Raises:
        HTTPException 404: If driver profile not found
        HTTPException 400: If active vehicle limit exceeded or duplicate plate/registration
    """
    try:
        await ensure_driver_vehicle_schema_compat(db)

        driver = await crud.get_driver_profile(db, user_id)
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found. Please register as a driver first."
            )
        
        # Enforce active vehicle limit
        active_count = await crud.count_active_vehicles(db, driver.user_id, driver.id)
        if active_count >= MAX_ACTIVE_VEHICLES:
            logger.warning(
                f"Vehicle limit exceeded: driver_id={driver.id}, "
                f"active={active_count}, limit={MAX_ACTIVE_VEHICLES}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot add more than {MAX_ACTIVE_VEHICLES} active vehicles. "
                       f"Please deactivate an existing vehicle first."
            )
        
        # Add vehicle (owner_id = user_id)
        vehicle = await crud.add_vehicle(db, driver.user_id, vehicle_data, driver.id)
        
        logger.info(f"Added vehicle: driver_id={driver.id}, vehicle_id={vehicle.id}")
        
        return _format_response(
            data=VehiclePublic.model_validate(vehicle).model_dump()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in add_vehicle_service: {str(e)}")
        return _format_response(error="Failed to add vehicle")


async def get_driver_vehicles_service(
    db: AsyncSession,
    user_id: UUID
) -> Dict[str, Any]:
    """
    Get all vehicles for a driver.
    
    Args:
        db: Async database session
        user_id: UUID of the user
    
    Returns:
        Standardized response with list of vehicles
    
    Raises:
        HTTPException 404: If driver profile not found
    """
    try:
        await ensure_driver_vehicle_schema_compat(db)

        driver = await crud.get_driver_profile(db, user_id)
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found"
            )
        
        vehicles = await crud.get_driver_vehicles(db, driver.user_id, driver.id)
        
        vehicles_public = [VehiclePublic.model_validate(v).model_dump() for v in vehicles]
        
        return _format_response(data=vehicles_public)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_driver_vehicles_service: {str(e)}")
        return _format_response(error="Failed to retrieve vehicles")


async def update_vehicle_service(
    db: AsyncSession,
    user_id: UUID,
    vehicle_id: UUID,
    vehicle_update: VehicleUpdate
) -> Dict[str, Any]:
    """
    Update vehicle details.
    
    Args:
        db: Async database session
        user_id: UUID of the user
        vehicle_id: UUID of the vehicle
        vehicle_update: VehicleUpdate schema
    
    Returns:
        Standardized response with updated vehicle
    
    Raises:
        HTTPException 404: If driver or vehicle not found, or not owned by driver
    """
    try:
        await ensure_driver_vehicle_schema_compat(db)

        driver = await crud.get_driver_profile(db, user_id)
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found"
            )
        
        vehicle = await crud.update_vehicle(db, driver.user_id, vehicle_id, vehicle_update, driver.id)
        
        logger.info(f"Updated vehicle: driver_id={driver.id}, vehicle_id={vehicle_id}")
        
        return _format_response(
            data=VehiclePublic.model_validate(vehicle).model_dump()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in update_vehicle_service: {str(e)}")
        return _format_response(error="Failed to update vehicle")


async def remove_vehicle_service(
    db: AsyncSession,
    user_id: UUID,
    vehicle_id: UUID
) -> Dict[str, Any]:
    """
    Remove a vehicle from driver's profile.
    
    Args:
        db: Async database session
        user_id: UUID of the user
        vehicle_id: UUID of the vehicle
    
    Returns:
        Standardized response with success message
    
    Raises:
        HTTPException 404: If driver or vehicle not found, or not owned by driver
    
    Notes:
        - Permanently deletes vehicle record
        - Cannot be undone
    """
    try:
        await ensure_driver_vehicle_schema_compat(db)

        driver = await crud.get_driver_profile(db, user_id)
        
        if not driver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Driver profile not found"
            )
        
        await crud.remove_vehicle(db, driver.user_id, vehicle_id, driver.id)
        
        logger.info(f"Removed vehicle: driver_id={driver.id}, vehicle_id={vehicle_id}")
        
        return _format_response(
            data={"message": "Vehicle removed successfully", "vehicle_id": str(vehicle_id)}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in remove_vehicle_service: {str(e)}")
        return _format_response(error="Failed to remove vehicle")


# ============================================
# VERIFICATION HOOKS (Future Integration)
# ============================================

async def verify_driver_documents_service(
    db: AsyncSession,
    driver_id: UUID,
    cnic_verified: bool = False,
    license_verified: bool = False
) -> Dict[str, Any]:
    """
    Mock verification service for driver documents.
    
    Future Integration:
    - Connect to AI verification microservice
    - OCR for CNIC and license scanning
    - Facial recognition for identity verification
    - Real-time status updates
    
    Args:
        db: Async database session
        driver_id: UUID of the driver profile
        cnic_verified: CNIC verification result
        license_verified: License verification result
    
    Returns:
        Standardized response with verification status
    
    Notes:
        - Currently a mock implementation
        - In production, will integrate with external verification APIs
        - Auto-updates driver status to 'active' if all verified
    """
    try:
        await ensure_driver_vehicle_schema_compat(db)

        # TODO: Integrate with AI verification service
        # For now, just update verification flags
        
        # Overall verification is True only if both CNIC and at least one vehicle is verified
        is_verified = cnic_verified and license_verified
        
        driver = await crud.update_driver_verification(
            db, driver_id, is_verified, cnic_verified
        )
        
        logger.info(
            f"Verification updated: driver_id={driver_id}, "
            f"cnic={cnic_verified}, license={license_verified}"
        )
        
        return _format_response(
            data={
                "driver_id": str(driver.id),
                "is_verified": driver.is_verified,
                "cnic_verified": driver.cnic_verified,
                "status": driver.status,
                "message": "Verification status updated successfully"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in verify_driver_documents_service: {str(e)}")
        return _format_response(error="Failed to update verification status")
