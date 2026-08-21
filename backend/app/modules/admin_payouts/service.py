"""
Service layer for Admin Payouts (Prompt 12C).
"""

import csv
import io
from typing import List, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import Payout

from . import crud


async def get_pending_payouts(
    db: AsyncSession,
    limit: int,
    offset: int
) -> Tuple[int, List[Payout]]:
    total = await crud.count_pending_payouts(db)
    payouts = await crud.list_pending_payouts(db, limit=limit, offset=offset)
    return total, payouts


async def approve_payout(
    db: AsyncSession,
    payout_id: UUID,
    admin_id: UUID,
    notes: str | None
) -> Payout:
    payout = await crud.get_payout_for_update(db, payout_id)
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")

    return await crud.approve_payout(db, payout, admin_id, notes)


async def reject_payout(
    db: AsyncSession,
    payout_id: UUID,
    admin_id: UUID,
    notes: str | None
) -> Payout:
    payout = await crud.get_payout_for_update(db, payout_id)
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found")

    return await crud.reject_payout(db, payout, admin_id, notes)


async def export_payouts_csv(db: AsyncSession) -> str:
    payouts = await crud.list_payouts_for_export(db)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "payout_id",
        "driver_id",
        "amount",
        "method",
        "status",
        "created_at",
        "processed_at",
        "admin_id",
        "admin_action",
        "admin_action_at"
    ])

    for payout in payouts:
        writer.writerow([
            str(payout.id),
            str(payout.driver_id),
            float(payout.amount),
            payout.method.value if payout.method else None,
            payout.status.value if payout.status else None,
            payout.created_at.isoformat() if payout.created_at else None,
            payout.processed_at.isoformat() if payout.processed_at else None,
            str(payout.admin_id) if payout.admin_id else None,
            payout.admin_action,
            payout.admin_action_at.isoformat() if payout.admin_action_at else None
        ])

    return output.getvalue()
