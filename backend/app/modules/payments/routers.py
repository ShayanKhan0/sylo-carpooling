"""
API Router for Payments Module.

Endpoints for wallet management, transactions, and payouts.
All endpoints protected by JWT authentication.

Author: Smart Carpooling Development Team
Created: 2025-11-08
"""

from typing import Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User

from .schemas import (
    WalletCreate, WalletResponse, TopUpRequest, DeductRequest,
    TransactionResponse, TransactionListResponse, PayoutRequest,
    PayoutResponse, PaymentWebhook, OperationResponse,
    PropTopUpRequest, PropPayoutRequest
)
from . import service, crud


payments_router = APIRouter(prefix="/api/v1/payments", tags=["Payments"])


# ============================================================================
# WALLET ENDPOINTS
# ============================================================================

@payments_router.post(
    "/wallet/create",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Create Wallet",
    description="""
    Create a new wallet for user.
    
    **Typically called automatically** during user registration.
    Manual creation only for admin/special cases.
    
    **Business Rules:**
    - One wallet per user (enforced by unique constraint)
    - Initial balance defaults to 0.00 PKR
    - Wallet auto-created with user account
    
    **Returns:**
    - Wallet details with ID, balance, currency
    
    **Example Request:**
    ```json
    {
        "user_id": "123e4567-e89b-12d3-a456-426614174000",
        "initial_balance": 0.00,
        "currency": "PKR"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "id": "987...",
            "user_id": "123...",
            "balance": 0.00,
            "currency": "PKR",
            "created_at": "2025-11-08T10:00:00Z"
        }
    }
    ```
    """
)
async def create_wallet(
    request: WalletCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create wallet for user."""
    return await service.initialize_wallet_service(db, request.user_id)


@payments_router.get(
    "/wallet/balance/{user_id}",
    response_model=Dict[str, Any],
    summary="Get Wallet Balance",
    description="""
    Get current wallet balance for user.
    
    **Authorization:** User can only view their own balance (unless admin).
    
    **Returns:**
    - Current balance
    - Currency
    - Last updated timestamp
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "user_id": "123...",
            "balance": 1250.50,
            "currency": "PKR",
            "last_updated": "2025-11-08T15:30:00Z"
        }
    }
    ```
    """
)
async def get_balance(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get wallet balance."""
    from app.models.enums import UserRole
    if str(current_user.id) != str(user_id) and current_user.role != UserRole.ADMIN:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="You can only view your own wallet balance")
    return await service.get_balance_service(db, user_id)


@payments_router.post(
    "/wallet/topup",
    response_model=Dict[str, Any],
    summary="Top-Up Wallet",
    description="""
    Add funds to wallet via payment provider.
    
    **Payment Providers Supported:**
    - JazzCash (jazzcash)
    - EasyPaisa (easypaisa)
    - Stripe (stripe)
    - PayPal (paypal)
    - Mock (mock) - for testing
    
    **Process:**
    1. Validate payment provider
    2. Create pending transaction
    3. Process payment with provider
    4. Update wallet balance if successful
    5. Update transaction status
    
    **Requirements:**
    - Amount must be positive
    - Amount limited to 2 decimal places
    - Provider must be configured with API keys
    
    **Example Request:**
    ```json
    {
        "amount": 500.00,
        "provider": "jazzcash",
        "provider_txn_id": "JC202511081234567",
        "description": "Wallet top-up via JazzCash"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "success": true,
            "message": "Top-up successful",
            "transaction_id": "TXN-20251108-ABC123",
            "wallet_balance": 1750.50,
            "amount_added": 500.00
        }
    }
    ```
    
    **Error Response:**
    ```json
    {
        "status": "error",
        "data": null,
        "error": "Payment declined by provider"
    }
    ```
    """
)
async def topup_wallet(
    request: TopUpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Top-up wallet via payment provider."""
    return await service.topup_wallet_service(db, current_user.id, request)


@payments_router.post(
    "/wallet/prop/topup",
    response_model=Dict[str, Any],
    summary="Prop Money Top-Up",
    description="""
    Internal Prop Money top-up.

    Credits wallet balance immediately and logs an auditable transaction.
    This endpoint is intentionally separate from real payment gateways.
    """,
)
async def prop_topup_wallet(
    request: PropTopUpRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Top-up wallet instantly via internal Prop Money."""
    return await service.prop_topup_wallet_service(db, current_user.id, request)


@payments_router.post(
    "/wallet/prop/payout",
    response_model=Dict[str, Any],
    summary="Prop Money Payout",
    description="""
    Internal Prop Money payout.

    Deducts wallet balance immediately and logs an auditable transaction.
    Returns 400 if available balance is insufficient.
    """,
)
async def prop_payout_wallet(
    request: PropPayoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Deduct wallet balance instantly via internal Prop Money payout."""
    return await service.prop_payout_wallet_service(db, current_user.id, request)


@payments_router.post(
    "/wallet/deduct",
    response_model=Dict[str, Any],
    summary="Deduct from Wallet",
    description="""
    Deduct funds from wallet.
    
    **Use Cases:**
    - Ride payment
    - Platform fees
    - Cancellation charges
    - Other deductions
    
    **Validation:**
    - Checks sufficient balance before deduction
    - Amount must be positive
    - Creates transaction record for audit trail
    
    **Authorization:** Only authorized services can deduct funds.
    
    **Example Request:**
    ```json
    {
        "amount": 150.00,
        "ride_id": "abc12345-e89b-12d3-a456-426614174222",
        "description": "Payment for ride #12345",
        "metadata": {
            "driver_share": 120.00,
            "platform_commission": 30.00
        }
    }
    ```
    """
)
async def deduct_from_wallet(
    request: DeductRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Deduct funds from wallet."""
    return await service.deduct_from_wallet_service(db, current_user.id, request)


# ============================================================================
# TRANSACTION ENDPOINTS
# ============================================================================

@payments_router.get(
    "/wallet/transactions",
    response_model=Dict[str, Any],
    summary="Get Transaction History",
    description="""
    Get user transaction history with pagination and filters.
    
    **Query Parameters:**
    - `type`: Filter by transaction type (topup, deduct, refund, etc.)
    - `status`: Filter by status (pending, completed, failed)
    - `limit`: Records per page (default 20, max 100)
    - `offset`: Pagination offset (default 0)
    
    **Returns:**
    - List of transactions ordered by created_at DESC
    - Total count
    - Page info
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "transactions": [
                {
                    "id": "111...",
                    "txn_id": "TXN-20251108-ABC123",
                    "amount": 500.00,
                    "type": "topup",
                    "status": "completed",
                    "provider": "jazzcash",
                    "created_at": "2025-11-08T10:00:00Z"
                }
            ],
            "total_count": 25,
            "page": 1,
            "page_size": 20
        }
    }
    ```
    """
)
async def get_transactions(
    type: Optional[str] = Query(None, description="Filter by transaction type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100, description="Records per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get transaction history."""
    from .models import TransactionTypeEnum, TransactionStatusEnum
    
    txn_type = None
    if type:
        try:
            txn_type = TransactionTypeEnum(type)
        except ValueError:
            pass
    
    txn_status = None
    if status:
        try:
            txn_status = TransactionStatusEnum(status)
        except ValueError:
            pass
    
    transactions = await crud.get_user_transactions(
        db, current_user.id, txn_type, txn_status, limit, offset
    )
    
    total_count = await crud.get_transaction_count(
        db, current_user.id, txn_type, txn_status
    )
    
    return {
        "status": "ok",
        "data": {
            "transactions": [TransactionResponse.model_validate(t).model_dump() for t in transactions],
            "total_count": total_count,
            "page": (offset // limit) + 1,
            "page_size": limit
        },
        "error": None
    }


# ============================================================================
# PAYOUT ENDPOINTS
# ============================================================================

@payments_router.post(
    "/payout/request",
    response_model=Dict[str, Any],
    status_code=status.HTTP_201_CREATED,
    summary="Request Payout",
    description="""
    Request driver payout to bank account or mobile wallet.
    
    **Requirements:**
    - Minimum amount: 500 PKR
    - Driver must be verified
    - Sufficient wallet balance
    - Valid payment method details
    
    **Payout Methods:**
    - bank_transfer: Bank account transfer
    - jazzcash: JazzCash mobile wallet
    - easypaisa: EasyPaisa mobile wallet
    - stripe: Stripe Connect
    - paypal: PayPal transfer
    
    **Process:**
    1. Validate driver and balance
    2. Create payout record (status: PENDING)
    3. Deduct from driver wallet
    4. Queue for processing
    5. Transfer to payment provider
    6. Update status (COMPLETED/FAILED)
    
    **Account Details Format:**
    - Bank: Account number (digits, spaces, dashes)
    - JazzCash/EasyPaisa: 03XX-XXXXXXX (11-digit Pakistani mobile)
    
    **Example Request:**
    ```json
    {
        "amount": 2500.00,
        "method": "jazzcash",
        "account_details": "03001234567",
        "notes": "Weekly earnings payout"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "status": "ok",
        "data": {
            "id": "888...",
            "driver_id": "555...",
            "amount": 2500.00,
            "method": "jazzcash",
            "account_details": "*******4567",
            "status": "pending",
            "created_at": "2025-11-08T16:00:00Z"
        }
    }
    ```
    
    **Security:**
    - Account details masked in response (last 4 digits only)
    - Rate limiting applied
    - Fraud detection for unusual patterns
    """
)
async def request_payout(
    request: PayoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Request payout / withdrawal."""
    return await service.request_payout_service(db, current_user.id, request)


@payments_router.get(
    "/payout/history",
    response_model=Dict[str, Any],
    summary="Get Payout History",
    description="""
    Get driver payout history.
    
    **Query Parameters:**
    - `status`: Filter by payout status
    - `limit`: Records per page (default 20, max 100)
    - `offset`: Pagination offset
    
    **Returns:**
    - List of payouts ordered by created_at DESC
    - Total count
    """
)
async def get_payout_history(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get payout history."""
    from .models import PayoutStatusEnum
    
    payout_status = None
    if status:
        try:
            payout_status = PayoutStatusEnum(status)
        except ValueError:
            pass
    
    payouts = await crud.get_driver_payouts(
        db, current_user.id, payout_status, limit, offset
    )
    
    return {
        "status": "ok",
        "data": {
            "payouts": [PayoutResponse.model_validate(p).model_dump() for p in payouts],
            "total_count": len(payouts),
            "page": (offset // limit) + 1,
            "page_size": limit
        },
        "error": None
    }


# ============================================================================
# WEBHOOK ENDPOINTS
# ============================================================================

@payments_router.post(
    "/webhook/verify",
    response_model=Dict[str, Any],
    summary="Payment Webhook Verification",
    description="""
    Verify and process payment provider webhooks.
    
    **Supported Providers:**
    - JazzCash
    - EasyPaisa
    - Stripe
    - PayPal
    
    **Security:**
    - Signature verification using HMAC-SHA256
    - Validates webhook authenticity
    - Prevents replay attacks
    
    **Process:**
    1. Verify webhook signature
    2. Extract transaction ID and status
    3. Update transaction record
    4. Update wallet balance if needed
    5. Send confirmation to provider
    
    **Example Webhook:**
    ```json
    {
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
            "status": "SUCCESS"
        }
    }
    ```
    
    **Note:** This endpoint typically called by payment providers, not clients.
    """
)
async def verify_payment_webhook(
    webhook: PaymentWebhook,
    db: AsyncSession = Depends(get_db)
):
    """Verify and process payment webhook."""
    return await service.verify_payment_webhook_service(db, webhook)
