"""In-memory cache with atomic refresh."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Generic, TypeVar


logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class CacheEntry(Generic[T]):
    """A cached value with metadata."""
    value: T
    created_at: float
    ttl_seconds: float
    key: str

    @property
    def is_expired(self) -> bool:
        return time.time() > self.created_at + self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


@dataclass
class InMemoryCache:
    """
    Thread-safe in-memory cache with:
    - TTL-based expiration
    - Atomic refresh (for hot reload)
    - LRU eviction
    - Background refresh support

    Optimized for read-heavy workloads (moniker lookups).
    """
    # Maximum entries
    max_size: int = 10000

    # Default TTL
    default_ttl_seconds: float = 300.0  # 5 minutes

    # Internal storage
    _store: dict[str, CacheEntry] = field(default_factory=dict, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _access_order: list[str] = field(default_factory=list, init=False)

    # Stats
    _hits: int = field(default=0, init=False)
    _misses: int = field(default=0, init=False)

    def get(self, key: str) -> Any | None:
        """
        Get a value from cache (synchronous, lock-free read).

        Returns None if not found or expired.
        """
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None

        if entry.is_expired:
            self._misses += 1
            return None

        self._hits += 1
        return entry.value

    def get_entry(self, key: str) -> CacheEntry | None:
        """Get the full cache entry (including metadata)."""
        entry = self._store.get(key)
        if entry is None or entry.is_expired:
            return None
        return entry

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: float | None = None,
    ) -> None:
        """Set a value in cache."""
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds

        entry = CacheEntry(
            value=value,
            created_at=time.time(),
            ttl_seconds=ttl,
            key=key,
        )

        async with self._lock:
            self._store[key] = entry
            self._update_access(key)
            await self._evict_if_needed()

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        async with self._lock:
            if key in self._store:
                del self._store[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                return True
            return False

    async def clear(self) -> None:
        """Clear all entries."""
        async with self._lock:
            self._store.clear()
            self._access_order.clear()

    async def get_or_load(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        ttl_seconds: float | None = None,
    ) -> Any:
        """
        Get from cache or load if missing/expired.

        This is the primary pattern for cache-aside.
        """
        # Fast path: cache hit
        value = self.get(key)
        if value is not None:
            return value

        # Slow path: load and cache
        value = await loader()
        await self.set(key, value, ttl_seconds)
        return value

    async def refresh(
        self,
        key: str,
        loader: Callable[[], Awaitable[Any]],
        ttl_seconds: float | None = None,
    ) -> Any:
        """
        Force refresh a key (for background refresh).

        Loads new value and atomically replaces the old one.
        """
        value = await loader()
        await self.set(key, value, ttl_seconds)
        return value

    async def atomic_replace_all(self, entries: dict[str, Any], ttl_seconds: float | None = None) -> None:
        """
        Atomically replace all cache entries.

        Use for bulk refresh (e.g., reloading catalog from source).
        """
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        now = time.time()

        new_store = {
            key: CacheEntry(value=value, created_at=now, ttl_seconds=ttl, key=key)
            for key, value in entries.items()
        }

        async with self._lock:
            self._store = new_store
            self._access_order = list(new_store.keys())

        logger.info(f"Cache atomically replaced with {len(entries)} entries")

    def _update_access(self, key: str) -> None:
        """Update access order for LRU (caller holds lock)."""
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

    async def _evict_if_needed(self) -> None:
        """Evict oldest entries if over capacity (caller holds lock)."""
        while len(self._store) > self.max_size and self._access_order:
            oldest = self._access_order.pop(0)
            self._store.pop(oldest, None)

    async def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        removed = 0
        async with self._lock:
            expired_keys = [
                key for key, entry in self._store.items()
                if entry.is_expired
            ]
            for key in expired_keys:
                del self._store[key]
                if key in self._access_order:
                    self._access_order.remove(key)
                removed += 1
        return removed

    @property
    def size(self) -> int:
        """Current number of entries."""
        return len(self._store)

    @property
    def stats(self) -> dict:
        """Cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0

        return {
            "size": self.size,
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round(hit_rate, 2),
        }
