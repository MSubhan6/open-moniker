"""Redis cache adapter for query result caching."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..config import RedisConfig


logger = logging.getLogger(__name__)


@dataclass
class CachedData:
    """Cached query result with metadata."""
    data: list[dict[str, Any]]
    row_count: int
    last_refresh: datetime
    refresh_duration_ms: float
    columns: list[str] | None = None

    def to_json(self) -> str:
        """Serialize to JSON for Redis storage."""
        return json.dumps({
            "data": self.data,
            "row_count": self.row_count,
            "last_refresh": self.last_refresh.isoformat(),
            "refresh_duration_ms": self.refresh_duration_ms,
            "columns": self.columns,
        })

    @classmethod
    def from_json(cls, json_str: str) -> CachedData:
        """Deserialize from JSON."""
        d = json.loads(json_str)
        return cls(
            data=d["data"],
            row_count=d["row_count"],
            last_refresh=datetime.fromisoformat(d["last_refresh"]),
            refresh_duration_ms=d["refresh_duration_ms"],
            columns=d.get("columns"),
        )


class RedisCache:
    """
    Redis-based cache for query results.

    Provides persistent caching that survives service restarts and can be
    shared across multiple service instances.

    Key format: {prefix}{path}
    Value: JSON-serialized CachedData
    """

    def __init__(self, config: RedisConfig):
        self.config = config
        self._client = None
        self._connected = False

    async def connect(self) -> bool:
        """Connect to Redis. Returns True if successful."""
        if not self.config.enabled:
            logger.info("Redis caching disabled")
            return False

        try:
            import redis.asyncio as redis

            self._client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                decode_responses=True,
            )

            # Test connection
            await self._client.ping()
            self._connected = True
            logger.info(f"Connected to Redis at {self.config.host}:{self.config.port}")
            return True

        except ImportError:
            logger.warning("redis package not installed, caching disabled")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._connected = False
            logger.info("Redis connection closed")

    def _key(self, path: str) -> str:
        """Build Redis key from path."""
        return f"{self.config.prefix}{path}"

    async def get(self, path: str) -> CachedData | None:
        """
        Get cached data for a path.

        Returns None if not found or Redis unavailable.
        """
        if not self._connected or not self._client:
            return None

        try:
            key = self._key(path)
            data = await self._client.get(key)

            if data is None:
                return None

            return CachedData.from_json(data)

        except Exception as e:
            logger.error(f"Redis get error for {path}: {e}")
            return None

    async def set(
        self,
        path: str,
        cached_data: CachedData,
        ttl_seconds: int | None = None,
    ) -> bool:
        """
        Store cached data for a path.

        Args:
            path: The moniker path
            cached_data: The data to cache
            ttl_seconds: Optional TTL (if None, no expiration)

        Returns True if successful.
        """
        if not self._connected or not self._client:
            return False

        try:
            key = self._key(path)
            json_data = cached_data.to_json()

            if ttl_seconds:
                await self._client.setex(key, ttl_seconds, json_data)
            else:
                await self._client.set(key, json_data)

            return True

        except Exception as e:
            logger.error(f"Redis set error for {path}: {e}")
            return False

    async def delete(self, path: str) -> bool:
        """Delete cached data for a path."""
        if not self._connected or not self._client:
            return False

        try:
            key = self._key(path)
            await self._client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis delete error for {path}: {e}")
            return False

    async def get_ttl(self, path: str) -> int | None:
        """Get remaining TTL for a cached entry."""
        if not self._connected or not self._client:
            return None

        try:
            key = self._key(path)
            ttl = await self._client.ttl(key)
            # Redis returns -2 if key doesn't exist, -1 if no expiry
            if ttl < 0:
                return None
            return ttl
        except Exception as e:
            logger.error(f"Redis ttl error for {path}: {e}")
            return None

    async def list_cached_paths(self) -> list[str]:
        """List all cached paths."""
        if not self._connected or not self._client:
            return []

        try:
            pattern = f"{self.config.prefix}*"
            keys = []
            async for key in self._client.scan_iter(match=pattern):
                # Remove prefix to get path
                path = key[len(self.config.prefix):]
                keys.append(path)
            return keys
        except Exception as e:
            logger.error(f"Redis scan error: {e}")
            return []

    @property
    def is_connected(self) -> bool:
        """Check if connected to Redis."""
        return self._connected

    async def health_check(self) -> dict[str, Any]:
        """Get health status of Redis connection."""
        if not self._connected or not self._client:
            return {
                "status": "disconnected",
                "enabled": self.config.enabled,
            }

        try:
            start = time.perf_counter()
            await self._client.ping()
            latency_ms = (time.perf_counter() - start) * 1000

            info = await self._client.info("memory")
            used_memory = info.get("used_memory_human", "unknown")

            cached_count = 0
            async for _ in self._client.scan_iter(match=f"{self.config.prefix}*"):
                cached_count += 1

            return {
                "status": "connected",
                "host": f"{self.config.host}:{self.config.port}",
                "latency_ms": round(latency_ms, 2),
                "memory_used": used_memory,
                "cached_queries": cached_count,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
            }
