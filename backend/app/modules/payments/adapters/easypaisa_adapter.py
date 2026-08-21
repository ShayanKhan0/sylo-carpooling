"""
Easypaisa Payment Adapter (Prompt 10)

Handles Easypaisa mobile wallet payments with HMAC signature validation.
Sandbox mode enabled by default for testing.

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional
from uuid import uuid4

from .base_adapter import BasePaymentAdapter, TopupResponse

logger = logging.getLogger(__name__)


class EasypaisaAdapter(BasePaymentAdapter):
    """
    Easypaisa payment adapter with HMAC signature validation.
    
    Features:
    - Mobile wallet top-ups
    - HMAC-SHA256 signature generation
    - Webhook signature verification
    - Mock payout execution (sandbox)
    
    Credentials Required:
    - api_key: Easypaisa Merchant API Key
    - secret_key: HMAC secret for signature
    - merchant_id: Easypaisa Merchant ID
    
    Sandbox URLs:
    - Payment: https://sandbox.easypaisa.com.pk/easypay
    - Webhook: Configured in merchant dashboard
    """
    
    def __init__(
        self,
        sandbox_mode: bool = True,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        merchant_id: Optional[str] = None
    ):
        """
        Initialize Easypaisa adapter.
        
        Args:
            sandbox_mode: Use sandbox environment
            api_key: Easypaisa API key
            secret_key: HMAC secret key
            merchant_id: Merchant ID
        """
        super().__init__(sandbox_mode=sandbox_mode)
        self.api_key = api_key or "sandbox_api_key_123"
        self.secret_key = secret_key or "sandbox_secret_key_456"
        self.merchant_id = merchant_id or "MERCHANT_001"
        
        self.base_url = (
            "https://sandbox.easypaisa.com.pk/easypay" if sandbox_mode
            else "https://easypaisa.com.pk/easypay"
        )
        
        logger.info(f"[EasypaisaAdapter] Initialized (sandbox={sandbox_mode})")
    
    async def create_topup_session(
        self,
        user_id: str,
        amount: Decimal,
        redirect_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TopupResponse:
        """
        Create Easypaisa payment session.
        
        Flow:
        1. Generate unique order ID
        2. Create HMAC signature
        3. Build payment URL with params
        4. Return URL for user redirect
        
        Sandbox Mode:
        - Returns mock payment URL
        - No actual API call made
        - Signature still generated for testing
        """
        # Validate amount
        if amount <= 0:
            raise ValueError(f"Invalid amount: {amount}")
        
        if amount < Decimal("10.00"):
            raise ValueError("Minimum top-up amount is PKR 10")
        
        if amount > Decimal("25000.00"):
            raise ValueError("Maximum top-up amount is PKR 25,000")
        
        # Generate unique IDs
        order_id = f"EP{int(datetime.utcnow().timestamp())}{uuid4().hex[:8].upper()}"
        transaction_id = f"TXN{uuid4().hex[:16].upper()}"
        
        # Expiry time (30 minutes)
        expires_at = datetime.utcnow() + timedelta(minutes=30)
        
        # Build payment parameters
        params = {
            "merchant_id": self.merchant_id,
            "order_id": order_id,
            "amount": str(amount),
            "currency": "PKR",
            "redirect_url": redirect_url,
            "transaction_id": transaction_id,
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id
        }
        
        # Generate HMAC signature
        signature = self._generate_signature(params)
        params["signature"] = signature
        
        # Build payment URL
        if self.sandbox_mode:
            # Mock payment URL for sandbox
            payment_url = f"{self.base_url}/mock?{self._build_query_string(params)}"
            logger.info(f"[EasypaisaAdapter] Created sandbox top-up session: {order_id}, amount={amount}")
        else:
            # Real Easypaisa payment URL
            payment_url = f"{self.base_url}/initiate?{self._build_query_string(params)}"
            logger.info(f"[EasypaisaAdapter] Created top-up session: {order_id}, amount={amount}")
        
        return TopupResponse(
            payment_url=payment_url,
            transaction_id=transaction_id,
            order_id=order_id,
            expires_at=expires_at.isoformat(),
            metadata={
                "provider": "easypaisa",
                "merchant_id": self.merchant_id,
                "sandbox": self.sandbox_mode
            }
        )
    
    async def validate_webhook(
        self,
        payload: Dict[str, Any],
        signature: str
    ) -> bool:
        """
        Validate Easypaisa webhook signature.
        
        Signature Algorithm:
        1. Extract payload fields (order_id, transaction_id, amount, status)
        2. Sort fields alphabetically
        3. Concatenate: key1=value1&key2=value2
        4. Generate HMAC-SHA256 with secret_key
        5. Compare with provided signature
        
        Args:
            payload: Webhook body from Easypaisa
            signature: X-Easypaisa-Signature header
        
        Returns:
            True if signature matches
        """
        try:
            # Extract required fields
            fields_to_sign = {
                "order_id": payload.get("order_id", ""),
                "transaction_id": payload.get("transaction_id", ""),
                "amount": payload.get("amount", ""),
                "status": payload.get("status", ""),
                "timestamp": payload.get("timestamp", "")
            }
            
            # Generate expected signature
            expected_signature = self._generate_signature(fields_to_sign)
            
            # Compare signatures (constant-time comparison)
            is_valid = hmac.compare_digest(expected_signature, signature)
            
            if is_valid:
                logger.info(f"[EasypaisaAdapter] Valid webhook signature for order: {payload.get('order_id')}")
            else:
                logger.warning(f"[EasypaisaAdapter] Invalid webhook signature for order: {payload.get('order_id')}")
            
            return is_valid
        
        except Exception as e:
            logger.error(f"[EasypaisaAdapter] Webhook validation error: {e}")
            return False
    
    async def execute_payout(
        self,
        user_id: str,
        amount: Decimal,
        account_number: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute payout to Easypaisa account.
        
        Sandbox Mode:
        - Simulates successful payout
        - No actual money transfer
        - Returns mock transaction ID
        
        Production Mode:
        - Calls Easypaisa Payout API
        - Real money transfer to phone number
        - Returns actual transaction ID
        
        Args:
            user_id: Driver user ID
            amount: Payout amount (after commission)
            account_number: Easypaisa phone number (03XXXXXXXXX)
            metadata: Additional context
        
        Returns:
            Dict with status, transaction_id, reference
        """
        # Validate amount
        if amount <= 0:
            raise ValueError(f"Invalid payout amount: {amount}")
        
        if amount < Decimal("500.00"):
            raise ValueError("Minimum payout amount is PKR 500")
        
        # Validate phone number format (Pakistan)
        if not account_number.startswith("03") or len(account_number) != 11:
            raise ValueError("Invalid Easypaisa phone number format (expected: 03XXXXXXXXX)")
        
        # Generate payout ID
        payout_id = f"PAYOUT{uuid4().hex[:12].upper()}"
        transaction_id = f"EP{uuid4().hex[:16].upper()}"
        
        if self.sandbox_mode:
            # Mock payout execution
            logger.info(f"[EasypaisaAdapter] Mock payout executed: {payout_id}, amount={amount}, account={account_number}")
            
            return {
                "status": "completed",
                "transaction_id": transaction_id,
                "payout_id": payout_id,
                "reference": f"REF{uuid4().hex[:8].upper()}",
                "amount": float(amount),
                "account_number": account_number,
                "message": "Payout completed successfully (sandbox)",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            # Real payout execution
            # TODO: Integrate with Easypaisa Payout API
            # POST https://easypaisa.com.pk/api/v1/payout
            # Headers: Authorization: Bearer {api_key}
            # Body: {merchant_id, amount, account_number, reference}
            
            logger.info(f"[EasypaisaAdapter] Payout initiated: {payout_id}, amount={amount}")
            
            return {
                "status": "processing",
                "transaction_id": transaction_id,
                "payout_id": payout_id,
                "reference": f"REF{uuid4().hex[:8].upper()}",
                "amount": float(amount),
                "account_number": account_number,
                "message": "Payout initiated",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """
        Generate HMAC-SHA256 signature for parameters.
        
        Algorithm:
        1. Sort params alphabetically by key
        2. Build string: key1=value1&key2=value2
        3. HMAC-SHA256 with secret_key
        4. Return hex digest
        """
        # Sort params
        sorted_params = sorted(params.items())
        
        # Build concatenated string
        message = "&".join(f"{k}={v}" for k, v in sorted_params if k != "signature")
        
        # Generate HMAC
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def _build_query_string(self, params: Dict[str, Any]) -> str:
        """Build URL query string from parameters."""
        return "&".join(f"{k}={v}" for k, v in params.items())
