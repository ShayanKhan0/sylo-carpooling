"""
Database models for Verification Module.

Models:
- UserVerification: Document verification records for users
- VerificationAttempt: AI and admin review attempts with scores

Author: Smart Carpooling Development Team
Created: 2025-11-08
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, Enum as SQLEnum, Index, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class DocumentTypeEnum(str, enum.Enum):
    """
    Types of documents that can be uploaded for verification.
    
    Types:
    - CNIC: Computerized National Identity Card (Pakistan)
    - DRIVING_LICENSE: Driver's license
    - VEHICLE_REGISTRATION: Vehicle registration certificate
    - SELFIE: User selfie for facial recognition
    - INSURANCE: Vehicle insurance document
    """
    CNIC = "cnic"
    DRIVING_LICENSE = "driving_license"
    VEHICLE_REGISTRATION = "vehicle_registration"
    SELFIE = "selfie"
    INSURANCE = "insurance"


class VerificationStatusEnum(str, enum.Enum):
    """
    Verification status lifecycle.
    
    States:
    - PENDING: Document uploaded, awaiting AI/admin review
    - UNDER_REVIEW: Being reviewed by AI or admin
    - VERIFIED: Successfully verified and approved
    - REJECTED: Verification failed or rejected
    - EXPIRED: Verification expired (documents need renewal)
    """
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"


class UserVerification(Base):
    """
    User document verification records.
    
    Business Rules:
    - Each user can have multiple verification records (one per document type)
    - Documents stored securely in /static/uploads/verification/
    - AI auto-verifies if confidence score > 90%
    - Admin can manually override AI decision
    - Verification expires after configurable period (e.g., 1 year)
    - Failed attempts logged in VerificationAttempt
    
    Verification Flow:
    1. User uploads document (status=PENDING)
    2. AI analyzes document (OCR + face match if applicable)
    3. If AI score > 90%, auto-verify (status=VERIFIED)
    4. If AI score < 90%, flag for admin review (status=UNDER_REVIEW)
    5. Admin reviews and approves/rejects
    6. User notified of decision
    
    Security:
    - Documents stored with UUID-based filenames
    - No public URLs to documents
    - Access controlled via JWT auth
    - Sensitive data encrypted at rest
    """
    __tablename__ = "user_verifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Document details
    doc_type = Column(SQLEnum(DocumentTypeEnum, native_enum=False), nullable=False, index=True)
    doc_path = Column(String(512), nullable=False)  # Relative path to uploaded file
    doc_number = Column(String(50), nullable=True)  # Extracted document number (CNIC number, license number, etc.)
    
    # Verification status
    status = Column(SQLEnum(VerificationStatusEnum, native_enum=False), nullable=False, default=VerificationStatusEnum.PENDING, index=True)
    
    # AI and review details
    ai_confidence = Column(Float, nullable=True)  # 0.0 - 1.0
    ai_remarks = Column(Text, nullable=True)  # AI-generated notes
    admin_remarks = Column(Text, nullable=True)  # Admin review notes
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # Admin user ID
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    verified_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)  # Verification expiry date
    
    # Metadata
    meta_data = Column(Text, nullable=True)  # JSON: extracted OCR data, face match details, etc.
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="verifications")
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    attempts = relationship("VerificationAttempt", back_populates="verification", cascade="all, delete-orphan")
    
    # Constraints and indexes
    __table_args__ = (
        Index('idx_verification_user_id', 'user_id'),
        Index('idx_verification_status', 'status'),
        Index('idx_verification_doc_type', 'doc_type'),
        Index('idx_verification_created_at', 'created_at'),
    )

    def __repr__(self):
        return f"<UserVerification(user_id={self.user_id}, doc_type={self.doc_type}, status={self.status})>"


class VerificationAttempt(Base):
    """
    Log of all verification attempts (AI and admin reviews).
    
    Business Rules:
    - Every AI analysis creates an attempt record
    - Every admin review creates an attempt record
    - Provides complete audit trail
    - Helps track verification success rates
    - Used for AI model improvement
    
    Performance:
    - Indexed by verification_id and timestamp
    - Read-heavy table (mostly for analytics)
    - Partition by date for large volumes
    """
    __tablename__ = "verification_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    verification_id = Column(UUID(as_uuid=True), ForeignKey("user_verifications.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Attempt details
    attempt_type = Column(String(20), nullable=False)  # "ai_analysis" or "admin_review"
    ai_score = Column(Float, nullable=True)  # AI confidence score (0.0 - 1.0)
    
    # Decision
    decision = Column(String(20), nullable=False)  # "approved", "rejected", "flagged"
    remarks = Column(Text, nullable=True)
    
    # Review details
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)  # Admin user if manual review
    
    # Timestamp
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # AI analysis metadata
    ocr_data = Column(Text, nullable=True)  # JSON: extracted text from OCR
    face_match_score = Column(Float, nullable=True)  # Face recognition similarity (0.0 - 1.0)
    meta_data = Column(Text, nullable=True)  # JSON: additional AI analysis data
    
    # Relationships
    verification = relationship("UserVerification", back_populates="attempts")
    reviewer = relationship("User")
    
    # Constraints and indexes
    __table_args__ = (
        Index('idx_attempt_verification_id', 'verification_id'),
        Index('idx_attempt_created_at', 'created_at'),
        Index('idx_attempt_decision', 'decision'),
    )

    def __repr__(self):
        return f"<VerificationAttempt(verification_id={self.verification_id}, type={self.attempt_type}, decision={self.decision})>"

