"""
Pydantic Schemas for Prompt 10 - Payments & Wallets

Request/Response schemas for pluggable payment adapters:
- Top-up session initiation
- Webhook confirmation
- Payout execution
- Reconciliation reporting

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field, validator, ConfigDict

from .models import PaymentProviderEnum, PaymentStatusEnum


# ============================================================================
# TOP-UP SCHEMAS (Prompt 10)
# ============================================================================

class TopupSessionRequest(BaseModel):
    """
    Request to initiate top-up payment session.
    
    Used by POST /api/payments/topup endpoint.
    """
    amount: Decimal = Field(
        ...,
        gt=0,
        description="Top-up amount in PKR"
    )
    provider: PaymentProviderEnum = Field(
        ...,
        description="Payment provider (easypaisa, jazzcash, card)"
    )
    redirect_url: str = Field(
        ...,
        min_length=1,
        description="URL to redirect after payment completion"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional context for payment"
    )
    
    @validator("amount")
    def validate_amount(cls, v):
        """Validate amount is reasonable."""
        if v < Decimal("10.00"):
            raise ValueError("Minimum top-up amount is PKR 10")
        if v > Decimal("100000.00"):
            raise ValueError("Maximum top-up amount is PKR 100,000")
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": 1000.00,
                "provider": "easypaisa",
                "redirect_url": "https://app.smartcarpooling.com/payment/confirm",
                "metadata": {"user_note": "Monthly top-up"}
            }
        }
    )


class TopupSessionResponse(BaseModel):
    """
    Response from top-up session creation.
    
    Contains payment URL for user redirect.
    """
    payment_url: str = Field(..., description="URL to redirect user for payment")
    transaction_id: str = Field(..., description="Provider transaction ID")
    order_id: str = Field(..., description="Internal order ID")
    amount: Decimal = Field(..., description="Requested amount")
    commission: Decimal = Field(..., description="Platform commission")
    net_amount: Decimal = Field(..., description="Amount to credit to wallet")
    provider: str = Field(..., description="Payment provider")
    expires_at: str = Field(..., description="Payment session expiry time (ISO 8601)")
    idempotency_key: str = Field(..., description="Idempotency key for duplicate detection")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "payment_url": "https://sandbox.easypaisa.com.pk/easypay/mock?session_id=12345",
                "transaction_id": "EP1733692800ABCD1234",
                "order_id": "ORD123456",
                "amount": 1000.00,
                "commission": 50.00,
                "net_amount": 950.00,
                "provider": "easypaisa",
                "expires_at": "2025-12-08T12:30:00Z",
                "idempotency_key": "idempotency_1733692800_user123"
            }
        }
    )


# ============================================================================
# WEBHOOK SCHEMAS (Prompt 10)
# ============================================================================

class WebhookConfirmRequest(BaseModel):
    """
    Webhook payload from payment provider.
    
    Used by POST /api/payments/webhook/confirm endpoint.
    """
    order_id: str = Field(..., description="Internal order ID")
    transaction_id: str = Field(..., description="Provider transaction ID")
    amount: str = Field(..., description="Transaction amount")
    status: str = Field(..., description="Payment status (success, failed, pending)")
    provider: str = Field(..., description="Payment provider")
    signature: str = Field(..., description="Webhook signature for verification")
    timestamp: str = Field(..., description="Webhook timestamp (ISO 8601)")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional provider-specific data"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "order_id": "ORD123456",
                "transaction_id": "EP1733692800ABCD1234",
                "amount": "950.00",
                "status": "success",
                "provider": "easypaisa",
                "signature": "abc123def456...",
                "timestamp": "2025-12-08T12:15:00Z",
                "metadata": {"card_last4": "1234"}
            }
        }
    )


class WebhookConfirmResponse(BaseModel):
    """
    Response to webhook confirmation.
    
    Acknowledges receipt and processing status.
    """
    success: bool = Field(..., description="Webhook processing status")
    message: str = Field(..., description="Processing message")
    order_id: str = Field(..., description="Internal order ID")
    wallet_balance: Optional[Decimal] = Field(
        default=None,
        description="Updated wallet balance (if successful)"
    )
    cached: bool = Field(
        default=False,
        description="True if this is a cached idempotent response"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Payment confirmed and wallet credited",
                "order_id": "ORD123456",
                "wallet_balance": 5950.00,
                "cached": False
            }
        }
    )


# ============================================================================
# PAYOUT SCHEMAS (Prompt 10)
# ============================================================================

class WithdrawRequest(BaseModel):
    """
    Request to withdraw funds (driver payout).
    
    Used by POST /api/payments/withdraw endpoint.
    """
    amount: Decimal = Field(
        ...,
        gt=0,
        description="Withdrawal amount in PKR"
    )
    provider: PaymentProviderEnum = Field(
        ...,
        description="Payout provider (easypaisa, jazzcash, card)"
    )
    account_number: str = Field(
        ...,
        min_length=1,
        description="Account number or phone number for payout"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional context (bank name, account title, etc.)"
    )
    
    @validator("amount")
    def validate_amount(cls, v):
        """Validate withdrawal amount is reasonable."""
        if v < Decimal("500.00"):
            raise ValueError("Minimum withdrawal amount is PKR 500")
        if v > Decimal("50000.00"):
            raise ValueError("Maximum withdrawal amount is PKR 50,000")
        return v
    
    @validator("account_number")
    def validate_account_number(cls, v, values):
        """Validate account number format based on provider."""
        provider = values.get("provider")
        
        if provider in [PaymentProviderEnum.EASYPAISA, PaymentProviderEnum.JAZZCASH]:
            # Validate phone number format
            if not v.startswith("03") or len(v) != 11:
                raise ValueError("Invalid phone number format (expected: 03XXXXXXXXX)")
        elif provider == PaymentProviderEnum.CARD:
            # Validate IBAN format
            if not v.startswith("PK") or len(v) != 24:
                raise ValueError("Invalid IBAN format (expected: PKXXXXXXXXXXXXXXXXXXXX)")
        
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": 5000.00,
                "provider": "easypaisa",
                "account_number": "03001234567",
                "metadata": {"account_title": "John Doe"}
            }
        }
    )


class WithdrawResponse(BaseModel):
    """
    Response from withdrawal request.
    
    Contains payout status and transaction details.
    """
    success: bool = Field(..., description="Payout initiation status")
    message: str = Field(..., description="Payout message")
    payout_id: str = Field(..., description="Payout ID")
    transaction_id: str = Field(..., description="Provider transaction ID")
    amount: Decimal = Field(..., description="Requested amount")
    commission: Decimal = Field(..., description="Platform commission")
    net_amount: Decimal = Field(..., description="Amount transferred to account")
    provider: str = Field(..., description="Payout provider")
    account_number: str = Field(..., description="Masked account number")
    status: str = Field(..., description="Payout status (completed, processing, failed)")
    estimated_settlement: Optional[str] = Field(
        default=None,
        description="Estimated settlement date (ISO 8601)"
    )
    wallet_balance: Decimal = Field(..., description="Updated wallet balance")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Withdrawal successful",
                "payout_id": "PAYOUT123456",
                "transaction_id": "EP1733692800PAYOUT",
                "amount": 5000.00,
                "commission": 150.00,
                "net_amount": 4850.00,
                "provider": "easypaisa",
                "account_number": "0300123****",
                "status": "completed",
                "estimated_settlement": "2025-12-10T00:00:00Z",
                "wallet_balance": 950.00
            }
        }
    )


# ============================================================================
# RECONCILIATION SCHEMAS (Prompt 10)
# ============================================================================

class ReconciliationReportResponse(BaseModel):
    """
    Reconciliation report response.
    
    Used by GET /api/admin/payments/reconciliation endpoint.
    """
    summary: Dict[str, Any] = Field(..., description="Summary statistics")
    provider_breakdown: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="Per-provider reconciliation data"
    )
    details: Dict[str, List[Dict[str, Any]]] = Field(
        ...,
        description="Detailed mismatch lists"
    )
    generated_at: str = Field(..., description="Report generation time (ISO 8601)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "summary": {
                    "total_intent_amount": 100000.00,
                    "total_transaction_amount": 99500.00,
                    "matched_count": 45,
                    "unmatched_intents_count": 2,
                    "unmatched_transactions_count": 1,
                    "mismatched_amounts_count": 1,
                    "discrepancy": 500.00
                },
                "provider_breakdown": {
                    "easypaisa": {
                        "intent_count": 20,
                        "transaction_count": 20,
                        "intent_amount": 50000.00,
                        "transaction_amount": 50000.00
                    }
                },
                "details": {
                    "unmatched_intents": [],
                    "unmatched_transactions": [],
                    "mismatched_amounts": []
                },
                "generated_at": "2025-12-08T02:00:00Z"
            }
        }
    )


class ReconciliationSingleResponse(BaseModel):
    """
    Single payment intent reconciliation result.
    
    Used by GET /api/admin/payments/reconciliation/{intent_id} endpoint.
    """
    status: str = Field(..., description="Reconciliation status (matched, unmatched)")
    intent: Dict[str, Any] = Field(..., description="Payment intent details")
    transaction: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Matching transaction details (if found)"
    )
    amount_match: Optional[bool] = Field(
        default=None,
        description="True if amounts match"
    )
    difference: Optional[float] = Field(
        default=None,
        description="Amount difference (if mismatch)"
    )
    message: Optional[str] = Field(
        default=None,
        description="Additional message"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "matched",
                "intent": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "amount": 950.00,
                    "provider_txn_id": "EP1733692800ABCD1234",
                    "status": "success"
                },
                "transaction": {
                    "id": "660e8400-e29b-41d4-a716-446655440000",
                    "amount": 950.00,
                    "provider_txn_id": "EP1733692800ABCD1234",
                    "status": "completed"
                },
                "amount_match": True,
                "difference": 0
            }
        }
    )
