"""
Purpose: Security utilities for authentication and authorization.
         Includes JWT token handling, password hashing, and verification.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 7, 2025
Notes: Uses industry-standard libraries (passlib, python-jose) for security.
       All passwords are hashed using bcrypt with proper salting.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token with user data.

    Args:
        data: Dictionary containing user data (user_id, email, role)
        expires_delta: Optional custom expiration time (default: 15 minutes)

    Returns:
        Encoded JWT token as string

    JWT Structure:
        {
            "sub": user_id (UUID string),
            "email": user_email,
            "role": user_role,
            "type": "access",
            "exp": expiry_timestamp
        }

    Example:
        >>> token_data = {"sub": str(user.id), "email": user.email, "role": user.role}
        >>> token = create_access_token(data=token_data)
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(
    data: Dict[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT refresh token for long-term authentication.

    Args:
        data: Dictionary containing user data (user_id, email, role)
        expires_delta: Optional custom expiration time (default: 7 days)

    Returns:
        Encoded JWT refresh token as string

    JWT Structure:
        {
            "sub": user_id (UUID string),
            "email": user_email,
            "role": user_role,
            "type": "refresh",
            "exp": expiry_timestamp
        }

    Notes:
        Refresh tokens have longer expiration times (7 days default) and are used
        to obtain new access tokens without re-authentication.
        These tokens must be stored in the database for revocation support.
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string to decode

    Returns:
        Dictionary containing token payload if valid, None otherwise

    Example:
        >>> payload = decode_token(token)
        >>> if payload:
        >>>     user_id = payload.get("sub")
    """
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a hashed password.

    Args:
        plain_password: The plain text password to verify
        hashed_password: The hashed password to compare against

    Returns:
        True if password matches, False otherwise

    Example:
        >>> is_valid = verify_password("user_password", stored_hash)
        >>> if is_valid:
        >>>     # Password is correct
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash a plain password using bcrypt.

    Args:
        password: Plain text password to hash

    Returns:
        Hashed password string

    Example:
        >>> hashed = get_password_hash("my_secure_password")
        >>> # Returns: "$2b$12$KIXxKj5..."
    """
    return pwd_context.hash(password)


def generate_verification_token() -> str:
    """
    Generate a random verification token for email/phone verification.

    Returns:
        Random verification token string

    Notes:
        This is used for email verification, password reset, etc.
        Token should be stored in database and expire after set time.
    """
    import secrets

    return secrets.token_urlsafe(32)


def verify_token_type(token_or_payload: Union[str, Dict[str, Any]], expected_type: str) -> bool:
    """
    Verify that a token is of the expected type (access or refresh).

    Args:
        token_or_payload: JWT token string or decoded payload
        expected_type: Expected token type ("access" or "refresh")

    Returns:
        True if token type matches expected type, False otherwise
    """
    if isinstance(token_or_payload, dict):
        payload = token_or_payload
    else:
        payload = decode_token(token_or_payload)

    if not payload:
        return False

    token_type = payload.get("type")
    return token_type == expected_type
