"""
Purpose: Wallet model for user payment balances.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Each user has one wallet for managing payments.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, DECIMAL, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.models.wallet_transaction import WalletTransaction


class Wallet(Base):
    """
    Wallet model representing user payment balances.
    
    Attributes:
        id: Unique identifier (UUID)
        user_id: Foreign key to user (one-to-one)
        balance: Current wallet balance
        created_at: Wallet creation timestamp
        updated_at: Last update timestamp
    
    Relationships:
        user: Associated user account
        transactions: All wallet transactions
    """
    
    __tablename__ = "wallets"
    
    # Primary Key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    
    # User Reference (one-to-one)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    
    # Balance
    balance: Mapped[Decimal] = mapped_column(
        DECIMAL(10, 2),
        nullable=False,
        default=Decimal("0.00")
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now()
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )
    
    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="wallet"
    )
    
    transactions: Mapped[list["WalletTransaction"]] = relationship(
        "WalletTransaction",
        back_populates="wallet",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index("idx_wallets_user_id", "user_id", unique=True),
    )
    
    def __repr__(self) -> str:
        return f"<Wallet(id={self.id}, user_id={self.user_id}, balance={self.balance})>"
