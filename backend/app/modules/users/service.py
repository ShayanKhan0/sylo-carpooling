"""
Module: Users
Purpose: Business logic layer for user profile and saved address management.
         Orchestrates CRUD operations with validation and business rules.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 7, 2025
Notes: Service layer sits between routers and CRUD layer.
       Enforces business rules like address limits, photo validation, etc.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from uuid import UUID
from typing import Dict, Optional
import logging
import base64
import binascii
import re
from pathlib import Path
from datetime import datetime, timezone

from app.modules.users import crud
from app.modules.drivers import crud as driver_crud
from app.modules.auth import crud as auth_crud
from app.modules.verification.models import DocumentTypeEnum
from app.modules.users.schemas import (
    UserProfileUpdate, 
    SavedAddressCreate,
    UserWithProfilePublic,
    UserProfilePublic,
    SavedAddressPublic
)

logger = logging.getLogger(__name__)


_ALLOWED_PROFILE_IMAGE_EXTENSIONS = {
    "jpeg": "jpg",
    "jpg": "jpg",
    "png": "png",
    "gif": "gif",
    "webp": "webp",
}
_MAX_PROFILE_PHOTO_BYTES = 4 * 1024 * 1024  # 4 MB
_PROFILE_PHOTO_SUBDIR = Path("uploads") / "profile_photos"


def _backend_static_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "static"


def _delete_file_if_exists(file_path: Path) -> None:
    try:
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
    except Exception as exc:
        logger.warning("Failed to delete profile photo file %s: %s", file_path, exc)


def _delete_local_profile_photo_if_any(photo_value: Optional[str]) -> None:
    normalized = str(photo_value or "").strip().replace("\\", "/")
    if not normalized:
        return

    if normalized.startswith("/static/"):
        relative = normalized[len("/static/") :]
    elif normalized.startswith("static/"):
        relative = normalized[len("static/") :]
    else:
        return

    static_root = _backend_static_dir()
    profile_root = (static_root / _PROFILE_PHOTO_SUBDIR).resolve()
    target = (static_root / relative).resolve()

    try:
        if not str(target).startswith(str(profile_root)):
            return
        _delete_file_if_exists(target)
    except Exception as exc:
        logger.warning("Failed to cleanup previous profile photo %s: %s", target, exc)


def _decode_profile_photo_data_uri(photo: str) -> tuple[str, bytes]:
    header, separator, encoded_payload = photo.partition(",")
    if not separator:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "error",
                "data": None,
                "error": "Invalid photo format. Please upload JPG, PNG, GIF, or WEBP.",
            },
        )

    header_lower = header.lower()
    if not header_lower.startswith("data:image/") or ";base64" not in header_lower:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "error",
                "data": None,
                "error": "Invalid photo format. Please upload JPG, PNG, GIF, or WEBP.",
            },
        )

    subtype = header_lower[len("data:image/") :].split(";", 1)[0].strip()
    extension = _ALLOWED_PROFILE_IMAGE_EXTENSIONS.get(subtype)
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "status": "error",
                "data": None,
                "error": "Unsupported photo format. Allowed formats: JPG, PNG, GIF, WEBP.",
            },
        )

    try:
        decoded = base64.b64decode(encoded_payload.strip(), validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "error",
                "data": None,
                "error": "Invalid base64 image payload.",
            },
        )

    if not decoded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "status": "error",
                "data": None,
                "error": "Uploaded photo is empty.",
            },
        )

    if len(decoded) > _MAX_PROFILE_PHOTO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "status": "error",
                "data": None,
                "error": "Photo size exceeds 4MB limit.",
            },
        )

    return extension, decoded


def _persist_profile_photo_file(user_id: UUID, extension: str, content: bytes) -> tuple[Path, str]:
    static_root = _backend_static_dir()
    output_dir = static_root / _PROFILE_PHOTO_SUBDIR
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    file_name = f"{user_id}_{timestamp}.{extension}"
    target_path = output_dir / file_name
    target_path.write_bytes(content)

    relative_public_path = f"/static/{_PROFILE_PHOTO_SUBDIR.as_posix()}/{file_name}"
    return target_path, relative_public_path


def _normalize_text(value: Optional[str]) -> str:
    return (value or "").strip()


async def _get_user_role_text(db: AsyncSession, user_id: UUID) -> str:
    user = await auth_crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "error", "data": None, "error": "User not found"},
        )

    role_value = getattr(user, "role", None)
    if hasattr(role_value, "value"):
        return str(role_value.value).strip().lower()
    return str(role_value or "").strip().lower()


async def _ensure_profile_exists(db: AsyncSession, user_id: UUID):
    """Ensure profile row exists for a user, with a safe retry on concurrent creation."""
    existing_profile = await crud.get_user_profile(db, user_id)
    if existing_profile:
        return existing_profile

    logger.info("Profile missing for user %s; attempting auto-create", user_id)
    create_error: Optional[HTTPException] = None

    try:
        await crud.create_user_profile(db, user_id)
    except HTTPException as exc:
        # Another concurrent request may create the row first; re-check before failing.
        create_error = exc
        logger.warning(
            "Profile auto-create returned an error for user %s: %s",
            user_id,
            exc.detail,
        )

    existing_profile = await crud.get_user_profile(db, user_id)
    if existing_profile:
        return existing_profile

    if create_error:
        raise create_error

    return None


async def get_user_profile_service(db: AsyncSession, user_id: UUID) -> Dict:
    """
    Get complete user data including profile and saved addresses.
    
    Business logic wrapper around CRUD operation.
    Returns standardized response format.
    
    Args:
        db: Async database session
        user_id: UUID of the authenticated user
    
    Returns:
        Standardized response with user, profile, and addresses
    
    Flow:
        1. Fetch user with profile and addresses
        2. Return structured response
    
    Example Response:
        {
            "status": "ok",
            "data": {
                "id": "...",
                "email": "...",
                "profile": {...},
                "saved_addresses": [...]
            },
            "error": null
        }
    """
    try:
        logger.info(f"Fetching profile for user: {user_id}")
        
        user = await crud.get_user_with_profile_and_addresses(db, user_id)
        
        if not user:
            logger.warning(f"User not found: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"status": "error", "data": None, "error": "User not found"}
            )
        
        # Convert to response schema
        # Note: UserWithProfilePublic expects these attributes
        response_data = {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role.value if hasattr(user.role, 'value') else user.role,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "created_at": user.created_at,
            "profile": UserProfilePublic.from_orm(user.profile) if user.profile else None,
            "saved_addresses": [SavedAddressPublic.from_orm(addr) for addr in user.saved_addresses]
        }
        
        return {
            "status": "ok",
            "data": response_data,
            "error": None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching user profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "data": None, "error": "Failed to fetch user profile"}
        )


async def update_user_profile_service(
    db: AsyncSession, 
    user_id: UUID, 
    profile_update: UserProfileUpdate
) -> Dict:
    """
    Update user profile with validation.
    
    Business rules:
    - Students: Can set organization_name and organization_type
    - Drivers: Can set CNIC, driving_license, car_registration
    - All: Can update personal info (gender, DOB, photo)
    
    Args:
        db: Async database session
        user_id: UUID of the authenticated user
        profile_update: UserProfileUpdate schema with fields to update
    
    Returns:
        Standardized response with updated profile
    
    Raises:
        HTTPException: If profile not found or update fails
    """
    try:
        logger.info(f"Updating profile for user: {user_id}")

        incoming_update_data = profile_update.model_dump(exclude_unset=True)
        user_role_text = await _get_user_role_text(db, user_id)

        if user_role_text == "driver" and "profile_photo" in incoming_update_data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "status": "error",
                    "data": None,
                    "error": (
                        "Drivers cannot change profile photo directly. "
                        "Use Profile camera action and complete selfie re-verification."
                    ),
                },
            )

        # Ensure profile exists for legacy users created before profile auto-provision.
        existing_profile = await _ensure_profile_exists(db, user_id)
        previous_cnic = _normalize_text(existing_profile.cnic if existing_profile else None)
        previous_license = _normalize_text(existing_profile.driving_license if existing_profile else None)
        if not existing_profile:
            logger.error("Failed to initialize profile for user %s before update", user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "error",
                    "data": None,
                    "error": "Failed to initialize profile before update",
                },
            )
        
        # Update profile via CRUD
        updated_profile = await crud.update_user_profile(db, user_id, profile_update)
        
        if not updated_profile:
            logger.info(
                "Profile still missing for user %s after update attempt; retrying with auto-create",
                user_id,
            )
            ensured_profile = await _ensure_profile_exists(db, user_id)
            if ensured_profile:
                updated_profile = await crud.update_user_profile(db, user_id, profile_update)

        if not updated_profile:
            logger.error("Failed to initialize profile for user %s during update", user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "error",
                    "data": None,
                    "error": "Failed to initialize profile before update",
                },
            )

        cnic_changed = False
        license_changed = False

        if 'cnic' in incoming_update_data:
            cnic_changed = _normalize_text(updated_profile.cnic) != previous_cnic
        if 'driving_license' in incoming_update_data:
            license_changed = _normalize_text(updated_profile.driving_license) != previous_license

        if cnic_changed or license_changed:
            try:
                doc_types = []
                if cnic_changed:
                    doc_types.append(DocumentTypeEnum.CNIC)
                if license_changed:
                    doc_types.append(DocumentTypeEnum.DRIVING_LICENSE)

                # When identity fields change, remove only the affected uploaded
                # verification documents so users must re-upload those images.
                from app.modules.verification import service as verification_service

                deleted_documents = []
                for doc_type in doc_types:
                    delete_result = await verification_service.delete_uploaded_document_service(
                        db=db,
                        user_id=user_id,
                        doc_type=doc_type,
                    )

                    payload = delete_result.get("data") if isinstance(delete_result, dict) else {}
                    deleted_documents.append(
                        {
                            "doc_type": doc_type.value,
                            "deleted": bool((payload or {}).get("deleted", False)),
                            "deleted_count": int((payload or {}).get("deleted_count") or 0),
                        }
                    )

                await driver_crud.sync_identity_after_profile_update(
                    db=db,
                    user_id=user_id,
                    cnic_number=updated_profile.cnic,
                    license_number=updated_profile.driving_license,
                    cnic_changed=cnic_changed,
                    license_changed=license_changed,
                )

                logger.info(
                    "Profile identity changed for user %s (cnic=%s, license=%s, deleted=%s)",
                    user_id,
                    cnic_changed,
                    license_changed,
                    deleted_documents,
                )
            except Exception as sync_error:
                logger.error(
                    "Post-update verification sync failed for user %s: %s",
                    user_id,
                    str(sync_error),
                )
        
        return {
            "status": "ok",
            "data": UserProfilePublic.from_orm(updated_profile).dict(),
            "error": None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "data": None, "error": "Failed to update profile"}
        )


async def upload_profile_photo_service(db: AsyncSession, user_id: UUID, photo: str) -> Dict:
    """
    Upload or update user profile photo.
    
    Validation:
    - Photo can be URL or base64 data URI
    - Base64 image uploads are decoded and saved as local static files
    - Supported image formats: JPG, PNG, GIF, WEBP
    - Maximum decoded image size: 4 MB
    
    Args:
        db: Async database session
        user_id: UUID of the authenticated user
        photo: URL or base64 data URI
    
    Returns:
        Standardized response with updated profile
    
    Notes:
        - Photo validation happens in Pydantic schema
        - Consider adding image format validation (JPEG, PNG only)
        - Consider adding virus scanning for uploaded files
    """
    try:
        logger.info(f"Uploading profile photo for user: {user_id}")
        user_role_text = await _get_user_role_text(db, user_id)

        if user_role_text == "driver":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "status": "error",
                    "data": None,
                    "error": (
                        "Drivers cannot change profile photo directly. "
                        "Use Profile camera action and complete selfie re-verification."
                    ),
                },
            )
        
        incoming_photo = (photo or "").strip()
        if not incoming_photo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "status": "error",
                    "data": None,
                    "error": "Photo cannot be empty.",
                },
            )

        previous_profile = await _ensure_profile_exists(db, user_id)
        if not previous_profile:
            logger.error("Failed to initialize profile for user %s before photo upload", user_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "error",
                    "data": None,
                    "error": "Failed to initialize profile before photo upload",
                },
            )
        previous_photo = str(getattr(previous_profile, "profile_photo", "") or "").strip()

        stored_photo = incoming_photo
        created_file_path: Optional[Path] = None

        if incoming_photo.startswith("data:image/"):
            extension, content = _decode_profile_photo_data_uri(incoming_photo)
            created_file_path, stored_photo = _persist_profile_photo_file(
                user_id=user_id,
                extension=extension,
                content=content,
            )

        try:
            updated_profile = await crud.update_profile_photo(db, user_id, stored_photo)
        except Exception:
            if created_file_path is not None:
                _delete_file_if_exists(created_file_path)
            raise
        
        if not updated_profile:
            logger.info(
                "Profile still missing for user %s after upload attempt; retrying with auto-create",
                user_id,
            )
            ensured_profile = await _ensure_profile_exists(db, user_id)
            if ensured_profile:
                updated_profile = await crud.update_profile_photo(db, user_id, stored_photo)

        if not updated_profile:
            if created_file_path is not None:
                _delete_file_if_exists(created_file_path)
            logger.error(
                "Failed to initialize profile for user %s during photo upload",
                user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "status": "error",
                    "data": None,
                    "error": "Failed to initialize profile before photo upload",
                },
            )

        if stored_photo != previous_photo:
            _delete_local_profile_photo_if_any(previous_photo)
        
        return {
            "status": "ok",
            "data": UserProfilePublic.from_orm(updated_profile).dict(),
            "error": None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading profile photo: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "data": None, "error": "Failed to upload photo"}
        )


async def get_saved_addresses_service(db: AsyncSession, user_id: UUID) -> Dict:
    """
    Get all saved addresses for a user.
    
    Args:
        db: Async database session
        user_id: UUID of the authenticated user
    
    Returns:
        Standardized response with list of addresses
    """
    try:
        logger.info(f"Fetching saved addresses for user: {user_id}")
        
        addresses = await crud.get_saved_addresses(db, user_id)
        
        return {
            "status": "ok",
            "data": [SavedAddressPublic.from_orm(addr).dict() for addr in addresses],
            "error": None
        }
    
    except Exception as e:
        logger.error(f"Error fetching saved addresses: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "data": None, "error": "Failed to fetch saved addresses"}
        )


async def add_saved_address_service(
    db: AsyncSession, 
    user_id: UUID, 
    address_in: SavedAddressCreate
) -> Dict:
    """
    Add a new saved address with validation.
    
    Business rules:
    - Maximum 5 addresses per user (configurable)
    - Label must be unique per user
    - Coordinates must be valid (validated in schema)
    
    Future enhancements:
    - Verify address against Google Maps API
    - Auto-complete address from coordinates
    - Suggest nearby saved addresses to avoid duplicates
    
    Args:
        db: Async database session
        user_id: UUID of the authenticated user
        address_in: SavedAddressCreate schema with address data
    
    Returns:
        Standardized response with created address
    
    Raises:
        HTTPException: If limit reached or duplicate label
    """
    try:
        logger.info(f"Adding saved address for user: {user_id}")
        
        new_address = await crud.add_saved_address(db, user_id, address_in)
        
        return {
            "status": "ok",
            "data": SavedAddressPublic.from_orm(new_address).dict(),
            "error": None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding saved address: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "data": None, "error": "Failed to add saved address"}
        )


async def delete_saved_address_service(
    db: AsyncSession, 
    user_id: UUID, 
    address_id: UUID
) -> Dict:
    """
    Delete a saved address.
    
    Validates user owns the address before deletion.
    
    Args:
        db: Async database session
        user_id: UUID of the authenticated user
        address_id: UUID of the address to delete
    
    Returns:
        Standardized success message
    
    Raises:
        HTTPException: If address not found or unauthorized
    """
    try:
        logger.info(f"Deleting saved address {address_id} for user: {user_id}")
        
        success = await crud.delete_saved_address(db, user_id, address_id)
        
        if not success:
            logger.warning(f"Address not found or unauthorized: {address_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "status": "error",
                    "data": None,
                    "error": "Address not found or unauthorized"
                }
            )
        
        return {
            "status": "ok",
            "data": {"message": "Address deleted successfully"},
            "error": None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting saved address: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "data": None, "error": "Failed to delete address"}
        )
