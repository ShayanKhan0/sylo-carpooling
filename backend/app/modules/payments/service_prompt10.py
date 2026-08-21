"""
Enhanced Payment Service Layer (Prompt 10)

New business logic for pluggable payment adapters:
- Top-up session initiation with adapters
- Webhook processing with idempotency
- Driver payout execution
- Commission calculation integration

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    PaymentIntent,
    Wallet,
    Transaction,
    Payout,
    PaymentProviderEnum,
    PaymentStatusEnum,
    TransactionTypeEnum,
    TransactionStatusEnum,
    PayoutStatusEnum
)
from .schemas_prompt10 import (
    TopupSessionRequest,
    TopupSessionResponse,
    WebhookConfirmRequest,
    WebhookConfirmResponse,
    WithdrawRequest,
    WithdrawResponse
)
from .adapters import PaymentAdapterFactory
from .commission import CommissionEngine
from .idempotency import IdempotencySystem
from . import crud

logger = logging.getLogger(__name__)


class PaymentService:
    """
    Enhanced payment service with pluggable adapters (Prompt 10).
    
    Features:
    - Adapter-based payment processing
    - Commission calculation
    - Idempotency handling
    - Webhook signature validation
    - Payout execution
    
    Usage:
        service = PaymentService(
            db=db,
            sandbox_mode=True,
            topup_commission_rate=Decimal("0.05"),
            payout_commission_rate=Decimal("0.03")
        )
        
        # Initiate top-up
        response = await service.initiate_topup(user_id, request)
        
        # Process webhook
        result = await service.process_webhook(webhook_data)
        
        # Execute payout
        result = await service.execute_payout(user_id, request)
    """
    
    def __init__(
        self,
        db: AsyncSession,
        sandbox_mode: bool = True,
        topup_commission_rate: Decimal = Decimal("0.05"),
        payout_commission_rate: Decimal = Decimal("0.03"),
        idempotency_ttl: int = 3600,
        provider_credentials: Optional[Dict[str, Dict[str, Any]]] = None
    ):
        """
        Initialize payment service.
        
        Args:
            db: Database session
            sandbox_mode: Use sandbox environment for all providers
            topup_commission_rate: Commission rate for top-ups (default: 5%)
            payout_commission_rate: Commission rate for payouts (default: 3%)
            idempotency_ttl: TTL for idempotency records (default: 1 hour)
            provider_credentials: Provider-specific API credentials
        """
        self.db = db
        self.sandbox_mode = sandbox_mode
        self.commission_engine = CommissionEngine(
            topup_rate=topup_commission_rate,
            payout_rate=payout_commission_rate
        )
        self.idempotency_system = IdempotencySystem(db, ttl_seconds=idempotency_ttl)
        self.provider_credentials = provider_credentials or {}
        
        logger.info(f"[PaymentService] Initialized (sandbox={sandbox_mode})")
    
    async def initiate_topup(
        self,
        user_id: UUID,
        request: TopupSessionRequest
    ) -> TopupSessionResponse:
        """
        Initiate wallet top-up payment session.
        
        Flow:
        1. Get user wallet
        2. Calculate commission
        3. Create PaymentIntent (status=PENDING)
        4. Get payment adapter for provider
        5. Create top-up session with adapter
        6. Update PaymentIntent with payment_url
        7. Return response with payment_url for user redirect
        
        Args:
            user_id: User ID
            request: Top-up request with amount and provider
        
        Returns:
            TopupSessionResponse with payment_url
        
        Raises:
            HTTPException: If wallet not found or adapter fails
        """
        logger.info(f"[PaymentService] Initiating top-up for user {user_id}: {request.amount} PKR via {request.provider.value}")
        
        # Get wallet
        result = await self.db.execute(select(Wallet).where(Wallet.user_id == user_id))
        wallet = result.scalar_one_or_none()
        if not wallet:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wallet not found"
            )
        
        # Calculate commission
        net_amount, commission = self.commission_engine.calculate_topup_commission(request.amount)
        
        logger.info(f"[PaymentService] Commission calculated: amount={request.amount}, commission={commission}, net={net_amount}")
        
        # Generate idempotency key
        idempotency_key = f"topup_{user_id}_{int(datetime.utcnow().timestamp())}_{uuid4().hex[:8]}"
        
        # Create PaymentIntent
        intent = PaymentIntent(
            wallet_id=wallet.id,
            user_id=user_id,
            amount=request.amount,
            commission_amount=commission,
            net_amount=net_amount,
            provider=request.provider,
            status=PaymentStatusEnum.PENDING,
            redirect_url=request.redirect_url,
            idempotency_key=idempotency_key,
            expires_at=datetime.utcnow() + timedelta(minutes=30)
        )
        
        self.db.add(intent)
        await self.db.commit()
        await self.db.refresh(intent)
        
        logger.info(f"[PaymentService] Created PaymentIntent: {intent.id}")
        
        try:
            # Get payment adapter
            adapter = PaymentAdapterFactory.create_adapter(
                provider=request.provider.value,
                sandbox_mode=self.sandbox_mode,
                credentials=self.provider_credentials.get(request.provider.value, {})
            )
            
            # Create top-up session with adapter
            adapter_response = await adapter.create_topup_session(
                user_id=str(user_id),
                amount=request.amount,
                redirect_url=request.redirect_url,
                metadata=request.metadata
            )
            
            # Update PaymentIntent with provider details
            intent.provider_transaction_id = adapter_response.transaction_id
            intent.provider_order_id = adapter_response.order_id
            intent.payment_url = adapter_response.payment_url
            intent.status = PaymentStatusEnum.PROCESSING
            
            await self.db.commit()
            
            logger.info(f"[PaymentService] Top-up session created: payment_url={adapter_response.payment_url}")
            
            return TopupSessionResponse(
                payment_url=adapter_response.payment_url,
                transaction_id=adapter_response.transaction_id,
                order_id=adapter_response.order_id,
                amount=request.amount,
                commission=commission,
                net_amount=net_amount,
                provider=request.provider.value,
                expires_at=intent.expires_at.isoformat(),
                idempotency_key=idempotency_key
            )
        
        except Exception as e:
            # Mark intent as failed
            intent.status = PaymentStatusEnum.FAILED
            intent.failure_reason = str(e)
            await self.db.commit()
            
            logger.error(f"[PaymentService] Top-up initiation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initiate payment: {str(e)}"
            )
    
    async def process_webhook(
        self,
        webhook_data: WebhookConfirmRequest
    ) -> WebhookConfirmResponse:
        """
        Process payment webhook from provider.
        
        Flow:
        1. Check idempotency (prevent duplicate processing)
        2. Find PaymentIntent by order_id
        3. Get payment adapter for signature validation
        4. Validate webhook signature
        5. Update PaymentIntent status
        6. If success: Credit wallet and create Transaction
        7. Cache idempotent response
        8. Return confirmation
        
        Args:
            webhook_data: Webhook payload from provider
        
        Returns:
            WebhookConfirmResponse with processing status
        
        Raises:
            HTTPException: If validation fails or processing error
        """
        logger.info(f"[PaymentService] Processing webhook for order: {webhook_data.order_id}")
        
        # Check idempotency
        cached_response = await self.idempotency_system.check_and_register(
            key=f"webhook_{webhook_data.order_id}_{webhook_data.transaction_id}",
            request_method="POST",
            request_path="/api/payments/webhook/confirm",
            request_payload=webhook_data.model_dump()
        )
        
        if cached_response:
            # Duplicate webhook - return cached response
            logger.info(f"[PaymentService] Duplicate webhook detected for order: {webhook_data.order_id}")
            return WebhookConfirmResponse(
                success=True,
                message="Webhook already processed (cached response)",
                order_id=webhook_data.order_id,
                wallet_balance=Decimal(str(cached_response.get("payload", {}).get("wallet_balance", 0))),
                cached=True
            )
        
        # Find PaymentIntent
        intent_res = await self.db.execute(
            select(PaymentIntent).where(PaymentIntent.provider_order_id == webhook_data.order_id)
        )
        intent = intent_res.scalar_one_or_none()
        
        if not intent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment intent not found for order: {webhook_data.order_id}"
            )
        
        # Get payment adapter for signature validation
        adapter = PaymentAdapterFactory.create_adapter(
            provider=intent.provider.value,
            sandbox_mode=self.sandbox_mode,
            credentials=self.provider_credentials.get(intent.provider.value, {})
        )
        
        # Validate webhook signature
        is_valid = await adapter.validate_webhook(
            payload=webhook_data.model_dump(),
            signature=webhook_data.signature
        )
        
        if not is_valid:
            logger.warning(f"[PaymentService] Invalid webhook signature for order: {webhook_data.order_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature"
            )
        
        # Update PaymentIntent
        intent.webhook_received_at = datetime.utcnow()
        intent.webhook_payload = webhook_data.model_dump_json()
        
        # Process based on status
        if webhook_data.status.lower() == "success":
            # Payment successful - credit wallet
            intent.status = PaymentStatusEnum.SUCCESS
            
            w_res = await self.db.execute(select(Wallet).where(Wallet.id == intent.wallet_id))
            wallet = w_res.scalar_one_or_none()
            wallet.balance += intent.net_amount
            wallet.last_updated = datetime.utcnow()
            
            # Create Transaction record
            transaction = Transaction(
                wallet_id=intent.wallet_id,
                user_id=intent.user_id,
                amount=intent.net_amount,
                type=TransactionTypeEnum.TOPUP,
                status=TransactionStatusEnum.COMPLETED,
                provider=intent.provider.value,
                provider_txn_id=intent.provider_transaction_id,
                description=f"Wallet top-up via {intent.provider.value}",
                metadata={"payment_intent_id": str(intent.id), "commission": float(intent.commission_amount)}
            )
            
            self.db.add(transaction)
            await self.db.commit()
            
            logger.info(f"[PaymentService] Payment successful: order={webhook_data.order_id}, amount={intent.net_amount}, new_balance={wallet.balance}")
            
            response = WebhookConfirmResponse(
                success=True,
                message="Payment confirmed and wallet credited",
                order_id=webhook_data.order_id,
                wallet_balance=wallet.balance,
                cached=False
            )
        
        else:
            # Payment failed
            intent.status = PaymentStatusEnum.FAILED
            intent.failure_reason = webhook_data.metadata.get("failure_reason", "Payment declined")
            
            await self.db.commit()
            
            logger.info(f"[PaymentService] Payment failed: order={webhook_data.order_id}, reason={intent.failure_reason}")
            
            response = WebhookConfirmResponse(
                success=False,
                message=f"Payment failed: {intent.failure_reason}",
                order_id=webhook_data.order_id,
                wallet_balance=None,
                cached=False
            )
        
        # Cache idempotent response
        await self.idempotency_system.cache_response(
            key=f"webhook_{webhook_data.order_id}_{webhook_data.transaction_id}",
            response_status=200,
            response_payload=response.model_dump()
        )
        
        return response
    
    async def execute_payout(
        self,
        user_id: UUID,
        request: WithdrawRequest
    ) -> WithdrawResponse:
        """
        Execute driver payout.
        
        Flow:
        1. Get user wallet
        2. Check sufficient balance
        3. Calculate commission
        4. Create Payout record (status=PENDING)
        5. Get payment adapter
        6. Execute payout with adapter
        7. Deduct from wallet if successful
        8. Create Transaction record
        9. Update Payout status
        10. Return response
        
        Args:
            user_id: User ID (driver)
            request: Withdrawal request with amount and provider
        
        Returns:
            WithdrawResponse with payout status
        
        Raises:
            HTTPException: If insufficient balance or payout fails
        """
        logger.info(f"[PaymentService] Executing payout for user {user_id}: {request.amount} PKR via {request.provider.value}")
        
        # Get wallet
        w_res = await self.db.execute(select(Wallet).where(Wallet.user_id == user_id))
        wallet = w_res.scalar_one_or_none()
        if not wallet:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wallet not found"
            )
        
        # Check sufficient balance
        if wallet.balance < request.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient balance. Available: {wallet.balance} PKR, Requested: {request.amount} PKR"
            )
        
        # Calculate commission
        net_amount, commission = self.commission_engine.calculate_payout_commission(request.amount)
        
        logger.info(f"[PaymentService] Payout commission calculated: amount={request.amount}, commission={commission}, net={net_amount}")
        
        # Create Payout record
        payout = Payout(
            wallet_id=wallet.id,
            user_id=user_id,
            amount=request.amount,
            status=PayoutStatusEnum.PENDING,
            method=request.provider.value.upper(),  # EASYPAISA, JAZZCASH, CARD
            account_number=request.account_number,
            metadata=request.metadata
        )
        
        self.db.add(payout)
        await self.db.commit()
        await self.db.refresh(payout)
        
        logger.info(f"[PaymentService] Created Payout: {payout.id}")
        
        try:
            # Get payment adapter
            adapter = PaymentAdapterFactory.create_adapter(
                provider=request.provider.value,
                sandbox_mode=self.sandbox_mode,
                credentials=self.provider_credentials.get(request.provider.value, {})
            )
            
            # Execute payout with adapter
            adapter_response = await adapter.execute_payout(
                user_id=str(user_id),
                amount=net_amount,
                account_number=request.account_number,
                metadata=request.metadata
            )
            
            if adapter_response.get("status") in ["completed", "processing"]:
                # Deduct from wallet
                wallet.balance -= request.amount
                wallet.last_updated = datetime.utcnow()
                
                # Update Payout
                payout.status = PayoutStatusEnum.COMPLETED if adapter_response.get("status") == "completed" else PayoutStatusEnum.PROCESSING
                payout.provider_txn_id = adapter_response.get("transaction_id")
                payout.completed_at = datetime.utcnow() if payout.status == PayoutStatusEnum.COMPLETED else None
                
                # Create Transaction record
                transaction = Transaction(
                    wallet_id=wallet.id,
                    user_id=user_id,
                    amount=request.amount,
                    type=TransactionTypeEnum.PAYOUT,
                    status=TransactionStatusEnum.COMPLETED,
                    provider=request.provider.value,
                    provider_txn_id=adapter_response.get("transaction_id"),
                    description=f"Payout to {request.account_number}",
                    metadata={"payout_id": str(payout.id), "commission": float(commission), "net_amount": float(net_amount)}
                )
                
                self.db.add(transaction)
                await self.db.commit()
                
                logger.info(f"[PaymentService] Payout successful: payout_id={payout.id}, net_amount={net_amount}")
                
                # Mask account number
                masked_account = request.account_number[:6] + "****" if len(request.account_number) > 10 else "****"
                
                return WithdrawResponse(
                    success=True,
                    message=adapter_response.get("message", "Withdrawal successful"),
                    payout_id=str(payout.id),
                    transaction_id=adapter_response.get("transaction_id"),
                    amount=request.amount,
                    commission=commission,
                    net_amount=net_amount,
                    provider=request.provider.value,
                    account_number=masked_account,
                    status=payout.status.value,
                    estimated_settlement=adapter_response.get("estimated_settlement"),
                    wallet_balance=wallet.balance
                )
            
            else:
                # Payout failed
                payout.status = PayoutStatusEnum.FAILED
                payout.failure_reason = adapter_response.get("message", "Payout failed")
                await self.db.commit()
                
                logger.error(f"[PaymentService] Payout failed: {payout.failure_reason}")
                
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=payout.failure_reason
                )
        
        except Exception as e:
            # Mark payout as failed
            payout.status = PayoutStatusEnum.FAILED
            payout.failure_reason = str(e)
            await self.db.commit()
            
            logger.error(f"[PaymentService] Payout execution failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Payout failed: {str(e)}"
            )
