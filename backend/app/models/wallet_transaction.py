"""
Purpose: Wallet transaction model for payment history.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Records all wallet transactions (topup, payout, ride payments).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, DECIMAL, Index, JSON, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base
from app.models.enums import TransactionType, TransactionStatus

if TYPE_CHECKING:
    from app.models.wallet import Wallet


class WalletTransaction(Base):
    """
    Wallet transaction model for payment history.
    
    Attributes:
        id: Unique identifier (UUID)
        wallet_id: Foreign key to wallet
        amount: Transaction amount (positive for credits, negative for debits)
        type: Transaction type (topup, payout, ride)
        status: Transaction status (pending, completed, failed)
        metadata: Additional transaction details (JSON)
        created_at: Transaction timestamp
        updated_at: Last update timestamp
    
    Relationships:
        wallet: Associated wallet
    """
    
    __tablename__ = "wallet_transactions"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    
    # Wallet Reference
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wallets.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Transaction Details
    amount: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 2),
        nullable=False
    )
    
    type: Mapped[TransactionType] = mapped_column(
        SQLEnum(TransactionType, name="transaction_type"),
        nullable=False,
        index=True
    )
    
    status: Mapped[TransactionStatus] = mapped_column(
        SQLEnum(TransactionStatus, name="transaction_status"),
        nullable=False,
        default=TransactionStatus.PENDING,
        index=True
    )
    
    # Additional metadata (payment gateway info, ride details, etc.)
    # Note: renamed from 'metadata' to 'transaction_metadata' to avoid conflict with SQLAlchemy's Base.metadata
    transaction_metadata: Mapped[dict | None] = mapped_column(
        "metadata",  # Column name in database is still 'metadata'
        JSON,
        nullable=True,
        comment="Additional transaction details: {ride_id: 'uuid', payment_method: 'card', gateway_txn_id: 'xxx'}"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        index=True
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    wallet: Mapped["Wallet"] = relationship(
        "Wallet",
        back_populates="transactions"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_wallet_transactions_wallet_id", "wallet_id"),
        Index("idx_wallet_transactions_type", "type"),
        Index("idx_wallet_transactions_status", "status"),
        Index("idx_wallet_transactions_created_at", "created_at"),
        # Composite indexes for common queries
        Index("idx_wallet_transactions_wallet_status", "wallet_id", "status"),
        Index("idx_wallet_transactions_wallet_created", "wallet_id", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<WalletTransaction(id={self.id}, wallet_id={self.wallet_id}, amount={self.amount}, type={self.type}, status={self.status})>"
