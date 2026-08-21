"""
Purpose: Admin flag model for flagging objects for review.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Generic flagging system for admins to track issues with any object type.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Index, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import FlagSeverity, FlagStatus


class AdminFlag(Base):
    """
    Admin flag model for flagging objects for review.
    
    Attributes:
        id: Unique identifier (UUID)
        object_type: Type of object (e.g., 'user', 'driver', 'ride', 'booking')
        object_id: UUID of the flagged object
        reason: Reason for flagging
        severity: Flag severity (low, medium, high)
        status: Flag status (open, resolved, dismissed)
        created_at: Flag creation timestamp
        updated_at: Last update timestamp
    
    Notes:
        - Generic flagging system for any object type
        - object_type and object_id form a polymorphic reference
        - Admins can use this to track problematic users, rides, etc.
    """
    
    __tablename__ = "admin_flags"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    
    # Object Reference (polymorphic)
    object_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Type of flagged object: 'user', 'driver', 'ride', 'booking', 'verification'"
    )
    
    object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="UUID of the flagged object"
    )
    
    # Flag Details
    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Reason for flagging"
    )
    
    severity: Mapped[FlagSeverity] = mapped_column(
        SQLEnum(
            FlagSeverity,
            name="flag_severity",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=FlagSeverity.MEDIUM,
        index=True
    )
    
    status: Mapped[FlagStatus] = mapped_column(
        SQLEnum(
            FlagStatus,
            name="flag_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=FlagStatus.OPEN,
        index=True
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        index=True
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_admin_flags_object_type", "object_type"),
        Index("idx_admin_flags_object_id", "object_id"),
        Index("idx_admin_flags_severity", "severity"),
        Index("idx_admin_flags_status", "status"),
        Index("idx_admin_flags_created_at", "created_at"),
        # Composite indexes for common queries
        Index("idx_admin_flags_object", "object_type", "object_id"),
        Index("idx_admin_flags_status_severity", "status", "severity"),
        Index("idx_admin_flags_status_created", "status", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<AdminFlag(id={self.id}, object_type={self.object_type}, object_id={self.object_id}, severity={self.severity}, status={self.status})>"
