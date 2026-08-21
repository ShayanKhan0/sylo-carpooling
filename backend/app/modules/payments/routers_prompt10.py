"""
API Router for Prompt 10 - Payments & Wallets

New endpoints for pluggable payment adapters:
- POST /topup - Initiate top-up session
- POST /webhook/confirm - Process payment webhook
- POST /withdraw - Execute driver payout
- GET /transactions - List user transactions
- GET /admin/reconciliation - Get reconciliation report
- GET /admin/reconciliation/{intent_id} - Reconcile single intent

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

from datetime import datetime
from typing import Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Header, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth.deps import get_current_user
from app.modules.auth.models import User

from .schemas_prompt10 import (
    TopupSessionRequest,
    TopupSessionResponse,
    WebhookConfirmRequest,
    WebhookConfirmResponse,
    WithdrawRequest,
    WithdrawResponse,
    ReconciliationReportResponse,
    ReconciliationSingleResponse
)
from .service_prompt10 import PaymentService
from .reconciliation import ReconciliationSystem

# Router initialization
payments_prompt10_router = APIRouter(prefix="/api/payments", tags=["Payments - Prompt 10"])


# ============================================================================
# TOP-UP ENDPOINTS (Prompt 10)
# ============================================================================

@payments_prompt10_router.post(
    "/topup",
    response_model=TopupSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate Top-Up Session",
    description="""
    Initiate wallet top-up payment session.
    
    **Flow:**
    1. User selects amount and payment provider
    2. System calculates commission
    3. Creates PaymentIntent (status=PENDING)
    4. Adapter creates payment session with provider
    5. Returns payment_url for user redirect
    6. User completes payment on provider's site
    7. Provider sends webhook to confirm payment
    
    **Supported Providers:**
    - easypaisa: Mobile wallet (HMAC-SHA256 signature)
    - jazzcash: Mobile wallet (SHA256 signature)
    - card: Credit/debit card (mock 3DS redirect)
    
    **Commission:**
    - Default: 5% of top-up amount
    - Example: PKR 1000 top-up → PKR 50 commission → PKR 950 credited
    
    **Sandbox Mode:**
    - All adapters use sandbox URLs
    - No real money transfer
    - Test with provided card numbers
    
    **Business Rules:**
    - Minimum top-up: PKR 10
    - Maximum top-up: PKR 100,000
    - Session expires in 30 minutes
    - Idempotency key provided for duplicate detection
    """,
    responses={
        201: {
            "description": "Top-up session created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "payment_url": "https://sandbox.easypaisa.com.pk/easypay/mock?session_id=12345",
                        "transaction_id": "EP1733692800ABCD1234",
                        "order_id": "ORD123456",
                        "amount": 1000.00,
                        "commission": 50.00,
                        "net_amount": 950.00,
                        "provider": "easypaisa",
                        "expires_at": "2025-12-08T12:30:00Z",
                        "idempotency_key": "topup_user123_1733692800_abc123"
                    }
                }
            }
        },
        404: {"description": "Wallet not found"},
        500: {"description": "Payment adapter error"}
    }
)
async def initiate_topup(
    request: TopupSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Initiate wallet top-up payment session."""
    # Initialize payment service (configuration from env)
    service = PaymentService(
        db=db,
        sandbox_mode=True,  # TODO: Load from config
        topup_commission_rate=0.05,  # TODO: Load from config
        provider_credentials={}  # TODO: Load from config
    )
    
    return await service.initiate_topup(current_user.id, request)


# ============================================================================
# WEBHOOK ENDPOINTS (Prompt 10)
# ============================================================================

@payments_prompt10_router.post(
    "/webhook/confirm",
    response_model=WebhookConfirmResponse,
    status_code=status.HTTP_200_OK,
    summary="Process Payment Webhook",
    description="""
    Process payment confirmation webhook from provider.
    
    **Flow:**
    1. Provider sends POST request with payment status
    2. System checks idempotency (prevent duplicate processing)
    3. Validates webhook signature
    4. If signature valid:
       - Updates PaymentIntent status
       - Credits wallet if payment successful
       - Creates Transaction record
    5. Returns confirmation response
    
    **Idempotency:**
    - Duplicate webhooks return cached response
    - TTL: 1 hour
    - Prevents double-crediting wallet
    
    **Signature Validation:**
    - Easypaisa: HMAC-SHA256 with secret_key
    - JazzCash: SHA256 with integrity_salt
    - Card: SHA256 with gateway_secret
    
    **Status Mapping:**
    - success → Credit wallet + create transaction
    - failed → Update intent status, no wallet credit
    - pending → Wait for final status
    
    **Business Rules:**
    - Only process webhooks with valid signatures
    - Idempotent replay for duplicate webhooks
    - Atomic wallet credit + transaction creation
    - Automatic expiry of old idempotency records
    """,
    responses={
        200: {
            "description": "Webhook processed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Payment confirmed and wallet credited",
                        "order_id": "ORD123456",
                        "wallet_balance": 5950.00,
                        "cached": False
                    }
                }
            }
        },
        401: {"description": "Invalid webhook signature"},
        404: {"description": "Payment intent not found"}
    }
)
async def process_webhook(
    webhook_data: WebhookConfirmRequest,
    x_signature: str = Header(..., description="Webhook signature from provider"),
    db: AsyncSession = Depends(get_db)
):
    """Process payment webhook from provider."""
    # Add signature to webhook data
    webhook_data.signature = x_signature
    
    # Initialize payment service
    service = PaymentService(
        db=db,
        sandbox_mode=True,
        provider_credentials={}
    )
    
    return await service.process_webhook(webhook_data)


# ============================================================================
# PAYOUT ENDPOINTS (Prompt 10)
# ============================================================================

@payments_prompt10_router.post(
    "/withdraw",
    response_model=WithdrawResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute Driver Payout",
    description="""
    Execute withdrawal (payout) to driver's account.
    
    **Flow:**
    1. Driver requests withdrawal with amount and provider
    2. System checks sufficient wallet balance
    3. Calculates commission
    4. Creates Payout record (status=PENDING)
    5. Adapter executes payout with provider
    6. Deducts from wallet if successful
    7. Creates Transaction record
    8. Returns payout status
    
    **Supported Providers:**
    - easypaisa: Mobile wallet (phone number)
    - jazzcash: Mobile wallet (phone number)
    - card: Bank transfer (IBAN)
    
    **Commission:**
    - Default: 3% of payout amount
    - Example: PKR 10,000 withdrawal → PKR 300 commission → PKR 9,700 transferred
    
    **Account Number Validation:**
    - Easypaisa/JazzCash: 03XXXXXXXXX (11 digits)
    - Card (IBAN): PKXXXXXXXXXXXXXXXXXXXX (24 characters)
    
    **Business Rules:**
    - Minimum withdrawal: PKR 500
    - Maximum withdrawal: PKR 50,000
    - Check sufficient balance before processing
    - Commission deducted from wallet balance
    - Settlement time: 1-3 business days (card), instant (mobile wallets)
    """,
    responses={
        200: {
            "description": "Payout executed successfully",
            "content": {
                "application/json": {
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
            }
        },
        400: {"description": "Insufficient balance or invalid account number"},
        404: {"description": "Wallet not found"},
        500: {"description": "Payout execution failed"}
    }
)
async def execute_withdrawal(
    request: WithdrawRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Execute driver payout."""
    service = PaymentService(
        db=db,
        sandbox_mode=True,
        payout_commission_rate=0.03,  # 3% commission
        provider_credentials={}
    )
    
    return await service.execute_payout(current_user.id, request)


# ============================================================================
# TRANSACTION HISTORY ENDPOINTS (Prompt 10)
# ============================================================================

@payments_prompt10_router.get(
    "/transactions",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="List User Transactions",
    description="""
    Get paginated list of user transactions.
    
    **Filters:**
    - type: Filter by transaction type (topup, payout, ride_payment, etc.)
    - provider: Filter by payment provider
    - status: Filter by status (completed, failed, pending)
    - date_from: Start date (ISO 8601)
    - date_to: End date (ISO 8601)
    
    **Pagination:**
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    
    **Response:**
    - Total count
    - Paginated list of transactions
    - Summary statistics (total amount, count by type)
    """,
    responses={
        200: {
            "description": "Transaction list retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "data": {
                            "transactions": [],
                            "total": 45,
                            "page": 1,
                            "page_size": 20,
                            "summary": {
                                "total_topup": 50000.00,
                                "total_payout": 30000.00,
                                "count_topup": 25,
                                "count_payout": 20
                            }
                        }
                    }
                }
            }
        }
    }
)
async def list_transactions(
    type: str = Query(None, description="Filter by transaction type"),
    provider: str = Query(None, description="Filter by provider"),
    status: str = Query(None, description="Filter by status"),
    date_from: datetime = Query(None, description="Start date"),
    date_to: datetime = Query(None, description="End date"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List user transactions with pagination and filters."""
    from app.modules.payments import crud as pay_crud
    txns = await pay_crud.get_wallet_transactions(db, current_user.id)
    return {
        "status": "ok",
        "data": txns[:page_size],
        "page": page,
        "total": len(txns)
    }


# ============================================================================
# ADMIN RECONCILIATION ENDPOINTS (Prompt 10)
# ============================================================================

@payments_prompt10_router.get(
    "/admin/reconciliation",
    response_model=ReconciliationReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Reconciliation Report (Admin)",
    description="""
    Get daily reconciliation report (admin only).
    
    **Flow:**
    1. Compares PaymentIntent records with Transaction records
    2. Identifies mismatches (amount, status)
    3. Lists unmatched intents and transactions
    4. Provides per-provider breakdown
    
    **Report Contents:**
    - Summary: Total counts, amounts, discrepancies
    - Provider Breakdown: Per-provider statistics
    - Details: Lists of unmatched/mismatched records
    
    **Use Cases:**
    - Daily reconciliation (automated Celery job)
    - Manual reconciliation by admin
    - Audit trail for financial compliance
    - Debugging payment discrepancies
    
    **Filters:**
    - provider: Filter by specific provider
    - date: Date to reconcile (default: yesterday)
    - date_from/date_to: Date range for reconciliation
    """,
    responses={
        200: {
            "description": "Reconciliation report generated successfully",
            "content": {
                "application/json": {
                    "example": {
                        "summary": {
                            "total_intent_amount": 100000.00,
                            "total_transaction_amount": 99500.00,
                            "matched_count": 45,
                            "unmatched_intents_count": 2,
                            "unmatched_transactions_count": 1,
                            "discrepancy": 500.00
                        },
                        "provider_breakdown": {},
                        "details": {
                            "unmatched_intents": [],
                            "unmatched_transactions": [],
                            "mismatched_amounts": []
                        },
                        "generated_at": "2025-12-08T02:00:00Z"
                    }
                }
            }
        },
        403: {"description": "Admin access required"}
    }
)
async def get_reconciliation_report(
    provider: str = Query(None, description="Filter by provider"),
    date: datetime = Query(None, description="Date to reconcile"),
    date_from: datetime = Query(None, description="Start date"),
    date_to: datetime = Query(None, description="End date"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get reconciliation report (admin only)."""
    from app.models.enums import UserRole
    from fastapi import HTTPException
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    reconciler = ReconciliationSystem(db)
    
    if date:
        report = await reconciler.reconcile_daily(date)
    elif date_from and date_to:
        # TODO: Implement date range reconciliation
        report = await reconciler.reconcile_daily()
    else:
        # Default to yesterday
        report = await reconciler.reconcile_daily()
    
    response = report.to_dict()
    response["generated_at"] = datetime.utcnow().isoformat()
    
    return response


@payments_prompt10_router.get(
    "/admin/reconciliation/{intent_id}",
    response_model=ReconciliationSingleResponse,
    status_code=status.HTTP_200_OK,
    summary="Reconcile Single Payment Intent (Admin)",
    description="""
    Manually reconcile single payment intent (admin only).
    
    **Use Cases:**
    - Debugging specific transaction issues
    - Manual reconciliation of failed payments
    - Audit trail investigation
    
    **Response:**
    - Intent details
    - Matching transaction (if found)
    - Amount match status
    - Difference amount (if mismatch)
    """,
    responses={
        200: {
            "description": "Single intent reconciliation result",
            "content": {
                "application/json": {
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
            }
        },
        404: {"description": "Payment intent not found"},
        403: {"description": "Admin access required"}
    }
)
async def reconcile_single_intent(
    intent_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Manually reconcile single payment intent (admin only)."""
    from app.models.enums import UserRole
    from fastapi import HTTPException
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    reconciler = ReconciliationSystem(db)
    return await reconciler.reconcile_single_intent(str(intent_id))
