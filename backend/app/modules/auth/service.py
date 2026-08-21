"""
Module: Authentication Service

Purpose: Business logic layer for Firebase-based authentication operations.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: February 14, 2026
Notes: Uses Firebase Admin SDK for token verification.
       Handles user registration, login, token refresh, and session management.
       AUTO-CREATES user profile on registration.
"""

from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth import crud
from app.modules.auth.schemas import UserCreate, UserPublic
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token_type,
)
from app.core.config import settings
from app.core.firebase_admin import verify_firebase_token, initialize_firebase

# Import users CRUD for profile auto-creation
from app.modules.users import crud as users_crud
# Import payments CRUD for wallet auto-creation
from app.modules.payments import crud as payments_crud

import logging

logger = logging.getLogger(__name__)

# Initialize Firebase on module import
initialize_firebase()


async def register_user(db: AsyncSession, user_in: UserCreate) -> dict:
    """
    Register a new user using Firebase authentication.
    
    Flow:
    1. Verify Firebase ID token
    2. Extract user info from token (email, uid)
    3. Create user in PostgreSQL database
    4. Auto-create user profile and wallet
    5. Return JWT tokens for backend API access
    """
    try:
        logger.info(f"🔥 Registration attempt with Firebase token")
        
        # 1. Verify Firebase ID token
        try:
            firebase_user = await verify_firebase_token(user_in.firebase_id_token)
        except ValueError as e:
            logger.error(f"❌ Firebase token verification failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e)
            )
        
        email = firebase_user["email"]
        firebase_uid = firebase_user["firebase_uid"]
        
        logger.info(f"✅ Firebase token verified for: {email}")
        
        # 2. Create user in database (profile data only — auth via Firebase)
        new_user = await crud.create_user_with_firebase(
            db=db,
            full_name=user_in.full_name,
            email=email,
            firebase_uid=firebase_uid,
            phone=user_in.phone,
            role=user_in.role,
            is_verified=firebase_user.get("email_verified", False)
        )
        
        logger.info(f"✅ User created in database: {new_user.id}")
        
        # ── Extract all values NOW, before profile/wallet creation ──
        # SQLAlchemy back-population from related object creation can trigger
        # synchronous lazy-loads on User relationships, causing MissingGreenlet.
        user_id = new_user.id
        user_email = new_user.email
        user_role_value = new_user.role.value
        user_data = {
            "id": new_user.id,
            "full_name": new_user.full_name,
            "email": new_user.email,
            "phone": new_user.phone,
            "role": new_user.role.value,
            "firebase_uid": new_user.firebase_uid,
            "is_active": new_user.is_active,
            "is_verified": new_user.is_verified,
            "created_at": new_user.created_at,
        }
        
        # 3. Auto-create user profile
        try:
            profile = await users_crud.create_user_profile(db, user_id)
            logger.info(f"✅ User profile auto-created: {profile.id}")
        except Exception as profile_error:
            logger.warning(f"⚠️ Profile auto-creation failed for user {user_id}: {profile_error}")
        
        # 4. Auto-create wallet with balance 0
        try:
            wallet = await payments_crud.create_wallet(db, user_id)
            logger.info(f"✅ Wallet auto-created for user {user_id}")
        except Exception as wallet_error:
            logger.warning(f"⚠️ Wallet auto-creation failed for user {user_id}: {wallet_error}")
        
        # 5. Generate JWT tokens for backend API access (using extracted values)
        access_token = create_access_token(
            data={"sub": str(user_id), "email": user_email, "role": user_role_value}
        )
        refresh_token = create_refresh_token(
            data={"sub": str(user_id), "type": "refresh"}
        )
        
        refresh_expires = datetime.utcnow() + timedelta(
            seconds=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60
        )
        await crud.save_refresh_token(db, user_id, refresh_token, refresh_expires)
        
        logger.info(f"🎉 Registration successful for user: {user_id}")
        
        # Build UserPublic from extracted dict (avoids ORM lazy-load)
        user_public = UserPublic.model_validate(user_data)
        
        return {
            "status": "ok",
            "data": {
                "user": user_public,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            },
            "error": None
        }
        
    except ValueError as e:
        error_msg = str(e)
        logger.error(f"❌ Registration failed: {error_msg}")
        
        # If email already registered but firebase_uid differs, update it and log them in
        if "email already registered" in error_msg.lower():
            try:
                existing_user = await crud.get_user_by_email(db, email)
                if existing_user and existing_user.firebase_uid != firebase_uid:
                    logger.info(f"🔄 Updating firebase_uid for existing user {email}")
                    existing_user.firebase_uid = firebase_uid
                    existing_user.is_verified = firebase_user.get("email_verified", False)
                    if user_in.full_name and user_in.full_name != existing_user.full_name:
                        existing_user.full_name = user_in.full_name
                    if user_in.phone and user_in.phone != existing_user.phone:
                        existing_user.phone = user_in.phone
                    await db.commit()
                    await db.refresh(existing_user)
                    logger.info(f"✅ firebase_uid updated, logging in user {existing_user.id}")
                    return await login_user(db, user_in.firebase_id_token)
            except HTTPException:
                raise
            except Exception as inner_e:
                logger.warning(f"⚠️ Failed to auto-link existing account: {inner_e}")
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    except Exception as e:
        logger.exception(f"❌ Unexpected error during registration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration failed: {type(e).__name__}: {str(e)}"
        )


async def login_user(db: AsyncSession, firebase_id_token: str) -> dict:
    """
    Authenticate user using Firebase token.
    
    Flow:
    1. Verify Firebase ID token
    2. Find user in database by firebase_uid
    3. Check if user is active
    4. Return JWT tokens for backend API access
    """
    try:
        logger.info(f"🔥 Login attempt with Firebase token")
        
        # 1. Verify Firebase ID token
        try:
            firebase_user = await verify_firebase_token(firebase_id_token)
        except ValueError as e:
            logger.error(f"❌ Firebase token verification failed: {e}")
            msg = str(e).lower()
            detail = (
                "Server is missing Firebase Admin credentials (set FCM_CREDENTIALS_PATH or "
                "GOOGLE_APPLICATION_CREDENTIALS to your service account JSON)."
                if "not configured" in msg or "credentials" in msg
                else "Invalid authentication token"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=detail,
            )
        
        firebase_uid = firebase_user["firebase_uid"]
        email = firebase_user["email"]
        
        logger.info(f"✅ Firebase token verified for: {email}")
        
        # 2. Find user in database by firebase_uid
        user = await crud.get_user_by_firebase_uid(db, firebase_uid)
        
        if not user:
            # Fallback: look up by email (handles Firebase account re-creation)
            user = await crud.get_user_by_email(db, email)
            if user:
                # Update the stale firebase_uid to the current one
                logger.info(f"🔄 Updating firebase_uid for {email} (old → new)")
                user.firebase_uid = firebase_uid
                await db.commit()
                await db.refresh(user)
            else:
                logger.warning(f"❌ Login failed: No user found for email {email} or firebase_uid {firebase_uid}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not found. Please register first."
                )
        
        # 3. Check if user is active
        if not user.is_active:
            logger.warning(f"❌ Login failed: Inactive account {user.id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive. Please contact support."
            )
        
        # 4. Generate JWT tokens for backend API access
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email, "role": user.role.value}
        )
        refresh_token = create_refresh_token(
            data={"sub": str(user.id), "type": "refresh"}
        )
        
        refresh_expires = datetime.utcnow() + timedelta(
            seconds=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60
        )
        await crud.save_refresh_token(db, user.id, refresh_token, refresh_expires)
        
        logger.info(f"🎉 Login successful for user: {user.id}")
        
        return {
            "status": "ok",
            "data": {
                "user": UserPublic.from_orm(user),
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            },
            "error": None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Unexpected error during login: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> dict:
    db_token = await crud.get_refresh_token(db, refresh_token)
    
    if not db_token:
        logger.warning("Refresh failed: Token not found or revoked")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    try:
        payload = decode_token(refresh_token)
        verify_token_type(payload, "refresh")
        
        user_id = UUID(payload.get("sub"))
    except Exception:
        logger.warning("Refresh failed: Invalid token payload")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user = await crud.get_user_by_id(db, user_id)
    
    if not user or not user.is_active:
        logger.warning(f"Refresh failed: User {user_id} not found or inactive")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    new_access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )
    
    logger.info(f"Access token refreshed for user: {user.id}")
    
    return {
        "status": "ok",
        "data": {
            "access_token": new_access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        },
        "error": None
    }


async def logout_user(db: AsyncSession, refresh_token: str) -> dict:
    """
    Logout user by revoking refresh token.
    """
    revoked = await crud.revoke_refresh_token(db, refresh_token)
    
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh token not found"
        )
    
    logger.info("✅ User logged out successfully")
    
    return {
        "status": "ok",
        "data": {"message": "Logged out successfully"},
    }

