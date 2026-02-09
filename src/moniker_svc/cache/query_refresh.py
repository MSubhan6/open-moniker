"""Background refresh manager for expensive cached queries."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Awaitable

from .redis import RedisCache, CachedData
from ..catalog.types import QueryCacheConfig


logger = logging.getLogger(__name__)


class CacheStatus(str, Enum):
    """Status of cached query result."""
    FRESH = "fresh"      # Within TTL, data is current
    STALE = "stale"      # Past TTL but data available, refresh triggered
    LOADING = "loading"  # No data yet, refresh in progress
    ERROR = "error"      # Refresh failed, may have stale data


@dataclass
class CachedQueryResult:
    """
    Result from cached query with metadata.

    Provides both the data and information about cache state
    for client transparency.
    """
    data: list[dict[str, Any]] | None
    row_count: int | None
    status: CacheStatus
    cached: bool
    cache_age_seconds: float | None = None
    last_refresh: datetime | None = None
    next_refresh: datetime | None = None
    refresh_duration_ms: float | None = None
    message: str | None = None
    columns: list[str] | None = None


@dataclass
class RegisteredQuery:
    """A query registered for background refresh."""
    path: str
    cache_config: QueryCacheConfig
    fetch_fn: Callable[[], Awaitable[tuple[list[dict], list[str] | None]]]
    last_refresh: datetime | None = None
    next_refresh: datetime | None = None
    refresh_in_progress: bool = False
    last_error: str | None = None
    consecutive_errors: int = 0


@dataclass
class CachedQueryManager:
    """
    Manages background refresh of expensive queries.

    Features:
    - Registers queries for scheduled background refresh
    - Serves stale data while refresh is in progress
    - Handles cold starts gracefully (loading state)
    - Tracks refresh metadata for transparency
    """
    redis_cache: RedisCache

    # Internal state
    _registered: dict[str, RegisteredQuery] = field(default_factory=dict, init=False)
    _running: bool = field(default=False, init=False)
    _refresh_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _loading_paths: set[str] = field(default_factory=set, init=False)

    def register(
        self,
        path: str,
        cache_config: QueryCacheConfig,
        fetch_fn: Callable[[], Awaitable[tuple[list[dict], list[str] | None]]],
    ) -> None:
        """
        Register a query for background refresh.

        Args:
            path: The moniker path
            cache_config: Cache configuration
            fetch_fn: Async function that returns (data, columns) tuple
        """
        self._registered[path] = RegisteredQuery(
            path=path,
            cache_config=cache_config,
            fetch_fn=fetch_fn,
            next_refresh=datetime.now(),  # Refresh immediately
        )
        logger.info(
            f"Registered cached query: {path} "
            f"(ttl={cache_config.ttl_seconds}s, "
            f"refresh_interval={cache_config.refresh_interval_seconds}s)"
        )

    def is_registered(self, path: str) -> bool:
        """Check if a path is registered for caching."""
        return path in self._registered

    async def get_cached_result(self, path: str) -> CachedQueryResult:
        """
        Get cached result with cold-start handling.

        Logic:
        1. If fresh data in cache -> return fresh
        2. If stale data in cache -> return stale + trigger background refresh
        3. If no data + refresh in progress -> return loading status
        4. If no data + no refresh -> trigger refresh + return loading status
        """
        registered = self._registered.get(path)
        if not registered:
            return CachedQueryResult(
                data=None,
                row_count=None,
                status=CacheStatus.ERROR,
                cached=False,
                message=f"Path {path} not registered for caching",
            )

        # Try to get from Redis
        cached = await self.redis_cache.get(path)

        if cached:
            age_seconds = (datetime.now() - cached.last_refresh).total_seconds()
            is_stale = age_seconds > registered.cache_config.ttl_seconds

            if is_stale:
                # Trigger background refresh if not already in progress
                if not registered.refresh_in_progress:
                    asyncio.create_task(self._refresh_single(path))

                return CachedQueryResult(
                    data=cached.data,
                    row_count=cached.row_count,
                    status=CacheStatus.STALE,
                    cached=True,
                    cache_age_seconds=age_seconds,
                    last_refresh=cached.last_refresh,
                    next_refresh=registered.next_refresh,
                    refresh_duration_ms=cached.refresh_duration_ms,
                    columns=cached.columns,
                    message="Data is stale, refresh in progress",
                )
            else:
                return CachedQueryResult(
                    data=cached.data,
                    row_count=cached.row_count,
                    status=CacheStatus.FRESH,
                    cached=True,
                    cache_age_seconds=age_seconds,
                    last_refresh=cached.last_refresh,
                    next_refresh=registered.next_refresh,
                    refresh_duration_ms=cached.refresh_duration_ms,
                    columns=cached.columns,
                )

        # No data in cache - check if loading
        if path in self._loading_paths or registered.refresh_in_progress:
            return CachedQueryResult(
                data=None,
                row_count=None,
                status=CacheStatus.LOADING,
                cached=False,
                message="Data is loading, please try again shortly",
            )

        # No data and not loading - trigger refresh
        asyncio.create_task(self._refresh_single(path))

        return CachedQueryResult(
            data=None,
            row_count=None,
            status=CacheStatus.LOADING,
            cached=False,
            message="Data is loading, please try again shortly",
        )

    async def _refresh_single(self, path: str) -> bool:
        """
        Refresh a single query.

        Returns True if successful.
        """
        registered = self._registered.get(path)
        if not registered:
            return False

        # Prevent concurrent refresh of same path
        async with self._refresh_lock:
            if registered.refresh_in_progress:
                return False
            registered.refresh_in_progress = True
            self._loading_paths.add(path)

        try:
            logger.info(f"Starting refresh for {path}")
            start = time.perf_counter()

            # Execute the fetch
            data, columns = await registered.fetch_fn()

            duration_ms = (time.perf_counter() - start) * 1000
            now = datetime.now()

            # Store in Redis
            cached_data = CachedData(
                data=data,
                row_count=len(data),
                last_refresh=now,
                refresh_duration_ms=duration_ms,
                columns=columns,
            )

            success = await self.redis_cache.set(
                path,
                cached_data,
                # Set Redis TTL to be longer than our logical TTL
                # to allow serving stale data during refresh
                ttl_seconds=registered.cache_config.ttl_seconds * 3,
            )

            if success:
                registered.last_refresh = now
                registered.next_refresh = now + timedelta(
                    seconds=registered.cache_config.refresh_interval_seconds
                )
                registered.last_error = None
                registered.consecutive_errors = 0
                logger.info(
                    f"Refreshed {path}: {len(data)} rows in {duration_ms:.0f}ms"
                )
                return True
            else:
                raise Exception("Failed to store in Redis")

        except Exception as e:
            registered.last_error = str(e)
            registered.consecutive_errors += 1
            # Back off on consecutive errors
            backoff = min(300, 30 * registered.consecutive_errors)
            registered.next_refresh = datetime.now() + timedelta(seconds=backoff)
            logger.error(f"Failed to refresh {path}: {e}")
            return False

        finally:
            registered.refresh_in_progress = False
            self._loading_paths.discard(path)

    async def refresh_all_startup(self) -> dict[str, bool]:
        """
        Refresh all queries marked for startup refresh.

        Returns dict of path -> success.
        """
        results = {}

        for path, registered in self._registered.items():
            if registered.cache_config.refresh_on_startup:
                success = await self._refresh_single(path)
                results[path] = success

        return results

    async def refresh_loop(self) -> None:
        """
        Background loop that refreshes queries on schedule.

        Should be started as an asyncio task.
        """
        self._running = True
        logger.info("Starting cached query refresh loop")

        while self._running:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds

                now = datetime.now()
                for path, registered in self._registered.items():
                    if registered.next_refresh and now >= registered.next_refresh:
                        if not registered.refresh_in_progress:
                            asyncio.create_task(self._refresh_single(path))

            except asyncio.CancelledError:
                logger.info("Refresh loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in refresh loop: {e}")

        logger.info("Cached query refresh loop stopped")

    async def stop(self) -> None:
        """Stop the refresh loop."""
        self._running = False

    async def trigger_refresh(self, path: str) -> bool:
        """Manually trigger a refresh for a specific path."""
        if path not in self._registered:
            return False
        return await self._refresh_single(path)

    def get_status(self) -> dict[str, Any]:
        """Get status of all registered queries."""
        queries = []
        for path, registered in self._registered.items():
            queries.append({
                "path": path,
                "ttl_seconds": registered.cache_config.ttl_seconds,
                "refresh_interval_seconds": registered.cache_config.refresh_interval_seconds,
                "last_refresh": registered.last_refresh.isoformat() if registered.last_refresh else None,
                "next_refresh": registered.next_refresh.isoformat() if registered.next_refresh else None,
                "refresh_in_progress": registered.refresh_in_progress,
                "last_error": registered.last_error,
                "consecutive_errors": registered.consecutive_errors,
            })

        return {
            "running": self._running,
            "registered_count": len(self._registered),
            "queries": queries,
        }

    async def get_detailed_status(self) -> dict[str, Any]:
        """Get detailed status including cache contents."""
        status = self.get_status()

        # Add cache info for each query
        for query in status["queries"]:
            path = query["path"]
            cached = await self.redis_cache.get(path)
            if cached:
                query["cached"] = True
                query["cache_row_count"] = cached.row_count
                query["cache_age_seconds"] = (
                    datetime.now() - cached.last_refresh
                ).total_seconds()
                query["cache_refresh_duration_ms"] = cached.refresh_duration_ms
            else:
                query["cached"] = False

        # Add Redis health
        status["redis"] = await self.redis_cache.health_check()

        return status
