"""
Payment Adapter Factory (Prompt 10)

Factory pattern for creating payment adapter instances.
Supports dynamic provider selection based on configuration.

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

import logging
from typing import Dict, Any, Optional

from .base_adapter import BasePaymentAdapter
from .easypaisa_adapter import EasypaisaAdapter
from .jazzcash_adapter import JazzCashAdapter
from .card_adapter import CardAdapter
from ..models import PaymentProviderEnum

logger = logging.getLogger(__name__)


class PaymentAdapterFactory:
    """
    Factory for creating payment adapter instances.
    
    Usage:
        adapter = PaymentAdapterFactory.create_adapter(
            provider="easypaisa",
            sandbox_mode=True,
            credentials={
                "api_key": "your_key",
                "secret_key": "your_secret"
            }
        )
        
        response = await adapter.create_topup_session(
            user_id="user123",
            amount=Decimal("1000.00"),
            redirect_url="https://app.com/confirm"
        )
    """
    
    _adapters: Dict[str, type] = {
        PaymentProviderEnum.EASYPAISA.value: EasypaisaAdapter,
        PaymentProviderEnum.JAZZCASH.value: JazzCashAdapter,
        PaymentProviderEnum.CARD.value: CardAdapter
    }
    
    @classmethod
    def create_adapter(
        cls,
        provider: str,
        sandbox_mode: bool = True,
        credentials: Optional[Dict[str, Any]] = None
    ) -> BasePaymentAdapter:
        """
        Create payment adapter instance for specified provider.
        
        Args:
            provider: Payment provider name (easypaisa, jazzcash, card)
            sandbox_mode: Use sandbox environment
            credentials: Provider-specific credentials
        
        Returns:
            Initialized payment adapter instance
        
        Raises:
            ValueError: If provider is not supported
        
        Examples:
            # Easypaisa adapter
            adapter = PaymentAdapterFactory.create_adapter(
                provider="easypaisa",
                sandbox_mode=True,
                credentials={
                    "api_key": "your_key",
                    "secret_key": "your_secret",
                    "merchant_id": "MERCHANT_001"
                }
            )
            
            # JazzCash adapter
            adapter = PaymentAdapterFactory.create_adapter(
                provider="jazzcash",
                sandbox_mode=True,
                credentials={
                    "merchant_id": "MC12345",
                    "password": "your_password",
                    "integrity_salt": "your_salt"
                }
            )
            
            # Card adapter (always sandbox)
            adapter = PaymentAdapterFactory.create_adapter(
                provider="card",
                credentials={
                    "gateway_key": "your_key",
                    "gateway_secret": "your_secret"
                }
            )
        """
        # Validate provider
        if provider not in cls._adapters:
            supported = ", ".join(cls._adapters.keys())
            raise ValueError(f"Unsupported provider: {provider}. Supported: {supported}")
        
        # Get adapter class
        adapter_class = cls._adapters[provider]
        
        # Initialize credentials
        credentials = credentials or {}
        
        # Create adapter instance
        adapter = adapter_class(
            sandbox_mode=sandbox_mode,
            **credentials
        )
        
        logger.info(f"[PaymentAdapterFactory] Created {provider} adapter (sandbox={sandbox_mode})")
        
        return adapter
    
    @classmethod
    def get_supported_providers(cls) -> list:
        """
        Get list of supported payment providers.
        
        Returns:
            List of provider names (str)
        """
        return list(cls._adapters.keys())
    
    @classmethod
    def register_adapter(cls, provider: str, adapter_class: type):
        """
        Register custom payment adapter.
        
        Allows extending factory with new providers without modifying core code.
        
        Args:
            provider: Provider name (e.g., "stripe", "paypal")
            adapter_class: Adapter class inheriting from BasePaymentAdapter
        
        Example:
            class StripeAdapter(BasePaymentAdapter):
                # Implementation
                pass
            
            PaymentAdapterFactory.register_adapter("stripe", StripeAdapter)
        """
        if not issubclass(adapter_class, BasePaymentAdapter):
            raise TypeError("Adapter class must inherit from BasePaymentAdapter")
        
        cls._adapters[provider] = adapter_class
        logger.info(f"[PaymentAdapterFactory] Registered custom adapter: {provider}")


# Convenience functions for direct adapter creation

def create_easypaisa_adapter(
    api_key: str,
    secret_key: str,
    merchant_id: str,
    sandbox_mode: bool = True
) -> EasypaisaAdapter:
    """Create Easypaisa adapter with credentials."""
    return EasypaisaAdapter(
        sandbox_mode=sandbox_mode,
        api_key=api_key,
        secret_key=secret_key,
        merchant_id=merchant_id
    )


def create_jazzcash_adapter(
    merchant_id: str,
    password: str,
    integrity_salt: str,
    sandbox_mode: bool = True
) -> JazzCashAdapter:
    """Create JazzCash adapter with credentials."""
    return JazzCashAdapter(
        sandbox_mode=sandbox_mode,
        merchant_id=merchant_id,
        password=password,
        integrity_salt=integrity_salt
    )


def create_card_adapter(
    gateway_key: str,
    gateway_secret: str
) -> CardAdapter:
    """Create Card adapter with credentials (always sandbox)."""
    return CardAdapter(
        sandbox_mode=True,  # Always sandbox
        gateway_key=gateway_key,
        gateway_secret=gateway_secret
    )
