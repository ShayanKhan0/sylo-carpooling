"""
Purpose: Verification model for document verification (KYC).
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Stores document verification records including OCR data and face matching.
"""

# === VERIFICATION FUNCTIONALITY START ===

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, Float, Text, JSON, Index, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import VerificationStatus

if TYPE_CHECKING:
    from app.modules.auth.models import User


class Verification(Base):
    """
    Verification model for document verification (KYC).
    
    Attributes:
        id: Unique identifier (UUID)
        user_id: Foreign key to user
        document_type: Type of document (e.g., 'cnic', 'license', 'passport')
        document_url: URL to uploaded document image
        ocr_fields: Extracted OCR data (JSON)
        face_match_score: Face matching confidence score
        status: Verification status (pending, verified, rejected)
        confidence_score: Overall verification confidence
        review_notes: Manual review notes from admin
        created_at: Verification request timestamp
        updated_at: Last update timestamp
    
    Relationships:
        user: User requesting verification
    """
    
    __tablename__ = "verifications"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    
    # User Reference
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Document Information
    document_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Document type: 'cnic', 'license', 'passport', 'vehicle_registration'"
    )
    
    document_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="URL to uploaded document image (S3 or similar)"
    )
    
    # OCR Extracted Data
    ocr_fields: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="OCR extracted fields: {name: 'John Doe', cnic: '12345-1234567-1', dob: '1990-01-01'}"
    )
    
    # Face Matching
    face_match_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Face matching confidence score (0.0 to 1.0)"
    )
    
    # Verification Status
    status: Mapped[VerificationStatus] = mapped_column(
        SQLEnum(
            VerificationStatus,
            name="verification_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=VerificationStatus.PENDING,
        index=True
    )
    
    confidence_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="Overall verification confidence score (0.0 to 1.0)"
    )
    
    # Review Information
    review_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Manual review notes from admin"
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
    
    # Relationships
    user: Mapped["User"] = relationship("User")
    
    # Indexes
    __table_args__ = (
        Index("idx_verifications_user_id", "user_id"),
        Index("idx_verifications_status", "status"),
        Index("idx_verifications_document_type", "document_type"),
        Index("idx_verifications_created_at", "created_at"),
        # Composite index for common queries
        Index("idx_verifications_user_status", "user_id", "status"),
    )
    
    def __repr__(self) -> str:
        return f"<Verification(id={self.id}, user_id={self.user_id}, type={self.document_type}, status={self.status})>"

# === VERIFICATION FUNCTIONALITY END ===
