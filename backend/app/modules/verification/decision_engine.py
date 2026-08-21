"""
Decision Engine - Automated Verification Decision Rules

Purpose: Implements business logic for automated verification approval/rejection.
         Uses OCR confidence and face match scores to make decisions.

Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: December 7, 2025
"""

from typing import Tuple, Dict, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class VerificationDecision(str, Enum):
    """Verification decision outcomes."""
    APPROVED = "approved"
    MANUAL_REVIEW = "manual_review"
    REJECTED = "rejected"


class DecisionReason(str, Enum):
    """Reasons for verification decisions."""
    AUTO_APPROVED = "Auto-approved: High confidence scores"
    HIGH_OCR_GOOD_FACE = "Auto-approved: Excellent OCR and face match"
    GOOD_OVERALL = "Auto-approved: Overall confidence meets threshold"
    
    MANUAL_OCR_BORDERLINE = "Manual review: OCR confidence borderline"
    MANUAL_FACE_BORDERLINE = "Manual review: Face match score borderline"
    MANUAL_MIXED_SCORES = "Manual review: Mixed confidence scores"
    MANUAL_REQUIRES_VERIFICATION = "Manual review: Requires admin verification"
    
    REJECTED_LOW_OCR = "Rejected: Low OCR confidence"
    REJECTED_LOW_FACE = "Rejected: Low face match score"
    REJECTED_POOR_QUALITY = "Rejected: Poor overall quality"
    REJECTED_NO_FACE = "Rejected: No face detected"


class VerificationDecisionEngine:
    """
    Decision engine for automated verification approval.
    
    Implements multi-tier decision logic based on:
    - OCR confidence score (text extraction quality)
    - Face match similarity score
    - Document type requirements
    - Overall confidence threshold
    
    Decision Tiers:
    1. AUTO-APPROVED: High confidence, no human review needed
    2. MANUAL REVIEW: Borderline scores, requires admin review
    3. REJECTED: Low confidence, automatic rejection
    """
    
    def __init__(
        self,
        ocr_approval_threshold: float = 0.90,
        face_approval_threshold: float = 0.85,
        ocr_rejection_threshold: float = 0.75,
        face_rejection_threshold: float = 0.70,
        overall_approval_threshold: float = 0.88
    ):
        """
        Initialize decision engine with thresholds.
        
        Args:
            ocr_approval_threshold: Minimum OCR score for auto-approval (default: 0.90)
            face_approval_threshold: Minimum face score for auto-approval (default: 0.85)
            ocr_rejection_threshold: Maximum OCR score before rejection (default: 0.75)
            face_rejection_threshold: Maximum face score before rejection (default: 0.70)
            overall_approval_threshold: Minimum combined score for approval (default: 0.88)
        """
        self.ocr_approval_threshold = ocr_approval_threshold
        self.face_approval_threshold = face_approval_threshold
        self.ocr_rejection_threshold = ocr_rejection_threshold
        self.face_rejection_threshold = face_rejection_threshold
        self.overall_approval_threshold = overall_approval_threshold
        
        logger.info(
            f"Decision Engine initialized - "
            f"OCR approval: {ocr_approval_threshold}, "
            f"Face approval: {face_approval_threshold}, "
            f"Overall: {overall_approval_threshold}"
        )
    
    async def evaluate(
        self,
        ocr_score: float,
        face_score: float,
        document_type: str = "generic",
        has_face: bool = True
    ) -> Tuple[VerificationDecision, str, float]:
        """
        Evaluate verification and make automated decision.
        
        Decision Logic:
        1. If OCR >= 0.90 AND face >= 0.85: AUTO-APPROVE
        2. If 0.75 <= OCR < 0.90 OR 0.70 <= face < 0.85: MANUAL REVIEW
        3. If OCR < 0.75 OR face < 0.70: REJECT
        4. Special handling for documents without faces (vehicle registration)
        
        Args:
            ocr_score: OCR confidence score (0.0 - 1.0)
            face_score: Face match score (0.0 - 1.0)
            document_type: Type of document being verified
            has_face: Whether document should have a face photo
        
        Returns:
            Tuple of (decision, reason, overall_confidence)
            - decision: VerificationDecision enum
            - reason: Human-readable reason string
            - overall_confidence: Combined confidence score (0.0 - 1.0)
        """
        # Validate inputs
        ocr_score = max(0.0, min(1.0, ocr_score))
        face_score = max(0.0, min(1.0, face_score))
        
        # Calculate overall confidence
        if has_face:
            # Weighted average: 60% face match + 40% OCR
            overall_confidence = (0.6 * face_score) + (0.4 * ocr_score)
        else:
            # Documents without face (vehicle registration): 100% OCR
            overall_confidence = ocr_score
            face_score = 1.0  # Set to 1.0 for documents without face requirement
        
        logger.info(
            f"[DECISION ENGINE] Evaluating - OCR: {ocr_score:.2f}, "
            f"Face: {face_score:.2f}, Overall: {overall_confidence:.2f}, "
            f"Has Face: {has_face}"
        )
        
        # Decision logic
        decision, reason = self._apply_decision_rules(
            ocr_score, face_score, overall_confidence, has_face, document_type
        )
        
        logger.info(f"[DECISION ENGINE] Decision: {decision.value}, Reason: {reason}")
        
        return decision, reason, round(overall_confidence, 3)
    
    def _apply_decision_rules(
        self,
        ocr_score: float,
        face_score: float,
        overall_confidence: float,
        has_face: bool,
        document_type: str
    ) -> Tuple[VerificationDecision, str]:
        """
        Apply decision rules to determine outcome.
        
        Args:
            ocr_score: OCR confidence
            face_score: Face match score
            overall_confidence: Combined score
            has_face: Whether face is required
            document_type: Document type
        
        Returns:
            Tuple of (decision, reason)
        """
        # Rule 1: Check for rejection conditions first
        if ocr_score < self.ocr_rejection_threshold:
            return VerificationDecision.REJECTED, DecisionReason.REJECTED_LOW_OCR.value
        
        if has_face and face_score < self.face_rejection_threshold:
            return VerificationDecision.REJECTED, DecisionReason.REJECTED_LOW_FACE.value
        
        if has_face and face_score < 0.50:
            return VerificationDecision.REJECTED, DecisionReason.REJECTED_NO_FACE.value
        
        if overall_confidence < 0.65:
            return VerificationDecision.REJECTED, DecisionReason.REJECTED_POOR_QUALITY.value
        
        # Rule 2: Check for auto-approval conditions
        if ocr_score >= self.ocr_approval_threshold and face_score >= self.face_approval_threshold:
            return VerificationDecision.APPROVED, DecisionReason.HIGH_OCR_GOOD_FACE.value
        
        if overall_confidence >= self.overall_approval_threshold:
            return VerificationDecision.APPROVED, DecisionReason.GOOD_OVERALL.value
        
        # Rule 3: Everything else goes to manual review
        if ocr_score < self.ocr_approval_threshold:
            return VerificationDecision.MANUAL_REVIEW, DecisionReason.MANUAL_OCR_BORDERLINE.value
        
        if has_face and face_score < self.face_approval_threshold:
            return VerificationDecision.MANUAL_REVIEW, DecisionReason.MANUAL_FACE_BORDERLINE.value
        
        return VerificationDecision.MANUAL_REVIEW, DecisionReason.MANUAL_MIXED_SCORES.value
    
    def get_thresholds(self) -> Dict[str, float]:
        """
        Get current threshold configuration.
        
        Returns:
            Dictionary of threshold values
        """
        return {
            "ocr_approval": self.ocr_approval_threshold,
            "face_approval": self.face_approval_threshold,
            "ocr_rejection": self.ocr_rejection_threshold,
            "face_rejection": self.face_rejection_threshold,
            "overall_approval": self.overall_approval_threshold
        }
    
    def update_thresholds(self, **kwargs) -> None:
        """
        Update threshold values dynamically.
        
        Args:
            **kwargs: Threshold name and new value
        
        Example:
            >>> engine.update_thresholds(ocr_approval_threshold=0.92)
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                if 0.0 <= value <= 1.0:
                    setattr(self, key, value)
                    logger.info(f"Updated {key} to {value}")
                else:
                    logger.warning(f"Invalid threshold value for {key}: {value}")
            else:
                logger.warning(f"Unknown threshold parameter: {key}")


# Factory function to get decision engine
def get_decision_engine(config: Dict[str, Any] = None) -> VerificationDecisionEngine:
    """
    Factory function to get decision engine instance.
    
    Args:
        config: Optional configuration dictionary with threshold values
    
    Returns:
        VerificationDecisionEngine instance
    
    Usage:
        >>> engine = get_decision_engine()
        >>> decision, reason, score = await engine.evaluate(0.92, 0.88)
    """
    if config is None:
        config = {}
    
    return VerificationDecisionEngine(
        ocr_approval_threshold=config.get("ocr_approval_threshold", 0.90),
        face_approval_threshold=config.get("face_approval_threshold", 0.85),
        ocr_rejection_threshold=config.get("ocr_rejection_threshold", 0.75),
        face_rejection_threshold=config.get("face_rejection_threshold", 0.70),
        overall_approval_threshold=config.get("overall_approval_threshold", 0.88)
    )


# Convenience function for backward compatibility
async def evaluate(ocr_score: float, face_score: float) -> Tuple[str, str]:
    """
    Simplified evaluation function for backward compatibility.
    
    Args:
        ocr_score: OCR confidence score (0.0 - 1.0)
        face_score: Face match score (0.0 - 1.0)
    
    Returns:
        Tuple of (status, notes)
        - status: "approved", "manual_review", or "rejected"
        - notes: Human-readable reason
    
    Usage:
        >>> status, notes = await evaluate(0.92, 0.88)
        >>> print(f"Status: {status}, Notes: {notes}")
    """
    engine = get_decision_engine()
    decision, reason, _ = await engine.evaluate(ocr_score, face_score)
    return decision.value, reason
