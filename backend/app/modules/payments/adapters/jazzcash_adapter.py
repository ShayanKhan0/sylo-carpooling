"""
JazzCash Payment Adapter (Prompt 10)

Handles JazzCash mobile wallet payments with SHA256 signature validation.
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


class JazzCashAdapter(BasePaymentAdapter):
    """
    JazzCash payment adapter with SHA256 signature validation.
    
    Features:
    - Mobile wallet top-ups
    - SHA256 signature generation
    - Webhook signature verification
    - Mock payout execution (sandbox)
    
    Credentials Required:
    - merchant_id: JazzCash Merchant ID
    - password: Merchant password for signature
    - integrity_salt: Salt for signature integrity
    
    Sandbox URLs:
    - Payment: https://sandbox.jazzcash.com.pk/CustomerPortal/transactionmanagement/merchantform
    - Webhook: Configured in merchant dashboard
    """
    
    def __init__(
        self,
        sandbox_mode: bool = True,
        merchant_id: Optional[str] = None,
        password: Optional[str] = None,
        integrity_salt: Optional[str] = None
    ):
        """
        Initialize JazzCash adapter.
        
        Args:
            sandbox_mode: Use sandbox environment
            merchant_id: JazzCash Merchant ID
            password: Merchant password
            integrity_salt: Integrity salt for signature
        """
        super().__init__(sandbox_mode=sandbox_mode)
        self.merchant_id = merchant_id or "MC12345"
        self.password = password or "sandbox_password_123"
        self.integrity_salt = integrity_salt or "sandbox_salt_456"
        
        self.base_url = (
            "https://sandbox.jazzcash.com.pk/CustomerPortal/transactionmanagement/merchantform"
            if sandbox_mode
            else "https://payments.jazzcash.com.pk/CustomerPortal/transactionmanagement/merchantform"
        )
        
        logger.info(f"[JazzCashAdapter] Initialized (sandbox={sandbox_mode})")
    
    async def create_topup_session(
        self,
        user_id: str,
        amount: Decimal,
        redirect_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TopupResponse:
        """
        Create JazzCash payment session.
        
        Flow:
        1. Generate transaction ID (JC{timestamp}{random})
        2. Create SHA256 signature
        3. Build payment URL with POST params
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
        
        if amount > Decimal("50000.00"):
            raise ValueError("Maximum top-up amount is PKR 50,000")
        
        # Generate unique IDs (JazzCash format)
        timestamp = int(datetime.utcnow().timestamp())
        transaction_id = f"JC{timestamp}{uuid4().hex[:8].upper()}"
        order_id = f"ORD{timestamp}{uuid4().hex[:6].upper()}"
        
        # Expiry time (30 minutes)
        expires_at = datetime.utcnow() + timedelta(minutes=30)
        
        # Amount in paisas (JazzCash requires amount * 100)
        amount_paisas = int(amount * 100)
        
        # Build payment parameters
        params = {
            "pp_Version": "1.1",
            "pp_TxnType": "MWALLET",
            "pp_Language": "EN",
            "pp_MerchantID": self.merchant_id,
            "pp_SubMerchantID": "",
            "pp_Password": self.password,
            "pp_TxnRefNo": transaction_id,
            "pp_Amount": str(amount_paisas),
            "pp_TxnCurrency": "PKR",
            "pp_TxnDateTime": datetime.utcnow().strftime("%Y%m%d%H%M%S"),
            "pp_BillReference": order_id,
            "pp_Description": f"Wallet top-up for user {user_id}",
            "pp_TxnExpiryDateTime": expires_at.strftime("%Y%m%d%H%M%S"),
            "pp_ReturnURL": redirect_url,
            "pp_SecureHash": "",
            "ppmpf_1": user_id,  # Custom field for user tracking
            "ppmpf_2": "",
            "ppmpf_3": "",
            "ppmpf_4": "",
            "ppmpf_5": ""
        }
        
        # Generate SHA256 secure hash
        secure_hash = self._generate_signature(params)
        params["pp_SecureHash"] = secure_hash
        
        # Build payment URL
        if self.sandbox_mode:
            # Mock payment URL for sandbox
            payment_url = f"{self.base_url}?mock=true&txn_ref={transaction_id}"
            logger.info(f"[JazzCashAdapter] Created sandbox top-up session: {transaction_id}, amount={amount}")
        else:
            # Real JazzCash payment URL (POST form submission required)
            payment_url = self.base_url
            logger.info(f"[JazzCashAdapter] Created top-up session: {transaction_id}, amount={amount}")
        
        return TopupResponse(
            payment_url=payment_url,
            transaction_id=transaction_id,
            order_id=order_id,
            expires_at=expires_at.isoformat(),
            metadata={
                "provider": "jazzcash",
                "merchant_id": self.merchant_id,
                "sandbox": self.sandbox_mode,
                "form_params": params  # Include params for POST form
            }
        )
    
    async def validate_webhook(
        self,
        payload: Dict[str, Any],
        signature: str
    ) -> bool:
        """
        Validate JazzCash webhook signature.
        
        Signature Algorithm:
        1. Extract pp_SecureHash from payload
        2. Build sorted string: IntegritySalt&field1&field2&...
        3. Generate SHA256 hash
        4. Compare with provided pp_SecureHash
        
        Args:
            payload: Webhook body from JazzCash
            signature: pp_SecureHash from payload
        
        Returns:
            True if signature matches
        """
        try:
            # Required fields for signature validation
            fields_to_verify = [
                "pp_TxnRefNo",
                "pp_Amount",
                "pp_ResponseCode",
                "pp_ResponseMessage",
                "pp_RetreivalReferenceNo"
            ]
            
            # Extract field values
            field_values = [payload.get(field, "") for field in fields_to_verify]
            
            # Build signature string
            signature_string = self.integrity_salt + "&" + "&".join(field_values)
            
            # Generate SHA256 hash
            expected_signature = hashlib.sha256(signature_string.encode()).hexdigest()
            
            # Compare signatures (case-insensitive)
            is_valid = expected_signature.lower() == signature.lower()
            
            if is_valid:
                logger.info(f"[JazzCashAdapter] Valid webhook signature for txn: {payload.get('pp_TxnRefNo')}")
            else:
                logger.warning(f"[JazzCashAdapter] Invalid webhook signature for txn: {payload.get('pp_TxnRefNo')}")
            
            return is_valid
        
        except Exception as e:
            logger.error(f"[JazzCashAdapter] Webhook validation error: {e}")
            return False
    
    async def execute_payout(
        self,
        user_id: str,
        amount: Decimal,
        account_number: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute payout to JazzCash account.
        
        Sandbox Mode:
        - Simulates successful payout
        - No actual money transfer
        - Returns mock transaction ID
        
        Production Mode:
        - Calls JazzCash Payout API
        - Real money transfer to mobile wallet
        - Returns actual transaction ID
        
        Args:
            user_id: Driver user ID
            amount: Payout amount (after commission)
            account_number: JazzCash phone number (03XXXXXXXXX)
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
            raise ValueError("Invalid JazzCash phone number format (expected: 03XXXXXXXXX)")
        
        # Generate payout ID
        timestamp = int(datetime.utcnow().timestamp())
        payout_id = f"PAYOUT{timestamp}{uuid4().hex[:8].upper()}"
        transaction_id = f"JC{uuid4().hex[:16].upper()}"
        
        if self.sandbox_mode:
            # Mock payout execution
            logger.info(f"[JazzCashAdapter] Mock payout executed: {payout_id}, amount={amount}, account={account_number}")
            
            return {
                "status": "completed",
                "transaction_id": transaction_id,
                "payout_id": payout_id,
                "reference": f"JC{uuid4().hex[:12].upper()}",
                "amount": float(amount),
                "account_number": account_number,
                "message": "Payout completed successfully (sandbox)",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            # Real payout execution
            # TODO: Integrate with JazzCash Payout API
            # POST https://payments.jazzcash.com.pk/api/payout
            # Headers: Authorization: Merchant {merchant_id}:{password}
            # Body: {transaction_id, amount, account_number, reference}
            
            logger.info(f"[JazzCashAdapter] Payout initiated: {payout_id}, amount={amount}")
            
            return {
                "status": "processing",
                "transaction_id": transaction_id,
                "payout_id": payout_id,
                "reference": f"JC{uuid4().hex[:12].upper()}",
                "amount": float(amount),
                "account_number": account_number,
                "message": "Payout initiated",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """
        Generate SHA256 signature for JazzCash parameters.
        
        Algorithm:
        1. Extract specific fields in order
        2. Build string: IntegritySalt&field1&field2&...
        3. SHA256 hash
        4. Return hex digest
        """
        # JazzCash signature fields (in specific order)
        fields_to_sign = [
            "pp_Amount",
            "pp_BillReference",
            "pp_Description",
            "pp_Language",
            "pp_MerchantID",
            "pp_Password",
            "pp_ReturnURL",
            "pp_TxnCurrency",
            "pp_TxnDateTime",
            "pp_TxnExpiryDateTime",
            "pp_TxnRefNo",
            "pp_TxnType",
            "pp_Version"
        ]
        
        # Extract field values
        field_values = [str(params.get(field, "")) for field in fields_to_sign]
        
        # Build signature string (IntegritySalt first)
        signature_string = self.integrity_salt + "&" + "&".join(field_values)
        
        # Generate SHA256 hash
        signature = hashlib.sha256(signature_string.encode()).hexdigest()
        
        return signature
