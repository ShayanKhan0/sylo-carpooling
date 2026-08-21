"""
Admin Authentication Security Utilities (Prompt 12A)

Provides admin-only JWT handling and access control.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import ipaddress

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.config import settings
from app.db.session import get_db
from app.modules.auth import crud as auth_crud
from app.modules.auth.models import User, UserRole

admin_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/auth/login")


def create_admin_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create admin-only access token.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "admin_access", "aud": "admin"})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_admin_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            audience="admin",
        )
    except JWTError:
        return None


def _is_ip_allowed(client_ip: str) -> bool:
    if not settings.ADMIN_IP_ALLOWLIST:
        return False

    try:
        ip_obj = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    for entry in settings.ADMIN_IP_ALLOWLIST:
        try:
            if "/" in entry:
                if ip_obj in ipaddress.ip_network(entry, strict=False):
                    return True
            else:
                if ip_obj == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            continue

    return False


async def require_admin_ip_allowlist(request: Request) -> None:
    """
    Enforce admin IP allowlist for sensitive actions.
    """
    client_ip = request.client.host if request.client else ""
    if not _is_ip_allowed(client_ip):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin action not allowed from this IP"
        )


async def require_admin(
    token: str = Depends(admin_oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Require a valid admin token and admin role.
    """
    payload = decode_admin_token(token)
    if not payload or payload.get("type") != "admin_access" or payload.get("aud") != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        user_id = UUID(payload.get("sub"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token payload",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user = await auth_crud.get_user_by_id(db, user_id)
    if not user or user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin account is inactive"
        )

    return user
