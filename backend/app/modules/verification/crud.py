"""
CRUD operations for Verification Module.

Database operations for user verifications and verification attempts.

Author: Smart Carpooling Development Team
Created: 2025-11-08
"""

from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select, and_, or_, desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from app.core.config import settings

from .models import UserVerification, VerificationAttempt, DocumentTypeEnum, VerificationStatusEnum
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# USER VERIFICATION CRUD
# ============================================================================

async def create_verification(
    db: AsyncSession,
    user_id: UUID,
    doc_type: DocumentTypeEnum,
    doc_path: str,
    doc_number: Optional[str] = None,
    ai_confidence: Optional[float] = None,
    ai_remarks: Optional[str] = None,
    verification_status: VerificationStatusEnum = VerificationStatusEnum.PENDING,
    metadata: Optional[str] = None
) -> UserVerification:
    """
    Create new verification record.
    
    Args:
        db: Database session
        user_id: User ID
        doc_type: Document type
        doc_path: Path to uploaded document
        doc_number: Extracted document number
        ai_confidence: AI confidence score
        ai_remarks: AI-generated remarks
        verification_status: Initial status
        metadata: Additional metadata (JSON string)
    
    Returns:
        Created UserVerification record
    
    Raises:
        HTTPException: If database operation fails
    """
    try:
        # Calculate expiry date (1 year from now for verified documents)
        expires_at = None
        verified_at = None
        if verification_status == VerificationStatusEnum.VERIFIED:
            expires_at = datetime.utcnow() + timedelta(days=365)
            verified_at = datetime.utcnow()

        verification = UserVerification(
            user_id=user_id,
            doc_type=doc_type,
            doc_path=doc_path,
            doc_number=doc_number,
            status=verification_status,
            ai_confidence=ai_confidence,
            ai_remarks=ai_remarks,
            verified_at=verified_at,
            expires_at=expires_at,
            meta_data=metadata
        )

        db.add(verification)
        await db.commit()
        await db.refresh(verification)

        logger.info(f"Verification created: {verification.id} for user {user_id}, type {doc_type}")
        return verification

    except IntegrityError as e:
        await db.rollback()
        error_text = str(e)

        # Compatibility path for legacy schema that enforces UNIQUE(user_id).
        if "user_verifications_user_id_key" in error_text:
            try:
                existing_result = await db.execute(
                    select(UserVerification).where(UserVerification.user_id == user_id)
                )
                existing = existing_result.scalar_one_or_none()

                if existing:
                    existing.doc_type = doc_type
                    existing.doc_path = doc_path
                    existing.doc_number = doc_number
                    existing.status = verification_status
                    existing.ai_confidence = ai_confidence
                    existing.ai_remarks = ai_remarks
                    existing.meta_data = metadata
                    existing.updated_at = datetime.utcnow()

                    if verification_status == VerificationStatusEnum.VERIFIED:
                        existing.verified_at = datetime.utcnow()
                        existing.expires_at = datetime.utcnow() + timedelta(days=365)
                    else:
                        existing.verified_at = None
                        existing.expires_at = None

                    await db.commit()
                    await db.refresh(existing)

                    logger.warning(
                        "Legacy UNIQUE(user_id) detected on user_verifications; updated existing row %s",
                        existing.id,
                    )
                    return existing
            except Exception as fallback_exc:
                await db.rollback()
                logger.error("Legacy upsert fallback failed: %s", fallback_exc)

        logger.error(f"Error creating verification: {error_text}")
        detail_message = "Failed to create verification record"
        if settings.DEBUG:
            detail_message = f"{detail_message}: {error_text}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail_message
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating verification: {str(e)}")
        detail_message = "Failed to create verification record"
        if settings.DEBUG:
            detail_message = f"{detail_message}: {str(e)}"
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail_message
        )


async def get_verification_by_id(
    db: AsyncSession,
    verification_id: UUID,
    include_attempts: bool = False
) -> Optional[UserVerification]:
    """
    Get verification by ID.
    
    Args:
        db: Database session
        verification_id: Verification ID
        include_attempts: Include verification attempts
    
    Returns:
        UserVerification or None
    """
    try:
        query = select(UserVerification).where(UserVerification.id == verification_id)
        
        if include_attempts:
            query = query.options(selectinload(UserVerification.attempts))
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error fetching verification {verification_id}: {str(e)}")
        return None


async def get_user_verifications(
    db: AsyncSession,
    user_id: UUID,
    doc_type: Optional[DocumentTypeEnum] = None,
    status_filter: Optional[VerificationStatusEnum] = None,
    include_attempts: bool = False
) -> List[UserVerification]:
    """
    Get all verifications for a user.
    
    Args:
        db: Database session
        user_id: User ID
        doc_type: Filter by document type
        status_filter: Filter by status
        include_attempts: Include verification attempts
    
    Returns:
        List of UserVerification records
    """
    try:
        query = select(UserVerification).where(UserVerification.user_id == user_id)
        
        if doc_type:
            query = query.where(UserVerification.doc_type == doc_type)
        
        if status_filter:
            query = query.where(UserVerification.status == status_filter)
        
        if include_attempts:
            query = query.options(selectinload(UserVerification.attempts))
        
        query = query.order_by(desc(UserVerification.created_at))
        
        result = await db.execute(query)
        return list(result.scalars().all())
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error fetching verifications for user {user_id}: {str(e)}")
        return []


async def update_verification_status(
    db: AsyncSession,
    verification_id: UUID,
    new_status: VerificationStatusEnum,
    admin_remarks: Optional[str] = None,
    reviewed_by: Optional[UUID] = None
) -> Optional[UserVerification]:
    """
    Update verification status.
    
    Args:
        db: Database session
        verification_id: Verification ID
        new_status: New status
        admin_remarks: Admin review notes
        reviewed_by: Admin user ID
    
    Returns:
        Updated UserVerification or None
    """
    try:
        verification = await get_verification_by_id(db, verification_id)
        
        if not verification:
            return None
        
        verification.status = new_status
        verification.updated_at = datetime.utcnow()
        
        if admin_remarks:
            verification.admin_remarks = admin_remarks
        
        if reviewed_by:
            verification.reviewed_by = reviewed_by
        
        if new_status == VerificationStatusEnum.VERIFIED:
            verification.verified_at = datetime.utcnow()
            verification.expires_at = datetime.utcnow() + timedelta(days=365)
        
        await db.commit()
        await db.refresh(verification)
        
        logger.info(f"Verification {verification_id} status updated to {new_status}")
        return verification
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating verification status: {str(e)}")
        return None


async def invalidate_user_document_verifications(
    db: AsyncSession,
    user_id: UUID,
    doc_types: List[DocumentTypeEnum],
    reason: str,
) -> int:
    """
    Invalidate existing verification records for selected document types.

    This is used when user identity fields are changed from Profile Edit,
    requiring the user to re-upload updated documents.

    Returns:
        Number of verification rows updated.
    """
    if not doc_types:
        return 0

    try:
        result = await db.execute(
            select(UserVerification).where(
                and_(
                    UserVerification.user_id == user_id,
                    UserVerification.doc_type.in_(doc_types),
                )
            )
        )
        verifications = list(result.scalars().all())

        if not verifications:
            return 0

        for verification in verifications:
            verification.status = VerificationStatusEnum.REJECTED
            verification.admin_remarks = reason
            verification.reviewed_by = None
            verification.verified_at = None
            verification.expires_at = None
            verification.updated_at = datetime.utcnow()

        await db.commit()

        logger.info(
            "Invalidated %s verification record(s) for user %s (docs=%s)",
            len(verifications),
            user_id,
            [doc.value for doc in doc_types],
        )
        return len(verifications)

    except Exception as e:
        await db.rollback()
        logger.error("Error invalidating verifications for user %s: %s", user_id, str(e))
        return 0


async def delete_verification(db: AsyncSession, verification_id: UUID) -> bool:
    """
    Delete verification record.
    
    Args:
        db: Database session
        verification_id: Verification ID
    
    Returns:
        True if deleted, False otherwise
    """
    try:
        verification = await get_verification_by_id(db, verification_id)
        
        if not verification:
            return False
        
        await db.delete(verification)
        await db.commit()
        
        logger.info(f"Verification {verification_id} deleted")
        return True
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting verification: {str(e)}")
        return False


# ============================================================================
# VERIFICATION ATTEMPT CRUD
# ============================================================================

async def create_verification_attempt(
    db: AsyncSession,
    verification_id: UUID,
    attempt_type: str,
    decision: str,
    ai_score: Optional[float] = None,
    face_match_score: Optional[float] = None,
    remarks: Optional[str] = None,
    reviewed_by: Optional[UUID] = None,
    ocr_data: Optional[str] = None,
    metadata: Optional[str] = None
) -> VerificationAttempt:
    """
    Create verification attempt record.
    
    Args:
        db: Database session
        verification_id: Verification ID
        attempt_type: "ai_analysis" or "admin_review"
        decision: "approved", "rejected", or "flagged"
        ai_score: AI confidence score
        face_match_score: Face recognition score
        remarks: Attempt remarks
        reviewed_by: Admin user ID (if manual review)
        ocr_data: OCR extracted data (JSON string)
        metadata: Additional metadata (JSON string)
    
    Returns:
        Created VerificationAttempt record
    """
    try:
        attempt = VerificationAttempt(
            verification_id=verification_id,
            attempt_type=attempt_type,
            decision=decision,
            ai_score=ai_score,
            face_match_score=face_match_score,
            remarks=remarks,
            reviewed_by=reviewed_by,
            ocr_data=ocr_data,
            meta_data=metadata
        )
        
        db.add(attempt)
        await db.commit()
        await db.refresh(attempt)
        
        logger.info(f"Verification attempt created: {attempt.id} for verification {verification_id}")
        return attempt
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating verification attempt: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create verification attempt"
        )


async def get_verification_attempts(
    db: AsyncSession,
    verification_id: UUID
) -> List[VerificationAttempt]:
    """
    Get all attempts for a verification.
    
    Args:
        db: Database session
        verification_id: Verification ID
    
    Returns:
        List of VerificationAttempt records
    """
    try:
        query = select(VerificationAttempt).where(
            VerificationAttempt.verification_id == verification_id
        ).order_by(desc(VerificationAttempt.created_at))
        
        result = await db.execute(query)
        return list(result.scalars().all())
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error fetching verification attempts: {str(e)}")
        return []


async def get_verification_statistics(
    db: AsyncSession,
    user_id: Optional[UUID] = None
) -> dict:
    """
    Get verification statistics.
    
    Args:
        db: Database session
        user_id: Optional user ID to filter by
    
    Returns:
        Dictionary with statistics
    """
    try:
        query = select(UserVerification)
        
        if user_id:
            query = query.where(UserVerification.user_id == user_id)
        
        result = await db.execute(query)
        verifications = list(result.scalars().all())
        
        total = len(verifications)
        verified = sum(1 for v in verifications if v.status == VerificationStatusEnum.VERIFIED)
        pending = sum(1 for v in verifications if v.status == VerificationStatusEnum.PENDING)
        under_review = sum(1 for v in verifications if v.status == VerificationStatusEnum.UNDER_REVIEW)
        rejected = sum(1 for v in verifications if v.status == VerificationStatusEnum.REJECTED)
        
        return {
            "total": total,
            "verified": verified,
            "pending": pending,
            "under_review": under_review,
            "rejected": rejected,
            "verification_rate": round(verified / total * 100, 2) if total > 0 else 0
        }
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error fetching verification statistics: {str(e)}")
        return {"total": 0, "verified": 0, "pending": 0, "under_review": 0, "rejected": 0, "verification_rate": 0}

