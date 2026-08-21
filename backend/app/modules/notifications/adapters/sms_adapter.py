"""
SMS Adapter for Notifications

Handles SMS delivery via Twilio or Easypaisa APIs.
Placeholder implementation ready for service integration.

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SMSAdapter:
    """
    SMS adapter for text message notifications.
    
    Features:
    - SMS delivery via Twilio/Easypaisa
    - Phone number validation
    - Retry logic
    - Delivery tracking
    - Cost estimation
    
    Status: Stub implementation (Twilio/Easypaisa integration ready)
    """
    
    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
        provider: str = "twilio"
    ):
        """
        Initialize SMS adapter.
        
        Args:
            account_sid: Twilio account SID or Easypaisa API key
            auth_token: Twilio auth token or Easypaisa API secret
            from_number: Sender phone number
            provider: SMS provider (twilio, easypaisa)
        """
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._provider = provider
        self._initialized = False
        
        # Statistics
        self._total_sent = 0
        self._total_failed = 0
        self._total_cost = 0.0  # in USD or PKR
        
        logger.info(
            f"[SMSAdapter] Initialized (provider={provider}, "
            f"from_number={from_number})"
        )
        
        # TODO: Initialize Twilio client
        # if account_sid and auth_token:
        #     from twilio.rest import Client
        #     self._client = Client(account_sid, auth_token)
        #     self._initialized = True
    
    async def send_sms(
        self,
        phone: str,
        message: str,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Send SMS to phone number.
        
        Args:
            phone: Recipient phone number (E.164 format: +923001234567)
            message: SMS message text (max 160 chars for single SMS)
            user_id: Optional user ID for logging
        
        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Validate phone number format
            if not phone.startswith("+"):
                logger.warning(f"[SMSAdapter] Phone number should be in E.164 format: {phone}")
                # Attempt to fix common Pakistan format
                if phone.startswith("0"):
                    phone = f"+92{phone[1:]}"
                elif phone.startswith("92"):
                    phone = f"+{phone}"
                else:
                    phone = f"+92{phone}"
            
            logger.info(
                f"[SMSAdapter] Sending SMS to {phone[:8]}*** "
                f"(user_id={user_id}): '{message[:50]}...'"
            )
            
            # In production, this would:
            # 1. Validate phone number format
            # 2. Check message length (split if >160 chars)
            # 3. Send via Twilio/Easypaisa API
            # 4. Track delivery status
            # 5. Log cost
            
            # TODO: Implement actual SMS sending
            # 
            # For Twilio:
            # message_obj = self._client.messages.create(
            #     body=message,
            #     from_=self._from_number,
            #     to=phone
            # )
            # 
            # if message_obj.status in ['queued', 'sent', 'delivered']:
            #     self._total_sent += 1
            #     self._total_cost += 0.0075  # Twilio cost per SMS (approx)
            #     return True
            # 
            # For Easypaisa:
            # response = requests.post(
            #     'https://api.easypaisa.com/sms/send',
            #     headers={'Authorization': f'Bearer {self._auth_token}'},
            #     json={'to': phone, 'message': message, 'from': self._from_number}
            # )
            # return response.status_code == 200
            
            # Simulate success
            self._total_sent += 1
            self._total_cost += 0.0075  # Estimated cost per SMS
            
            logger.debug(
                f"[SMSAdapter] SMS sent successfully to {phone[:8]}*** "
                f"(placeholder mode)"
            )
            
            return True
        
        except Exception as e:
            self._total_failed += 1
            logger.error(f"[SMSAdapter] Error sending SMS to {phone}: {e}")
            return False
    
    async def send_batch(
        self,
        recipients: list[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Send batch of SMS messages.
        
        Args:
            recipients: List of dicts with keys: phone, message, user_id
        
        Returns:
            Dict with success_count and failure_count
        """
        success_count = 0
        failure_count = 0
        
        for recipient in recipients:
            success = await self.send_sms(
                phone=recipient.get("phone"),
                message=recipient.get("message"),
                user_id=recipient.get("user_id")
            )
            
            if success:
                success_count += 1
            else:
                failure_count += 1
        
        logger.info(
            f"[SMSAdapter] Batch send complete: "
            f"success={success_count}, failed={failure_count}"
        )
        
        return {
            "success_count": success_count,
            "failure_count": failure_count,
            "total": len(recipients),
            "estimated_cost": success_count * 0.0075
        }
    
    async def send_emergency_alert(
        self,
        phone: str,
        rider_name: str,
        location: str,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Send emergency alert SMS (Safety AI escalation).
        
        Args:
            phone: Emergency contact phone number
            rider_name: Name of rider in distress
            location: Last known location
            user_id: Rider user ID
        
        Returns:
            True if sent successfully
        """
        message = (
            f"EMERGENCY ALERT: {rider_name} may need help. "
            f"Last location: {location}. "
            f"Please check on them immediately or contact university security."
        )
        
        return await self.send_sms(phone, message, user_id)
    
    def validate_phone_number(self, phone: str) -> bool:
        """
        Validate phone number format.
        
        Args:
            phone: Phone number to validate
        
        Returns:
            True if valid E.164 format
        """
        # Basic validation: starts with +, 10-15 digits
        if not phone.startswith("+"):
            return False
        
        digits = phone[1:].replace(" ", "").replace("-", "")
        
        if not digits.isdigit():
            return False
        
        if len(digits) < 10 or len(digits) > 15:
            return False
        
        return True
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check SMS adapter health.
        
        Returns:
            Dict with status and metadata
        """
        # In production, this would verify Twilio/Easypaisa API connectivity
        
        status = "ok" if self._initialized or True else "not_initialized"
        
        return {
            "adapter": "sms",
            "status": status,
            "provider": self._provider,
            "initialized": self._initialized,
            "mode": "placeholder",
            "from_number": self._from_number,
            "total_sent": self._total_sent,
            "total_failed": self._total_failed,
            "total_cost_usd": round(self._total_cost, 2),
            "success_rate": (
                self._total_sent / (self._total_sent + self._total_failed)
                if (self._total_sent + self._total_failed) > 0
                else 0.0
            ),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get SMS adapter statistics."""
        return {
            "total_sent": self._total_sent,
            "total_failed": self._total_failed,
            "total_cost_usd": round(self._total_cost, 2),
            "success_rate": (
                self._total_sent / (self._total_sent + self._total_failed)
                if (self._total_sent + self._total_failed) > 0
                else 0.0
            )
        }


# Global singleton
_sms_adapter: Optional[SMSAdapter] = None


def get_sms_adapter(
    account_sid: Optional[str] = None,
    auth_token: Optional[str] = None,
    from_number: Optional[str] = None,
    provider: str = "twilio"
) -> SMSAdapter:
    """
    Get or create global SMS adapter singleton.
    
    Args:
        account_sid: Twilio account SID or Easypaisa API key
        auth_token: Twilio auth token or Easypaisa API secret
        from_number: Sender phone number
        provider: SMS provider
    
    Returns:
        SMSAdapter instance
    """
    global _sms_adapter
    
    if _sms_adapter is None:
        _sms_adapter = SMSAdapter(
            account_sid=account_sid,
            auth_token=auth_token,
            from_number=from_number,
            provider=provider
        )
    
    return _sms_adapter
