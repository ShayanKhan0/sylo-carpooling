"""
Audit Logging for Verification Module

Purpose: Provides audit trail for verification events using LogEntry table.
         Logs all verification activities for compliance and debugging.

Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: December 7, 2025
"""

from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.modules.admin.models import LogEntry, LogLevel
import logging

logger = logging.getLogger(__name__)


class VerificationAuditLogger:
    """
    Audit logger for verification module.
    Uses LogEntry table to log verification events for compliance and debugging.
    """

    @staticmethod
    async def log_event(
        db: AsyncSession,
        user_id: UUID,
        action: str,
        details: Dict[str, Any],
        severity: str = "info",
        flagged_by_id: Optional[UUID] = None
    ) -> bool:
        """
        Log a verification event.
        
        Args:
            db: Database session
            user_id: User ID related to this event
            action: Action performed (e.g., "upload", "processing", "approval")
            details: Dictionary with event details
            severity: Event severity ("debug", "info", "warning", "error", "critical")
            flagged_by_id: Optional admin user who flagged (unused for LogEntry compatibility)
        
        Returns:
            True if logged successfully, False otherwise
        """
        try:
            # Map string severity to LogLevel
            severity_map = {
                "debug": LogLevel.DEBUG,
                "info": LogLevel.INFO,
                "warning": LogLevel.WARNING,
                "error": LogLevel.ERROR,
                "critical": LogLevel.CRITICAL
            }
            
            level = severity_map.get(severity.lower(), LogLevel.INFO)
            
            # Create log entry
            log_entry = LogEntry(
                module="verification",
                level=level,
                message=f"Verification {action}",
                user_id=user_id,
                meta_data=details,
                timestamp=datetime.utcnow()
            )
            
            db.add(log_entry)
            await db.commit()
            
            logger.info(f"[AUDIT] Logged verification event: {action} for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"[AUDIT] Failed to log event: {e}")
            await db.rollback()
            return False

    @staticmethod
    async def log_upload(
        db: AsyncSession,
        user_id: UUID,
        document_type: str,
        file_size: int,
        file_name: str
    ) -> bool:
        """
        Log document upload event.
        
        Args:
            db: Database session
            user_id: User who uploaded the document
            document_type: Type of document (cnic, license, etc.)
            file_size: Size of uploaded file in bytes
            file_name: Name of uploaded file
        
        Returns:
            True if logged successfully
        """
        details = {
            "event": "document_upload",
            "document_type": document_type,
            "file_size_bytes": file_size,
            "file_name": file_name,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return await VerificationAuditLogger.log_event(
            db=db,
            user_id=user_id,
            action="document_upload",
            details=details,
            severity="info"
        )

    @staticmethod
    async def log_processing(
        db: AsyncSession,
        user_id: UUID,
        verification_id: UUID,
        ocr_score: float,
        face_score: float,
        overall_score: float,
        decision: str
    ) -> bool:
        """
        Log AI processing results.
        
        Args:
            db: Database session
            user_id: User being verified
            verification_id: Verification record ID
            ocr_score: OCR confidence score
            face_score: Face match score
            overall_score: Combined confidence score
            decision: Verification decision (approved, manual_review, rejected)
        
        Returns:
            True if logged successfully
        """
        details = {
            "event": "verification_processed",
            "verification_id": str(verification_id),
            "ocr_confidence": ocr_score,
            "face_match_score": face_score,
            "overall_confidence": overall_score,
            "decision": decision,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Determine severity based on decision
        severity = "info"
        if decision == "rejected":
            severity = "warning"
        elif decision == "manual_review":
            severity = "info"
        
        return await VerificationAuditLogger.log_event(
            db=db,
            user_id=user_id,
            action="ai_processing",
            details=details,
            severity=severity
        )

    @staticmethod
    async def log_approval(
        db: AsyncSession,
        user_id: UUID,
        verification_id: UUID,
        approved_by_id: Optional[UUID],
        auto_approved: bool,
        notes: Optional[str] = None
    ) -> bool:
        """
        Log verification approval event.
        
        Args:
            db: Database session
            user_id: User who was approved
            verification_id: Verification record ID
            approved_by_id: Admin who approved (None if auto-approved)
            auto_approved: Whether this was auto-approved
            notes: Optional admin notes
        
        Returns:
            True if logged successfully
        """
        details = {
            "event": "verification_approved",
            "verification_id": str(verification_id),
            "auto_approved": auto_approved,
            "approved_by_admin_id": str(approved_by_id) if approved_by_id else None,
            "notes": notes,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return await VerificationAuditLogger.log_event(
            db=db,
            user_id=user_id,
            action="approval",
            details=details,
            severity="info"
        )

    @staticmethod
    async def log_rejection(
        db: AsyncSession,
        user_id: UUID,
        verification_id: UUID,
        rejected_by_id: Optional[UUID],
        reason: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Log verification rejection event.
        
        Args:
            db: Database session
            user_id: User who was rejected
            verification_id: Verification record ID
            rejected_by_id: Admin who rejected (None if auto-rejected)
            reason: Rejection reason
            notes: Optional admin notes
        
        Returns:
            True if logged successfully
        """
        details = {
            "event": "verification_rejected",
            "verification_id": str(verification_id),
            "rejected_by_admin_id": str(rejected_by_id) if rejected_by_id else None,
            "reason": reason,
            "notes": notes,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return await VerificationAuditLogger.log_event(
            db=db,
            user_id=user_id,
            action="rejection",
            details=details,
            severity="warning"
        )

    @staticmethod
    async def log_manual_review_flagged(
        db: AsyncSession,
        user_id: UUID,
        verification_id: UUID,
        reason: str,
        scores: Dict[str, float]
    ) -> bool:
        """
        Log when verification is flagged for manual review.
        
        Args:
            db: Database session
            user_id: User flagged for review
            verification_id: Verification record ID
            reason: Reason for manual review
            scores: Dictionary with OCR and face scores
        
        Returns:
            True if logged successfully
        """
        details = {
            "event": "manual_review_flagged",
            "verification_id": str(verification_id),
            "reason": reason,
            "ocr_score": scores.get("ocr_score", 0.0),
            "face_score": scores.get("face_score", 0.0),
            "overall_score": scores.get("overall_score", 0.0),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return await VerificationAuditLogger.log_event(
            db=db,
            user_id=user_id,
            action="manual_review_flag",
            details=details,
            severity="info"
        )

    @staticmethod
    async def log_admin_review_completed(
        db: AsyncSession,
        user_id: UUID,
        verification_id: UUID,
        admin_id: UUID,
        decision: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Log when admin completes manual review.
        
        Args:
            db: Database session
            user_id: User who was reviewed
            verification_id: Verification record ID
            admin_id: Admin who completed the review
            decision: Review decision (approved/rejected)
            notes: Optional review notes
        
        Returns:
            True if logged successfully
        """
        details = {
            "event": "admin_review_completed",
            "verification_id": str(verification_id),
            "admin_id": str(admin_id),
            "decision": decision,
            "notes": notes,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        severity = "info" if decision == "approved" else "warning"
        
        return await VerificationAuditLogger.log_event(
            db=db,
            user_id=user_id,
            action="admin_review",
            details=details,
            severity=severity
        )

    @staticmethod
    async def get_user_audit_trail(
        db: AsyncSession,
        user_id: UUID,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit trail for a specific user.
        
        Args:
            db: Database session
            user_id: User ID to get audit trail for
            limit: Maximum number of entries to return
        
        Returns:
            List of audit log dictionaries
        """
        try:
            query = select(LogEntry).where(
                LogEntry.user_id == user_id,
                LogEntry.module == "verification"
            ).order_by(LogEntry.timestamp.desc()).limit(limit)
            
            result = await db.execute(query)
            logs = result.scalars().all()
            
            return [
                {
                    "id": str(log.id),
                    "level": log.level.value,
                    "message": log.message,
                    "details": log.meta_data,
                    "timestamp": log.timestamp.isoformat()
                }
                for log in logs
            ]
            
        except Exception as e:
            logger.error(f"[AUDIT] Failed to retrieve audit trail: {e}")
            return []


# Helper function for backward compatibility
async def log_verification_event(
    db: AsyncSession,
    user_id: UUID,
    event_type: str,
    details: Dict[str, Any]
) -> bool:
    """
    Simplified audit logging function.
    
    Args:
        db: Database session
        user_id: User ID
        event_type: Event type string
        details: Event details
    
    Returns:
        True if logged successfully
    """
    return await VerificationAuditLogger.log_event(
        db=db,
        user_id=user_id,
        action=event_type,
        details=details,
        severity="info"
    )
