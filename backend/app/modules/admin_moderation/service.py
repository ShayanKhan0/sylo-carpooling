"""
Service layer for Admin Moderation (Prompt 12B).
"""

from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.verification import crud as verification_crud
from app.modules.verification.models import VerificationStatusEnum, DocumentTypeEnum
from app.modules.verification.schemas import VerificationResponse

from . import crud
from .models import DisputeStatusEnum, DisputeCategoryEnum, DisputePriorityEnum


# ============================
# Verification Moderation
# ============================

async def get_verification_queue(
    db: AsyncSession,
    statuses: List[VerificationStatusEnum],
    doc_type: Optional[DocumentTypeEnum],
    limit: int,
    offset: int
):
    total = await crud.count_verification_queue(db, statuses, doc_type)
    items = await crud.list_verification_queue(db, statuses, doc_type, limit, offset)
    return total, items


async def get_verification_detail(db: AsyncSession, verification_id: UUID) -> Optional[VerificationResponse]:
    verification = await verification_crud.get_verification_by_id(db, verification_id, include_attempts=True)
    if not verification:
        return None
    return VerificationResponse.model_validate(verification)


async def review_verification(
    db: AsyncSession,
    verification_id: UUID,
    decision: str,
    remarks: Optional[str],
    reviewer_id: UUID
):
    verification = await verification_crud.get_verification_by_id(db, verification_id)
    if not verification:
        raise HTTPException(status_code=404, detail="Verification record not found")

    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Decision must be 'approved' or 'rejected'")

    new_status = VerificationStatusEnum.VERIFIED if decision == "approved" else VerificationStatusEnum.REJECTED

    updated = await verification_crud.update_verification_status(
        db,
        verification_id=verification_id,
        new_status=new_status,
        admin_remarks=remarks,
        reviewed_by=reviewer_id
    )

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update verification status")

    await verification_crud.create_verification_attempt(
        db,
        verification_id=verification_id,
        attempt_type="admin_review",
        decision=decision,
        ai_score=verification.ai_confidence,
        face_match_score=None,
        remarks=remarks,
        reviewed_by=reviewer_id,
        ocr_data=None,
        metadata=None
    )

    return updated


# ============================
# Dispute Moderation
# ============================

async def get_disputes(
    db: AsyncSession,
    status_filter: Optional[DisputeStatusEnum],
    category: Optional[DisputeCategoryEnum],
    priority: Optional[DisputePriorityEnum],
    limit: int = 50,
    offset: int = 0
):
    total = await crud.count_disputes(db, status_filter, category, priority)
    disputes = await crud.list_disputes(db, status_filter, category, priority, limit, offset)
    return total, disputes


async def get_dispute_detail(db: AsyncSession, dispute_id: UUID):
    dispute = await crud.get_dispute_by_id(db, dispute_id)
    if not dispute:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispute not found")
    return dispute


async def resolve_dispute(
    db: AsyncSession,
    dispute_id: UUID,
    status_value: DisputeStatusEnum,
    resolution: str,
    admin_notes: Optional[str],
    action_taken: Optional[str],
    resolved_by: UUID
):
    if status_value not in {DisputeStatusEnum.RESOLVED, DisputeStatusEnum.REJECTED}:
        raise HTTPException(status_code=400, detail="Status must be 'resolved' or 'rejected'")

    dispute = await crud.get_dispute_by_id(db, dispute_id)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")

    updated = await crud.update_dispute_resolution(
        db,
        dispute=dispute,
        status=status_value,
        resolution=resolution,
        admin_notes=admin_notes,
        action_taken=action_taken,
        resolved_by=resolved_by
    )

    return updated
