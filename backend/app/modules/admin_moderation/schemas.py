"""
Pydantic schemas for Admin Moderation (Prompt 12B).
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, validator

from app.modules.verification.models import DocumentTypeEnum, VerificationStatusEnum
from .models import DisputeCategoryEnum, DisputeStatusEnum, DisputePriorityEnum


# ============================
# Verification Queue Schemas
# ============================

class VerificationQueueItem(BaseModel):
    id: UUID
    user_id: UUID
    doc_type: DocumentTypeEnum
    status: VerificationStatusEnum
    ai_confidence: Optional[float]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerificationQueueResponse(BaseModel):
    total: int
    items: List[VerificationQueueItem]


class VerificationReviewRequest(BaseModel):
    decision: str = Field(..., description="Admin decision: 'approved' or 'rejected'")
    remarks: Optional[str] = Field(None, max_length=500, description="Admin review notes")

    @validator("decision")
    def validate_decision(cls, v):
        if v not in {"approved", "rejected"}:
            raise ValueError("Decision must be 'approved' or 'rejected'")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "decision": "approved",
                "remarks": "Document verified successfully"
            }
        }
    )


class VerificationReviewResponse(BaseModel):
    id: UUID
    status: VerificationStatusEnum
    admin_remarks: Optional[str]
    reviewed_by: Optional[UUID]
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================
# Dispute Schemas
# ============================

class DisputeAttachmentResponse(BaseModel):
    id: UUID
    file_name: str
    file_path: str
    content_type: Optional[str]
    file_size: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DisputeResponse(BaseModel):
    id: UUID
    reporter_id: Optional[UUID]
    reported_user_id: Optional[UUID]
    ride_id: Optional[UUID]
    title: str
    description: str
    category: DisputeCategoryEnum
    status: DisputeStatusEnum
    priority: DisputePriorityEnum
    admin_notes: Optional[str]
    resolution: Optional[str]
    action_taken: Optional[str]
    resolved_by: Optional[UUID]
    resolved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    attachments: List[DisputeAttachmentResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DisputeListResponse(BaseModel):
    total: int
    disputes: List[DisputeResponse]


class DisputeResolveRequest(BaseModel):
    status: DisputeStatusEnum = Field(..., description="Resolution status: resolved or rejected")
    resolution: str = Field(..., min_length=3, max_length=1000)
    action_taken: Optional[str] = Field(None, max_length=100, description="Admin action summary (e.g., refund, warning)")
    admin_notes: Optional[str] = Field(None, max_length=1000)

    @validator("status")
    def validate_status(cls, v):
        if v not in {DisputeStatusEnum.RESOLVED, DisputeStatusEnum.REJECTED}:
            raise ValueError("Status must be 'resolved' or 'rejected'")
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "resolved",
                "resolution": "Refund approved and issued.",
                "action_taken": "refund",
                "admin_notes": "Verified ride cancellation with support logs."
            }
        }
    )
