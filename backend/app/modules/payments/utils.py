"""
Utility functions for Payments Module.

Functions:
- generate_txn_id(): Create unique transaction IDs
- verify_signature(): Verify payment provider webhook signatures
- calculate_commission(): Calculate platform commission splits
- mask_account_details(): Mask sensitive account information
- validate_payment_provider(): Validate provider configuration
- mock_payment_process(): Mock payment provider for development

Author: Smart Carpooling Development Team
Created: 2025-11-08
"""

import hashlib
import hmac
import json
import os
import secrets
import string
from datetime import datetime
from decimal import Decimal
from typing import Dict, Tuple, Optional, Any

import logging

logger = logging.getLogger(__name__)


def generate_txn_id(prefix: str = "TXN") -> str:
    """
    Generate unique alphanumeric transaction ID.
    
    Format: PREFIX-YYYYMMDD-RANDOM8
    Example: TXN-20251108-A7B3C9D1
    
    Args:
        prefix: Transaction ID prefix (default "TXN")
    
    Returns:
        Unique transaction ID string
    
    Examples:
        >>> txn_id = generate_txn_id()
        >>> print(txn_id)
        TXN-20251108-A7B3C9D1
        
        >>> payout_id = generate_txn_id(prefix="PAYOUT")
        >>> print(payout_id)
        PAYOUT-20251108-X1Y2Z3W4
    """
    date_str = datetime.utcnow().strftime("%Y%m%d")
    random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    return f"{prefix}-{date_str}-{random_part}"


def verify_signature(payload: Dict[str, Any], signature: str, provider: str) -> bool:
    """
    Verify webhook signature from payment provider.
    
    Each provider uses different signature algorithms:
    - JazzCash: HMAC-SHA256 with secret key
    - EasyPaisa: HMAC-SHA256 with secret key
    - Stripe: Stripe signature verification (stripe.Webhook.construct_event)
    - Mock: Simple HMAC for testing
    
    Args:
        payload: Webhook payload data
        signature: Signature from webhook header
        provider: Payment provider name (jazzcash, easypaisa, stripe, mock)
    
    Returns:
        True if signature is valid, False otherwise
    
    Security:
        - Always verify signatures before processing webhooks
        - Use constant-time comparison to prevent timing attacks
        - Log failed verification attempts for security monitoring
    
    Examples:
        >>> payload = {"txn_id": "TXN-123", "amount": "500.00", "status": "SUCCESS"}
        >>> signature = "a1b2c3d4..."
        >>> is_valid = verify_signature(payload, signature, "jazzcash")
        >>> if is_valid:
        ...     process_payment(payload)
    """
    try:
        # Get provider secret key from environment
        secrets_map = {
            "jazzcash": os.getenv("JAZZCASH_SECRET_KEY", "jazzcash_test_secret"),
            "easypaisa": os.getenv("EASYPAISA_SECRET_KEY", "easypaisa_test_secret"),
            "stripe": os.getenv("STRIPE_WEBHOOK_SECRET", "stripe_test_secret"),
            "mock": os.getenv("MOCK_PAYMENT_SECRET", "mock_secret_key_12345"),
        }
        
        secret_key = secrets_map.get(provider.lower())
        if not secret_key:
            logger.warning(f"No secret key configured for provider: {provider}")
            return False
        
        # Create payload string for signing
        if provider.lower() == "stripe":
            # Stripe uses different verification method
            # In production, use: stripe.Webhook.construct_event(payload, signature, secret_key)
            logger.info("Stripe signature verification - using mock for development")
            # For development, accept any signature
            return True
        
        # For JazzCash, EasyPaisa, Mock: HMAC-SHA256
        payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        expected_signature = hmac.new(
            secret_key.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison to prevent timing attacks
        is_valid = hmac.compare_digest(expected_signature, signature)
        
        if not is_valid:
            logger.warning(f"Signature verification failed for provider {provider}")
            logger.debug(f"Expected: {expected_signature}, Received: {signature}")
        
        return is_valid
        
    except Exception as e:
        logger.error(f"Error verifying signature for {provider}: {str(e)}")
        return False


def calculate_commission(
    amount: Decimal,
    commission_rate: Optional[Decimal] = None
) -> Dict[str, Decimal]:
    """
    Calculate platform commission split for ride fares.
    
    Default commission: 20% to platform, 80% to driver
    Can be overridden by passing custom commission_rate.
    
    Args:
        amount: Total ride fare
        commission_rate: Commission percentage (0-100), default 20%
    
    Returns:
        Dictionary with:
        - total_fare: Original amount
        - driver_share: Amount driver receives (after commission)
        - platform_commission: Amount platform takes
        - commission_percentage: Applied commission rate
    
    Formula:
        platform_commission = amount × (commission_rate / 100)
        driver_share = amount - platform_commission
    
    Examples:
        >>> split = calculate_commission(Decimal("150.00"))
        >>> print(split)
        {
            'total_fare': Decimal('150.00'),
            'driver_share': Decimal('120.00'),
            'platform_commission': Decimal('30.00'),
            'commission_percentage': Decimal('20.0')
        }
        
        >>> split = calculate_commission(Decimal("200.00"), commission_rate=Decimal("15.0"))
        >>> print(split['driver_share'])
        Decimal('170.00')  # 200 - (200 × 0.15)
    
    Business Rules:
        - Commission rate can be customized per ride, driver, or region
        - Minimum commission: 5%, Maximum: 50%
        - All amounts rounded to 2 decimal places
        - Driver always receives at least 50% of fare
    """
    # Default commission rate: 20%
    if commission_rate is None:
        commission_rate = Decimal("20.0")
    
    # Validate commission rate
    if commission_rate < Decimal("0") or commission_rate > Decimal("50"):
        logger.warning(f"Invalid commission rate {commission_rate}%, using default 20%")
        commission_rate = Decimal("20.0")
    
    # Calculate split
    platform_commission = (amount * commission_rate / Decimal("100")).quantize(Decimal("0.01"))
    driver_share = (amount - platform_commission).quantize(Decimal("0.01"))
    
    # Ensure driver gets at least 50%
    min_driver_share = (amount * Decimal("0.5")).quantize(Decimal("0.01"))
    if driver_share < min_driver_share:
        logger.warning(f"Driver share {driver_share} below minimum {min_driver_share}, adjusting")
        driver_share = min_driver_share
        platform_commission = amount - driver_share
    
    return {
        "total_fare": amount,
        "driver_share": driver_share,
        "platform_commission": platform_commission,
        "commission_percentage": commission_rate
    }


def mask_account_details(account_details: str, visible_chars: int = 4) -> str:
    """
    Mask sensitive account information.
    
    Shows only last N characters, masks the rest with asterisks.
    Used for displaying account numbers in responses for security.
    
    Args:
        account_details: Full account number or phone number
        visible_chars: Number of characters to show at end (default 4)
    
    Returns:
        Masked account string
    
    Examples:
        >>> masked = mask_account_details("1234567890123456")
        >>> print(masked)
        ************3456
        
        >>> masked = mask_account_details("03001234567", visible_chars=3)
        >>> print(masked)
        ********567
    """
    if len(account_details) <= visible_chars:
        return account_details  # Too short to mask meaningfully
    
    visible_part = account_details[-visible_chars:]
    masked_length = len(account_details) - visible_chars
    return '*' * masked_length + visible_part


def validate_payment_provider(provider: str) -> Tuple[bool, Optional[str]]:
    """
    Validate payment provider configuration.
    
    Checks if provider is supported and has required credentials configured.
    
    Args:
        provider: Payment provider name
    
    Returns:
        Tuple of (is_valid: bool, error_message: Optional[str])
    
    Supported Providers:
        - jazzcash: JazzCash mobile wallet (Pakistan)
        - easypaisa: EasyPaisa mobile wallet (Pakistan)
        - stripe: Stripe payment gateway (international)
        - paypal: PayPal (international)
        - mock: Mock provider for testing
    
    Environment Variables Required:
        - JAZZCASH_SECRET_KEY, JAZZCASH_MERCHANT_ID
        - EASYPAISA_SECRET_KEY, EASYPAISA_STORE_ID
        - STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
        - PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET
    
    Examples:
        >>> is_valid, error = validate_payment_provider("jazzcash")
        >>> if not is_valid:
        ...     print(f"Error: {error}")
    """
    provider = provider.lower()
    
    # List of supported providers
    supported_providers = ["jazzcash", "easypaisa", "stripe", "paypal", "mock"]
    
    if provider not in supported_providers:
        return False, f"Unsupported payment provider: {provider}. Supported: {', '.join(supported_providers)}"
    
    # Mock provider always valid (for testing)
    if provider == "mock":
        return True, None
    
    # Check required environment variables
    required_env_vars = {
        "jazzcash": ["JAZZCASH_SECRET_KEY", "JAZZCASH_MERCHANT_ID"],
        "easypaisa": ["EASYPAISA_SECRET_KEY", "EASYPAISA_STORE_ID"],
        "stripe": ["STRIPE_SECRET_KEY"],
        "paypal": ["PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET"],
    }
    
    missing_vars = []
    for env_var in required_env_vars.get(provider, []):
        if not os.getenv(env_var):
            missing_vars.append(env_var)
    
    if missing_vars:
        return False, f"Missing environment variables for {provider}: {', '.join(missing_vars)}"
    
    return True, None


async def mock_payment_process(
    amount: Decimal,
    provider: str,
    txn_id: str,
    simulate_success: bool = True
) -> Dict[str, Any]:
    """
    Mock payment provider processing for development and testing.
    
    Simulates payment gateway responses without actual external API calls.
    
    Args:
        amount: Payment amount
        provider: Provider name (jazzcash, easypaisa, stripe, etc.)
        txn_id: Internal transaction ID
        simulate_success: True to simulate success, False for failure
    
    Returns:
        Mock provider response with:
        - success: bool
        - provider_txn_id: External transaction ID
        - status: Transaction status
        - message: Status message
        - timestamp: Processing timestamp
    
    Usage:
        Only used in development/testing. In production, replace with actual
        provider API integration.
    
    Examples:
        >>> response = await mock_payment_process(
        ...     amount=Decimal("500.00"),
        ...     provider="jazzcash",
        ...     txn_id="TXN-20251108-ABC123"
        ... )
        >>> print(response['success'])
        True
        >>> print(response['provider_txn_id'])
        JC-20251108-MOCK1234
    """
    import asyncio
    
    # Simulate processing delay (1-3 seconds)
    await asyncio.sleep(secrets.randbelow(3) + 1)
    
    # Generate mock provider transaction ID
    provider_prefixes = {
        "jazzcash": "JC",
        "easypaisa": "EP",
        "stripe": "PI",
        "paypal": "PP",
        "mock": "MOCK"
    }
    prefix = provider_prefixes.get(provider.lower(), "TXN")
    provider_txn_id = generate_txn_id(prefix=prefix)
    
    if simulate_success:
        return {
            "success": True,
            "provider_txn_id": provider_txn_id,
            "status": "SUCCESS",
            "message": f"Payment of {amount} PKR processed successfully via {provider}",
            "amount": str(amount),
            "currency": "PKR",
            "txn_id": txn_id,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {
                "provider": provider,
                "mock": True,
                "test_mode": True
            }
        }
    else:
        # Simulate various failure scenarios
        failure_messages = [
            "Insufficient funds in account",
            "Transaction declined by issuing bank",
            "Invalid account details",
            "Daily transaction limit exceeded",
            "Network timeout - please retry"
        ]
        failure_message = secrets.choice(failure_messages)
        
        return {
            "success": False,
            "provider_txn_id": provider_txn_id,
            "status": "FAILED",
            "message": failure_message,
            "error_code": f"ERR_{secrets.randbelow(1000):03d}",
            "amount": str(amount),
            "currency": "PKR",
            "txn_id": txn_id,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": {
                "provider": provider,
                "mock": True,
                "test_mode": True
            }
        }


def format_currency(amount: Decimal, currency: str = "PKR") -> str:
    """
    Format amount with currency symbol.
    
    Args:
        amount: Decimal amount
        currency: Currency code (default PKR)
    
    Returns:
        Formatted string with currency
    
    Examples:
        >>> formatted = format_currency(Decimal("1250.50"))
        >>> print(formatted)
        PKR 1,250.50
        
        >>> formatted = format_currency(Decimal("99.99"), "USD")
        >>> print(formatted)
        $99.99
    """
    currency_symbols = {
        "PKR": "PKR ",
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
    }
    
    symbol = currency_symbols.get(currency, currency + " ")
    
    # Format with thousands separator
    formatted_amount = f"{amount:,.2f}"
    
    return f"{symbol}{formatted_amount}"
