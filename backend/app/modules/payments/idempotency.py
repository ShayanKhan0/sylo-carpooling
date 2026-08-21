"""
Idempotency System (Prompt 10)

Prevents duplicate webhook processing using database-backed idempotency records.
TTL-based expiry ensures automatic cleanup of old records.
Fully async, using AsyncSession.

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from .models import IdempotencyRecord

logger = logging.getLogger(__name__)


class IdempotencyError(Exception):
    """Raised when idempotency check fails."""
    pass


class IdempotencySystem:
    """
    Database-backed idempotency system for webhook deduplication.
    
    Features:
    - Prevents duplicate webhook processing
    - Caches response for replay (idempotent replay)
    - TTL-based expiry (default: 1 hour)
    - Thread-safe with database unique constraint
    
    Flow:
    1. check_and_register(key, request_data)
    2. If key exists: return cached response (duplicate)
    3. If key not exists: register key, return None (process request)
    4. After processing: cache_response(key, response)
    5. Future requests with same key: return cached response
    
    Usage:
        idempotency = IdempotencySystem(db)
        
        # Check for duplicate
        cached = await idempotency.check_and_register(
            key="webhook_txn_12345",
            request_method="POST",
            request_path="/api/payments/webhook",
            request_payload={"transaction_id": "12345"}
        )
        
        if cached:
            # Duplicate request - return cached response
            return cached
        
        # New request - process it
        result = await process_webhook(...)
        
        # Cache response for future duplicates
        await idempotency.cache_response(
            key="webhook_txn_12345",
            response_status=200,
            response_payload={"status": "success"}
        )
    """
    
    def __init__(self, db: AsyncSession, ttl_seconds: int = 3600):
        """
        Initialize idempotency system.
        
        Args:
            db: Database session
            ttl_seconds: Time-to-live for idempotency records (default: 1 hour)
        """
        self.db = db
        self.ttl_seconds = ttl_seconds
    
    async def check_and_register(
        self,
        key: str,
        request_method: str,
        request_path: str,
        request_payload: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Check if request is duplicate and register if new.
        
        Args:
            key: Idempotency key (e.g., webhook transaction ID)
            request_method: HTTP method (POST, GET, etc.)
            request_path: Request path (/api/payments/webhook)
            request_payload: Request body
        
        Returns:
            Cached response if duplicate, None if new request
        
        Raises:
            IdempotencyError: If registration fails
        """
        try:
            # Check for existing record
            result = await self.db.execute(
                select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == key)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                # Duplicate request detected
                if existing.expires_at < datetime.utcnow():
                    # Record expired - delete and process as new
                    logger.info(f"[Idempotency] Expired record found for key: {key}, deleting")
                    await self.db.delete(existing)
                    await self.db.commit()
                else:
                    # Valid cached response
                    logger.info(f"[Idempotency] Duplicate request detected for key: {key}, returning cached response")
                    
                    if existing.response_payload:
                        return {
                            "status": existing.response_status,
                            "payload": json.loads(existing.response_payload) if isinstance(existing.response_payload, str) else existing.response_payload,
                            "cached": True,
                            "cached_at": existing.created_at.isoformat()
                        }
                    else:
                        # No cached response yet (processing in progress)
                        logger.warning(f"[Idempotency] Duplicate request in progress for key: {key}")
                        raise IdempotencyError(f"Request with key {key} is already being processed")
            
            # Register new idempotency record
            expires_at = datetime.utcnow() + timedelta(seconds=self.ttl_seconds)
            
            record = IdempotencyRecord(
                idempotency_key=key,
                request_method=request_method,
                request_path=request_path,
                request_payload=json.dumps(request_payload) if request_payload else None,
                response_status=None,
                response_payload=None,
                expires_at=expires_at
            )
            
            self.db.add(record)
            await self.db.commit()
            
            logger.info(f"[Idempotency] Registered new key: {key}, expires at {expires_at.isoformat()}")
            
            return None  # New request - proceed with processing
        
        except IntegrityError:
            # Race condition - another request registered the key simultaneously
            await self.db.rollback()
            logger.warning(f"[Idempotency] Race condition detected for key: {key}, retrying")
            
            # Retry check
            result = await self.db.execute(
                select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == key)
            )
            existing = result.scalar_one_or_none()
            
            if existing and existing.response_payload:
                return {
                    "status": existing.response_status,
                    "payload": json.loads(existing.response_payload) if isinstance(existing.response_payload, str) else existing.response_payload,
                    "cached": True,
                    "cached_at": existing.created_at.isoformat()
                }
            else:
                raise IdempotencyError(f"Request with key {key} is already being processed")
        
        except Exception as e:
            logger.error(f"[Idempotency] Error checking key {key}: {e}")
            raise IdempotencyError(f"Idempotency check failed: {e}")
    
    async def cache_response(
        self,
        key: str,
        response_status: int,
        response_payload: Dict[str, Any]
    ) -> bool:
        """
        Cache response for future duplicate requests.
        
        Args:
            key: Idempotency key
            response_status: HTTP status code
            response_payload: Response body
        
        Returns:
            True if cached successfully
        """
        try:
            result = await self.db.execute(
                select(IdempotencyRecord).where(IdempotencyRecord.idempotency_key == key)
            )
            record = result.scalar_one_or_none()
            
            if record:
                record.response_status = response_status
                record.response_payload = json.dumps(response_payload)
                await self.db.commit()
                
                logger.info(f"[Idempotency] Cached response for key: {key}, status={response_status}")
                return True
            else:
                logger.warning(f"[Idempotency] Key not found for caching: {key}")
                return False
        
        except Exception as e:
            logger.error(f"[Idempotency] Error caching response for key {key}: {e}")
            return False
    
    async def cleanup_expired(self) -> int:
        """
        Delete expired idempotency records.
        
        Should be run periodically (e.g., daily Celery task).
        
        Returns:
            Number of records deleted
        """
        try:
            from sqlalchemy import delete as sql_delete
            result = await self.db.execute(
                sql_delete(IdempotencyRecord).where(
                    IdempotencyRecord.expires_at < datetime.utcnow()
                )
            )
            deleted = result.rowcount
            await self.db.commit()
            
            logger.info(f"[Idempotency] Cleaned up {deleted} expired records")
            return deleted
        
        except Exception as e:
            logger.error(f"[Idempotency] Error cleaning up expired records: {e}")
            await self.db.rollback()
            return 0


# Async convenience functions

async def check_idempotency(
    db: AsyncSession,
    key: str,
    request_method: str,
    request_path: str,
    request_payload: Optional[Dict[str, Any]] = None,
    ttl_seconds: int = 3600
) -> Optional[Dict[str, Any]]:
    """Check and register idempotency key. Returns cached response if duplicate, None if new."""
    system = IdempotencySystem(db, ttl_seconds)
    return await system.check_and_register(key, request_method, request_path, request_payload)


async def cache_idempotent_response(
    db: AsyncSession,
    key: str,
    response_status: int,
    response_payload: Dict[str, Any]
) -> bool:
    """Cache response for idempotency key. Returns True if cached successfully."""
    system = IdempotencySystem(db)
    return await system.cache_response(key, response_status, response_payload)
