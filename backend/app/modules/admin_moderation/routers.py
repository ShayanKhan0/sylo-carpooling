"""
Admin Moderation API Router (Prompt 12B)

Admin-only moderation workflows for verifications and disputes.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.admin_auth import require_admin, require_admin_ip_allowlist
from app.db.session import get_db
from app.modules.auth.models import User
from app.modules.verification.models import VerificationStatusEnum, DocumentTypeEnum
from app.modules.verification.schemas import VerificationResponse

from . import schemas, service
from app.modules.admin_audit import service as audit_service
from .models import DisputeStatusEnum, DisputeCategoryEnum, DisputePriorityEnum

router = APIRouter(prefix="/moderation", tags=["Admin Moderation (Prompt 12B)"])


# ============================
# Verification Queue
# ============================

@router.get(
    "/verifications/queue",
    response_model=schemas.VerificationQueueResponse,
    summary="List verification queue",
    description="Returns verification records pending or under review."
)
async def list_verification_queue(
    status: Optional[List[VerificationStatusEnum]] = Query(None, description="Filter by status (pending/under_review)"),
    doc_type: Optional[DocumentTypeEnum] = Query(None, description="Filter by document type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    statuses = status or [VerificationStatusEnum.PENDING, VerificationStatusEnum.UNDER_REVIEW]
    total, items = await service.get_verification_queue(db, statuses, doc_type, limit, offset)
    return schemas.VerificationQueueResponse(total=total, items=items)


@router.get(
    "/verifications/{verification_id}",
    response_model=VerificationResponse,
    summary="Get verification detail",
    description="Returns full verification details including attempts."
)
async def get_verification_detail(
    verification_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    verification = await service.get_verification_detail(db, verification_id)
    if not verification:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Verification record not found")
    return verification


@router.post(
    "/verifications/{verification_id}/review",
    response_model=schemas.VerificationReviewResponse,
    summary="Review verification",
    description="Approve or reject a verification record (admin IP allowlist enforced)."
)
async def review_verification(
    verification_id: UUID,
    request: schemas.VerificationReviewRequest,
    http_request: Request,
    admin: User = Depends(require_admin),
    _: None = Depends(require_admin_ip_allowlist),
    db: AsyncSession = Depends(get_db)
):
    updated = await service.review_verification(
        db,
        verification_id=verification_id,
        decision=request.decision,
        remarks=request.remarks,
        reviewer_id=admin.id
    )
    client_ip = http_request.client.host if http_request.client else None
    await audit_service.log_action(
        db=db,
        admin_id=admin.id,
        action_type=f"verification_{request.decision}",
        target_entity="user_verification",
        target_id=str(verification_id),
        metadata={"remarks": request.remarks},
        ip_address=client_ip
    )
    return schemas.VerificationReviewResponse.model_validate(updated)


# ============================
# Dispute Moderation
# ============================

@router.get(
    "/disputes",
    response_model=schemas.DisputeListResponse,
    summary="List disputes",
    description="Returns disputes with optional filters."
)
async def list_disputes(
    status: Optional[DisputeStatusEnum] = Query(None),
    category: Optional[DisputeCategoryEnum] = Query(None),
    priority: Optional[DisputePriorityEnum] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    total, disputes = await service.get_disputes(db, status, category, priority, limit, offset)
    return schemas.DisputeListResponse(total=total, disputes=disputes)


@router.get(
    "/disputes/{dispute_id}",
    response_model=schemas.DisputeResponse,
    summary="Get dispute detail",
    description="Returns dispute details with attachments."
)
async def get_dispute_detail(
    dispute_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    return await service.get_dispute_detail(db, dispute_id)


@router.post(
    "/disputes/{dispute_id}/resolve",
    response_model=schemas.DisputeResponse,
    summary="Resolve dispute",
    description="Resolve or reject a dispute (admin IP allowlist enforced)."
)
async def resolve_dispute(
    dispute_id: UUID,
    request: schemas.DisputeResolveRequest,
    http_request: Request,
    admin: User = Depends(require_admin),
    _: None = Depends(require_admin_ip_allowlist),
    db: AsyncSession = Depends(get_db)
):
    result = await service.resolve_dispute(
        db,
        dispute_id=dispute_id,
        status_value=request.status,
        resolution=request.resolution,
        admin_notes=request.admin_notes,
        action_taken=request.action_taken,
        resolved_by=admin.id
    )
    client_ip = http_request.client.host if http_request.client else None
    await audit_service.log_action(
        db=db,
        admin_id=admin.id,
        action_type="dispute_resolved" if request.status == DisputeStatusEnum.RESOLVED else "dispute_rejected",
        target_entity="dispute",
        target_id=str(dispute_id),
        metadata={"action_taken": request.action_taken},
        ip_address=client_ip
    )
    if request.action_taken and request.action_taken.lower() in {"refund", "suspend", "suspension"}:
        await audit_service.log_action(
            db=db,
            admin_id=admin.id,
            action_type=request.action_taken.lower(),
            target_entity="dispute",
            target_id=str(dispute_id),
            metadata={"resolution": request.resolution},
            ip_address=client_ip
        )
    return result
