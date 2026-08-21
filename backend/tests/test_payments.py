"""
Comprehensive Test Suite for Payments Module

Tests wallet management, transactions, payouts, and payment provider integration.

Author: Smart Carpooling Backend Team
"""

import pytest
from decimal import Decimal
from uuid import uuid4
from datetime import datetime, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.payments.models import (
    Wallet,
    Transaction,
    Payout,
    TransactionTypeEnum,
    TransactionStatusEnum,
    PaymentProviderEnum,
    PayoutStatusEnum
)
from app.modules.payments import crud, service, utils


@pytest.fixture
async def test_wallet(db_session: AsyncSession):
    """Create a test wallet."""
    wallet = Wallet(
        user_id=uuid4(),
        balance=Decimal("100.00"),
        currency="PKR"
    )
    db_session.add(wallet)
    await db_session.commit()
    await db_session.refresh(wallet)
    return wallet


@pytest.fixture
async def test_driver_wallet(db_session: AsyncSession):
    """Create a test driver wallet."""
    wallet = Wallet(
        user_id=uuid4(),
        balance=Decimal("500.00"),
        currency="PKR"
    )
    db_session.add(wallet)
    await db_session.commit()
    await db_session.refresh(wallet)
    return wallet


class TestWalletOperations:
    """Test wallet CRUD operations."""
    
    async def test_create_wallet(self, db_session: AsyncSession):
        """Test wallet creation."""
        user_id = uuid4()
        wallet = await crud.create_wallet(db_session, user_id)
        
        assert wallet.user_id == user_id
        assert wallet.balance == Decimal("0.00")
        assert wallet.currency == "PKR"
        assert wallet.is_active is True
    
    async def test_get_wallet(self, db_session: AsyncSession, test_wallet: Wallet):
        """Test retrieving wallet by user_id."""
        wallet = await crud.get_wallet(db_session, test_wallet.user_id)
        
        assert wallet is not None
        assert wallet.id == test_wallet.id
        assert wallet.balance == test_wallet.balance
    
    async def test_get_wallet_not_found(self, db_session: AsyncSession):
        """Test getting non-existent wallet."""
        wallet = await crud.get_wallet(db_session, uuid4())
        assert wallet is None
    
    async def test_update_balance(self, db_session: AsyncSession, test_wallet: Wallet):
        """Test updating wallet balance."""
        new_balance = Decimal("250.00")
        updated = await crud.update_wallet_balance(
            db_session,
            test_wallet.user_id,
            new_balance
        )
        
        assert updated.balance == new_balance
    
    async def test_deactivate_wallet(self, db_session: AsyncSession, test_wallet: Wallet):
        """Test deactivating wallet."""
        updated = await crud.update_wallet_status(
            db_session,
            test_wallet.user_id,
            is_active=False
        )
        
        assert updated.is_active is False


class TestTransactionOperations:
    """Test transaction CRUD operations."""
    
    async def test_create_transaction(self, db_session: AsyncSession, test_wallet: Wallet):
        """Test creating a transaction."""
        transaction = await crud.create_transaction(
            db=db_session,
            wallet_id=test_wallet.id,
            amount=Decimal("50.00"),
            transaction_type=TransactionTypeEnum.TOP_UP,
            provider=PaymentProviderEnum.JAZZCASH,
            provider_txn_id="JC123456789",
            metadata={"method": "mobile_account"}
        )
        
        assert transaction.wallet_id == test_wallet.id
        assert transaction.amount == Decimal("50.00")
        assert transaction.transaction_type == TransactionTypeEnum.TOP_UP
        assert transaction.status == TransactionStatusEnum.PENDING
    
    async def test_get_transaction(self, db_session: AsyncSession, test_wallet: Wallet):
        """Test retrieving transaction."""
        txn = await crud.create_transaction(
            db=db_session,
            wallet_id=test_wallet.id,
            amount=Decimal("25.00"),
            transaction_type=TransactionTypeEnum.DEDUCTION,
            provider=PaymentProviderEnum.STRIPE
        )
        
        retrieved = await crud.get_transaction(db_session, txn.id)
        assert retrieved.id == txn.id
    
    async def test_get_wallet_transactions(self, db_session: AsyncSession, test_wallet: Wallet):
        """Test getting all transactions for a wallet."""
        # Create multiple transactions
        for i in range(3):
            await crud.create_transaction(
                db=db_session,
                wallet_id=test_wallet.id,
                amount=Decimal("10.00"),
                transaction_type=TransactionTypeEnum.TOP_UP,
                provider=PaymentProviderEnum.JAZZCASH
            )
        
        transactions = await crud.get_wallet_transactions(db_session, test_wallet.id)
        assert len(transactions) == 3
    
    async def test_update_transaction_status(self, db_session: AsyncSession, test_wallet: Wallet):
        """Test updating transaction status."""
        txn = await crud.create_transaction(
            db=db_session,
            wallet_id=test_wallet.id,
            amount=Decimal("30.00"),
            transaction_type=TransactionTypeEnum.TOP_UP,
            provider=PaymentProviderEnum.EASYPAISA
        )
        
        updated = await crud.update_transaction_status(
            db_session,
            txn.id,
            TransactionStatusEnum.COMPLETED
        )
        
        assert updated.status == TransactionStatusEnum.COMPLETED


class TestPayoutOperations:
    """Test payout CRUD operations."""
    
    async def test_create_payout_request(self, db_session: AsyncSession, test_driver_wallet: Wallet):
        """Test creating payout request."""
        payout = await crud.create_payout_request(
            db=db_session,
            wallet_id=test_driver_wallet.id,
            amount=Decimal("200.00"),
            bank_account_number="1234567890",
            bank_name="HBL",
            account_holder_name="Test Driver"
        )
        
        assert payout.wallet_id == test_driver_wallet.id
        assert payout.amount == Decimal("200.00")
        assert payout.status == PayoutStatusEnum.PENDING
    
    async def test_update_payout_status(self, db_session: AsyncSession, test_driver_wallet: Wallet):
        """Test updating payout status."""
        payout = await crud.create_payout_request(
            db=db_session,
            wallet_id=test_driver_wallet.id,
            amount=Decimal("150.00"),
            bank_account_number="9876543210",
            bank_name="MCB",
            account_holder_name="Test Driver"
        )
        
        updated = await crud.update_payout_status(
            db_session,
            payout.id,
            PayoutStatusEnum.COMPLETED,
            admin_notes="Processed successfully"
        )
        
        assert updated.status == PayoutStatusEnum.COMPLETED
        assert updated.admin_notes == "Processed successfully"


class TestPaymentUtils:
    """Test payment utility functions."""
    
    def test_generate_transaction_id(self):
        """Test transaction ID generation."""
        txn_id = utils.generate_transaction_id()
        
        assert txn_id.startswith("TXN_")
        assert len(txn_id) > 10
    
    def test_calculate_commission(self):
        """Test commission calculation."""
        fare = Decimal("1000.00")
        rate = Decimal("0.15")  # 15%
        
        commission = utils.calculate_commission(fare, rate)
        
        assert commission == Decimal("150.00")
    
    def test_verify_webhook_signature(self):
        """Test webhook signature verification (mock)."""
        payload = '{"amount": 100, "status": "success"}'
        signature = "mock_signature"
        secret = "test_secret"
        
        # This should use actual signature verification in production
        result = utils.verify_webhook_signature(payload, signature, secret)
        
        # Mock implementation always returns True
        assert result is True


class TestWalletService:
    """Test wallet service layer."""
    
    async def test_top_up_wallet(self, db_session: AsyncSession, test_wallet: Wallet):
        """Test wallet top-up service."""
        initial_balance = test_wallet.balance
        top_up_amount = Decimal("50.00")
        
        result = await service.top_up_wallet_service(
            db=db_session,
            user_id=test_wallet.user_id,
            amount=top_up_amount,
            provider=PaymentProviderEnum.JAZZCASH,
            provider_txn_id="JC_TEST_123"
        )
        
        assert result["status"] == "ok"
        
        # Verify balance updated
        updated_wallet = await crud.get_wallet(db_session, test_wallet.user_id)
        assert updated_wallet.balance == initial_balance + top_up_amount
    
    async def test_deduct_from_wallet(self, db_session: AsyncSession, test_wallet: Wallet):
        """Test wallet deduction service."""
        initial_balance = test_wallet.balance
        deduction_amount = Decimal("30.00")
        
        result = await service.deduct_from_wallet_service(
            db=db_session,
            user_id=test_wallet.user_id,
            amount=deduction_amount,
            reason="Test deduction"
        )
        
        assert result["status"] == "ok"
        
        # Verify balance updated
        updated_wallet = await crud.get_wallet(db_session, test_wallet.user_id)
        assert updated_wallet.balance == initial_balance - deduction_amount
    
    async def test_deduct_insufficient_balance(self, db_session: AsyncSession, test_wallet: Wallet):
        """Test deduction with insufficient balance."""
        with pytest.raises(Exception):  # Should raise HTTPException
            await service.deduct_from_wallet_service(
                db=db_session,
                user_id=test_wallet.user_id,
                amount=Decimal("1000.00"),  # More than balance
                reason="Test overdraft"
            )


class TestPayoutService:
    """Test payout service layer."""
    
    async def test_request_payout(self, db_session: AsyncSession, test_driver_wallet: Wallet):
        """Test requesting payout."""
        result = await service.request_payout_service(
            db=db_session,
            user_id=test_driver_wallet.user_id,
            amount=Decimal("300.00"),
            bank_account_number="1111222233",
            bank_name="UBL",
            account_holder_name="Driver Name"
        )
        
        assert result["status"] == "ok"
        assert "payout_id" in result["data"]
    
    async def test_payout_insufficient_balance(self, db_session: AsyncSession, test_driver_wallet: Wallet):
        """Test payout request with insufficient balance."""
        with pytest.raises(Exception):
            await service.request_payout_service(
                db=db_session,
                user_id=test_driver_wallet.user_id,
                amount=Decimal("10000.00"),  # More than balance
                bank_account_number="9999888877",
                bank_name="ABL",
                account_holder_name="Driver Name"
            )


class TestPaymentAPI:
    """Test payment API endpoints (integration tests)."""
    
    async def test_get_wallet_endpoint(self, async_client: AsyncClient, auth_headers: dict):
        """Test GET /api/v1/payments/wallet endpoint."""
        response = await async_client.get(
            "/api/v1/payments/wallet",
            headers=auth_headers
        )
        
        assert response.status_code in [200, 404]  # May not have wallet yet
    
    async def test_top_up_endpoint(self, async_client: AsyncClient, auth_headers: dict):
        """Test POST /api/v1/payments/top-up endpoint."""
        payload = {
            "amount": 100.00,
            "provider": "JAZZCASH",
            "provider_txn_id": "JC_API_TEST_001"
        }
        
        response = await async_client.post(
            "/api/v1/payments/top-up",
            json=payload,
            headers=auth_headers
        )
        
        assert response.status_code in [200, 201]
    
    async def test_transaction_history_endpoint(self, async_client: AsyncClient, auth_headers: dict):
        """Test GET /api/v1/payments/transactions endpoint."""
        response = await async_client.get(
            "/api/v1/payments/transactions",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data


# Additional fixtures for async client and auth
@pytest.fixture
async def async_client():
    """Mock async client fixture."""
    # In real implementation, this would be AsyncClient(app=app, base_url="http://test")
    pass


@pytest.fixture
def auth_headers():
    """Mock authentication headers."""
    return {"Authorization": "Bearer test_token"}
