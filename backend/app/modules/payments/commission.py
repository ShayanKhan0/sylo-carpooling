"""
Commission Engine (Prompt 10)

Calculates commission for top-ups and payouts.
Percentage-based with configurable rates.

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class CommissionEngine:
    """
    Commission calculation engine for payments.
    
    Features:
    - Percentage-based commission
    - Separate rates for top-ups and payouts
    - Configurable minimum/maximum commission
    - Rounding to 2 decimal places
    
    Commission Structure:
    - Top-up: User pays commission on deposit (e.g., 5% of PKR 1000 = PKR 50)
    - Payout: Platform deducts commission before transfer (e.g., 3% of PKR 1000 = PKR 30)
    
    Usage:
        engine = CommissionEngine(topup_rate=0.05, payout_rate=0.03)
        
        # Calculate top-up commission
        net_amount, commission = engine.calculate_topup_commission(
            amount=Decimal("1000.00")
        )
        # Result: net_amount=950.00, commission=50.00
        
        # Calculate payout commission
        net_amount, commission = engine.calculate_payout_commission(
            amount=Decimal("1000.00")
        )
        # Result: net_amount=970.00, commission=30.00
    """
    
    def __init__(
        self,
        topup_rate: Decimal = Decimal("0.05"),  # 5% default
        payout_rate: Decimal = Decimal("0.03"),  # 3% default
        min_commission: Decimal = Decimal("0.00"),
        max_commission: Optional[Decimal] = None
    ):
        """
        Initialize commission engine.
        
        Args:
            topup_rate: Commission rate for top-ups (0.05 = 5%)
            payout_rate: Commission rate for payouts (0.03 = 3%)
            min_commission: Minimum commission amount (PKR)
            max_commission: Maximum commission amount (PKR, None = unlimited)
        """
        self.topup_rate = topup_rate
        self.payout_rate = payout_rate
        self.min_commission = min_commission
        self.max_commission = max_commission
        
        logger.info(
            f"[CommissionEngine] Initialized: topup={topup_rate*100}%, "
            f"payout={payout_rate*100}%, min={min_commission}, max={max_commission}"
        )
    
    def calculate_topup_commission(
        self,
        amount: Decimal,
        custom_rate: Optional[Decimal] = None
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculate commission for wallet top-up.
        
        Formula:
        - Commission = amount × topup_rate
        - Net Amount = amount - commission
        
        Example:
        - Amount: PKR 1000
        - Rate: 5%
        - Commission: PKR 50
        - Net Amount: PKR 950 (credited to wallet)
        
        Args:
            amount: Top-up amount requested by user
            custom_rate: Override default rate (optional)
        
        Returns:
            Tuple[net_amount, commission]
        """
        if amount <= 0:
            raise ValueError(f"Invalid top-up amount: {amount}")
        
        # Use custom rate or default
        rate = custom_rate if custom_rate is not None else self.topup_rate
        
        # Calculate commission
        commission = self._apply_commission(amount, rate)
        
        # Net amount (what user receives in wallet)
        net_amount = amount - commission
        
        logger.info(
            f"[CommissionEngine] Top-up commission calculated: "
            f"amount={amount}, rate={rate*100}%, commission={commission}, net={net_amount}"
        )
        
        return net_amount, commission
    
    def calculate_payout_commission(
        self,
        amount: Decimal,
        custom_rate: Optional[Decimal] = None
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculate commission for driver payout.
        
        Formula:
        - Commission = amount × payout_rate
        - Net Amount = amount - commission
        
        Example:
        - Amount: PKR 1000 (driver's wallet balance)
        - Rate: 3%
        - Commission: PKR 30
        - Net Amount: PKR 970 (transferred to driver's account)
        
        Args:
            amount: Payout amount requested by driver
            custom_rate: Override default rate (optional)
        
        Returns:
            Tuple[net_amount, commission]
        """
        if amount <= 0:
            raise ValueError(f"Invalid payout amount: {amount}")
        
        # Use custom rate or default
        rate = custom_rate if custom_rate is not None else self.payout_rate
        
        # Calculate commission
        commission = self._apply_commission(amount, rate)
        
        # Net amount (what driver receives in account)
        net_amount = amount - commission
        
        logger.info(
            f"[CommissionEngine] Payout commission calculated: "
            f"amount={amount}, rate={rate*100}%, commission={commission}, net={net_amount}"
        )
        
        return net_amount, commission
    
    def _apply_commission(self, amount: Decimal, rate: Decimal) -> Decimal:
        """
        Apply commission rate with min/max constraints.
        
        Args:
            amount: Base amount
            rate: Commission rate (0.05 = 5%)
        
        Returns:
            Commission amount (rounded to 2 decimals)
        """
        # Calculate raw commission
        commission = amount * rate
        
        # Round to 2 decimal places
        commission = commission.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
        # Apply minimum commission
        if commission < self.min_commission:
            commission = self.min_commission
        
        # Apply maximum commission (if set)
        if self.max_commission is not None and commission > self.max_commission:
            commission = self.max_commission
        
        return commission
    
    def get_effective_rate(
        self,
        amount: Decimal,
        is_topup: bool = True
    ) -> Decimal:
        """
        Get effective commission rate after min/max constraints.
        
        Useful for displaying actual rate to users.
        
        Args:
            amount: Transaction amount
            is_topup: True for top-up, False for payout
        
        Returns:
            Effective rate as decimal (0.05 = 5%)
        """
        rate = self.topup_rate if is_topup else self.payout_rate
        commission = self._apply_commission(amount, rate)
        
        # Calculate effective rate
        effective_rate = commission / amount if amount > 0 else Decimal("0")
        
        return effective_rate


# Convenience functions

def calculate_topup_commission(
    amount: Decimal,
    rate: Decimal = Decimal("0.05"),
    min_commission: Decimal = Decimal("0.00"),
    max_commission: Optional[Decimal] = None
) -> Tuple[Decimal, Decimal]:
    """
    Calculate top-up commission (convenience function).
    
    Args:
        amount: Top-up amount
        rate: Commission rate (default: 5%)
        min_commission: Minimum commission
        max_commission: Maximum commission
    
    Returns:
        Tuple[net_amount, commission]
    """
    engine = CommissionEngine(
        topup_rate=rate,
        min_commission=min_commission,
        max_commission=max_commission
    )
    return engine.calculate_topup_commission(amount)


def calculate_payout_commission(
    amount: Decimal,
    rate: Decimal = Decimal("0.03"),
    min_commission: Decimal = Decimal("0.00"),
    max_commission: Optional[Decimal] = None
) -> Tuple[Decimal, Decimal]:
    """
    Calculate payout commission (convenience function).
    
    Args:
        amount: Payout amount
        rate: Commission rate (default: 3%)
        min_commission: Minimum commission
        max_commission: Maximum commission
    
    Returns:
        Tuple[net_amount, commission]
    """
    engine = CommissionEngine(
        payout_rate=rate,
        min_commission=min_commission,
        max_commission=max_commission
    )
    return engine.calculate_payout_commission(amount)


def apply_commission(
    amount: Decimal,
    rate: Decimal,
    min_commission: Decimal = Decimal("0.00"),
    max_commission: Optional[Decimal] = None
) -> Tuple[Decimal, Decimal]:
    """
    Apply commission to any amount (generic function).
    
    Args:
        amount: Base amount
        rate: Commission rate
        min_commission: Minimum commission
        max_commission: Maximum commission
    
    Returns:
        Tuple[net_amount, commission]
    """
    engine = CommissionEngine(
        topup_rate=rate,
        min_commission=min_commission,
        max_commission=max_commission
    )
    return engine.calculate_topup_commission(amount)
