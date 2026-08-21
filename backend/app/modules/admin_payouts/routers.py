"""
Admin Payouts API Router (Prompt 12C)

Admin-only payouts management and CSV export.
"""

from fastapi import APIRouter, Depends, Query, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.security.admin_auth import require_admin, require_admin_ip_allowlist
from app.db.session import get_db
from app.modules.auth.models import User

from . import schemas, service
from app.modules.admin_audit import service as audit_service

router = APIRouter(prefix="/payouts", tags=["Admin Payouts (Prompt 12C)"])


@router.get(
    "/pending",
    response_model=schemas.PayoutListResponse,
    summary="List pending payouts",
    description="Returns driver payout requests that are pending."
)
async def list_pending_payouts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    total, payouts = await service.get_pending_payouts(db, limit=limit, offset=offset)
    return schemas.PayoutListResponse(total=total, payouts=payouts)


@router.post(
    "/{payout_id}/approve",
    response_model=schemas.PayoutDecisionResponse,
    summary="Approve payout",
    description="Approve payout request (admin IP allowlist enforced)."
)
async def approve_payout(
    payout_id: UUID,
    request: schemas.PayoutDecisionRequest,
    http_request: Request,
    admin: User = Depends(require_admin),
    _: None = Depends(require_admin_ip_allowlist),
    db: AsyncSession = Depends(get_db)
):
    payout = await service.approve_payout(db, payout_id, admin.id, request.notes)
    client_ip = http_request.client.host if http_request.client else None
    await audit_service.log_action(
        db=db,
        admin_id=admin.id,
        action_type="payout_approved",
        target_entity="payout",
        target_id=str(payout_id),
        metadata={"notes": request.notes},
        ip_address=client_ip
    )
    return schemas.PayoutDecisionResponse.model_validate(payout)


@router.post(
    "/{payout_id}/reject",
    response_model=schemas.PayoutDecisionResponse,
    summary="Reject payout",
    description="Reject payout request (admin IP allowlist enforced)."
)
async def reject_payout(
    payout_id: UUID,
    request: schemas.PayoutDecisionRequest,
    http_request: Request,
    admin: User = Depends(require_admin),
    _: None = Depends(require_admin_ip_allowlist),
    db: AsyncSession = Depends(get_db)
):
    payout = await service.reject_payout(db, payout_id, admin.id, request.notes)
    client_ip = http_request.client.host if http_request.client else None
    await audit_service.log_action(
        db=db,
        admin_id=admin.id,
        action_type="payout_rejected",
        target_entity="payout",
        target_id=str(payout_id),
        metadata={"notes": request.notes},
        ip_address=client_ip
    )
    return schemas.PayoutDecisionResponse.model_validate(payout)


@router.get(
    "/export/csv",
    summary="Export payouts as CSV",
    description="Download CSV export of payout data."
)
async def export_payouts_csv(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    csv_content = await service.export_payouts_csv(db)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=payouts_export.csv"}
    )
