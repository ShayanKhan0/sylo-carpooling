"""
Pydantic schemas for Verification Module.

Schemas for document verification, AI analysis, and admin review.

Author: Smart Carpooling Development Team
Created: 2025-11-08
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, validator, ConfigDict

from .models import DocumentTypeEnum, VerificationStatusEnum


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class VerificationRequest(BaseModel):
    """
    Request schema for uploading verification document.
    
    Used when user uploads CNIC, license, vehicle registration, etc.
    """
    user_id: UUID = Field(..., description="User ID requesting verification")
    doc_type: DocumentTypeEnum = Field(..., description="Type of document being uploaded")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "doc_type": "cnic"
            }
        }
    )


class AdminReviewRequest(BaseModel):
    """
    Request schema for admin manual review.
    
    Used when admin approves or rejects a verification.
    """
    decision: str = Field(..., description="Admin decision: 'approved' or 'rejected'")
    remarks: Optional[str] = Field(None, max_length=500, description="Admin review notes")
    
    @validator('decision')
    def validate_decision(cls, v):
        if v not in ['approved', 'rejected']:
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


class AIVerifyRequest(BaseModel):
    """
    Request schema for triggering manual AI verification.
    
    Used in test/development mode to manually trigger AI analysis.
    """
    verification_id: UUID = Field(..., description="Verification record ID")
    force_reprocess: Optional[bool] = Field(False, description="Force reprocessing even if already analyzed")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "verification_id": "789e0123-e45b-12d3-a456-426614174222",
                "force_reprocess": False
            }
        }
    )


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class VerificationResponse(BaseModel):
    """
    Response schema for verification record.
    
    Returns complete verification details including status and AI analysis.
    """
    id: UUID
    user_id: UUID
    doc_type: DocumentTypeEnum
    doc_path: str
    doc_number: Optional[str]
    status: VerificationStatusEnum
    ai_confidence: Optional[float]
    ai_remarks: Optional[str]
    admin_remarks: Optional[str]
    reviewed_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    verified_at: Optional[datetime]
    expires_at: Optional[datetime]
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "789...",
                "user_id": "123...",
                "doc_type": "cnic",
                "doc_path": "/uploads/verification/123_cnic_abc123.jpg",
                "doc_number": "12345-6789012-3",
                "status": "verified",
                "ai_confidence": 0.95,
                "ai_remarks": "Document verified with high confidence",
                "admin_remarks": None,
                "reviewed_by": None,
                "created_at": "2025-11-08T10:00:00Z",
                "updated_at": "2025-11-08T10:02:00Z",
                "verified_at": "2025-11-08T10:02:00Z",
                "expires_at": "2026-11-08T10:02:00Z"
            }
        }
    )


class VerificationStatus(BaseModel):
    """
    Simplified verification status response.
    
    Used for quick status checks without full details.
    """
    user_id: UUID
    verifications: Dict[str, str] = Field(..., description="Map of doc_type to status")
    overall_verified: bool = Field(..., description="True if all required docs verified")
    missing_documents: List[str] = Field(..., description="List of missing document types")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "123...",
                "verifications": {
                    "cnic": "verified",
                    "driving_license": "verified",
                    "vehicle_registration": "pending"
                },
                "overall_verified": False,
                "missing_documents": []
            }
        }
    )


class AIDecisionResponse(BaseModel):
    """
    Response schema for AI verification decision.
    
    Returns AI analysis results including confidence scores.
    """
    verification_id: UUID
    decision: str = Field(..., description="AI decision: 'approved', 'flagged', or 'rejected'")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall AI confidence score")
    ocr_confidence: Optional[float] = Field(None, description="OCR accuracy score")
    face_match_score: Optional[float] = Field(None, description="Face recognition similarity score")
    extracted_data: Optional[Dict[str, Any]] = Field(None, description="Extracted document data")
    remarks: str = Field(..., description="AI-generated remarks")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "verification_id": "789...",
                "decision": "approved",
                "confidence": 0.95,
                "ocr_confidence": 0.97,
                "face_match_score": 0.93,
                "extracted_data": {
                    "cnic_number": "12345-6789012-3",
                    "name": "JOHN DOE",
                    "dob": "01-01-1990"
                },
                "remarks": "Document verified with high confidence. All checks passed."
            }
        }
    )


class VerificationAttemptResponse(BaseModel):
    """
    Response schema for verification attempt record.
    """
    id: UUID
    verification_id: UUID
    attempt_type: str
    ai_score: Optional[float]
    decision: str
    remarks: Optional[str]
    reviewed_by: Optional[UUID]
    created_at: datetime
    face_match_score: Optional[float]
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "456...",
                "verification_id": "789...",
                "attempt_type": "ai_analysis",
                "ai_score": 0.95,
                "decision": "approved",
                "remarks": "High confidence verification",
                "reviewed_by": None,
                "created_at": "2025-11-08T10:01:00Z",
                "face_match_score": 0.93
            }
        }
    )


class VerificationListResponse(BaseModel):
    """
    Response schema for list of verifications.
    """
    total: int
    verifications: List[VerificationResponse]
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 3,
                "verifications": [
                    {
                        "id": "789...",
                        "user_id": "123...",
                        "doc_type": "cnic",
                        "status": "verified",
                        "ai_confidence": 0.95
                    }
                ]
            }
        }
    )


# ============================================================================
# OPERATION RESPONSE SCHEMA
# ============================================================================

class OperationResponse(BaseModel):
    """
    Generic operation response.
    """
    message: str
    verification_id: Optional[UUID] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Document uploaded successfully",
                "verification_id": "789..."
            }
        }
    )
