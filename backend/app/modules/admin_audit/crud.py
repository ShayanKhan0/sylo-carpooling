"""
CRUD operations for Admin Audit Logs (Prompt 12D).
"""

import json
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AdminAuditLog


async def create_log(
    db: AsyncSession,
    admin_id: Optional[UUID],
    action_type: str,
    target_entity: str,
    target_id: Optional[str],
    metadata: Optional[dict],
    ip_address: Optional[str]
) -> AdminAuditLog:
    log = AdminAuditLog(
        admin_id=admin_id,
        action_type=action_type,
        target_entity=target_entity,
        target_id=target_id,
        meta_data=json.dumps(metadata) if metadata is not None else None,
        ip_address=ip_address
    )

    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def count_logs(
    db: AsyncSession,
    admin_id: Optional[UUID] = None,
    action_type: Optional[str] = None,
    target_entity: Optional[str] = None
) -> int:
    query = select(func.count()).select_from(AdminAuditLog)

    if admin_id:
        query = query.where(AdminAuditLog.admin_id == admin_id)
    if action_type:
        query = query.where(AdminAuditLog.action_type == action_type)
    if target_entity:
        query = query.where(AdminAuditLog.target_entity == target_entity)

    result = await db.execute(query)
    return int(result.scalar() or 0)


async def list_logs(
    db: AsyncSession,
    admin_id: Optional[UUID] = None,
    action_type: Optional[str] = None,
    target_entity: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[AdminAuditLog]:
    query = select(AdminAuditLog)

    if admin_id:
        query = query.where(AdminAuditLog.admin_id == admin_id)
    if action_type:
        query = query.where(AdminAuditLog.action_type == action_type)
    if target_entity:
        query = query.where(AdminAuditLog.target_entity == target_entity)

    query = query.order_by(AdminAuditLog.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_log_by_id(db: AsyncSession, log_id: UUID) -> Optional[AdminAuditLog]:
    result = await db.execute(select(AdminAuditLog).where(AdminAuditLog.id == log_id))
    return result.scalar_one_or_none()
