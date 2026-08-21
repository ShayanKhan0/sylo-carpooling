"""
Pydantic schemas for Payments Module.

Schemas for request validation and response serialization:
- Wallet management (create, balance, top-up, deduct, transfer)
- Transaction tracking
- Payout requests
- Payment webhook verification

Author: Smart Carpooling Development Team
Created: 2025-11-08
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, validator, ConfigDict

from .models import TransactionTypeEnum, TransactionStatusEnum, PayoutStatusEnum, PayoutMethodEnum


# ============================================================================
# WALLET SCHEMAS
# ============================================================================

class WalletCreate(BaseModel):
    """
    Request schema for creating a new wallet.
    
    Typically called automatically when user registers.
    Manual creation only for admin/special cases.
    """
    user_id: UUID = Field(..., description="User ID to create wallet for")
    initial_balance: Optional[Decimal] = Field(
        default=Decimal("0.00"),
        ge=0,
        description="Initial balance (default 0.00 PKR)"
    )
    currency: Optional[str] = Field(
        default="PKR",
        min_length=3,
        max_length=3,
        description="Currency code (ISO 4217)"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "initial_balance": 0.00,
                "currency": "PKR"
            }
        }
    )


class WalletResponse(BaseModel):
    """
    Response schema for wallet information.
    
    Returns complete wallet details including balance and metadata.
    """
    id: UUID
    user_id: UUID
    balance: Decimal = Field(..., description="Current wallet balance")
    currency: str
    created_at: datetime
    last_updated: datetime
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "987e6543-e21b-12d3-a456-426614174111",
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "balance": 1250.50,
                "currency": "PKR",
                "created_at": "2025-11-08T10:00:00Z",
                "last_updated": "2025-11-08T15:30:00Z"
            }
        }
    )


class WalletBalanceResponse(BaseModel):
    """
    Simplified balance response.
    
    Quick balance check without full wallet details.
    """
    user_id: UUID
    balance: Decimal
    currency: str
    last_updated: datetime
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "balance": 1250.50,
                "currency": "PKR",
                "last_updated": "2025-11-08T15:30:00Z"
            }
        }
    )


# ============================================================================
# TRANSACTION SCHEMAS
# ============================================================================

class TopUpRequest(BaseModel):
    """
    Request schema for adding funds to wallet.
    
    User initiates top-up via payment provider (JazzCash, EasyPaisa, Stripe).
    """
    amount: Decimal = Field(..., gt=0, description="Amount to add (must be positive)")
    provider: str = Field(..., description="Payment provider: jazzcash, easypaisa, stripe")
    provider_txn_id: Optional[str] = Field(None, description="External transaction ID from provider")
    description: Optional[str] = Field(None, max_length=255, description="Optional description")
    
    @validator('amount')
    def validate_amount(cls, v):
        """Ensure amount has at most 2 decimal places."""
        if v.as_tuple().exponent < -2:
            raise ValueError('Amount can have at most 2 decimal places')
        return v
    
    @validator('provider')
    def validate_provider(cls, v):
        """Validate payment provider is supported."""
        allowed_providers = ['jazzcash', 'easypaisa', 'stripe', 'paypal', 'mock']
        if v.lower() not in allowed_providers:
            raise ValueError(f'Provider must be one of: {", ".join(allowed_providers)}')
        return v.lower()
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": 500.00,
                "provider": "jazzcash",
                "provider_txn_id": "JC202511081234567",
                "description": "Wallet top-up via JazzCash"
            }
        }
    )


class PropTopUpRequest(BaseModel):
    """
    Request schema for internal Prop Money top-up.

    This flow bypasses external gateways and credits wallet instantly.
    """
    amount: Decimal = Field(..., gt=0, description="Amount to add (must be positive)")
    description: Optional[str] = Field(None, max_length=255, description="Optional description")

    @validator('amount')
    def validate_amount(cls, v):
        """Ensure amount has at most 2 decimal places."""
        if v.as_tuple().exponent < -2:
            raise ValueError('Amount can have at most 2 decimal places')
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": 500.00,
                "description": "Prop Money top-up"
            }
        }
    )


class PropPayoutRequest(BaseModel):
    """
    Request schema for internal Prop Money payout.

    This flow bypasses external gateways and debits wallet instantly.
    """
    amount: Decimal = Field(..., gt=0, description="Amount to deduct (must be positive)")
    description: Optional[str] = Field(None, max_length=255, description="Optional description")

    @validator('amount')
    def validate_amount(cls, v):
        """Ensure amount has at most 2 decimal places."""
        if v.as_tuple().exponent < -2:
            raise ValueError('Amount can have at most 2 decimal places')
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": 300.00,
                "description": "Prop Money payout"
            }
        }
    )


class DeductRequest(BaseModel):
    """
    Request schema for deducting funds from wallet.
    
    Used for ride payments, fees, or other charges.
    Internal use - typically called by service layer, not directly by users.
    """
    amount: Decimal = Field(..., gt=0, description="Amount to deduct (must be positive)")
    ride_id: Optional[UUID] = Field(None, description="Associated ride ID if ride payment")
    description: Optional[str] = Field(None, max_length=255, description="Deduction reason")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional context (commission, etc.)")
    
    @validator('amount')
    def validate_amount(cls, v):
        """Ensure amount has at most 2 decimal places."""
        if v.as_tuple().exponent < -2:
            raise ValueError('Amount can have at most 2 decimal places')
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": 150.00,
                "ride_id": "abc12345-e89b-12d3-a456-426614174222",
                "description": "Payment for ride #12345",
                "metadata": {
                    "driver_share": 120.00,
                    "platform_commission": 30.00
                }
            }
        }
    )


class TransferRequest(BaseModel):
    """
    Request schema for transferring funds between wallets.
    
    Used for driver payouts or peer-to-peer transfers.
    """
    from_user_id: UUID = Field(..., description="Source user ID")
    to_user_id: UUID = Field(..., description="Destination user ID")
    amount: Decimal = Field(..., gt=0, description="Amount to transfer")
    description: Optional[str] = Field(None, max_length=255, description="Transfer purpose")
    
    @validator('amount')
    def validate_amount(cls, v):
        """Ensure amount has at most 2 decimal places."""
        if v.as_tuple().exponent < -2:
            raise ValueError('Amount can have at most 2 decimal places')
        return v
    
    @validator('to_user_id')
    def validate_different_users(cls, v, values):
        """Ensure from_user_id != to_user_id."""
        if 'from_user_id' in values and v == values['from_user_id']:
            raise ValueError('Cannot transfer to the same user')
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "from_user_id": "123e4567-e89b-12d3-a456-426614174000",
                "to_user_id": "987e6543-e21b-12d3-a456-426614174111",
                "amount": 200.00,
                "description": "Refund for canceled ride"
            }
        }
    )


class TransactionCreate(BaseModel):
    """
    Internal schema for creating transactions.
    
    Used by service layer to log all wallet operations.
    """
    wallet_id: UUID
    user_id: UUID
    amount: Decimal
    type: TransactionTypeEnum
    ride_id: Optional[UUID] = None
    provider: Optional[str] = None
    provider_txn_id: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    metadata: Optional[str] = None  # JSON string


class TransactionResponse(BaseModel):
    """
    Response schema for transaction details.
    
    Complete transaction information for history and tracking.
    """
    id: UUID
    txn_id: str
    wallet_id: UUID
    user_id: UUID
    amount: Decimal
    type: TransactionTypeEnum
    status: TransactionStatusEnum
    ride_id: Optional[UUID] = None
    payout_id: Optional[UUID] = None
    provider: Optional[str] = None
    provider_txn_id: Optional[str] = None
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "111e2222-e33b-44d5-a666-777777777777",
                "txn_id": "TXN-20251108-ABC123",
                "wallet_id": "987e6543-e21b-12d3-a456-426614174111",
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "amount": 500.00,
                "type": "topup",
                "status": "completed",
                "ride_id": None,
                "payout_id": None,
                "provider": "jazzcash",
                "provider_txn_id": "JC202511081234567",
                "description": "Wallet top-up via JazzCash",
                "created_at": "2025-11-08T10:00:00Z",
                "updated_at": "2025-11-08T10:00:30Z",
                "completed_at": "2025-11-08T10:00:30Z"
            }
        }
    )


class TransactionListResponse(BaseModel):
    """
    Response schema for transaction history.
    
    Paginated list of user transactions.
    """
    transactions: List[TransactionResponse]
    total_count: int
    page: int
    page_size: int
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "transactions": [
                    {
                        "id": "111e2222-e33b-44d5-a666-777777777777",
                        "txn_id": "TXN-20251108-ABC123",
                        "wallet_id": "987e6543-e21b-12d3-a456-426614174111",
                        "user_id": "123e4567-e89b-12d3-a456-426614174000",
                        "amount": 500.00,
                        "type": "topup",
                        "status": "completed",
                        "provider": "jazzcash",
                        "description": "Wallet top-up",
                        "created_at": "2025-11-08T10:00:00Z",
                        "updated_at": "2025-11-08T10:00:30Z",
                        "completed_at": "2025-11-08T10:00:30Z"
                    }
                ],
                "total_count": 25,
                "page": 1,
                "page_size": 20
            }
        }
    )


# ============================================================================
# PAYOUT SCHEMAS
# ============================================================================

class PayoutRequest(BaseModel):
    """
    Request schema for driver payout.
    
    Driver requests to withdraw earnings to their bank/wallet account.
    """
    amount: Decimal = Field(..., gt=0, description="Amount to payout (must be positive)")
    method: PayoutMethodEnum = Field(..., description="Payout method")
    account_details: str = Field(..., min_length=5, description="Bank account or wallet number")
    notes: Optional[str] = Field(None, description="Optional notes")
    
    @validator('amount')
    def validate_amount(cls, v):
        """Ensure amount has at most 2 decimal places and meets minimum."""
        if v.as_tuple().exponent < -2:
            raise ValueError('Amount can have at most 2 decimal places')
        if v < Decimal("500.00"):
            raise ValueError('Minimum payout amount is 500 PKR')
        return v
    
    @validator('account_details')
    def validate_account_details(cls, v, values):
        """Basic validation for account details format."""
        method = values.get('method')
        if method == PayoutMethodEnum.BANK_TRANSFER:
            if not v.replace('-', '').replace(' ', '').isdigit():
                raise ValueError('Bank account must contain only digits, spaces, and dashes')
        elif method in [PayoutMethodEnum.JAZZCASH, PayoutMethodEnum.EASYPAISA]:
            # Pakistani mobile numbers: 03XX-XXXXXXX
            cleaned = v.replace('-', '').replace(' ', '')
            if not (cleaned.isdigit() and len(cleaned) == 11 and cleaned.startswith('03')):
                raise ValueError('Mobile wallet number must be 11-digit Pakistani number starting with 03')
        return v
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": 2500.00,
                "method": "jazzcash",
                "account_details": "03001234567",
                "notes": "Weekly earnings payout"
            }
        }
    )


class PayoutResponse(BaseModel):
    """
    Response schema for payout information.
    
    Complete payout details including status and timestamps.
    """
    id: UUID
    driver_id: UUID
    amount: Decimal
    method: PayoutMethodEnum
    account_details: str = Field(..., description="Masked for security (last 4 digits only)")
    status: PayoutStatusEnum
    provider: Optional[str] = None
    provider_payout_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None
    
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "888e9999-e00a-11b2-c333-444444444444",
                "driver_id": "555e6666-e77b-88d9-a000-111111111111",
                "amount": 2500.00,
                "method": "jazzcash",
                "account_details": "*******4567",  # Masked
                "status": "completed",
                "provider": "jazzcash_api",
                "provider_payout_id": "JC_PAYOUT_20251108_XYZ789",
                "created_at": "2025-11-08T16:00:00Z",
                "updated_at": "2025-11-08T16:05:00Z",
                "processed_at": "2025-11-08T16:02:00Z",
                "completed_at": "2025-11-08T16:05:00Z",
                "notes": "Weekly earnings payout"
            }
        }
    )


class PayoutListResponse(BaseModel):
    """
    Response schema for payout history.
    
    Paginated list of driver payouts.
    """
    payouts: List[PayoutResponse]
    total_count: int
    page: int
    page_size: int
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "payouts": [
                    {
                        "id": "888e9999-e00a-11b2-c333-444444444444",
                        "driver_id": "555e6666-e77b-88d9-a000-111111111111",
                        "amount": 2500.00,
                        "method": "jazzcash",
                        "account_details": "*******4567",
                        "status": "completed",
                        "created_at": "2025-11-08T16:00:00Z",
                        "completed_at": "2025-11-08T16:05:00Z"
                    }
                ],
                "total_count": 8,
                "page": 1,
                "page_size": 20
            }
        }
    )


# ============================================================================
# PAYMENT WEBHOOK SCHEMAS
# ============================================================================

class PaymentWebhook(BaseModel):
    """
    Schema for payment provider webhook callbacks.
    
    Validates incoming webhook data from JazzCash, EasyPaisa, Stripe.
    Each provider has different payload structure - this is a generic wrapper.
    """
    provider: str = Field(..., description="Payment provider name")
    event_type: str = Field(..., description="Webhook event type (payment.success, payment.failed, etc.)")
    txn_id: str = Field(..., description="Our internal transaction ID")
    provider_txn_id: str = Field(..., description="Provider's transaction ID")
    amount: Decimal = Field(..., description="Transaction amount")
    status: str = Field(..., description="Transaction status from provider")
    signature: str = Field(..., description="Webhook signature for verification")
    payload: Dict[str, Any] = Field(..., description="Complete webhook payload")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "provider": "jazzcash",
                "event_type": "payment.success",
                "txn_id": "TXN-20251108-ABC123",
                "provider_txn_id": "JC202511081234567",
                "amount": 500.00,
                "status": "completed",
                "signature": "a1b2c3d4e5f6...",
                "payload": {
                    "transaction_id": "JC202511081234567",
                    "amount": "500.00",
                    "currency": "PKR",
                    "status": "SUCCESS",
                    "timestamp": "2025-11-08T10:00:30Z"
                }
            }
        }
    )


# ============================================================================
# OPERATION RESPONSE SCHEMAS
# ============================================================================

class OperationResponse(BaseModel):
    """
    Generic response for wallet operations.
    
    Standardized response format for top-up, deduct, transfer operations.
    """
    success: bool
    message: str
    transaction_id: Optional[str] = None
    wallet_balance: Optional[Decimal] = None
    transaction: Optional[TransactionResponse] = None
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Wallet top-up successful",
                "transaction_id": "TXN-20251108-ABC123",
                "wallet_balance": 1750.50,
                "transaction": {
                    "id": "111e2222-e33b-44d5-a666-777777777777",
                    "txn_id": "TXN-20251108-ABC123",
                    "amount": 500.00,
                    "type": "topup",
                    "status": "completed",
                    "created_at": "2025-11-08T10:00:00Z"
                }
            }
        }
    )


class RideFareSplit(BaseModel):
    """
    Schema for ride fare commission calculation.
    
    Shows breakdown of ride payment distribution.
    """
    ride_id: UUID
    total_fare: Decimal
    driver_share: Decimal
    platform_commission: Decimal
    commission_percentage: Decimal
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ride_id": "abc12345-e89b-12d3-a456-426614174222",
                "total_fare": 150.00,
                "driver_share": 120.00,
                "platform_commission": 30.00,
                "commission_percentage": 20.0
            }
        }
    )
