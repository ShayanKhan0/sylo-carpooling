"""
Admin Audit Logs API Router (Prompt 12D)

Admin-only access to audit logs.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.admin_auth import require_admin
from app.db.session import get_db
from app.modules.auth.models import User

from . import schemas, service

router = APIRouter(prefix="/audit", tags=["Admin Audit (Prompt 12D)"])


@router.get(
    "/logs",
    response_model=schemas.AuditLogListResponse,
    summary="List audit logs",
    description="Returns admin audit logs with optional filters."
)
async def list_audit_logs(
    admin_id: Optional[UUID] = Query(None),
    action_type: Optional[str] = Query(None),
    target_entity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    total, logs = await service.get_logs(db, admin_id, action_type, target_entity, limit, offset)
    return schemas.AuditLogListResponse(total=total, logs=logs)


@router.get(
    "/logs/{log_id}",
    response_model=schemas.AuditLogResponse,
    summary="Get audit log detail",
    description="Returns a single audit log entry."
)
async def get_audit_log(
    log_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    log = await service.get_log_detail(db, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return log
