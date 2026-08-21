"""
Card Payment Adapter (Prompt 10)

Handles credit/debit card payments with mock 3DS redirect.
Sandbox mode enabled by default for testing.

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

import hashlib
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional
from uuid import uuid4

from .base_adapter import BasePaymentAdapter, TopupResponse

logger = logging.getLogger(__name__)


class CardAdapter(BasePaymentAdapter):
    """
    Card payment adapter with mock 3DS redirect and authorization.
    
    Features:
    - Credit/debit card top-ups
    - Mock 3D Secure redirect
    - Fake authorization (success/failure based on card number)
    - Settlement webhook simulation
    - No real card processing (always sandbox)
    
    Test Cards (Sandbox):
    - Success: 4111111111111111 (Visa)
    - Decline: 4000000000000002 (Visa)
    - Insufficient Funds: 4000000000009995 (Visa)
    - Expired: 4000000000000069 (Visa)
    
    Credentials Required:
    - gateway_key: Payment gateway API key
    - gateway_secret: Secret for signature
    """
    
    def __init__(
        self,
        sandbox_mode: bool = True,
        gateway_key: Optional[str] = None,
        gateway_secret: Optional[str] = None
    ):
        """
        Initialize Card adapter.
        
        Args:
            sandbox_mode: Always True for card payments (no production)
            gateway_key: Payment gateway API key
            gateway_secret: Gateway secret for signature
        """
        super().__init__(sandbox_mode=True)  # Always sandbox for card
        self.gateway_key = gateway_key or "sandbox_gateway_key_123"
        self.gateway_secret = gateway_secret or "sandbox_gateway_secret_456"
        
        self.base_url = "https://sandbox-gateway.smartcarpooling.com"
        
        logger.info(f"[CardAdapter] Initialized (always sandbox mode)")
    
    async def create_topup_session(
        self,
        user_id: str,
        amount: Decimal,
        redirect_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TopupResponse:
        """
        Create card payment session with mock 3DS redirect.
        
        Flow:
        1. Generate session ID and transaction ID
        2. Create mock 3DS redirect URL
        3. Return URL for user to enter card details
        4. Mock authorization happens on redirect page
        5. Webhook simulates settlement
        
        Sandbox Mode:
        - Returns mock 3DS URL
        - User enters test card on redirect page
        - Authorization simulated based on card number
        - Settlement webhook sent automatically
        """
        # Validate amount
        if amount <= 0:
            raise ValueError(f"Invalid amount: {amount}")
        
        if amount < Decimal("50.00"):
            raise ValueError("Minimum card top-up amount is PKR 50")
        
        if amount > Decimal("100000.00"):
            raise ValueError("Maximum card top-up amount is PKR 100,000")
        
        # Generate unique IDs
        session_id = f"SESSION{uuid4().hex[:16].upper()}"
        transaction_id = f"CARD{int(datetime.utcnow().timestamp())}{uuid4().hex[:8].upper()}"
        order_id = f"ORD{uuid4().hex[:12].upper()}"
        
        # Expiry time (15 minutes for card sessions)
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        
        # Build payment parameters
        params = {
            "session_id": session_id,
            "transaction_id": transaction_id,
            "order_id": order_id,
            "amount": str(amount),
            "currency": "PKR",
            "redirect_url": redirect_url,
            "user_id": user_id,
            "gateway_key": self.gateway_key,
            "timestamp": datetime.utcnow().isoformat(),
            "expires_at": expires_at.isoformat()
        }
        
        # Generate signature
        signature = self._generate_signature(params)
        params["signature"] = signature
        
        # Build mock 3DS redirect URL
        payment_url = f"{self.base_url}/3ds/redirect?session_id={session_id}&amount={amount}&redirect_url={redirect_url}"
        
        logger.info(f"[CardAdapter] Created card payment session: {session_id}, amount={amount}")
        
        return TopupResponse(
            payment_url=payment_url,
            transaction_id=transaction_id,
            order_id=order_id,
            expires_at=expires_at.isoformat(),
            metadata={
                "provider": "card",
                "session_id": session_id,
                "sandbox": True,
                "test_cards": {
                    "success": "4111111111111111",
                    "decline": "4000000000000002",
                    "insufficient_funds": "4000000000009995",
                    "expired": "4000000000000069"
                },
                "instructions": "Use test card numbers for sandbox testing"
            }
        )
    
    async def validate_webhook(
        self,
        payload: Dict[str, Any],
        signature: str
    ) -> bool:
        """
        Validate card payment webhook signature.
        
        Signature Algorithm:
        1. Extract payload fields (session_id, transaction_id, status, amount)
        2. Sort fields alphabetically
        3. Build string: key1=value1&key2=value2
        4. Generate SHA256 with gateway_secret
        5. Compare with provided signature
        
        Args:
            payload: Webhook body from payment gateway
            signature: X-Gateway-Signature header
        
        Returns:
            True if signature matches
        """
        try:
            # Extract required fields
            fields_to_sign = {
                "session_id": payload.get("session_id", ""),
                "transaction_id": payload.get("transaction_id", ""),
                "order_id": payload.get("order_id", ""),
                "amount": payload.get("amount", ""),
                "status": payload.get("status", ""),
                "card_last4": payload.get("card_last4", ""),
                "timestamp": payload.get("timestamp", "")
            }
            
            # Generate expected signature
            expected_signature = self._generate_signature(fields_to_sign)
            
            # Compare signatures
            is_valid = expected_signature.lower() == signature.lower()
            
            if is_valid:
                logger.info(f"[CardAdapter] Valid webhook signature for session: {payload.get('session_id')}")
            else:
                logger.warning(f"[CardAdapter] Invalid webhook signature for session: {payload.get('session_id')}")
            
            return is_valid
        
        except Exception as e:
            logger.error(f"[CardAdapter] Webhook validation error: {e}")
            return False
    
    async def execute_payout(
        self,
        user_id: str,
        amount: Decimal,
        account_number: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute payout to card (bank transfer).
        
        Card payouts are processed as bank transfers (ACH/IBAN).
        Sandbox Mode:
        - Simulates successful transfer
        - No actual money transfer
        - Returns mock transaction ID
        
        Args:
            user_id: Driver user ID
            amount: Payout amount (after commission)
            account_number: IBAN or account number
            metadata: Additional context (bank_name, account_title)
        
        Returns:
            Dict with status, transaction_id, reference
        """
        # Validate amount
        if amount <= 0:
            raise ValueError(f"Invalid payout amount: {amount}")
        
        if amount < Decimal("1000.00"):
            raise ValueError("Minimum card payout amount is PKR 1,000")
        
        # Validate IBAN format (Pakistan)
        if not account_number.startswith("PK") or len(account_number) != 24:
            raise ValueError("Invalid IBAN format (expected: PKXXXXXXXXXXXXXXXXXXXX - 24 chars)")
        
        # Generate payout ID
        payout_id = f"PAYOUT{uuid4().hex[:12].upper()}"
        transaction_id = f"BANK{uuid4().hex[:16].upper()}"
        
        # Extract metadata
        bank_name = metadata.get("bank_name", "Unknown Bank") if metadata else "Unknown Bank"
        account_title = metadata.get("account_title", "Unknown") if metadata else "Unknown"
        
        # Mock payout execution (always sandbox)
        logger.info(f"[CardAdapter] Mock bank transfer executed: {payout_id}, amount={amount}, iban={account_number}")
        
        return {
            "status": "completed",
            "transaction_id": transaction_id,
            "payout_id": payout_id,
            "reference": f"BANK{uuid4().hex[:10].upper()}",
            "amount": float(amount),
            "account_number": account_number,
            "bank_name": bank_name,
            "account_title": account_title,
            "message": "Bank transfer completed successfully (sandbox - 1-3 business days)",
            "timestamp": datetime.utcnow().isoformat(),
            "estimated_settlement": (datetime.utcnow() + timedelta(days=2)).isoformat()
        }
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """
        Generate SHA256 signature for card payment parameters.
        
        Algorithm:
        1. Sort params alphabetically by key
        2. Build string: key1=value1&key2=value2
        3. Append gateway_secret
        4. SHA256 hash
        5. Return hex digest
        """
        # Sort params
        sorted_params = sorted(params.items())
        
        # Build concatenated string
        message = "&".join(f"{k}={v}" for k, v in sorted_params if k != "signature")
        
        # Append gateway secret
        message += f"&secret={self.gateway_secret}"
        
        # Generate SHA256 hash
        signature = hashlib.sha256(message.encode()).hexdigest()
        
        return signature
    
    def simulate_authorization(self, card_number: str, amount: Decimal) -> Dict[str, Any]:
        """
        Simulate card authorization based on test card number.
        
        Test Card Logic:
        - 4111111111111111: Success (authorized)
        - 4000000000000002: Decline (generic decline)
        - 4000000000009995: Decline (insufficient funds)
        - 4000000000000069: Decline (expired card)
        - Other: Success (default)
        
        Args:
            card_number: Test card number
            amount: Authorization amount
        
        Returns:
            Dict with status, auth_code, decline_reason
        """
        # Extract last 4 digits
        card_last4 = card_number[-4:] if len(card_number) >= 4 else "0000"
        
        # Simulate authorization
        if card_number == "4111111111111111":
            # Success
            return {
                "status": "authorized",
                "auth_code": f"AUTH{uuid4().hex[:8].upper()}",
                "card_last4": card_last4,
                "card_type": "visa",
                "amount": float(amount),
                "timestamp": datetime.utcnow().isoformat()
            }
        
        elif card_number == "4000000000000002":
            # Generic decline
            return {
                "status": "declined",
                "decline_reason": "do_not_honor",
                "card_last4": card_last4,
                "card_type": "visa",
                "amount": float(amount),
                "timestamp": datetime.utcnow().isoformat()
            }
        
        elif card_number == "4000000000009995":
            # Insufficient funds
            return {
                "status": "declined",
                "decline_reason": "insufficient_funds",
                "card_last4": card_last4,
                "card_type": "visa",
                "amount": float(amount),
                "timestamp": datetime.utcnow().isoformat()
            }
        
        elif card_number == "4000000000000069":
            # Expired card
            return {
                "status": "declined",
                "decline_reason": "expired_card",
                "card_last4": card_last4,
                "card_type": "visa",
                "amount": float(amount),
                "timestamp": datetime.utcnow().isoformat()
            }
        
        else:
            # Default success for any other card
            return {
                "status": "authorized",
                "auth_code": f"AUTH{uuid4().hex[:8].upper()}",
                "card_last4": card_last4,
                "card_type": "visa",
                "amount": float(amount),
                "timestamp": datetime.utcnow().isoformat()
            }
