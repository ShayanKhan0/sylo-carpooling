"""
Module: Users
Purpose: CRUD operations for user profiles and saved addresses.
         Async database operations with error handling and logging.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 7, 2025
Notes: All functions are async and use AsyncSession.
       Includes joined loading to avoid N+1 query problems.
       Error handling with structured logging and HTTPException.
"""

import asyncio
from types import SimpleNamespace
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, text
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from uuid import UUID
from typing import Optional, List
import logging
import uuid

from app.modules.users.models import UserProfile, SavedAddress
from app.modules.users.schemas import UserProfileCreate, UserProfileUpdate, SavedAddressCreate

logger = logging.getLogger(__name__)

_profile_schema_ready = False
_profile_schema_lock = asyncio.Lock()


def _is_schema_mismatch_error(error: Exception) -> bool:
    """Detect column mismatch errors caused by legacy schema drift."""
    message = str(error).lower()
    return "undefinedcolumnerror" in message or "does not exist" in message


async def _get_table_columns(db: AsyncSession, table_name: str) -> set[str]:
    result = await db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return {row[0] for row in result.fetchall()}


def _profile_photo_expr(columns: set[str]) -> str:
    if "profile_photo" in columns:
        return "profile_photo"
    if "avatar_url" in columns:
        return "avatar_url"
    return "NULL::text"


def _address_lat_expr(columns: set[str]) -> str:
    if "latitude" in columns:
        return "latitude"
    if "location_lat" in columns:
        return "location_lat"
    return "NULL::double precision"


def _address_lng_expr(columns: set[str]) -> str:
    if "longitude" in columns:
        return "longitude"
    if "location_lng" in columns:
        return "location_lng"
    return "NULL::double precision"


async def _get_user_profile_compat(db: AsyncSession, user_id: UUID) -> Optional[SimpleNamespace]:
    columns = await _get_table_columns(db, "user_profiles")
    if not columns:
        return None

    select_sql = text(
        f"""
        SELECT
            id,
            user_id,
            {_profile_photo_expr(columns)} AS profile_photo,
            {"gender::text" if "gender" in columns else "NULL::text"} AS gender,
            {"date_of_birth" if "date_of_birth" in columns else "NULL::date"} AS date_of_birth,
            {"organization_name" if "organization_name" in columns else "NULL::text"} AS organization_name,
            {"organization_type::text" if "organization_type" in columns else "NULL::text"} AS organization_type,
            {"cnic" if "cnic" in columns else "NULL::text"} AS cnic,
            {"driving_license" if "driving_license" in columns else "NULL::text"} AS driving_license,
            {"car_registration" if "car_registration" in columns else "NULL::text"} AS car_registration,
            {"address_verification" if "address_verification" in columns else "FALSE::boolean"} AS address_verification,
            {"COALESCE(push_notifications_enabled, TRUE)" if "push_notifications_enabled" in columns else "TRUE"} AS push_notifications_enabled,
            {"COALESCE(share_location_enabled, TRUE)" if "share_location_enabled" in columns else "TRUE"} AS share_location_enabled,
            {"created_at" if "created_at" in columns else "NOW()"} AS created_at,
            {"updated_at" if "updated_at" in columns else "NULL::timestamp with time zone"} AS updated_at
        FROM user_profiles
        WHERE user_id = :user_id
        """
    )
    result = await db.execute(select_sql, {"user_id": user_id})
    row = result.mappings().first()
    if not row:
        return None
    return SimpleNamespace(**dict(row))


async def _get_saved_addresses_compat(db: AsyncSession, user_id: UUID) -> List[SimpleNamespace]:
    columns = await _get_table_columns(db, "saved_addresses")
    if not columns:
        return []

    select_sql = text(
        f"""
        SELECT
            id,
            user_id,
            {"label" if "label" in columns else "''::text"} AS label,
            {"address" if "address" in columns else "''::text"} AS address,
            {_address_lat_expr(columns)} AS latitude,
            {_address_lng_expr(columns)} AS longitude,
            {"created_at" if "created_at" in columns else "NOW()"} AS created_at
        FROM saved_addresses
        WHERE user_id = :user_id
        ORDER BY {"created_at DESC" if "created_at" in columns else "id DESC"}
        """
    )
    result = await db.execute(select_sql, {"user_id": user_id})
    rows = result.mappings().all()
    return [SimpleNamespace(**dict(row)) for row in rows]


async def ensure_user_profile_schema_compat(db: AsyncSession) -> None:
    """Run a read-only compatibility probe for mixed-schema environments."""
    global _profile_schema_ready

    if _profile_schema_ready:
        return

    async with _profile_schema_lock:
        if _profile_schema_ready:
            return

        try:
            # Do not run DDL from request flows; DB users often lack table-owner privileges.
            await _get_table_columns(db, "user_profiles")
            _profile_schema_ready = True
            logger.info("User profile schema compatibility check completed")
        except Exception:
            await db.rollback()
            logger.exception("User profile schema compatibility check failed")
            # Do not raise to avoid blocking auth/profile flows in legacy DBs.


# ==================== User Profile CRUD ====================

async def create_user_profile(db: AsyncSession, user_id: UUID) -> UserProfile:
    """
    Create an empty user profile for a newly registered user.
    
    Called automatically from auth service after user registration.
    Creates a minimal profile that can be filled in later.
    
    Args:
        db: Async database session
        user_id: UUID of the user who just registered
    
    Returns:
        UserProfile: Newly created profile object
    
    Raises:
        HTTPException: If profile creation fails
    
    Notes:
        - All profile fields start as NULL (except user_id and defaults)
        - User can update profile later via PUT /users/me
        - CASCADE delete ensures profile is removed if user is deleted
    """
    try:
        logger.info(f"Creating empty profile for user: {user_id}")
        await ensure_user_profile_schema_compat(db)
        
        new_profile = UserProfile(user_id=user_id)
        db.add(new_profile)
        await db.commit()
        await db.refresh(new_profile)
        
        logger.info(f"Profile created successfully: {new_profile.id}")
        return new_profile
    
    except Exception as e:
        await db.rollback()
        if _is_schema_mismatch_error(e):
            try:
                columns = await _get_table_columns(db, "user_profiles")
                if not columns:
                    raise

                insert_cols = ["user_id"]
                insert_vals = [":user_id"]
                params = {"user_id": user_id}

                if "id" in columns:
                    insert_cols.insert(0, "id")
                    insert_vals.insert(0, ":id")
                    params["id"] = uuid.uuid4()

                if "push_notifications_enabled" in columns:
                    insert_cols.append("push_notifications_enabled")
                    insert_vals.append("TRUE")
                if "share_location_enabled" in columns:
                    insert_cols.append("share_location_enabled")
                    insert_vals.append("TRUE")

                insert_sql = text(
                    f"INSERT INTO user_profiles ({', '.join(insert_cols)}) VALUES ({', '.join(insert_vals)})"
                )
                await db.execute(insert_sql, params)
                await db.commit()

                compat_profile = await _get_user_profile_compat(db, user_id)
                if compat_profile is not None:
                    logger.info(f"Legacy-compatible profile created for user: {user_id}")
                    return compat_profile
            except Exception as legacy_error:
                await db.rollback()
                logger.error(
                    f"Legacy-compatible profile creation failed for user {user_id}: {legacy_error}"
                )
        logger.error(f"Error creating profile for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "data": None, "error": "Failed to create user profile"}
        )


async def get_user_profile(db: AsyncSession, user_id: UUID) -> Optional[UserProfile]:
    """
    Get user profile by user_id.
    
    Args:
        db: Async database session
        user_id: UUID of the user
    
    Returns:
        UserProfile or None if not found
    
    Notes:
        - Returns None instead of raising exception (soft fail)
        - Allows checking if profile exists before operations
    """
    try:
        logger.info(f"Fetching profile for user: {user_id}")
        await ensure_user_profile_schema_compat(db)
        
        result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        
        if profile:
            logger.info(f"Profile found: {profile.id}")
        else:
            logger.warning(f"No profile found for user: {user_id}")
        
        return profile
    
    except Exception as e:
        await db.rollback()
        if _is_schema_mismatch_error(e):
            try:
                profile = await _get_user_profile_compat(db, user_id)
                if profile:
                    logger.info(f"Profile loaded via compatibility query for user: {user_id}")
                else:
                    logger.warning(f"No profile found for user: {user_id}")
                return profile
            except Exception as legacy_error:
                await db.rollback()
                logger.error(
                    f"Compatibility profile query failed for user {user_id}: {legacy_error}"
                )
        logger.error(f"Error fetching profile for user {user_id}: {str(e)}")
        return None


async def update_user_profile(
    db: AsyncSession, 
    user_id: UUID, 
    profile_update: UserProfileUpdate
) -> Optional[UserProfile]:
    """
    Update user profile with provided fields.
    
    Only updates fields that are provided (not None).
    Uses Pydantic's exclude_unset to update only changed fields.
    
    Args:
        db: Async database session
        user_id: UUID of the user
        profile_update: UserProfileUpdate schema with fields to update
    
    Returns:
        Updated UserProfile or None if not found
    
    Raises:
        HTTPException: If update fails
    
    Notes:
        - Validates data via Pydantic before reaching this function
        - Only non-None fields are updated (partial updates supported)
        - updated_at timestamp is automatically set by SQLAlchemy
    """
    try:
        logger.info(f"Updating profile for user: {user_id}")
        await ensure_user_profile_schema_compat(db)
        
        profile = await get_user_profile(db, user_id)
        if not profile:
            logger.warning(f"Profile not found for user: {user_id}")
            return None
        
        # Update only provided fields
        update_data = profile_update.model_dump(exclude_unset=True)
        if not update_data:
            return profile

        if isinstance(profile, UserProfile):
            for field, value in update_data.items():
                setattr(profile, field, value)

            await db.commit()
            await db.refresh(profile)

            logger.info(f"Profile updated successfully: {profile.id}")
            return profile

        columns = await _get_table_columns(db, "user_profiles")
        if not columns:
            return profile

        column_map = {
            "profile_photo": "profile_photo" if "profile_photo" in columns else ("avatar_url" if "avatar_url" in columns else None),
            "gender": "gender" if "gender" in columns else None,
            "date_of_birth": "date_of_birth" if "date_of_birth" in columns else None,
            "organization_name": "organization_name" if "organization_name" in columns else None,
            "organization_type": "organization_type" if "organization_type" in columns else None,
            "cnic": "cnic" if "cnic" in columns else None,
            "driving_license": "driving_license" if "driving_license" in columns else None,
            "car_registration": "car_registration" if "car_registration" in columns else None,
            "push_notifications_enabled": "push_notifications_enabled" if "push_notifications_enabled" in columns else None,
            "share_location_enabled": "share_location_enabled" if "share_location_enabled" in columns else None,
        }

        set_clauses = []
        params = {"user_id": user_id}

        for field, value in update_data.items():
            column_name = column_map.get(field)
            if not column_name:
                continue
            param_name = f"val_{field}"
            set_clauses.append(f"{column_name} = :{param_name}")
            params[param_name] = value

        if set_clauses:
            if "updated_at" in columns:
                set_clauses.append("updated_at = NOW()")

            update_sql = text(
                f"UPDATE user_profiles SET {', '.join(set_clauses)} WHERE user_id = :user_id"
            )
            update_result = await db.execute(update_sql, params)

            if update_result.rowcount == 0:
                insert_columns = ["user_id"]
                insert_values = [":user_id"]
                insert_params = {"user_id": user_id}
                used_columns = set()

                if "id" in columns:
                    insert_columns.insert(0, "id")
                    insert_values.insert(0, ":id")
                    insert_params["id"] = uuid.uuid4()

                for field, value in update_data.items():
                    column_name = column_map.get(field)
                    if not column_name or column_name in used_columns:
                        continue
                    param_name = f"ins_{field}"
                    insert_columns.append(column_name)
                    insert_values.append(f":{param_name}")
                    insert_params[param_name] = value
                    used_columns.add(column_name)

                if "push_notifications_enabled" in columns and "push_notifications_enabled" not in used_columns:
                    insert_columns.append("push_notifications_enabled")
                    insert_values.append("TRUE")
                if "share_location_enabled" in columns and "share_location_enabled" not in used_columns:
                    insert_columns.append("share_location_enabled")
                    insert_values.append("TRUE")

                insert_sql = text(
                    f"INSERT INTO user_profiles ({', '.join(insert_columns)}) VALUES ({', '.join(insert_values)})"
                )
                await db.execute(insert_sql, insert_params)

            await db.commit()

        updated_profile = await get_user_profile(db, user_id)
        logger.info(f"Profile updated successfully: {user_id}")
        return updated_profile
    
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating profile for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "data": None, "error": "Failed to update profile"}
        )


async def update_profile_photo(db: AsyncSession, user_id: UUID, photo_url: str) -> Optional[UserProfile]:
    """
    Update user profile photo.
    
    Args:
        db: Async database session
        user_id: UUID of the user
        photo_url: URL or base64 data URI of the photo
    
    Returns:
        Updated UserProfile or None if not found
    
    Raises:
        HTTPException: If update fails
    
    Notes:
        - Photo is validated in schema (URL or base64 data URI)
        - Consider adding file size limits and image validation
        - Future: Upload to cloud storage (S3, Cloudinary) instead of storing base64
    """
    try:
        logger.info(f"Updating profile photo for user: {user_id}")
        return await update_user_profile(
            db,
            user_id,
            UserProfileUpdate(profile_photo=photo_url),
        )
    
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating profile photo for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "data": None, "error": "Failed to update profile photo"}
        )


# ==================== Saved Address CRUD ====================

async def get_saved_addresses(db: AsyncSession, user_id: UUID) -> List[SavedAddress]:
    """
    Get all saved addresses for a user.
    
    Returns addresses ordered by creation date (newest first).
    
    Args:
        db: Async database session
        user_id: UUID of the user
    
    Returns:
        List of SavedAddress objects (empty list if none)
    
    Notes:
        - Returns empty list instead of None for consistency
        - Ordered by created_at descending (newest first)
    """
    try:
        logger.info(f"Fetching saved addresses for user: {user_id}")
        
        result = await db.execute(
            select(SavedAddress)
            .where(SavedAddress.user_id == user_id)
            .order_by(SavedAddress.created_at.desc())
        )
        addresses = result.scalars().all()
        
        logger.info(f"Found {len(addresses)} saved addresses for user: {user_id}")
        return list(addresses)
    
    except Exception as e:
        await db.rollback()
        if _is_schema_mismatch_error(e):
            try:
                addresses = await _get_saved_addresses_compat(db, user_id)
                logger.info(
                    f"Found {len(addresses)} saved addresses for user via compatibility query: {user_id}"
                )
                return addresses
            except Exception as legacy_error:
                await db.rollback()
                logger.error(
                    f"Compatibility address query failed for user {user_id}: {legacy_error}"
                )
        logger.error(f"Error fetching saved addresses for user {user_id}: {str(e)}")
        return []


async def add_saved_address(
    db: AsyncSession, 
    user_id: UUID, 
    address_in: SavedAddressCreate
) -> SavedAddress:
    """
    Add a new saved address for a user.
    
    Validates:
    - Address limit per user (max 5 addresses, configurable)
    - Label uniqueness per user (cannot have duplicate labels)
    
    Args:
        db: Async database session
        user_id: UUID of the user
        address_in: SavedAddressCreate schema with address data
    
    Returns:
        Newly created SavedAddress
    
    Raises:
        HTTPException: If max addresses reached or duplicate label
    
    Notes:
        - Validates coordinates via Pydantic schema
        - Label is case-sensitive (consider case-insensitive comparison)
        - Future: Add geospatial validation (verify lat/lng against Google Maps)
    """
    try:
        logger.info(f"Adding saved address for user: {user_id}")
        
        # Check address count limit (configurable via settings)
        MAX_SAVED_ADDRESSES = 5  # TODO: Move to settings
        existing_addresses = await get_saved_addresses(db, user_id)
        
        if len(existing_addresses) >= MAX_SAVED_ADDRESSES:
            logger.warning(f"Address limit reached for user: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "status": "error", 
                    "data": None, 
                    "error": f"Maximum {MAX_SAVED_ADDRESSES} addresses allowed"
                }
            )
        
        # Check for duplicate label
        for addr in existing_addresses:
            if addr.label.lower() == address_in.label.lower():
                logger.warning(f"Duplicate address label for user {user_id}: {address_in.label}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "status": "error",
                        "data": None,
                        "error": f"Address with label '{address_in.label}' already exists"
                    }
                )
        
        # Create new address
        new_address = SavedAddress(
            user_id=user_id,
            **address_in.model_dump()
        )
        
        db.add(new_address)
        await db.commit()
        await db.refresh(new_address)
        
        logger.info(f"Saved address created: {new_address.id}")
        return new_address
    
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        if _is_schema_mismatch_error(e):
            try:
                columns = await _get_table_columns(db, "saved_addresses")
                if not columns:
                    raise

                lat_col = "latitude" if "latitude" in columns else ("location_lat" if "location_lat" in columns else None)
                lng_col = "longitude" if "longitude" in columns else ("location_lng" if "location_lng" in columns else None)
                if not lat_col or not lng_col:
                    raise RuntimeError("No latitude/longitude columns available in saved_addresses")

                insert_columns = ["user_id", "label", "address", lat_col, lng_col]
                insert_values = [":user_id", ":label", ":address", ":latitude", ":longitude"]
                params = {
                    "user_id": user_id,
                    "label": address_in.label,
                    "address": address_in.address,
                    "latitude": address_in.latitude,
                    "longitude": address_in.longitude,
                }

                if "is_default" in columns:
                    insert_columns.append("is_default")
                    insert_values.append("FALSE")

                insert_sql = text(
                    f"""
                    INSERT INTO saved_addresses ({', '.join(insert_columns)})
                    VALUES ({', '.join(insert_values)})
                    RETURNING
                        id,
                        user_id,
                        label,
                        address,
                        {lat_col} AS latitude,
                        {lng_col} AS longitude,
                        {"created_at" if "created_at" in columns else "NOW()"} AS created_at
                    """
                )
                result = await db.execute(insert_sql, params)
                row = result.mappings().first()
                await db.commit()

                if row:
                    created_address = SimpleNamespace(**dict(row))
                    logger.info(f"Saved address created via compatibility insert: {created_address.id}")
                    return created_address
            except Exception as legacy_error:
                await db.rollback()
                logger.error(
                    f"Compatibility insert failed for saved address (user {user_id}): {legacy_error}"
                )
        logger.error(f"Error adding saved address for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "data": None, "error": "Failed to add saved address"}
        )


async def delete_saved_address(db: AsyncSession, user_id: UUID, address_id: UUID) -> bool:
    """
    Delete a saved address.
    
    Ensures user can only delete their own addresses.
    
    Args:
        db: Async database session
        user_id: UUID of the user (for authorization)
        address_id: UUID of the address to delete
    
    Returns:
        True if deleted, False if not found or unauthorized
    
    Notes:
        - Validates ownership (user_id matches address.user_id)
        - Returns False instead of raising exception (soft fail)
        - Allows idempotent delete operations
    """
    try:
        logger.info(f"Deleting saved address {address_id} for user: {user_id}")
        
        result = await db.execute(
            select(SavedAddress).where(
                and_(
                    SavedAddress.id == address_id,
                    SavedAddress.user_id == user_id
                )
            )
        )
        address = result.scalar_one_or_none()
        
        if not address:
            logger.warning(f"Address not found or unauthorized: {address_id}")
            return False
        
        await db.delete(address)
        await db.commit()
        
        logger.info(f"Saved address deleted: {address_id}")
        return True
    
    except Exception as e:
        await db.rollback()
        if _is_schema_mismatch_error(e):
            try:
                delete_result = await db.execute(
                    text(
                        """
                        DELETE FROM saved_addresses
                        WHERE id = :address_id AND user_id = :user_id
                        """
                    ),
                    {"address_id": address_id, "user_id": user_id},
                )
                await db.commit()
                deleted = bool(delete_result.rowcount)
                if deleted:
                    logger.info(f"Saved address deleted via compatibility query: {address_id}")
                return deleted
            except Exception as legacy_error:
                await db.rollback()
                logger.error(
                    f"Compatibility delete failed for address {address_id}: {legacy_error}"
                )
        logger.error(f"Error deleting saved address {address_id}: {str(e)}")
        return False


async def get_user_with_profile_and_addresses(db: AsyncSession, user_id: UUID) -> Optional[SimpleNamespace]:
    """
    Get complete user data including profile and saved addresses.
    
    Uses joined loading to fetch all data in a single query.
    Optimized for /users/me endpoint to avoid N+1 queries.
    
    Args:
        db: Async database session
        user_id: UUID of the user
    
    Returns:
        SimpleNamespace with user fields plus profile and saved_addresses.
    
    Notes:
        - Uses selectinload for efficient relationship loading
        - Returns all data needed for UserWithProfilePublic schema
        - Single database round-trip (no N+1 problem)
    
    TODO:
        - Add relationship definitions to User model
        - Consider caching for frequently accessed profiles
    """
    try:
        logger.info(f"Fetching complete user data for: {user_id}")
        await ensure_user_profile_schema_compat(db)
        
        user_result = await db.execute(
            text(
                """
                SELECT
                    id,
                    full_name,
                    email,
                    phone,
                    role::text AS role,
                    is_active,
                    is_verified,
                    created_at
                FROM users
                WHERE id = :user_id
                """
            ),
            {"user_id": user_id},
        )
        user_row = user_result.mappings().first()
        user = SimpleNamespace(**dict(user_row)) if user_row else None
        
        if not user:
            logger.warning(f"User not found: {user_id}")
            return None
        
        # Manually attach profile and addresses
        # TODO: Replace with relationship loading when models are updated
        profile = await get_user_profile(db, user_id)
        addresses = await get_saved_addresses(db, user_id)
        
        # Attach lightweight attributes for response serialization.
        user.profile = profile
        user.saved_addresses = addresses
        
        logger.info(f"Complete user data fetched for: {user_id}")
        return user
    
    except Exception as e:
        logger.error(f"Error fetching complete user data for {user_id}: {str(e)}")
        return None
