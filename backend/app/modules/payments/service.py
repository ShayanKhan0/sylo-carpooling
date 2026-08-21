"""
Service layer for Payments Module.

Business logic for wallet operations, ride payments, and payouts.
Coordinates between CRUD operations, payment providers, and business rules.

Author: Smart Carpooling Development Team
Created: 2025-11-08
"""

import json
from decimal import Decimal
from typing import Dict, Any, Optional
from uuid import UUID

import logging
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
from .models import TransactionTypeEnum, TransactionStatusEnum, PayoutStatusEnum
from .schemas import (
    WalletResponse, TopUpRequest, DeductRequest, TransferRequest,
    TransactionCreate, TransactionResponse, OperationResponse,
    PayoutRequest, PayoutResponse, PaymentWebhook, RideFareSplit,
    PropTopUpRequest, PropPayoutRequest
)
from . import crud
from .utils import (
    generate_txn_id, verify_signature, calculate_commission,
    validate_payment_provider, mock_payment_process, mask_account_details
)


async def _ensure_wallet_for_user(db: AsyncSession, user_id: UUID):
    """Return an existing wallet or create a compatibility wallet row."""
    wallet = await crud.get_wallet_by_user_id(db, user_id)
    if wallet:
        return wallet

    try:
        # Compatibility mode: keep wallets.id aligned with user_id.
        await db.execute(
            text(
                """
                INSERT INTO wallets (id, user_id, balance, created_at, updated_at)
                VALUES (:id, :user_id, :balance, NOW(), NOW())
                ON CONFLICT (user_id) DO NOTHING
                """
            ),
            {
                "id": user_id,
                "user_id": user_id,
                "balance": Decimal("0.00"),
            },
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to ensure wallet for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create wallet",
        )

    wallet = await crud.get_wallet_by_user_id(db, user_id)
    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Wallet not found and could not be created",
        )

    return wallet


# ============================================================================
# WALLET SERVICES
# ============================================================================

async def initialize_wallet_service(
    db: AsyncSession,
    user_id: UUID
) -> Dict[str, Any]:
    """
    Initialize wallet for new user.
    
    Called automatically during user registration.
    Creates wallet with 0.00 PKR balance.
    """
    try:
        wallet = await crud.create_wallet(db, user_id)
        
        return {
            "status": "ok",
            "data": WalletResponse.model_validate(wallet).model_dump(),
            "error": None
        }
    except HTTPException as e:
        logger.error(f"Failed to initialize wallet for user {user_id}: {e.detail}")
        return {
            "status": "error",
            "data": None,
            "error": e.detail
        }


async def get_balance_service(
    db: AsyncSession,
    user_id: UUID
) -> Dict[str, Any]:
    """Get user wallet balance. Auto-creates wallet if not found."""
    wallet = await crud.get_wallet_by_user_id(db, user_id)
    
    if not wallet:
        # Auto-create wallet for this user
        try:
            wallet = await crud.create_wallet(db, user_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wallet not found and could not be created"
            )
    
    return {
        "status": "ok",
        "data": {
            "user_id": str(user_id),
            "balance": float(wallet.balance),
            "currency": wallet.currency,
            "last_updated": wallet.last_updated.isoformat()
        },
        "error": None
    }


async def topup_wallet_service(
    db: AsyncSession,
    user_id: UUID,
    request: TopUpRequest
) -> Dict[str, Any]:
    """
    Top-up wallet via payment provider.
    
    Process:
    1. Validate payment provider
    2. Get user wallet
    3. Create pending transaction
    4. Process payment with provider
    5. Update wallet balance if successful
    6. Update transaction status
    """
    # Validate provider
    is_valid, error = validate_payment_provider(request.provider)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)
    
    # Get wallet
    wallet = await crud.get_wallet_by_user_id(db, user_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    
    # Create transaction
    txn_id = generate_txn_id()
    txn_data = TransactionCreate(
        wallet_id=wallet.id,
        user_id=user_id,
        amount=request.amount,
        type=TransactionTypeEnum.TOPUP,
        provider=request.provider,
        provider_txn_id=request.provider_txn_id,
        description=request.description or "Wallet top-up",
        metadata=None
    )
    
    transaction = await crud.log_transaction(db, txn_data)
    transaction.txn_id = txn_id
    await db.commit()
    
    try:
        # Process payment with provider (mock for development)
        provider_response = await mock_payment_process(
            amount=request.amount,
            provider=request.provider,
            txn_id=txn_id,
            simulate_success=True
        )
        
        if provider_response.get("success"):
            # Update wallet balance
            await crud.update_wallet_balance(db, wallet.id, request.amount, "add")
            
            # Update transaction
            await crud.update_transaction_status(
                db, txn_id, TransactionStatusEnum.COMPLETED,
                json.dumps(provider_response)
            )
            
            # Get updated wallet
            updated_wallet = await crud.get_wallet(db, wallet.id)
            
            return {
                "status": "ok",
                "data": {
                    "success": True,
                    "message": "Top-up successful",
                    "transaction_id": txn_id,
                    "wallet_balance": float(updated_wallet.balance),
                    "amount_added": float(request.amount)
                },
                "error": None
            }
        else:
            # Payment failed
            await crud.update_transaction_status(
                db, txn_id, TransactionStatusEnum.FAILED,
                json.dumps(provider_response)
            )
            
            return {
                "status": "error",
                "data": None,
                "error": provider_response.get("message", "Payment failed")
            }
            
    except Exception as e:
        await crud.update_transaction_status(db, txn_id, TransactionStatusEnum.FAILED)
        logger.error(f"Top-up failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def prop_topup_wallet_service(
    db: AsyncSession,
    user_id: UUID,
    request: PropTopUpRequest
) -> Dict[str, Any]:
    """
    Top-up wallet using internal Prop Money.

    This flow is internal-only and credits balance instantly.
    """
    wallet = await _ensure_wallet_for_user(db, user_id)

    txn_data = TransactionCreate(
        wallet_id=wallet.id,
        user_id=user_id,
        amount=request.amount,
        type=TransactionTypeEnum.TOPUP,
        provider="prop_money",
        description=request.description or "Prop Money top-up",
        metadata=None,
    )

    transaction = await crud.log_transaction(db, txn_data)

    try:
        await crud.update_wallet_balance(db, wallet.id, request.amount, "add")
        await crud.update_transaction_status(
            db,
            transaction.txn_id,
            TransactionStatusEnum.COMPLETED,
            json.dumps({"provider": "prop_money", "success": True}),
        )

        updated_wallet = await crud.get_wallet(db, wallet.id)

        return {
            "status": "ok",
            "data": {
                "success": True,
                "message": "Prop Money top-up successful",
                "transaction_id": transaction.txn_id,
                "wallet_balance": float(updated_wallet.balance),
                "amount_added": float(request.amount),
            },
            "error": None,
        }
    except Exception as e:
        await crud.update_transaction_status(
            db,
            transaction.txn_id,
            TransactionStatusEnum.FAILED,
            json.dumps({"provider": "prop_money", "success": False, "error": str(e)}),
        )
        logger.error(f"Prop Money top-up failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Prop Money top-up failed")


async def prop_payout_wallet_service(
    db: AsyncSession,
    user_id: UUID,
    request: PropPayoutRequest
) -> Dict[str, Any]:
    """
    Deduct from wallet using internal Prop Money payout.

    This flow is internal-only and debits balance instantly.
    """
    wallet = await _ensure_wallet_for_user(db, user_id)

    if wallet.balance < request.amount:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Not enough available balance. "
                f"Available: {wallet.balance} PKR, Requested: {request.amount} PKR"
            ),
        )

    txn_data = TransactionCreate(
        wallet_id=wallet.id,
        user_id=user_id,
        amount=-request.amount,
        type=TransactionTypeEnum.PAYOUT,
        provider="prop_money",
        description=request.description or "Prop Money payout",
        metadata=None,
    )

    transaction = await crud.log_transaction(db, txn_data)

    try:
        await crud.update_wallet_balance(db, wallet.id, request.amount, "subtract")
        await crud.update_transaction_status(
            db,
            transaction.txn_id,
            TransactionStatusEnum.COMPLETED,
            json.dumps({"provider": "prop_money", "success": True}),
        )

        updated_wallet = await crud.get_wallet(db, wallet.id)

        return {
            "status": "ok",
            "data": {
                "success": True,
                "message": "Prop Money payout successful",
                "transaction_id": transaction.txn_id,
                "wallet_balance": float(updated_wallet.balance),
                "amount_deducted": float(request.amount),
            },
            "error": None,
        }
    except HTTPException as e:
        await crud.update_transaction_status(
            db,
            transaction.txn_id,
            TransactionStatusEnum.FAILED,
            json.dumps({"provider": "prop_money", "success": False, "error": str(e.detail)}),
        )
        if e.status_code == status.HTTP_400_BAD_REQUEST:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not enough available balance for this payout",
            )
        raise
    except Exception as e:
        await crud.update_transaction_status(
            db,
            transaction.txn_id,
            TransactionStatusEnum.FAILED,
            json.dumps({"provider": "prop_money", "success": False, "error": str(e)}),
        )
        logger.error(f"Prop Money payout failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Prop Money payout failed")


async def deduct_from_wallet_service(
    db: AsyncSession,
    user_id: UUID,
    request: DeductRequest
) -> Dict[str, Any]:
    """
    Deduct funds from wallet.
    
    Used for ride payments, fees, etc.
    """
    wallet = await crud.get_wallet_by_user_id(db, user_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    
    # Check sufficient balance
    if wallet.balance < request.amount:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance. Available: {wallet.balance}, Required: {request.amount}"
        )
    
    # Create transaction
    txn_id = generate_txn_id()
    txn_data = TransactionCreate(
        wallet_id=wallet.id,
        user_id=user_id,
        amount=-request.amount,  # Negative for deduction
        type=TransactionTypeEnum.DEDUCT,
        ride_id=request.ride_id,
        description=request.description or "Wallet deduction",
        metadata=json.dumps(request.metadata) if request.metadata else None
    )
    
    transaction = await crud.log_transaction(db, txn_data)
    transaction.txn_id = txn_id
    
    # Deduct balance
    await crud.update_wallet_balance(db, wallet.id, request.amount, "subtract")
    
    # Complete transaction
    await crud.update_transaction_status(db, txn_id, TransactionStatusEnum.COMPLETED)
    
    updated_wallet = await crud.get_wallet(db, wallet.id)
    
    return {
        "status": "ok",
        "data": {
            "success": True,
            "message": "Deduction successful",
            "transaction_id": txn_id,
            "wallet_balance": float(updated_wallet.balance),
            "amount_deducted": float(request.amount)
        },
        "error": None
    }


async def process_ride_payment_service(
    db: AsyncSession,
    passenger_id: UUID,
    driver_id: UUID,
    ride_id: UUID,
    fare_amount: Decimal,
    commission_rate: Optional[Decimal] = None
) -> Dict[str, Any]:
    """
    Process ride payment with commission split.
    
    Steps:
    1. Deduct fare from passenger wallet
    2. Calculate commission split
    3. Add driver share to driver wallet
    4. Log platform commission
    """
    # Calculate commission
    split = calculate_commission(fare_amount, commission_rate)
    
    # Deduct from passenger
    passenger_deduct = DeductRequest(
        amount=fare_amount,
        ride_id=ride_id,
        description=f"Payment for ride {ride_id}",
        metadata=split
    )
    
    passenger_result = await deduct_from_wallet_service(db, passenger_id, passenger_deduct)
    
    if passenger_result["status"] != "ok":
        raise HTTPException(status_code=400, detail="Failed to deduct from passenger")
    
    # Add to driver
    driver_wallet = await crud.get_wallet_by_user_id(db, driver_id)
    if not driver_wallet:
        # Create wallet for driver if not exists
        driver_wallet = await crud.create_wallet(db, driver_id)
    
    # Credit driver share
    txn_id = generate_txn_id()
    txn_data = TransactionCreate(
        wallet_id=driver_wallet.id,
        user_id=driver_id,
        amount=split["driver_share"],
        type=TransactionTypeEnum.COMMISSION,
        ride_id=ride_id,
        description=f"Earnings from ride {ride_id}",
        metadata=json.dumps(split)
    )
    
    await crud.log_transaction(db, txn_data)
    await crud.update_wallet_balance(db, driver_wallet.id, split["driver_share"], "add")
    
    return {
        "status": "ok",
        "data": {
            "success": True,
            "message": "Ride payment processed",
            "fare_split": {
                "total_fare": float(split["total_fare"]),
                "driver_share": float(split["driver_share"]),
                "platform_commission": float(split["platform_commission"]),
                "commission_percentage": float(split["commission_percentage"])
            }
        },
        "error": None
    }


async def request_payout_service(
    db: AsyncSession,
    driver_id: UUID,
    request: PayoutRequest
) -> Dict[str, Any]:
    """
    Request driver payout.
    
    Validates driver balance and creates payout request.
    """
    # Get driver wallet
    driver_wallet = await crud.get_wallet_by_user_id(db, driver_id)
    if not driver_wallet:
        raise HTTPException(status_code=404, detail="Driver wallet not found")
    
    # Check balance
    if driver_wallet.balance < request.amount:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient balance. Available: {driver_wallet.balance}"
        )
    
    # Create payout
    payout = await crud.create_payout(
        db,
        driver_id=driver_id,
        amount=request.amount,
        method=request.method.value,
        account_details=request.account_details,
        notes=request.notes
    )
    
    # Deduct from wallet
    await crud.update_wallet_balance(db, driver_wallet.id, request.amount, "subtract")
    
    # Create transaction
    txn_data = TransactionCreate(
        wallet_id=driver_wallet.id,
        user_id=driver_id,
        amount=-request.amount,
        type=TransactionTypeEnum.PAYOUT,
        payout_id=payout.id,
        description=f"Payout via {request.method.value}",
        metadata=None
    )
    
    await crud.log_transaction(db, txn_data)
    
    # Mask account details in response
    payout.account_details = mask_account_details(payout.account_details)
    
    return {
        "status": "ok",
        "data": PayoutResponse.model_validate(payout).model_dump(),
        "error": None
    }


async def verify_payment_webhook_service(
    db: AsyncSession,
    webhook: PaymentWebhook
) -> Dict[str, Any]:
    """
    Verify and process payment provider webhook.
    
    Validates signature and updates transaction status.
    """
    # Verify signature
    if not verify_signature(webhook.payload, webhook.signature, webhook.provider):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    
    # Get transaction
    transaction = await crud.get_transaction(db, webhook.txn_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    # Update based on webhook status
    if webhook.status.upper() in ["SUCCESS", "COMPLETED"]:
        new_status = TransactionStatusEnum.COMPLETED
    elif webhook.status.upper() in ["FAILED", "DECLINED"]:
        new_status = TransactionStatusEnum.FAILED
    else:
        new_status = TransactionStatusEnum.PROCESSING
    
    await crud.update_transaction_status(
        db, webhook.txn_id, new_status, json.dumps(webhook.payload)
    )
    
    return {
        "status": "ok",
        "data": {"message": "Webhook processed successfully"},
        "error": None
    }
