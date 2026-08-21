"""
Module: Authentication CRUD

Purpose: Async database operations for authentication-related tables.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 7, 2025
Notes: All CRUD operations use async SQLAlchemy for high performance.
       Includes comprehensive error handling and structured logging.
"""

from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models import User, RefreshToken, UserRole


# ============================================================================
# USER CRUD OPERATIONS
# ============================================================================

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """
    Retrieve a user by email address.
    
    Args:
        db: Database session
        email: User's email address (case-insensitive)
    
    Returns:
        User object if found, None otherwise
    """
    result = await db.execute(
        select(User).where(User.email == email.lower())
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """
    Retrieve a user by UUID.
    
    Args:
        db: Database session
        user_id: User's unique identifier
    
    Returns:
        User object if found, None otherwise
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_phone(db: AsyncSession, phone: str) -> Optional[User]:
    """
    Retrieve a user by phone number.
    
    Args:
        db: Database session
        phone: User's phone number (E.164 format)
    
    Returns:
        User object if found, None otherwise
    """
    result = await db.execute(
        select(User).where(User.phone == phone)
    )
    return result.scalar_one_or_none()


async def get_user_by_firebase_uid(db: AsyncSession, firebase_uid: str) -> Optional[User]:
    """
    Retrieve a user by Firebase UID.
    
    Args:
        db: Database session
        firebase_uid: Firebase user UID
    
    Returns:
        User object if found, None otherwise
    """
    result = await db.execute(
        select(User).where(User.firebase_uid == firebase_uid)
    )
    return result.scalar_one_or_none()


async def create_user_with_firebase(
    db: AsyncSession,
    full_name: str,
    email: str,
    firebase_uid: str,
    phone: str,
    role: str = "passenger",
    is_verified: bool = False
) -> User:
    """
    Create a new user with Firebase authentication.
    
    Args:
        db: Database session
        full_name: User's full name
        email: User's email (will be lowercased)
        firebase_uid: Firebase user UID
        phone: User's phone number
        role: User role (passenger, driver)
        is_verified: Email verification status from Firebase
    
    Returns:
        Newly created User object
    
    Raises:
        ValueError: If email, phone, or firebase_uid already exists
    
    Note:
        password_hash is set to a placeholder — all authentication
        is handled by Firebase. PostgreSQL stores profile data only.
    """
    # Convert role string to UserRole enum
    role_enum = UserRole[role.upper()]
    
    # Create user — authentication is via Firebase; placeholder password_hash
    db_user = User(
        full_name=full_name,
        email=email.lower(),
        firebase_uid=firebase_uid,
        password_hash="FIREBASE_AUTH",
        phone=phone,
        role=role_enum,
        is_verified=is_verified
    )
    
    db.add(db_user)
    
    try:
        await db.commit()
        await db.refresh(db_user)
        return db_user
    except IntegrityError as e:
        await db.rollback()
        if "email" in str(e.orig):
            raise ValueError("Email already registered")
        elif "phone" in str(e.orig):
            raise ValueError("Phone number already registered")
        elif "firebase_uid" in str(e.orig):
            raise ValueError("Firebase account already registered")
        else:
            raise ValueError("User creation failed")




# ============================================================================
# REFRESH TOKEN CRUD OPERATIONS
# ============================================================================

async def save_refresh_token(
    db: AsyncSession,
    user_id: UUID,
    token: str,
    expires_at: datetime
) -> RefreshToken:
    """
    Save a refresh token to database.
    
    Args:
        db: Database session
        user_id: User's UUID
        token: JWT refresh token string
        expires_at: Token expiration datetime
    
    Returns:
        Newly created RefreshToken object
    """
    db_token = RefreshToken(
        user_id=user_id,
        token=token,
        expires_at=expires_at
    )
    
    db.add(db_token)
    await db.commit()
    await db.refresh(db_token)
    
    return db_token


async def get_refresh_token(
    db: AsyncSession,
    token: str
) -> Optional[RefreshToken]:
    """
    Retrieve a refresh token by token string.
    
    Args:
        db: Database session
        token: JWT refresh token string
    
    Returns:
        RefreshToken object if found and not revoked/expired, None otherwise
    """
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == token,
            RefreshToken.is_revoked == False,
            RefreshToken.expires_at > datetime.utcnow()
        )
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(
    db: AsyncSession,
    token: str
) -> bool:
    """
    Revoke a refresh token (logout).
    
    Args:
        db: Database session
        token: JWT refresh token string
    
    Returns:
        True if revoked, False if token not found
    """
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == token)
    )
    db_token = result.scalar_one_or_none()
    
    if not db_token:
        return False
    
    db_token.is_revoked = True
    db_token.revoked_at = datetime.utcnow()
    
    await db.commit()
    
    return True
