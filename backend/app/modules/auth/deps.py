"""
Module: Authentication Dependencies

Purpose: Reusable FastAPI dependencies for authentication and authorization.
         Provides role-based access control (RBAC) guards for protecting routes.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: December 3, 2025
Notes: These dependencies can be used with FastAPI's Depends() for route protection.
"""

from typing import List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db.session import get_db
from app.modules.auth.models import User, UserRole
from app.modules.auth import crud
from app.core.security import decode_token, verify_token_type
from app.core.config import settings

# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ============================================================================
# BASE AUTHENTICATION DEPENDENCY
# ============================================================================

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Extract and validate current user from JWT token.
    
    Args:
        token: JWT token from Authorization header
        db: Database session
    
    Returns:
        User object if token valid
    
    Raises:
        HTTPException 401: Invalid token or user not found
        HTTPException 403: User account inactive
    
    Usage:
        @router.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"user_id": user.id}
    """
    try:
        payload = decode_token(token)
        verify_token_type(payload, "access")
        
        user_id = UUID(payload.get("sub"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user = await crud.get_user_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    return user


# ============================================================================
# BASIC AUTHENTICATION DEPENDENCIES
# ============================================================================

async def require_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Require that the current user is active (not disabled).
    
    Args:
        current_user: Authenticated user from JWT token
    
    Returns:
        User object if active
    
    Raises:
        HTTPException 403: If user is inactive
    
    Usage:
        @router.get("/protected")
        async def protected_route(user: User = Depends(require_active_user)):
            return {"user_id": user.id}
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact support."
        )
    return current_user


async def require_verified_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Require that the current user has verified their email.
    
    Args:
        current_user: Authenticated user from JWT token
    
    Returns:
        User object if verified
    
    Raises:
        HTTPException 403: If user email not verified
    
    Usage:
        @router.post("/post-ride")
        async def post_ride(user: User = Depends(require_verified_user)):
            # Only verified users can post rides
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email address to access this feature."
        )
    return current_user


# ============================================================================
# ROLE-BASED ACCESS CONTROL (RBAC) DEPENDENCIES
# ============================================================================

async def require_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Require that the current user has ADMIN role.
    
    Args:
        current_user: Authenticated user from JWT token
    
    Returns:
        User object if admin
    
    Raises:
        HTTPException 403: If user is not an admin
    
    Usage:
        @router.get("/admin/dashboard")
        async def admin_dashboard(admin: User = Depends(require_admin)):
            return {"admin_data": ...}
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required to access this resource."
        )
    return current_user


async def require_driver(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Require that the current user has DRIVER role.
    
    Args:
        current_user: Authenticated user from JWT token
    
    Returns:
        User object if driver
    
    Raises:
        HTTPException 403: If user is not a driver
    
    Usage:
        @router.post("/rides/offer")
        async def offer_ride(driver: User = Depends(require_driver)):
            # Only drivers can offer rides
    """
    if current_user.role != UserRole.DRIVER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Driver account required to access this resource."
        )
    return current_user


async def require_passenger(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Require that the current user has PASSENGER role.
    
    Args:
        current_user: Authenticated user from JWT token
    
    Returns:
        User object if passenger
    
    Raises:
        HTTPException 403: If user is not a passenger
    
    Usage:
        @router.post("/rides/request")
        async def request_ride(passenger: User = Depends(require_passenger)):
            # Only passengers can request rides
    
    Note:
        STUDENT is treated as a legacy alias for PASSENGER
    """
    if current_user.role not in (UserRole.PASSENGER, UserRole.STUDENT):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Passenger account required to access this resource."
        )
    return current_user


async def require_organization(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Require that the current user has ORGANIZATION role.
    
    Args:
        current_user: Authenticated user from JWT token
    
    Returns:
        User object if organization
    
    Raises:
        HTTPException 403: If user is not an organization
    
    Usage:
        @router.post("/bulk/users")
        async def bulk_create_users(org: User = Depends(require_organization)):
            # Only organizations can bulk create users
    """
    if current_user.role != UserRole.ORGANIZATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization account required to access this resource."
        )
    return current_user


# ============================================================================
# FLEXIBLE ROLE CHECKING
# ============================================================================

def require_any_role(*allowed_roles: UserRole):
    """
    Create a dependency that requires any of the specified roles.
    
    Args:
        *allowed_roles: One or more UserRole enum values
    
    Returns:
        FastAPI dependency function
    
    Usage:
        from app.modules.auth.models import UserRole
        from app.modules.auth.deps import require_any_role
        
        @router.get("/rides/all")
        async def get_all_rides(
            user: User = Depends(require_any_role(UserRole.DRIVER, UserRole.ADMIN))
        ):
            # Only drivers and admins can access
            return {"rides": ...}
    
    Example with multiple roles:
        require_driver_or_admin = require_any_role(UserRole.DRIVER, UserRole.ADMIN)
        
        @router.get("/analytics")
        async def analytics(user: User = Depends(require_driver_or_admin)):
            return {"data": ...}
    """
    async def _role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            role_names = [role.value for role in allowed_roles]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(role_names)}"
            )
        return current_user
    
    return _role_checker


# ============================================================================
# COMBINED DEPENDENCIES
# ============================================================================

async def require_active_admin(
    current_user: User = Depends(require_admin)
) -> User:
    """
    Require active admin user (combines role + active check).
    
    Usage:
        @router.delete("/users/{user_id}")
        async def delete_user(admin: User = Depends(require_active_admin)):
            # Only active admins can delete users
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your admin account has been deactivated."
        )
    return current_user


async def require_verified_driver(
    current_user: User = Depends(require_driver)
) -> User:
    """
    Require verified driver (combines role + verification check).
    
    Usage:
        @router.post("/rides/accept/{ride_id}")
        async def accept_ride(driver: User = Depends(require_verified_driver)):
            # Only verified drivers can accept rides
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please complete driver verification to accept rides."
        )
    return current_user


# ============================================================================
# CONVENIENCE EXPORTS
# ============================================================================

__all__ = [
    "require_active_user",
    "require_verified_user",
    "require_admin",
    "require_driver",
    "require_passenger",
    "require_organization",
    "require_any_role",
    "require_active_admin",
    "require_verified_driver",
]
