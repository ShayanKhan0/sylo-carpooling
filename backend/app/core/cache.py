"""In-memory caching layer that replaces the Redis dependency."""

from __future__ import annotations

import asyncio
import time
from fnmatch import fnmatch
from typing import Any, Dict, Optional

from app.core.logger import get_logger

logger = get_logger(__name__)


class CacheClient:
    """Thread-safe in-memory cache with TTL support and helper utilities."""

    def __init__(self):
        self._store: Dict[str, tuple[Any, Optional[float]]] = {}
        self._lock = asyncio.Lock()
        self._connected = False

    async def connect(self):
        """Initialize cache storage (no external service required)."""
        self._connected = True
        logger.info("✅ In-memory cache initialized (Redis disabled)")

    async def disconnect(self):
        """Clear cache on shutdown."""
        async with self._lock:
            self._store.clear()
        self._connected = False
        logger.info("✅ In-memory cache cleared")

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def _ensure_connected(self):
        if not self._connected:
            await self.connect()

    async def set_cache(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        serialize: str = "json",
    ) -> bool:
        await self._ensure_connected()
        expires_at = time.time() + ttl if ttl else None
        async with self._lock:
            self._store[key] = (value, expires_at)
        logger.debug("✅ Cache SET: %s (TTL: %s)", key, ttl)
        return True

    async def get_cache(self, key: str, deserialize: str = "json") -> Optional[Any]:
        if not self._connected:
            return None
        async with self._lock:
            entry = self._store.get(key)
            if not entry:
                logger.debug("⚠️  Cache MISS: %s", key)
                return None
            value, expires_at = entry
            if expires_at and expires_at < time.time():
                del self._store[key]
                logger.debug("⚠️  Cache EXPIRED: %s", key)
                return None
            logger.debug("✅ Cache HIT: %s", key)
            return value

    async def delete_cache(self, *keys: str) -> int:
        if not self._connected or not keys:
            return 0
        deleted = 0
        async with self._lock:
            for key in keys:
                if key in self._store:
                    del self._store[key]
                    deleted += 1
        if deleted:
            logger.debug("✅ Cache DELETE: %s (%s deleted)", keys, deleted)
        return deleted

    async def invalidate_pattern(self, pattern: str) -> int:
        if not self._connected:
            return 0
        async with self._lock:
            keys_to_remove = [key for key in self._store if fnmatch(key, pattern)]
            for key in keys_to_remove:
                del self._store[key]
        if keys_to_remove:
            logger.info(
                "✅ Cache INVALIDATE: %s (%s keys)", pattern, len(keys_to_remove)
            )
        return len(keys_to_remove)

    async def exists(self, key: str) -> bool:
        value = await self.get_cache(key)
        return value is not None

    async def set_ttl(self, key: str, ttl: int) -> bool:
        if not self._connected:
            return False
        expires_at = time.time() + ttl if ttl else None
        async with self._lock:
            if key not in self._store:
                return False
            value, _ = self._store[key]
            self._store[key] = (value, expires_at)
        return True

    async def get_ttl(self, key: str) -> Optional[int]:
        if not self._connected:
            return None
        async with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            _, expires_at = entry
        if not expires_at:
            return None
        remaining = int(expires_at - time.time())
        return remaining if remaining > 0 else None

    # ========== Specialized Cache Methods ==========

    async def cache_driver_search(
        self,
        search_key: str,
        drivers: list,
        ttl: int = 60,
    ) -> bool:
        key = f"driver_search:{search_key}"
        return await self.set_cache(key, drivers, ttl=ttl)

    async def get_cached_driver_search(self, search_key: str) -> Optional[list]:
        key = f"driver_search:{search_key}"
        return await self.get_cache(key)

    async def cache_ride_match(
        self,
        ride_id: str,
        matches: list,
        ttl: int = 180,
    ) -> bool:
        key = f"ride_match:{ride_id}"
        return await self.set_cache(key, matches, ttl=ttl)

    async def get_cached_ride_match(self, ride_id: str) -> Optional[list]:
        key = f"ride_match:{ride_id}"
        return await self.get_cache(key)

    async def blacklist_token(
        self,
        token_jti: str,
        ttl: int = 604800,
    ) -> bool:
        key = f"blacklist:{token_jti}"
        return await self.set_cache(key, "1", ttl=ttl, serialize="raw")

    async def is_token_blacklisted(self, token_jti: str) -> bool:
        key = f"blacklist:{token_jti}"
        return await self.exists(key)

    # ========== Rate Limiting ==========

    async def check_rate_limit(
        self,
        identifier: str,
        limit: int = 60,
        window: int = 60,
    ) -> tuple[bool, int]:
        if not self._connected:
            return (True, limit)
        key = f"rate_limit:{identifier}"
        now = time.time()
        async with self._lock:
            entry = self._store.get(key)
            if not entry or (entry[1] and entry[1] < now):
                self._store[key] = (1, now + window)
                return (True, limit - 1)
            count, expires_at = entry
            if count >= limit:
                return (False, 0)
            self._store[key] = (count + 1, expires_at)
            return (True, limit - count - 1)


# Global cache instance
cache = CacheClient()


# ========== Helper Functions ==========

async def init_cache():
    await cache.connect()


async def close_cache():
    await cache.disconnect()


async def get_cache_client() -> CacheClient:
    return cache
