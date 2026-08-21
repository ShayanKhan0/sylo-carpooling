"""
Admin Auth Service (Prompt 12A)

Dedicated admin authentication logic.
"""

import logging
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security.admin_auth import create_admin_access_token
from app.core.security import verify_password
from app.modules.auth import crud as auth_crud
from app.modules.auth.models import UserRole
from app.modules.admin_audit import service as audit_service

logger = logging.getLogger(__name__)


async def login_admin(
    db: AsyncSession,
    email: str,
    password: str,
    client_ip: str | None = None
) -> dict:
    """
    Authenticate admin and issue admin-only token.
    Admin login uses email+password (not Firebase) for admin panel access.
    """
    # Look up admin by email and verify password
    admin_user = await auth_crud.get_user_by_email(db, email)
    if admin_user and not verify_password(password, admin_user.password_hash):
        admin_user = None

    if not admin_user:
        logger.warning(f"Admin login failed (invalid credentials): email={email}, ip={client_ip}")
        await audit_service.log_action(
            db=db,
            admin_id=None,
            action_type="admin_login_failed",
            target_entity="admin_auth",
            target_id=None,
            metadata={"email": email, "reason": "invalid_credentials"},
            ip_address=client_ip
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if admin_user.role != UserRole.ADMIN:
        logger.warning(f"Admin login failed (non-admin role): email={email}, ip={client_ip}")
        await audit_service.log_action(
            db=db,
            admin_id=admin_user.id if admin_user else None,
            action_type="admin_login_failed",
            target_entity="admin_auth",
            target_id=str(admin_user.id) if admin_user else None,
            metadata={"email": email, "reason": "non_admin_role"},
            ip_address=client_ip
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    if not admin_user.is_active:
        logger.warning(f"Admin login failed (inactive): user_id={admin_user.id}, ip={client_ip}")
        await audit_service.log_action(
            db=db,
            admin_id=admin_user.id,
            action_type="admin_login_failed",
            target_entity="admin_auth",
            target_id=str(admin_user.id),
            metadata={"email": email, "reason": "inactive_account"},
            ip_address=client_ip
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin account is inactive"
        )

    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_admin_access_token(
        data={"sub": str(admin_user.id), "email": admin_user.email, "role": admin_user.role.value},
        expires_delta=expires_delta
    )

    logger.info(f"Admin login successful: user_id={admin_user.id}")
    await audit_service.log_action(
        db=db,
        admin_id=admin_user.id,
        action_type="admin_login_success",
        target_entity="admin_auth",
        target_id=str(admin_user.id),
        metadata={"email": admin_user.email},
        ip_address=client_ip
    )

    return {
        "status": "ok",
        "data": {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": int(expires_delta.total_seconds())
        },
        "error": None
    }
