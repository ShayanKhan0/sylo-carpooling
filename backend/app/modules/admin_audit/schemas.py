"""
Pydantic schemas for Admin Audit Logs (Prompt 12D).
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditLogResponse(BaseModel):
    id: UUID
    admin_id: Optional[UUID]
    action_type: str
    target_entity: str
    target_id: Optional[str]
    metadata: Optional[str] = Field(default=None, alias="meta_data")
    ip_address: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AuditLogListResponse(BaseModel):
    total: int
    logs: List[AuditLogResponse]


class AuditLogFilter(BaseModel):
    admin_id: Optional[UUID] = None
    action_type: Optional[str] = None
    target_entity: Optional[str] = None

    model_config = ConfigDict(extra="forbid")
