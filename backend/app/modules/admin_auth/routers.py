"""
Admin Auth Router (Prompt 12A)

Admin-only login under /api/admin/auth/*
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.admin_auth import schemas, service

router = APIRouter(prefix="/auth", tags=["Admin Auth"])


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=dict,
    summary="Admin login",
    description="""
    Authenticate admin via email + password and issue admin-only JWT.

    **Security:**
    - Token is restricted to admin APIs
    - Non-admin roles receive 403
    """
)
async def admin_login(
    payload: schemas.AdminLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    client_ip = request.client.host if request.client else None
    return await service.login_admin(db, payload.email, payload.password, client_ip)
