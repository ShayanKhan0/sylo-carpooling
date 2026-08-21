"""
Payment Adapters Module (Prompt 10)

Pluggable payment adapters for multiple providers.
Supports Easypaisa, JazzCash, and Card payments.

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

from .base_adapter import BasePaymentAdapter, TopupResponse
from .easypaisa_adapter import EasypaisaAdapter
from .jazzcash_adapter import JazzCashAdapter
from .card_adapter import CardAdapter
from .factory import (
    PaymentAdapterFactory,
    create_easypaisa_adapter,
    create_jazzcash_adapter,
    create_card_adapter
)

__all__ = [
    # Base classes
    "BasePaymentAdapter",
    "TopupResponse",
    
    # Concrete adapters
    "EasypaisaAdapter",
    "JazzCashAdapter",
    "CardAdapter",
    
    # Factory
    "PaymentAdapterFactory",
    
    # Convenience functions
    "create_easypaisa_adapter",
    "create_jazzcash_adapter",
    "create_card_adapter"
]
