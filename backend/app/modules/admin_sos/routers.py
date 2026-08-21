from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.admin_auth import require_admin
from app.db.session import get_db
from app.modules.admin_sos import service


router = APIRouter(prefix="/sos", tags=["Admin SOS Dashboard"])


class AdminRemarkRequest(BaseModel):
    remarks: Optional[str] = Field(default=None, max_length=3000)


class AdminAssignRequest(BaseModel):
    assigned_to: str = Field(..., min_length=1, max_length=120)
    remarks: Optional[str] = Field(default=None, max_length=3000)


class AdminNoteRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=3000)


@router.get("/active", response_model=dict)
async def list_active_sos(
    limit: int = 100,
    current_admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    _ = current_admin
    return await service.list_active_sos_incidents(db, limit=limit)


@router.get("/history", response_model=dict)
async def list_history_sos(
    limit: int = 100,
    offset: int = 0,
    current_admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    _ = current_admin
    return await service.list_historical_sos_incidents(
        db,
        limit=limit,
        offset=offset,
    )


@router.get("/unlinked/active", response_model=dict)
async def list_unlinked_active_sos(
    limit: int = 100,
    offset: int = 0,
    current_admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    _ = current_admin
    return await service.list_unlinked_sos_incidents(
        db,
        active_only=True,
        limit=limit,
        offset=offset,
    )


@router.get("/unlinked/history", response_model=dict)
async def list_unlinked_history_sos(
    limit: int = 100,
    offset: int = 0,
    current_admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    _ = current_admin
    return await service.list_unlinked_sos_incidents(
        db,
        active_only=False,
        limit=limit,
        offset=offset,
    )


@router.get("/{incident_id}", response_model=dict)
async def sos_incident_detail(
    incident_id: UUID,
    current_admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    _ = current_admin
    return await service.get_sos_incident_detail(db, incident_id=incident_id)


@router.post("/{incident_id}/acknowledge", response_model=dict)
async def acknowledge_sos(
    incident_id: UUID,
    payload: AdminRemarkRequest,
    current_admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await service.acknowledge_incident(
        db,
        incident_id=incident_id,
        admin_user_id=current_admin.id,
        remarks=payload.remarks,
    )


@router.post("/{incident_id}/assign", response_model=dict)
async def assign_sos(
    incident_id: UUID,
    payload: AdminAssignRequest,
    current_admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await service.assign_incident(
        db,
        incident_id=incident_id,
        admin_user_id=current_admin.id,
        assigned_to=payload.assigned_to,
        remarks=payload.remarks,
    )


@router.post("/unlinked/{incident_id}/resolve", response_model=dict)
async def resolve_unlinked_sos(
    incident_id: UUID,
    current_admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await service.resolve_unlinked_incident(
        db,
        incident_id=incident_id,
        admin_user_id=current_admin.id,
    )


@router.post("/unlinked/resolve/{incident_id}", response_model=dict)
async def resolve_unlinked_sos_compat(
    incident_id: UUID,
    current_admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await service.resolve_unlinked_incident(
        db,
        incident_id=incident_id,
        admin_user_id=current_admin.id,
    )


@router.post("/{incident_id}/resolve", response_model=dict)
async def resolve_sos(
    incident_id: UUID,
    payload: Optional[AdminRemarkRequest] = None,
    current_admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await service.resolve_incident(
        db,
        incident_id=incident_id,
        admin_user_id=current_admin.id,
        remarks=payload.remarks if payload else None,
    )


@router.post("/resolve/{incident_id}", response_model=dict)
async def resolve_sos_compat(
    incident_id: UUID,
    payload: Optional[AdminRemarkRequest] = None,
    current_admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await service.resolve_incident(
        db,
        incident_id=incident_id,
        admin_user_id=current_admin.id,
        remarks=payload.remarks if payload else None,
    )


@router.post("/{incident_id}/notes", response_model=dict)
async def add_sos_note(
    incident_id: UUID,
    payload: AdminNoteRequest,
    current_admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return await service.add_incident_note(
        db,
        incident_id=incident_id,
        admin_user_id=current_admin.id,
        note=payload.note,
    )
