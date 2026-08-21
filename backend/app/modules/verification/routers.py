"""
API Router for Verification Module.

Endpoints for document verification, AI analysis, and admin review.
All endpoints protected by JWT authentication.

Author: Smart Carpooling Development Team
Created: 2025-11-08
"""

# === VERIFICATION FUNCTIONALITY START ===
from typing import Dict, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, Form, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User

from .schemas import (
    VerificationRequest,
    VerificationResponse,
    VerificationStatus,
    AIDecisionResponse,
    AdminReviewRequest,
    AIVerifyRequest,
    OperationResponse
)
from .models import DocumentTypeEnum
from . import service


router = APIRouter(prefix="/verification", tags=["Verification"])


async def _run_sanitized(coro):
    try:
        result = await coro
        return service.sanitize_verification_client_payload(result)
    except HTTPException as exc:
        raise service.sanitized_verification_http_exception(exc) from exc


# ============================================================================
# DOCUMENT UPLOAD ENDPOINT
# ============================================================================

@router.post(
    "/upload",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Upload Verification Document",
    description="""
    Upload document for verification (CNIC, driving license, vehicle registration, etc.).
    
    **Process:**
    1. Validate file (type, size, format)
    2. Save to secure location
    3. Trigger AI verification (OCR + face match)
    4. Auto-approve if confidence > 90%
    5. Flag for manual review if 70-90%
    6. Auto-reject if < 70%
    
    **Supported Documents:**
    - CNIC (Computerized National Identity Card)
    - Driving License
    - Vehicle Registration
    - Insurance Documents
    - Selfie (for face matching)
    
    **File Requirements:**
    - Formats: JPG, PNG, PDF
    - Max size: 10 MB
    - Clear, readable image
    
    **Returns:**
    - Verification ID
    - AI confidence score
    - Decision (approved/flagged/rejected)
    - Status (verified/under_review/rejected)
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "verification_id": "789...",
            "doc_type": "cnic",
            "status": "verified",
            "ai_confidence": 0.95,
            "decision": "approved",
            "message": "Document verified with 95.0% confidence"
        }
    }
    ```
    """
)
async def upload_document(
    doc_type: DocumentTypeEnum = Form(...),
    file: UploadFile = File(...),
    document_back_file: Optional[UploadFile] = File(None),
    selfie_file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Upload document for verification."""
    return await _run_sanitized(service.upload_document_service(
        db=db,
        user_id=current_user.id,
        doc_type=doc_type,
        file=file,
        document_back_file=document_back_file,
        selfie_file=selfie_file,
        user_role=current_user.role,
    ))


@router.delete(
    "/document/{doc_type}",
    response_model=Dict[str, Any],
    summary="Delete Uploaded Verification Document",
    description="Delete uploaded verification image(s) for the given document type of the current user."
)
async def delete_uploaded_document(
    doc_type: DocumentTypeEnum,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete uploaded verification document(s) for the current user."""
    return await _run_sanitized(service.delete_uploaded_document_service(
        db=db,
        user_id=current_user.id,
        doc_type=doc_type,
        user_role=current_user.role,
    ))


@router.post(
    "/selfie/reverify-intent",
    response_model=Dict[str, Any],
    summary="Start Driver Selfie Re-verification",
    description="Driver-only action to replace selfie: invalidates current selfie verification and marks driver pending until new selfie verification completes."
)
async def start_driver_selfie_reverification(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start driver selfie re-verification flow from profile camera action."""
    return await _run_sanitized(service.start_driver_selfie_reverification_service(
        db=db,
        user_id=current_user.id,
        user_role=current_user.role,
    ))


@router.post(
    "/identity-data/verify/{doc_type}",
    response_model=Dict[str, Any],
    summary="Run Identity Data Verification",
    description="Run Google OCR number-match verification for CNIC or driving license using the already uploaded image."
)
async def verify_identity_data(
    doc_type: DocumentTypeEnum,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run OCR identity-data verification on demand for driver flow."""
    return await _run_sanitized(service.verify_identity_data_service(
        db=db,
        user_id=current_user.id,
        doc_type=doc_type,
        user_role=current_user.role,
    ))


# ============================================================================
# VERIFICATION STATUS ENDPOINT
# ============================================================================

@router.get(
    "/status/{user_id}",
    response_model=Dict[str, Any],
    summary="Get Verification Status",
    description="""
    Get verification status for a user.
    
    **Authorization:** User can only view their own status (unless admin).
    
    **Returns:**
    - Map of document types to status
    - Overall verification status
    - List of missing documents
    
    **Document Status Values:**
    - `pending`: Uploaded, awaiting AI/admin review
    - `under_review`: Being reviewed by AI or admin
    - `verified`: Successfully verified
    - `rejected`: Verification failed
    - `expired`: Verification expired
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "user_id": "123...",
            "verifications": {
                "cnic": "verified",
                "driving_license": "verified",
                "vehicle_registration": "pending"
            },
            "overall_verified": false,
            "missing_documents": []
        }
    }
    ```
    """
)
async def get_verification_status(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get verification status for user."""
    from app.models.enums import UserRole
    if str(current_user.id) != str(user_id) and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="You can only view your own verification status")

    requested_user_role = current_user.role if str(current_user.id) == str(user_id) else None
    return await _run_sanitized(service.get_verification_status_service(
        db=db,
        user_id=user_id,
        user_role=requested_user_role,
    ))


# ============================================================================
# ADMIN REVIEW ENDPOINT
# ============================================================================

@router.put(
    "/review/{verification_id}",
    response_model=Dict[str, Any],
    summary="Admin Review Verification",
    description="""
    Admin manual review and approval/rejection of verification.
    
    **Authorization:** Admin only
    
    **Use Cases:**
    - AI confidence score 70-90% (flagged for review)
    - User dispute of auto-rejection
    - Manual quality check
    
    **Decision Options:**
    - `approved`: Approve verification (status → verified)
    - `rejected`: Reject verification (status → rejected)
    
    **Process:**
    1. Admin reviews document
    2. Makes decision (approve/reject)
    3. Adds remarks
    4. System updates status
    5. User notified
    
    **Example Request:**
    ```json
    {
        "decision": "approved",
        "remarks": "Document verified successfully"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "verification_id": "789...",
            "decision": "approved",
            "status": "verified",
            "reviewed_by": "admin-123...",
            "message": "Verification approved successfully"
        }
    }
    ```
    """
)
async def admin_review_verification(
    verification_id: UUID,
    request: AdminReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Admin review verification."""
    from app.models.enums import UserRole
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return await _run_sanitized(service.admin_review_verification_service(
        db=db,
        verification_id=verification_id,
        admin_user_id=current_user.id,
        decision=request.decision,
        remarks=request.remarks
    ))


# ============================================================================
# MANUAL AI VERIFICATION ENDPOINT (TEST MODE)
# ============================================================================

@router.post(
    "/ai/verify",
    response_model=Dict[str, Any],
    summary="Trigger AI Verification Manually",
    description="""
    Manually trigger AI verification (test/development mode).
    
    **Use Cases:**
    - Testing AI verification pipeline
    - Reprocessing failed verifications
    - Force reanalysis with updated AI models
    
    **Process:**
    1. Retrieve existing verification record
    2. Rerun OCR text extraction
    3. Rerun face matching (if applicable)
    4. Recalculate confidence score
    5. Update verification status
    6. Create new verification attempt
    
    **Parameters:**
    - `verification_id`: Verification record ID
    - `force_reprocess`: Force reprocessing even if already verified (default: false)
    
    **Returns:**
    - AI decision (approved/flagged/rejected)
    - Confidence scores (overall, OCR, face match)
    - Extracted document data
    - AI remarks
    
    **Example Request:**
    ```json
    {
        "verification_id": "789...",
        "force_reprocess": false
    }
    ```
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "verification_id": "789...",
            "decision": "approved",
            "confidence": 0.95,
            "ocr_confidence": 0.97,
            "face_match_score": 0.93,
            "extracted_data": {
                "cnic_number": "12345-6789012-3",
                "name": "JOHN DOE"
            },
            "remarks": "Document verified with high confidence"
        }
    }
    ```
    """
)
async def trigger_ai_verification(
    request: AIVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Manually trigger AI verification."""
    return await _run_sanitized(service.trigger_ai_verification_service(
        db=db,
        verification_id=request.verification_id,
        force_reprocess=request.force_reprocess
    ))


# ============================================================================
# ADMIN QUEUE ENDPOINT (Prompt 4 Requirement)
# ============================================================================

@router.get(
    "/admin/queue",
    response_model=Dict[str, Any],
    summary="Get Admin Review Queue",
    description="""
    Get paginated list of verifications pending manual review.
    
    **Admin Only Endpoint**
    
    Filters available:
    - status: Filter by verification status (default: manual_review)
    - min_score: Minimum confidence score
    - max_score: Maximum confidence score
    - date_from: Start date for filtering
    - date_to: End date for filtering
    - document_type: Filter by document type (cnic, license, etc.)
    - page: Page number (default: 1)
    - limit: Items per page (default: 20, max: 100)
    
    **Returns:**
    Paginated list of pending verifications with:
    - User information
    - Document details
    - Confidence scores
    - Submission timestamps
    - Review priority
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "items": [
                {
                    "verification_id": "...",
                    "user_id": "...",
                    "user_name": "John Doe",
                    "document_type": "cnic",
                    "confidence_score": 0.82,
                    "face_match_score": 0.78,
                    "submitted_at": "2025-12-07T10:30:00Z",
                    "priority": "medium"
                }
            ],
            "total": 45,
            "page": 1,
            "limit": 20,
            "pages": 3
        }
    }
    ```
    """
)
async def get_admin_review_queue(
    status_filter: Optional[str] = "manual_review",
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    document_type: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get admin review queue with filtering and pagination.
    
    Only accessible by admin users.
    """
    # Ensure admin access
    if current_user.role.value != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from sqlalchemy import select, and_
    from .models import UserVerification, VerificationStatusEnum
    from datetime import datetime as dt
    
    try:
        # Build query
        status_normalized = (status_filter or "manual_review").strip().lower()
        if status_normalized in {"manual_review", "under_review"}:
            queue_status = VerificationStatusEnum.UNDER_REVIEW
        elif status_normalized in {s.value for s in VerificationStatusEnum}:
            queue_status = VerificationStatusEnum(status_normalized)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status_filter: {status_filter}"
            )

        filters = [UserVerification.status == queue_status]
        
        # Apply filters
        if min_score is not None:
            filters.append(UserVerification.ai_confidence >= min_score)
        
        if max_score is not None:
            filters.append(UserVerification.ai_confidence <= max_score)
        
        if document_type:
            try:
                requested_doc_type = DocumentTypeEnum(document_type.strip().lower())
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid document_type: {document_type}"
                ) from exc
            filters.append(UserVerification.doc_type == requested_doc_type)
        
        if date_from:
            try:
                date_from_dt = dt.fromisoformat(date_from.replace('Z', '+00:00'))
                filters.append(UserVerification.created_at >= date_from_dt)
            except:
                pass
        
        if date_to:
            try:
                date_to_dt = dt.fromisoformat(date_to.replace('Z', '+00:00'))
                filters.append(UserVerification.created_at <= date_to_dt)
            except:
                pass
        
        # Count total
        count_query = select(UserVerification).where(and_(*filters))
        count_result = await db.execute(count_query)
        total = len(count_result.scalars().all())
        
        # Calculate pagination
        offset = (page - 1) * limit
        limit = min(limit, 100)  # Max 100 items per page
        
        # Get paginated results
        query = (
            select(UserVerification)
            .where(and_(*filters))
            .order_by(UserVerification.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        
        result = await db.execute(query)
        verifications = result.scalars().all()
        
        # Get user details for each verification
        from app.modules.users import crud as users_crud
        
        items = []
        for v in verifications:
            # Get user details
            user = await users_crud.get_user_profile(db, v.user_id)
            
            # Determine priority based on confidence score
            if v.ai_confidence < 0.75:
                priority = "high"
            elif v.ai_confidence < 0.85:
                priority = "medium"
            else:
                priority = "low"
            
            items.append({
                "verification_id": str(v.id),
                "user_id": str(v.user_id),
                "user_name": user.full_name if user else "Unknown",
                "document_type": v.doc_type.value,
                "confidence_score": v.ai_confidence,
                "face_match_score": None,  # Extract from metadata if needed
                "submitted_at": v.created_at.isoformat(),
                "priority": priority,
                "remarks": v.ai_remarks
            })
        
        pages = (total + limit - 1) // limit  # Ceiling division
        
        return service.sanitize_verification_client_payload({
            "status": "ok",
            "data": {
                "items": items,
                "total": total,
                "page": page,
                "limit": limit,
                "pages": pages
            },
            "error": None
        })
        
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching admin queue: {str(e)}", exc_info=True)
        raise service.sanitized_verification_http_exception(HTTPException(
            status_code=500,
            detail=f"Failed to fetch admin queue: {str(e)}"
        ))

# === VERIFICATION FUNCTIONALITY END ===
