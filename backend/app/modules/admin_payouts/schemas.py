"""
Pydantic schemas for Admin Payouts (Prompt 12C).
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from app.modules.payments.models import PayoutStatusEnum, PayoutMethodEnum


class PayoutListItem(BaseModel):
    id: UUID
    driver_id: UUID
    amount: float
    method: PayoutMethodEnum
    status: PayoutStatusEnum
    created_at: datetime
    processed_at: Optional[datetime]
    admin_id: Optional[UUID]
    admin_action: Optional[str]
    admin_action_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class PayoutListResponse(BaseModel):
    total: int
    payouts: List[PayoutListItem]


class PayoutDecisionRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=500, description="Admin notes for payout decision")


class PayoutDecisionResponse(BaseModel):
    id: UUID
    status: PayoutStatusEnum
    processed_at: Optional[datetime]
    admin_id: Optional[UUID]
    admin_action: Optional[str]
    admin_action_at: Optional[datetime]
    notes: Optional[str]

    model_config = ConfigDict(from_attributes=True)
