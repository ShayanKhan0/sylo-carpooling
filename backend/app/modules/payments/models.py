"""
Database models for Payments Module.

Models:
- Wallet: In-app wallet for users with balance tracking (imported from app.models.wallet)
- Transaction: Complete transaction history with type and status
- Payout: Driver earnings payout records

Note: Wallet model is centralized in app/models/wallet.py to avoid duplication.

Author: Smart Carpooling Development Team
Created: 2025-11-08
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, Text, Enum as SQLEnum, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base

# Import centralized Wallet model to avoid table duplication errors
from app.models.wallet import Wallet


class TransactionTypeEnum(str, enum.Enum):
    """
    Transaction type enumeration.
    
    Types:
    - TOPUP: User adds funds to wallet (via JazzCash, EasyPaisa, Stripe, etc.)
    - DEDUCT: Platform deducts funds (ride payment, fees)
    - REFUND: Return funds to user (canceled ride, overpayment)
    - PAYOUT: Transfer earnings to driver (bank, e-wallet)
    - COMMISSION: Platform commission deduction
    - BONUS: Promotional credits or bonuses
    """
    TOPUP = "topup"
    DEDUCT = "deduct"
    REFUND = "refund"
    PAYOUT = "payout"
    COMMISSION = "commission"
    BONUS = "bonus"


class TransactionStatusEnum(str, enum.Enum):
    """
    Transaction status lifecycle.
    
    States:
    - PENDING: Transaction initiated, awaiting confirmation
    - PROCESSING: Payment provider processing
    - COMPLETED: Successfully completed
    - FAILED: Transaction failed (insufficient funds, provider error)
    - REVERSED: Transaction reversed/rolled back
    """
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"


class PayoutStatusEnum(str, enum.Enum):
    """
    Payout status tracking.
    
    States:
    - PENDING: Payout requested, awaiting processing
    - PROCESSING: Being transferred to driver account
    - COMPLETED: Successfully transferred
    - FAILED: Transfer failed
    - CANCELLED: Payout cancelled
    """
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PayoutMethodEnum(str, enum.Enum):
    """
    Payout transfer methods.
    
    Methods:
    - BANK_TRANSFER: Direct bank transfer
    - JAZZCASH: JazzCash mobile wallet
    - EASYPAISA: EasyPaisa mobile wallet
    - STRIPE: Stripe Connect payout
    - PAYPAL: PayPal transfer
    """
    BANK_TRANSFER = "bank_transfer"
    JAZZCASH = "jazzcash"
    EASYPAISA = "easypaisa"
    STRIPE = "stripe"
    PAYPAL = "paypal"


class PaymentProviderEnum(str, enum.Enum):
    """
    Payment providers for top-ups (Prompt 10).
    
    Providers:
    - EASYPAISA: EasyPaisa mobile wallet
    - JAZZCASH: JazzCash mobile wallet
    - CARD: Credit/Debit card payments
    """
    EASYPAISA = "easypaisa"
    JAZZCASH = "jazzcash"
    CARD = "card"


class PaymentStatusEnum(str, enum.Enum):
    """
    Payment intent status (Prompt 10).
    
    States:
    - PENDING: Payment initiated, awaiting user action
    - PROCESSING: Payment being processed by provider
    - SUCCESS: Payment completed successfully
    - FAILED: Payment failed
    - EXPIRED: Payment session expired
    """
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    EXPIRED = "expired"


# NOTE: Wallet model moved to app/models/wallet.py to avoid duplication
# Import it from there instead: from app.models.wallet import Wallet
# 
# The duplicate Wallet class that was here has been removed to fix:
# "Table 'wallets' is already defined" error
#
# Original location: app/models/wallet.py (centralized model)
# Used by: earnings module, wallet_transactions, and this payments module


class Transaction(Base):
    """
    Complete transaction history for all wallet operations.
    
    Business Rules:
    - Every wallet change creates a transaction record
    - Transactions are immutable (never updated, only status changes)
    - Negative amount = deduction, Positive = addition
    - Transaction ID must be unique and traceable
    - All amounts in same currency as wallet
    - Provides complete audit trail
    
    Transaction Flow:
    1. Create with status=PENDING
    2. Process payment (status=PROCESSING)
    3. Update wallet balance
    4. Mark as COMPLETED or FAILED
    5. If failed, may create REVERSED transaction
    
    Performance:
    - Indexed by user_id, wallet_id, txn_id, created_at
    - Partitioning by date recommended for high volume
    """
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Unique transaction identifier for external tracking
    txn_id = Column(String(64), nullable=False, unique=True, index=True)
    
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Transaction details
    amount = Column(Numeric(10, 2), nullable=False)  # Positive or negative
    type = Column(SQLEnum(TransactionTypeEnum), nullable=False, index=True)
    status = Column(SQLEnum(TransactionStatusEnum), nullable=False, default=TransactionStatusEnum.PENDING, index=True)
    
    # Optional related entities
    # Temporarily commented out to fix table creation order
    # TODO: Re-enable after ensuring rides and payouts tables are created first
    ride_id = Column(UUID(as_uuid=True), nullable=True)  # ForeignKey removed temporarily
    payout_id = Column(UUID(as_uuid=True), nullable=True)  # ForeignKey removed temporarily
    # ride_id = Column(UUID(as_uuid=True), ForeignKey("rides.id", ondelete="SET NULL"), nullable=True)
    # payout_id = Column(UUID(as_uuid=True), ForeignKey("payouts.id", ondelete="SET NULL"), nullable=True)
    
    # Payment provider details
    provider = Column(String(50), nullable=True)  # "jazzcash", "easypaisa", "stripe"
    provider_txn_id = Column(String(128), nullable=True, index=True)  # External transaction ID
    provider_response = Column(Text, nullable=True)  # JSON response from provider
    
    # Description and notes
    description = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Metadata for additional context
    meta_data = Column(Text, nullable=True)  # JSON: commission split, fees, etc.
    
    # Relationships
    wallet = relationship("Wallet")
    user = relationship("User", back_populates="transactions")
    # Temporarily commented out - foreign keys removed
    # ride = relationship("Ride", back_populates="transactions")
    # payout = relationship("Payout", back_populates="transaction", uselist=False)
    
    # Constraints and indexes
    __table_args__ = (
        Index('idx_transaction_wallet_id', 'wallet_id'),
        Index('idx_transaction_user_id', 'user_id'),
        Index('idx_transaction_type', 'type'),
        Index('idx_transaction_status', 'status'),
        Index('idx_transaction_created_at', 'created_at'),
        Index('idx_transaction_provider_txn_id', 'provider_txn_id'),
    )

    def __repr__(self):
        return f"<Transaction(txn_id={self.txn_id}, type={self.type}, amount={self.amount}, status={self.status})>"


class Payout(Base):
    """
    Driver earnings payout records.
    
    Business Rules:
    - Only verified drivers can request payouts
    - Minimum payout amount (e.g., 500 PKR)
    - Payouts processed in batches (daily/weekly)
    - Driver must have valid payment method configured
    - Payout amount = driver earnings - platform commission
    - Creates corresponding PAYOUT transaction in wallet
    
    Payout Process:
    1. Driver requests payout
    2. System validates (verified, min amount, balance)
    3. Create payout record (status=PENDING)
    4. Deduct from driver wallet (create transaction)
    5. Send to payment provider (status=PROCESSING)
    6. Provider confirms (status=COMPLETED)
    7. Update transaction and payout status
    
    Security:
    - Payout methods must be verified (bank account, phone)
    - Rate limiting on payout requests
    - Fraud detection for unusual patterns
    """
    __tablename__ = "payouts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    driver_id = Column(UUID(as_uuid=True), ForeignKey("driver_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Payout amount (what driver receives)
    amount = Column(Numeric(10, 2), nullable=False)
    
    # Payment method and details
    method = Column(SQLEnum(PayoutMethodEnum), nullable=False)
    account_details = Column(Text, nullable=False)  # Encrypted bank/wallet account info
    
    # Status tracking
    status = Column(SQLEnum(PayoutStatusEnum), nullable=False, default=PayoutStatusEnum.PENDING, index=True)
    
    # Provider details
    provider = Column(String(50), nullable=True)
    provider_payout_id = Column(String(128), nullable=True, index=True)
    provider_response = Column(Text, nullable=True)
    
    # Admin processing
    admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    admin_action = Column(String(20), nullable=True)  # approved/rejected
    admin_action_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Notes and metadata
    notes = Column(Text, nullable=True)
    meta_data = Column(Text, nullable=True)  # JSON: fees, exchange rates, etc.
    
    # Relationships
    driver = relationship("DriverProfile")
    # TODO: Add FK and re-enable payout <-> transaction relationship
    admin = relationship("User", foreign_keys=[admin_id])
    
    # Constraints and indexes
    __table_args__ = (
        CheckConstraint('amount > 0', name='check_payout_amount_positive'),
        Index('idx_payout_driver_id', 'driver_id'),
        Index('idx_payout_status', 'status'),
        Index('idx_payout_created_at', 'created_at'),
    )

    def __repr__(self):
        return f"<Payout(driver_id={self.driver_id}, amount={self.amount}, method={self.method}, status={self.status})>"


class PaymentIntent(Base):
    """
    Payment Intent for Top-Ups (Prompt 10).
    
    Tracks the lifecycle of a payment from creation to completion.
    Used for wallet top-ups via Easypaisa, JazzCash, or Card.
    
    Flow:
    1. User initiates top-up → Create PaymentIntent (status=PENDING)
    2. System calls provider adapter → Get payment_url
    3. User completes payment on provider site
    4. Provider sends webhook → Update status
    5. Credit wallet if status=SUCCESS
    
    Business Rules:
    - Each payment intent has unique idempotency_key
    - Payment URL expires after 30 minutes
    - Commission applied on successful payments
    - Webhook must validate signature before processing
    """
    __tablename__ = "payment_intents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Amount details (PKR)
    amount = Column(Numeric(10, 2), nullable=False)  # Requested amount
    commission_amount = Column(Numeric(10, 2), default=0.00, nullable=False)
    net_amount = Column(Numeric(10, 2), nullable=False)  # amount - commission
    
    # Provider details
    provider = Column(SQLEnum(PaymentProviderEnum), nullable=False, index=True)
    provider_transaction_id = Column(String(255), unique=True, nullable=True, index=True)
    provider_order_id = Column(String(255), unique=True, nullable=True, index=True)
    
    # Payment URL for redirect
    payment_url = Column(Text, nullable=True)
    redirect_url = Column(Text, nullable=True)  # Return URL after payment
    
    # Status tracking
    status = Column(SQLEnum(PaymentStatusEnum), default=PaymentStatusEnum.PENDING, nullable=False, index=True)
    failure_reason = Column(Text, nullable=True)
    
    # Idempotency
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    
    # Webhook tracking
    webhook_received_at = Column(DateTime, nullable=True)
    webhook_payload = Column(Text, nullable=True)  # JSON string
    
    # Additional information (renamed from 'metadata' to avoid SQLAlchemy reserved word)
    extra_data = Column(Text, nullable=True)  # JSON: device_info, IP, etc.
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)  # Payment session expiry
    
    # Relationships
    wallet = relationship("Wallet")
    user = relationship("User")
    
    # Indexes
    __table_args__ = (
        Index('idx_payment_intents_status_created', 'status', 'created_at'),
        Index('idx_payment_intents_provider_status', 'provider', 'status'),
        Index('idx_payment_intents_user_id', 'user_id'),
    )
    
    def __repr__(self):
        return f"<PaymentIntent(id={self.id}, amount={self.amount}, provider={self.provider}, status={self.status})>"


class IdempotencyRecord(Base):
    """
    Idempotency tracking for webhook deduplication (Prompt 10).
    
    Prevents duplicate processing of payment webhooks.
    Essential for handling retries from payment providers.
    
    Business Rules:
    - Records expire after 1 hour (PAYMENTS_IDEMPOTENCY_TTL)
    - Key format: {provider}:{transaction_id}:{timestamp}
    - If key exists → return 200 with cached response
    - If key doesn't exist → process request, store key
    
    Use Cases:
    - Payment provider retries webhook
    - Network issues cause duplicate requests
    - User refreshes payment confirmation page
    """
    __tablename__ = "idempotency_records"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    
    # Request details
    request_method = Column(String(10), nullable=False)  # POST, GET, etc.
    request_path = Column(String(500), nullable=False)
    request_payload = Column(Text, nullable=True)  # JSON string
    
    # Response details (cached for replay)
    response_status = Column(String(10), nullable=True)  # HTTP status code
    response_payload = Column(Text, nullable=True)  # JSON response
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)  # Auto-expire after TTL
    
    # Indexes
    __table_args__ = (
        Index('idx_idempotency_records_key', 'idempotency_key'),
        Index('idx_idempotency_records_expires', 'expires_at'),
    )
    
    def __repr__(self):
        return f"<IdempotencyRecord(key={self.idempotency_key}, expires_at={self.expires_at})>"
