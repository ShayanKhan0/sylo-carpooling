"""Cache Layer for Matching Engine

In-memory LRU cache for low-latency cluster lookups and heatmap data.
No external dependency (Redis removed).
"""

import json
import logging
from collections import OrderedDict
from typing import Any, Optional

logger = logging.getLogger(__name__)


class InMemoryLRUCache:
    """
    Thread-safe LRU cache fallback when Redis unavailable.
    Used for cluster data and heatmap buckets.
    """

    def __init__(self, maxsize: int = 1000):
        self.cache: OrderedDict = OrderedDict()
        self.maxsize = maxsize

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache, return None if not found"""
        if key in self.cache:
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """
        Set value in cache with optional TTL (ignored in memory).
        
        Note: TTL not enforced in memory cache (would need background task).
        For production, always use Redis.
        """
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value

        # Evict oldest if over capacity
        if len(self.cache) > self.maxsize:
            self.cache.popitem(last=False)

    async def delete(self, key: str):
        """Remove key from cache"""
        self.cache.pop(key, None)

    async def clear(self):
        """Clear all cache entries"""
        self.cache.clear()


class CacheManager:
    """
    In-memory LRU cache manager for matching engine.
    """

    def __init__(self, redis_url: Optional[str] = None, namespace: str = "matching"):
        self.namespace = namespace
        self.fallback = InMemoryLRUCache(maxsize=1000)
        self.using_redis = False  # kept for API compat

    async def initialize(self):
        """Initialize cache (no-op, in-memory always ready)."""
        logger.info("✅ Matching cache initialized (in-memory)")

    async def close(self):
        """Clear cache."""
        await self.fallback.clear()

    def _make_key(self, key: str) -> str:
        """Namespace keys to avoid collisions"""
        return f"{self.namespace}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        namespaced_key = self._make_key(key)
        return await self.fallback.get(namespaced_key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in cache with optional TTL (TTL ignored in memory)."""
        namespaced_key = self._make_key(key)
        await self.fallback.set(namespaced_key, value, ttl)

    async def get_or_set(
        self,
        key: str,
        factory: callable,
        ttl: Optional[int] = None
    ) -> Any:
        """
        Get value from cache or compute and store if missing.
        
        Args:
            key: Cache key
            factory: Callable that computes value if cache miss
            ttl: TTL in seconds for stored value
            
        Returns:
            Cached or computed value
        """
        value = await self.get(key)
        if value is not None:
            return value

        # Cache miss - compute value
        value = await factory() if callable(factory) else factory
        await self.set(key, value, ttl)
        return value

    async def delete(self, key: str):
        """Delete key from cache."""
        namespaced_key = self._make_key(key)
        await self.fallback.delete(namespaced_key)

    async def delete_pattern(self, pattern: str):
        """Delete all keys matching pattern (clears entire cache in-memory)."""
        await self.fallback.clear()

    async def clear_namespace(self):
        """Clear all keys in current namespace."""
        await self.fallback.clear()


# Global cache instance
_cache_instance: Optional[CacheManager] = None


async def get_cache(redis_url: Optional[str] = None) -> CacheManager:
    """Get or create global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheManager(namespace="matching")
        await _cache_instance.initialize()
    return _cache_instance
