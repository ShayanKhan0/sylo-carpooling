"""
Notification Adapters Package

Pluggable adapters for multi-channel notification delivery:
- FCM (Firebase Cloud Messaging) - Push notifications
- SMS (Twilio/Easypaisa) - Text messages  
- Email (SMTP) - Email notifications

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

from app.modules.notifications.adapters.fcm_adapter import FCMAdapter
from app.modules.notifications.adapters.sms_adapter import SMSAdapter
from app.modules.notifications.adapters.email_adapter import EmailAdapter

__all__ = ["FCMAdapter", "SMSAdapter", "EmailAdapter"]
