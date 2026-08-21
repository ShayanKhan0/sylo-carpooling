"""
Base Payment Adapter Interface (Prompt 10)

Abstract base class for all payment provider adapters.
All adapters (Easypaisa, JazzCash, Card) must implement this interface.

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from decimal import Decimal


class TopupResponse:
    """Response from creating a top-up session."""
    
    def __init__(
        self,
        payment_url: str,
        transaction_id: str,
        order_id: str,
        expires_at: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.payment_url = payment_url
        self.transaction_id = transaction_id
        self.order_id = order_id
        self.expires_at = expires_at
        self.metadata = metadata or {}


class BasePaymentAdapter(ABC):
    """
    Abstract base class for payment adapters.
    
    All payment providers must implement:
    - create_topup_session: Initiate payment
    - validate_webhook: Verify webhook signature
    - execute_payout: Process driver payout
    """
    
    def __init__(self, sandbox_mode: bool = True, **credentials):
        """
        Initialize payment adapter.
        
        Args:
            sandbox_mode: If True, use sandbox/test environment
            **credentials: Provider-specific API keys and secrets
        """
        self.sandbox_mode = sandbox_mode
        self.credentials = credentials
    
    @abstractmethod
    async def create_topup_session(
        self,
        user_id: str,
        amount: Decimal,
        redirect_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TopupResponse:
        """
        Create a payment session for wallet top-up.
        
        Args:
            user_id: User requesting top-up
            amount: Amount in PKR
            redirect_url: URL to redirect after payment
            metadata: Additional context (order_id, etc.)
        
        Returns:
            TopupResponse with payment_url and transaction_id
        
        Raises:
            ValueError: If amount is invalid
            Exception: If provider API fails
        """
        pass
    
    @abstractmethod
    async def validate_webhook(
        self,
        payload: Dict[str, Any],
        signature: str
    ) -> bool:
        """
        Validate webhook signature from payment provider.
        
        Args:
            payload: Webhook body
            signature: Provider signature header
        
        Returns:
            True if signature is valid, False otherwise
        """
        pass
    
    @abstractmethod
    async def execute_payout(
        self,
        user_id: str,
        amount: Decimal,
        account_number: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute payout to driver account.
        
        Args:
            user_id: Driver user ID
            amount: Amount in PKR (after commission)
            account_number: Phone number or bank account
            metadata: Additional context
        
        Returns:
            Dict with status, transaction_id, reference
        
        Raises:
            ValueError: If amount or account invalid
            Exception: If payout fails
        """
        pass
    
    def get_provider_name(self) -> str:
        """Get provider name (easypaisa, jazzcash, card)."""
        return self.__class__.__name__.replace("Adapter", "").lower()
