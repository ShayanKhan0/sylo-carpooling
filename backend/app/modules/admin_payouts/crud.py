"""
CRUD operations for Admin Payouts (Prompt 12C).
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import Payout, PayoutStatusEnum


async def count_pending_payouts(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(Payout).where(Payout.status == PayoutStatusEnum.PENDING)
    )
    return int(result.scalar() or 0)


async def list_pending_payouts(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0
) -> List[Payout]:
    result = await db.execute(
        select(Payout)
        .where(Payout.status == PayoutStatusEnum.PENDING)
        .order_by(Payout.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_payout_for_update(db: AsyncSession, payout_id: UUID) -> Optional[Payout]:
    result = await db.execute(
        select(Payout)
        .where(Payout.id == payout_id)
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def approve_payout(
    db: AsyncSession,
    payout: Payout,
    admin_id: UUID,
    notes: Optional[str] = None
) -> Payout:
    if payout.status != PayoutStatusEnum.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payout already processed"
        )

    payout.status = PayoutStatusEnum.PROCESSING
    payout.processed_at = datetime.utcnow()
    payout.admin_id = admin_id
    payout.admin_action = "approved"
    payout.admin_action_at = datetime.utcnow()

    if notes:
        payout.notes = notes

    await db.commit()
    await db.refresh(payout)
    return payout


async def reject_payout(
    db: AsyncSession,
    payout: Payout,
    admin_id: UUID,
    notes: Optional[str] = None
) -> Payout:
    if payout.status != PayoutStatusEnum.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payout already processed"
        )

    payout.status = PayoutStatusEnum.CANCELLED
    payout.processed_at = datetime.utcnow()
    payout.admin_id = admin_id
    payout.admin_action = "rejected"
    payout.admin_action_at = datetime.utcnow()

    if notes:
        payout.notes = notes

    await db.commit()
    await db.refresh(payout)
    return payout


async def list_payouts_for_export(db: AsyncSession) -> List[Payout]:
    result = await db.execute(
        select(Payout)
        .order_by(Payout.created_at.desc())
    )
    return list(result.scalars().all())
