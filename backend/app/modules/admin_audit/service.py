"""
Service layer for Admin Audit Logs (Prompt 12D).
"""

from typing import Optional, Tuple, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from . import crud
from .models import AdminAuditLog


async def log_action(
    db: AsyncSession,
    admin_id: Optional[UUID],
    action_type: str,
    target_entity: str,
    target_id: Optional[str],
    metadata: Optional[dict],
    ip_address: Optional[str]
) -> AdminAuditLog:
    return await crud.create_log(
        db=db,
        admin_id=admin_id,
        action_type=action_type,
        target_entity=target_entity,
        target_id=target_id,
        metadata=metadata,
        ip_address=ip_address
    )


async def get_logs(
    db: AsyncSession,
    admin_id: Optional[UUID],
    action_type: Optional[str],
    target_entity: Optional[str],
    limit: int,
    offset: int
) -> Tuple[int, List[AdminAuditLog]]:
    total = await crud.count_logs(db, admin_id, action_type, target_entity)
    logs = await crud.list_logs(db, admin_id, action_type, target_entity, limit, offset)
    return total, logs


async def get_log_detail(db: AsyncSession, log_id: UUID) -> Optional[AdminAuditLog]:
    return await crud.get_log_by_id(db, log_id)
