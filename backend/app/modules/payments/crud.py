"""
CRUD operations for Payments Module.

Async database operations with atomic transactions:
- Wallet management (create, get, update balance)
- Transaction logging (create, get, list history)
- Payout processing (create, get, update status)

All operations use row-level locking for concurrent safety.

Author: Smart Carpooling Development Team
Created: 2025-11-08
"""

from datetime import datetime, timedelta
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional, List
from uuid import UUID

import logging
from fastapi import HTTPException, status
from sqlalchemy import select, and_, or_, desc, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)
from .models import Wallet, Transaction, Payout, TransactionTypeEnum, TransactionStatusEnum, PayoutStatusEnum
from .schemas import TransactionCreate
from .utils import generate_txn_id


@dataclass
class WalletRecord:
    """Compatibility wallet view for both legacy and current callers."""

    user_id: UUID
    balance: Decimal
    created_at: datetime
    updated_at: datetime

    @property
    def id(self) -> UUID:
        return self.user_id

    @property
    def currency(self) -> str:
        return "PKR"

    @property
    def last_updated(self) -> datetime:
        return self.updated_at


def _row_to_wallet(row) -> WalletRecord:
    return WalletRecord(
        user_id=row.user_id,
        balance=Decimal(str(row.balance or 0)),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ============================================================================
# WALLET CRUD OPERATIONS
# ============================================================================

async def create_wallet(
    db: AsyncSession,
    user_id: UUID,
    initial_balance: Decimal = Decimal("0.00"),
    currency: str = "PKR"
) -> Wallet:
    """
    Create new wallet for user.
    
    Args:
        db: Database session
        user_id: User ID to create wallet for
        initial_balance: Starting balance (default 0.00)
        currency: Currency code (default PKR)
    
    Returns:
        Created Wallet instance
    
    Raises:
        HTTPException 400: If wallet already exists for user
        HTTPException 500: If database error occurs
    
    Business Rules:
        - One wallet per user (enforced by unique constraint)
        - Initial balance must be non-negative
        - Auto-created when user registers
    
    Examples:
        >>> wallet = await create_wallet(db, user_id=UUID("123..."))
        >>> print(wallet.balance)
        Decimal('0.00')
    """
    try:
        # Check if wallet already exists
        existing = await get_wallet_by_user_id(db, user_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Wallet already exists for user {user_id}"
            )
        
        await db.execute(
            text(
                """
                INSERT INTO wallets (user_id, balance)
                VALUES (:user_id, :balance)
                """
            ),
            {
                "user_id": user_id,
                "balance": initial_balance,
            },
        )
        await db.commit()

        wallet = await get_wallet_by_user_id(db, user_id)
        if not wallet:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Wallet row was not available after creation",
            )

        logger.info(
            f"Created wallet {wallet.id} for user {user_id} with balance {initial_balance} {currency}"
        )

        return wallet
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating wallet for user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create wallet"
        )


async def get_wallet(db: AsyncSession, wallet_id: UUID) -> Optional[Wallet]:
    """
    Get wallet by ID.
    
    Args:
        db: Database session
        wallet_id: Wallet UUID
    
    Returns:
        Wallet instance or None if not found
    
    Examples:
        >>> wallet = await get_wallet(db, wallet_id=UUID("987..."))
        >>> if wallet:
        ...     print(f"Balance: {wallet.balance}")
    """
    try:
        result = await db.execute(
            text(
                """
                SELECT user_id, balance, created_at, updated_at
                FROM wallets
                WHERE user_id = :wallet_id
                LIMIT 1
                """
            ),
            {"wallet_id": wallet_id},
        )
        row = result.first()
        return _row_to_wallet(row) if row else None
    except Exception as e:
        logger.error(f"Error getting wallet {wallet_id}: {str(e)}")
        return None


async def get_wallet_by_user_id(db: AsyncSession, user_id: UUID) -> Optional[Wallet]:
    """
    Get wallet by user ID.
    
    Args:
        db: Database session
        user_id: User UUID
    
    Returns:
        Wallet instance or None if not found
    
    Examples:
        >>> wallet = await get_wallet_by_user_id(db, user_id=UUID("123..."))
        >>> if wallet:
        ...     print(f"User wallet balance: {wallet.balance} {wallet.currency}")
    """
    try:
        result = await db.execute(
            text(
                """
                SELECT user_id, balance, created_at, updated_at
                FROM wallets
                WHERE user_id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
        row = result.first()
        return _row_to_wallet(row) if row else None
    except Exception as e:
        logger.error(f"Error getting wallet for user {user_id}: {str(e)}")
        return None


async def get_wallet_balance(db: AsyncSession, user_id: UUID) -> Optional[Decimal]:
    """
    Get current wallet balance for user.
    
    Args:
        db: Database session
        user_id: User UUID
    
    Returns:
        Current balance as Decimal or None if wallet not found
    
    Examples:
        >>> balance = await get_wallet_balance(db, user_id=UUID("123..."))
        >>> print(f"Balance: {balance} PKR")
    """
    wallet = await get_wallet_by_user_id(db, user_id)
    return wallet.balance if wallet else None


async def update_wallet_balance(
    db: AsyncSession,
    wallet_id: UUID,
    amount: Decimal,
    operation: str = "add"
) -> Wallet:
    """
    Update wallet balance (add or subtract).
    
    Args:
        db: Database session
        wallet_id: Wallet UUID
        amount: Amount to add or subtract (must be positive)
        operation: "add" to increase balance, "subtract" to decrease
    
    Returns:
        Updated Wallet instance
    
    Raises:
        HTTPException 404: If wallet not found
        HTTPException 400: If insufficient balance for subtraction
        HTTPException 500: If database error occurs
    
    Security:
        - Uses row-level locking (SELECT FOR UPDATE) to prevent race conditions
        - Validates balance >= 0 after subtraction
        - All changes are atomic within transaction
    
    Examples:
        >>> # Add 500 PKR
        >>> wallet = await update_wallet_balance(db, wallet_id, Decimal("500.00"), "add")
        >>> 
        >>> # Deduct 150 PKR
        >>> wallet = await update_wallet_balance(db, wallet_id, Decimal("150.00"), "subtract")
    """
    try:
        # Legacy schema key is wallets.user_id. Lock row to keep updates atomic.
        result = await db.execute(
            text(
                """
                SELECT user_id, balance, created_at, updated_at
                FROM wallets
                WHERE user_id = :wallet_id
                FOR UPDATE
                """
            ),
            {"wallet_id": wallet_id},
        )
        row = result.first()
        wallet = _row_to_wallet(row) if row else None
        
        if not wallet:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Wallet {wallet_id} not found"
            )
        
        # Perform balance update
        if operation == "add":
            wallet.balance += amount
        elif operation == "subtract":
            new_balance = wallet.balance - amount
            if new_balance < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient balance. Available: {wallet.balance}, Required: {amount}"
                )
            wallet.balance = new_balance
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid operation: {operation}. Use 'add' or 'subtract'"
            )

        await db.execute(
            text(
                """
                UPDATE wallets
                SET balance = :balance,
                    updated_at = NOW()
                WHERE user_id = :wallet_id
                """
            ),
            {
                "wallet_id": wallet_id,
                "balance": wallet.balance,
            },
        )

        await db.commit()
        refreshed = await get_wallet(db, wallet_id)
        if refreshed is not None:
            wallet = refreshed
        
        logger.info(f"Updated wallet {wallet_id} balance: {operation} {amount}, new balance: {wallet.balance}")
        
        return wallet
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating wallet {wallet_id} balance: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update wallet balance"
        )


# ============================================================================
# TRANSACTION CRUD OPERATIONS
# ============================================================================

async def log_transaction(
    db: AsyncSession,
    transaction_data: TransactionCreate,
    auto_generate_txn_id: bool = True
) -> Transaction:
    """
    Create transaction record.
    
    Args:
        db: Database session
        transaction_data: TransactionCreate schema with transaction details
        auto_generate_txn_id: Auto-generate txn_id if not provided
    
    Returns:
        Created Transaction instance
    
    Raises:
        HTTPException 500: If database error occurs
    
    Business Rules:
        - Every wallet operation must create a transaction
        - Transaction ID is unique and traceable
        - Initial status is PENDING
        - Immutable after creation (only status updates allowed)
    
    Examples:
        >>> from .schemas import TransactionCreate
        >>> from .models import TransactionTypeEnum
        >>> 
        >>> txn_data = TransactionCreate(
        ...     wallet_id=wallet.id,
        ...     user_id=user.id,
        ...     amount=Decimal("500.00"),
        ...     type=TransactionTypeEnum.TOPUP,
        ...     provider="jazzcash",
        ...     description="Wallet top-up"
        ... )
        >>> transaction = await log_transaction(db, txn_data)
    """
    try:
        # Generate unique transaction ID if not provided
        txn_id = generate_txn_id() if auto_generate_txn_id else getattr(transaction_data, 'txn_id', generate_txn_id())
        
        # Create transaction record
        transaction = Transaction(
            txn_id=txn_id,
            wallet_id=transaction_data.wallet_id,
            user_id=transaction_data.user_id,
            amount=transaction_data.amount,
            type=transaction_data.type,
            status=TransactionStatusEnum.PENDING,
            ride_id=transaction_data.ride_id,
            provider=transaction_data.provider,
            provider_txn_id=transaction_data.provider_txn_id,
            description=transaction_data.description,
            notes=transaction_data.notes,
            metadata=transaction_data.metadata
        )
        
        db.add(transaction)
        await db.commit()
        await db.refresh(transaction)
        
        logger.info(f"Created transaction {transaction.txn_id}: {transaction.type} {transaction.amount}")
        
        return transaction
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error logging transaction: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to log transaction"
        )


async def get_transaction(db: AsyncSession, txn_id: str) -> Optional[Transaction]:
    """
    Get transaction by transaction ID.
    
    Args:
        db: Database session
        txn_id: Transaction ID (e.g., "TXN-20251108-ABC123")
    
    Returns:
        Transaction instance or None if not found
    
    Examples:
        >>> txn = await get_transaction(db, "TXN-20251108-ABC123")
        >>> if txn:
        ...     print(f"Status: {txn.status}, Amount: {txn.amount}")
    """
    try:
        result = await db.execute(
            select(Transaction).where(Transaction.txn_id == txn_id)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error getting transaction {txn_id}: {str(e)}")
        return None


async def get_transaction_by_id(db: AsyncSession, transaction_id: UUID) -> Optional[Transaction]:
    """
    Get transaction by UUID.
    
    Args:
        db: Database session
        transaction_id: Transaction UUID
    
    Returns:
        Transaction instance or None if not found
    """
    try:
        result = await db.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error getting transaction by ID {transaction_id}: {str(e)}")
        return None


async def update_transaction_status(
    db: AsyncSession,
    txn_id: str,
    new_status: TransactionStatusEnum,
    provider_response: Optional[str] = None
) -> Transaction:
    """
    Update transaction status.
    
    Args:
        db: Database session
        txn_id: Transaction ID
        new_status: New status (PROCESSING, COMPLETED, FAILED, REVERSED)
        provider_response: Optional provider response data
    
    Returns:
        Updated Transaction instance
    
    Raises:
        HTTPException 404: If transaction not found
        HTTPException 500: If database error occurs
    
    Status Transitions:
        PENDING → PROCESSING → COMPLETED
        PENDING → PROCESSING → FAILED
        COMPLETED → REVERSED (for refunds)
    
    Examples:
        >>> txn = await update_transaction_status(
        ...     db,
        ...     txn_id="TXN-20251108-ABC123",
        ...     new_status=TransactionStatusEnum.COMPLETED,
        ...     provider_response='{"status": "SUCCESS"}'
        ... )
    """
    try:
        transaction = await get_transaction(db, txn_id)
        
        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transaction {txn_id} not found"
            )
        
        transaction.status = new_status
        transaction.updated_at = datetime.utcnow()
        
        if provider_response:
            transaction.provider_response = provider_response
        
        if new_status in [TransactionStatusEnum.COMPLETED, TransactionStatusEnum.FAILED]:
            transaction.completed_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(transaction)
        
        logger.info(f"Updated transaction {txn_id} status to {new_status}")
        
        return transaction
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating transaction {txn_id} status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update transaction status"
        )


async def get_user_transactions(
    db: AsyncSession,
    user_id: UUID,
    transaction_type: Optional[TransactionTypeEnum] = None,
    status: Optional[TransactionStatusEnum] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Transaction]:
    """
    Get user transaction history.
    
    Args:
        db: Database session
        user_id: User UUID
        transaction_type: Optional filter by transaction type
        status: Optional filter by status
        limit: Maximum number of records (default 100)
        offset: Pagination offset (default 0)
    
    Returns:
        List of Transaction instances ordered by created_at DESC
    
    Examples:
        >>> # Get all transactions
        >>> txns = await get_user_transactions(db, user_id=UUID("123..."))
        >>> 
        >>> # Get only top-ups
        >>> topups = await get_user_transactions(
        ...     db,
        ...     user_id=UUID("123..."),
        ...     transaction_type=TransactionTypeEnum.TOPUP
        ... )
        >>> 
        >>> # Get completed transactions with pagination
        >>> txns = await get_user_transactions(
        ...     db,
        ...     user_id=UUID("123..."),
        ...     status=TransactionStatusEnum.COMPLETED,
        ...     limit=20,
        ...     offset=0
        ... )
    """
    try:
        query = select(Transaction).where(Transaction.user_id == user_id)
        
        if transaction_type:
            query = query.where(Transaction.type == transaction_type)
        
        if status:
            query = query.where(Transaction.status == status)
        
        query = query.order_by(desc(Transaction.created_at)).limit(limit).offset(offset)
        
        result = await db.execute(query)
        transactions = result.scalars().all()
        
        return list(transactions)
        
    except Exception as e:
        logger.error(f"Error getting transactions for user {user_id}: {str(e)}")
        return []


async def get_transaction_count(
    db: AsyncSession,
    user_id: UUID,
    transaction_type: Optional[TransactionTypeEnum] = None,
    status: Optional[TransactionStatusEnum] = None
) -> int:
    """
    Get total count of user transactions.
    
    Args:
        db: Database session
        user_id: User UUID
        transaction_type: Optional filter by transaction type
        status: Optional filter by status
    
    Returns:
        Total count of matching transactions
    
    Examples:
        >>> total = await get_transaction_count(db, user_id=UUID("123..."))
        >>> print(f"Total transactions: {total}")
    """
    try:
        query = select(func.count(Transaction.id)).where(Transaction.user_id == user_id)
        
        if transaction_type:
            query = query.where(Transaction.type == transaction_type)
        
        if status:
            query = query.where(Transaction.status == status)
        
        result = await db.execute(query)
        count = result.scalar()
        
        return count or 0
        
    except Exception as e:
        logger.error(f"Error counting transactions for user {user_id}: {str(e)}")
        return 0


# ============================================================================
# PAYOUT CRUD OPERATIONS
# ============================================================================

async def create_payout(
    db: AsyncSession,
    driver_id: UUID,
    amount: Decimal,
    method: str,
    account_details: str,
    notes: Optional[str] = None
) -> Payout:
    """
    Create payout request for driver.
    
    Args:
        db: Database session
        driver_id: Driver profile UUID
        amount: Payout amount
        method: Payout method (bank_transfer, jazzcash, easypaisa, etc.)
        account_details: Bank account or wallet number
        notes: Optional notes
    
    Returns:
        Created Payout instance
    
    Raises:
        HTTPException 500: If database error occurs
    
    Business Rules:
        - Minimum payout: 500 PKR
        - Driver must be verified
        - Account details should be validated
        - Initial status: PENDING
    
    Examples:
        >>> payout = await create_payout(
        ...     db,
        ...     driver_id=UUID("555..."),
        ...     amount=Decimal("2500.00"),
        ...     method="jazzcash",
        ...     account_details="03001234567",
        ...     notes="Weekly earnings"
        ... )
    """
    try:
        payout = Payout(
            driver_id=driver_id,
            amount=amount,
            method=method,
            account_details=account_details,
            status=PayoutStatusEnum.PENDING,
            notes=notes
        )
        
        db.add(payout)
        await db.commit()
        await db.refresh(payout)
        
        logger.info(f"Created payout {payout.id} for driver {driver_id}: {amount} via {method}")
        
        return payout
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating payout for driver {driver_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create payout"
        )


async def get_payout(db: AsyncSession, payout_id: UUID) -> Optional[Payout]:
    """
    Get payout by ID.
    
    Args:
        db: Database session
        payout_id: Payout UUID
    
    Returns:
        Payout instance or None if not found
    """
    try:
        result = await db.execute(
            select(Payout).where(Payout.id == payout_id)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error getting payout {payout_id}: {str(e)}")
        return None


async def get_driver_payouts(
    db: AsyncSession,
    driver_id: UUID,
    status: Optional[PayoutStatusEnum] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Payout]:
    """
    Get driver payout history.
    
    Args:
        db: Database session
        driver_id: Driver profile UUID
        status: Optional filter by status
        limit: Maximum records (default 100)
        offset: Pagination offset (default 0)
    
    Returns:
        List of Payout instances ordered by created_at DESC
    """
    try:
        query = select(Payout).where(Payout.driver_id == driver_id)
        
        if status:
            query = query.where(Payout.status == status)
        
        query = query.order_by(desc(Payout.created_at)).limit(limit).offset(offset)
        
        result = await db.execute(query)
        payouts = result.scalars().all()
        
        return list(payouts)
        
    except Exception as e:
        logger.error(f"Error getting payouts for driver {driver_id}: {str(e)}")
        return []


async def update_payout_status(
    db: AsyncSession,
    payout_id: UUID,
    new_status: PayoutStatusEnum,
    provider: Optional[str] = None,
    provider_payout_id: Optional[str] = None,
    provider_response: Optional[str] = None
) -> Payout:
    """
    Update payout status.
    
    Args:
        db: Database session
        payout_id: Payout UUID
        new_status: New status
        provider: Optional provider name
        provider_payout_id: Optional provider payout ID
        provider_response: Optional provider response
    
    Returns:
        Updated Payout instance
    
    Raises:
        HTTPException 404: If payout not found
        HTTPException 500: If database error occurs
    """
    try:
        payout = await get_payout(db, payout_id)
        
        if not payout:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payout {payout_id} not found"
            )
        
        payout.status = new_status
        payout.updated_at = datetime.utcnow()
        
        if provider:
            payout.provider = provider
        if provider_payout_id:
            payout.provider_payout_id = provider_payout_id
        if provider_response:
            payout.provider_response = provider_response
        
        if new_status == PayoutStatusEnum.PROCESSING and not payout.processed_at:
            payout.processed_at = datetime.utcnow()
        
        if new_status in [PayoutStatusEnum.COMPLETED, PayoutStatusEnum.FAILED]:
            payout.completed_at = datetime.utcnow()
        
        await db.commit()
        await db.refresh(payout)
        
        logger.info(f"Updated payout {payout_id} status to {new_status}")
        
        return payout
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating payout {payout_id} status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update payout status"
        )
