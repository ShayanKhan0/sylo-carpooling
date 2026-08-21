"""
CRUD operations for Admin Moderation (Prompt 12B).
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.verification.models import UserVerification, VerificationStatusEnum, DocumentTypeEnum
from .models import Dispute, DisputeStatusEnum, DisputeCategoryEnum, DisputePriorityEnum


# ============================
# Verification Queue
# ============================

async def list_verification_queue(
    db: AsyncSession,
    statuses: List[VerificationStatusEnum],
    doc_type: Optional[DocumentTypeEnum],
    limit: int,
    offset: int
) -> List[UserVerification]:
    query = select(UserVerification).where(UserVerification.status.in_(statuses))

    if doc_type:
        query = query.where(UserVerification.doc_type == doc_type)

    query = query.order_by(UserVerification.created_at.asc()).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def count_verification_queue(
    db: AsyncSession,
    statuses: List[VerificationStatusEnum],
    doc_type: Optional[DocumentTypeEnum]
) -> int:
    query = select(func.count()).select_from(UserVerification).where(UserVerification.status.in_(statuses))

    if doc_type:
        query = query.where(UserVerification.doc_type == doc_type)

    result = await db.execute(query)
    return int(result.scalar() or 0)


# ============================
# Disputes
# ============================

async def list_disputes(
    db: AsyncSession,
    status: Optional[DisputeStatusEnum],
    category: Optional[DisputeCategoryEnum],
    priority: Optional[DisputePriorityEnum],
    limit: int,
    offset: int
) -> List[Dispute]:
    query = select(Dispute).options(selectinload(Dispute.attachments))

    if status:
        query = query.where(Dispute.status == status)

    if category:
        query = query.where(Dispute.category == category)

    if priority:
        query = query.where(Dispute.priority == priority)

    query = query.order_by(desc(Dispute.created_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().unique().all())


async def count_disputes(
    db: AsyncSession,
    status: Optional[DisputeStatusEnum],
    category: Optional[DisputeCategoryEnum],
    priority: Optional[DisputePriorityEnum]
) -> int:
    query = select(func.count()).select_from(Dispute)

    if status:
        query = query.where(Dispute.status == status)

    if category:
        query = query.where(Dispute.category == category)

    if priority:
        query = query.where(Dispute.priority == priority)

    result = await db.execute(query)
    return int(result.scalar() or 0)


async def get_dispute_by_id(db: AsyncSession, dispute_id: UUID) -> Optional[Dispute]:
    query = select(Dispute).where(Dispute.id == dispute_id).options(selectinload(Dispute.attachments))
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_dispute_resolution(
    db: AsyncSession,
    dispute: Dispute,
    status: DisputeStatusEnum,
    resolution: str,
    admin_notes: Optional[str],
    action_taken: Optional[str],
    resolved_by: Optional[UUID]
) -> Dispute:
    dispute.status = status
    dispute.resolution = resolution
    dispute.admin_notes = admin_notes
    dispute.action_taken = action_taken
    dispute.resolved_by = resolved_by
    dispute.resolved_at = datetime.utcnow()
    dispute.updated_at = datetime.utcnow()

    db.add(dispute)
    await db.commit()
    await db.refresh(dispute)
    return dispute
