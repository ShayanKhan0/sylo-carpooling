"""
Escalation Manager for Safety AI

3-stage escalation workflow:
1. In-app popup (OK / Not OK / Need Assistance)
2. Emergency contacts notification
3. Admin dashboard alert
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.modules.safety_ai.detector import AnomalyResult
from app.modules.safety_ai.rule_engine import get_rule_engine

logger = logging.getLogger(__name__)


class EscalationStage(str, Enum):
    """Escalation stages"""
    STAGE_1_POPUP = "stage1_popup"
    STAGE_2_CONTACTS = "stage2_emergency_contacts"
    STAGE_3_ADMIN = "stage3_admin_alert"


class EscalationStatus(str, Enum):
    """Escalation status"""
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class EscalationAlert:
    """Escalation alert data structure"""
    
    def __init__(
        self,
        ride_id: UUID,
        anomaly: AnomalyResult,
        stage: EscalationStage,
        status: EscalationStatus = EscalationStatus.PENDING
    ):
        self.ride_id = ride_id
        self.anomaly = anomaly
        self.stage = stage
        self.status = status
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.actions_taken: List[str] = []
        self.timeout_at: Optional[datetime] = None
        self.user_response: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "ride_id": str(self.ride_id),
            "anomaly": self.anomaly.to_dict(),
            "stage": self.stage.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "actions_taken": self.actions_taken,
            "timeout_at": self.timeout_at.isoformat() if self.timeout_at else None,
            "user_response": self.user_response
        }


class EscalationManager:
    """
    Manages 3-stage escalation workflow for safety anomalies.
    
    Stage 1: In-app popup notification with driver response options
    Stage 2: SMS/FCM to emergency contacts + university security
    Stage 3: Admin dashboard flag for intervention
    """
    
    def __init__(self):
        """Initialize escalation manager"""
        self.rule_engine = get_rule_engine()
        self.active_alerts: Dict[UUID, EscalationAlert] = {}
        
        logger.info("✅ EscalationManager initialized")
    
    async def handle_anomaly(
        self,
        ride_id: UUID,
        anomaly: AnomalyResult,
        db: AsyncSession,
        rider_id: Optional[UUID] = None,
        driver_id: Optional[UUID] = None
    ) -> EscalationAlert:
        """
        Handle anomaly detection and initiate escalation.
        
        Args:
            ride_id: Ride UUID
            anomaly: Detected anomaly
            db: Database session
            rider_id: Rider user ID
            driver_id: Driver user ID
            
        Returns:
            EscalationAlert instance
        """
        # Check if alert already exists
        if ride_id in self.active_alerts:
            existing_alert = self.active_alerts[ride_id]
            
            # Update anomaly if severity increased
            if anomaly.severity == "high" and existing_alert.anomaly.severity != "high":
                existing_alert.anomaly = anomaly
                existing_alert.updated_at = datetime.utcnow()
                logger.warning(f"Updated alert for ride {ride_id} to high severity")
            
            return existing_alert
        
        # Create new alert
        alert = EscalationAlert(
            ride_id=ride_id,
            anomaly=anomaly,
            stage=EscalationStage.STAGE_1_POPUP
        )
        
        self.active_alerts[ride_id] = alert
        
        # Start Stage 1: In-app popup
        await self._execute_stage1(alert, rider_id, driver_id, db)
        
        return alert
    
    async def _execute_stage1(
        self,
        alert: EscalationAlert,
        rider_id: Optional[UUID],
        driver_id: Optional[UUID],
        db: AsyncSession
    ):
        """
        Stage 1: Send in-app popup notification.
        
        Args:
            alert: Escalation alert
            rider_id: Rider user ID
            driver_id: Driver user ID
            db: Database session
        """
        timeout_seconds = self.rule_engine.get_rule_value("escalation_stage1_timeout_seconds", 60)
        alert.timeout_at = datetime.utcnow() + timedelta(seconds=timeout_seconds)
        
        # Send push notification to rider's device
        try:
            notification_payload = {
                "type": "safety_alert",
                "title": "Safety Alert",
                "body": f"{alert.anomaly.severity.upper()}: {alert.anomaly.details.get('description', 'Anomaly detected')}",
                "action": "popup",
                "options": ["OK - I'm safe", "Not OK - Need help", "Emergency assistance"],
                "ride_id": str(alert.ride_id),
                "anomaly_type": alert.anomaly.anomaly_type
            }
            
            # TODO: Integrate with FCM/Push notification service
            await self._send_push_notification(rider_id, notification_payload)
            
            alert.actions_taken.append(f"Sent in-app popup at {datetime.utcnow().isoformat()}")
            logger.info(f"📱 Stage 1: Sent in-app popup to rider {rider_id} for ride {alert.ride_id}")
        
        except Exception as e:
            logger.error(f"Failed to send Stage 1 popup: {e}", exc_info=True)
    
    async def handle_user_response(
        self,
        ride_id: UUID,
        response: str,
        db: AsyncSession
    ) -> bool:
        """
        Handle user response to in-app popup.
        
        Args:
            ride_id: Ride UUID
            response: User response ("ok", "not_ok", "emergency")
            db: Database session
            
        Returns:
            True if alert resolved, False if escalated
        """
        if ride_id not in self.active_alerts:
            logger.warning(f"No active alert for ride {ride_id}")
            return False
        
        alert = self.active_alerts[ride_id]
        alert.user_response = response
        alert.updated_at = datetime.utcnow()
        
        if response == "ok":
            # User confirmed safety - resolve alert
            alert.status = EscalationStatus.RESOLVED
            alert.actions_taken.append(f"User confirmed safety at {datetime.utcnow().isoformat()}")
            logger.info(f"✅ Alert resolved for ride {ride_id} - user confirmed safety")
            
            # Clean up after resolution
            del self.active_alerts[ride_id]
            return True
        
        elif response in ["not_ok", "emergency"]:
            # Immediate escalation to Stage 2
            alert.status = EscalationStatus.ESCALATED
            alert.actions_taken.append(f"User requested help at {datetime.utcnow().isoformat()}")
            
            await self._execute_stage2(alert, db)
            return False
        
        return False
    
    async def _execute_stage2(
        self,
        alert: EscalationAlert,
        db: AsyncSession
    ):
        """
        Stage 2: Notify emergency contacts and university security.
        
        Args:
            alert: Escalation alert
            db: Database session
        """
        timeout_seconds = self.rule_engine.get_rule_value("escalation_stage2_timeout_seconds", 300)
        alert.stage = EscalationStage.STAGE_2_CONTACTS
        alert.timeout_at = datetime.utcnow() + timedelta(seconds=timeout_seconds)
        
        try:
            # Fetch rider's emergency contacts
            from app.modules.auth.models import User
            
            result = await db.execute(
                select(User).where(
                    User.id.in_(
                        select(User.id).join(...)  # TODO: Join with rides table
                    )
                )
            )
            rider = result.scalar_one_or_none()
            
            if rider and rider.emergency_contacts:
                # Send SMS to emergency contacts
                for contact in rider.emergency_contacts:
                    sms_message = (
                        f"SAFETY ALERT: {rider.full_name} may need assistance. "
                        f"Last known location: [GPS coordinates]. "
                        f"Anomaly: {alert.anomaly.details.get('description')}. "
                        f"Please check on them immediately."
                    )
                    
                    await self._send_sms(contact.phone, sms_message)
                    alert.actions_taken.append(f"SMS sent to {contact.name} at {datetime.utcnow().isoformat()}")
            
            # Notify university security
            security_message = {
                "ride_id": str(alert.ride_id),
                "anomaly_type": alert.anomaly.anomaly_type,
                "severity": alert.anomaly.severity,
                "rider_name": rider.full_name if rider else "Unknown",
                "location": f"[{alert.anomaly.details.get('lat', 0)}, {alert.anomaly.details.get('lng', 0)}]",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            await self._notify_university_security(security_message)
            alert.actions_taken.append(f"Notified university security at {datetime.utcnow().isoformat()}")
            
            logger.warning(f"🚨 Stage 2: Notified emergency contacts and security for ride {alert.ride_id}")
        
        except Exception as e:
            logger.error(f"Failed to execute Stage 2: {e}", exc_info=True)
            # Escalate immediately to Stage 3 if Stage 2 fails
            await self._execute_stage3(alert, db)
    
    async def _execute_stage3(
        self,
        alert: EscalationAlert,
        db: AsyncSession
    ):
        """
        Stage 3: Create admin dashboard alert.
        
        Args:
            alert: Escalation alert
            db: Database session
        """
        alert.stage = EscalationStage.STAGE_3_ADMIN
        alert.status = EscalationStatus.ESCALATED
        
        try:
            # Create admin flag in database
            from app.models.admin_flag import AdminFlag  # TODO: Verify model exists
            
            admin_flag = AdminFlag(
                ride_id=alert.ride_id,
                flag_type="safety_alert",
                severity=alert.anomaly.severity,
                description=alert.anomaly.details.get('description', 'Safety anomaly detected'),
                anomaly_type=alert.anomaly.anomaly_type,
                anomaly_confidence=alert.anomaly.confidence,
                escalation_stage=alert.stage.value,
                actions_taken=alert.actions_taken,
                created_at=datetime.utcnow()
            )
            
            db.add(admin_flag)
            await db.commit()
            
            alert.actions_taken.append(f"Admin flag created at {datetime.utcnow().isoformat()}")
            logger.critical(f"🚨🚨 Stage 3: Admin alert created for ride {alert.ride_id}")
        
        except Exception as e:
            logger.error(f"Failed to execute Stage 3: {e}", exc_info=True)
    
    async def check_timeouts(self, db: AsyncSession):
        """
        Check for escalation timeouts and auto-escalate.
        
        Should be called periodically by background task.
        
        Args:
            db: Database session
        """
        now = datetime.utcnow()
        
        for ride_id, alert in list(self.active_alerts.items()):
            if alert.status == EscalationStatus.RESOLVED:
                continue
            
            if alert.timeout_at and now > alert.timeout_at:
                logger.warning(f"⏰ Timeout reached for ride {ride_id}, escalating from {alert.stage}")
                
                if alert.stage == EscalationStage.STAGE_1_POPUP:
                    alert.actions_taken.append(f"Stage 1 timeout at {now.isoformat()}")
                    await self._execute_stage2(alert, db)
                
                elif alert.stage == EscalationStage.STAGE_2_CONTACTS:
                    alert.actions_taken.append(f"Stage 2 timeout at {now.isoformat()}")
                    await self._execute_stage3(alert, db)
    
    async def resolve_alert(
        self,
        ride_id: UUID,
        resolved_by: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Manually resolve an alert (typically by admin).
        
        Args:
            ride_id: Ride UUID
            resolved_by: User who resolved (admin username/ID)
            notes: Resolution notes
            
        Returns:
            True if resolved successfully
        """
        if ride_id not in self.active_alerts:
            return False
        
        alert = self.active_alerts[ride_id]
        alert.status = EscalationStatus.RESOLVED
        alert.updated_at = datetime.utcnow()
        alert.actions_taken.append(f"Resolved by {resolved_by} at {datetime.utcnow().isoformat()}")
        
        if notes:
            alert.actions_taken.append(f"Notes: {notes}")
        
        logger.info(f"✅ Alert for ride {ride_id} resolved by {resolved_by}")
        
        # Clean up
        del self.active_alerts[ride_id]
        return True
    
    async def _send_push_notification(
        self,
        user_id: Optional[UUID],
        payload: Dict
    ):
        """
        Send push notification via FCM.
        
        Args:
            user_id: Target user ID
            payload: Notification payload
        """
        # TODO: Integrate with Firebase Cloud Messaging
        # Placeholder implementation
        logger.info(f"📱 Would send push notification to user {user_id}: {payload['title']}")
    
    async def _send_sms(
        self,
        phone: str,
        message: str
    ):
        """
        Send SMS via Twilio or similar service.
        
        Args:
            phone: Phone number
            message: SMS content
        """
        # TODO: Integrate with Twilio or AWS SNS
        # Placeholder implementation
        logger.info(f"📞 Would send SMS to {phone}: {message[:50]}...")
    
    async def _notify_university_security(
        self,
        message: Dict
    ):
        """
        Notify university security team.
        
        Args:
            message: Alert details
        """
        # TODO: Integrate with university security system (email, webhook, etc.)
        # Placeholder implementation
        logger.info(f"🚓 Would notify university security: {message}")
    
    def get_active_alerts(self) -> List[Dict]:
        """Get all active alerts"""
        return [alert.to_dict() for alert in self.active_alerts.values()]
    
    def get_alert(self, ride_id: UUID) -> Optional[Dict]:
        """Get specific alert"""
        alert = self.active_alerts.get(ride_id)
        return alert.to_dict() if alert else None


# Global escalation manager instance
_escalation_manager_instance: Optional[EscalationManager] = None


def get_escalation_manager() -> EscalationManager:
    """Get global escalation manager instance (singleton)"""
    global _escalation_manager_instance
    
    if _escalation_manager_instance is None:
        _escalation_manager_instance = EscalationManager()
    
    return _escalation_manager_instance
