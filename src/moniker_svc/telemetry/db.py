"""Telemetry database layer with support for SQLite and PostgreSQL."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import aiosqlite

logger = logging.getLogger(__name__)

# Global connection pool
_db_pool: Any = None
_db_type: str = "sqlite"


async def initialize(db_type: str = "sqlite", **config):
    """Initialize the database connection pool."""
    global _db_pool, _db_type

    _db_type = db_type.lower()

    if _db_type == "sqlite":
        db_path = config.get("db_path", "./telemetry.db")
        logger.info(f"Initializing SQLite telemetry database at {db_path}")

        # Create schema if needed
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS access_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    request_id TEXT,
                    resolver_id TEXT NOT NULL,
                    region TEXT,
                    az TEXT,
                    moniker TEXT NOT NULL,
                    path TEXT,
                    namespace TEXT,
                    version TEXT,
                    source_type TEXT,
                    operation TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    latency_ms INTEGER NOT NULL,
                    cache_hit INTEGER DEFAULT 0,
                    status_code INTEGER,
                    error_type TEXT,
                    error_message TEXT,
                    caller_id TEXT,
                    metadata TEXT
                )
                """
            )
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON access_log(timestamp)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_resolver_id ON access_log(resolver_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_outcome ON access_log(outcome)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_moniker ON access_log(moniker)")
            await conn.commit()

        _db_pool = db_path  # For SQLite, we'll create connections on demand

    elif _db_type == "postgres" or _db_type == "postgresql":
        try:
            import asyncpg

            host = config.get("host", "localhost")
            port = config.get("port", 5432)
            database = config.get("database", "moniker_telemetry")
            user = config.get("user", "telemetry")
            password = config.get("password", "")
            pool_size = config.get("pool_size", 10)

            logger.info(f"Initializing PostgreSQL telemetry database at {host}:{port}/{database}")

            _db_pool = await asyncpg.create_pool(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                min_size=2,
                max_size=pool_size,
            )

            logger.info("PostgreSQL telemetry database pool created")

        except ImportError:
            logger.error("asyncpg not installed, falling back to SQLite")
            await initialize("sqlite", db_path="./telemetry.db")

    else:
        logger.warning(f"Unknown database type '{_db_type}', falling back to SQLite")
        await initialize("sqlite", db_path="./telemetry.db")


async def close():
    """Close the database connection pool."""
    global _db_pool

    if _db_pool is not None:
        if _db_type == "postgres" or _db_type == "postgresql":
            await _db_pool.close()
            logger.info("PostgreSQL telemetry database pool closed")
        _db_pool = None


@asynccontextmanager
async def get_connection() -> AsyncIterator[Any]:
    """Get a database connection from the pool."""
    if _db_pool is None:
        raise RuntimeError("Database not initialized")

    if _db_type == "sqlite":
        async with aiosqlite.connect(_db_pool) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn
    else:
        async with _db_pool.acquire() as conn:
            yield conn


async def get_live_metrics(seconds: int = 10) -> list[dict[str, Any]]:
    """Get live metrics for the last N seconds."""
    async with get_connection() as conn:
        if _db_type == "sqlite":
            rows = await conn.execute_fetchall(
                """
                SELECT
                    resolver_id,
                    region,
                    COUNT(*) as requests,
                    AVG(latency_ms) as avg_latency,
                    MAX(latency_ms) as max_latency,
                    SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as errors,
                    SUM(cache_hit) as cache_hits
                FROM access_log
                WHERE datetime(substr(timestamp, 1, 19)) > datetime('now', '-' || ? || ' seconds')
                GROUP BY resolver_id, region
                """,
                (seconds,),
            )

            return [
                {
                    "resolver_id": row[0],
                    "region": row[1] or "local",
                    "requests": row[2],
                    "rps": row[2] / seconds,
                    "avg_latency_ms": round(row[3], 2) if row[3] else 0,
                    "max_latency_ms": row[4] or 0,
                    "p95_latency_ms": round(row[3], 2) if row[3] else 0,  # Approximation
                    "errors": row[5],
                    "cache_hits": row[6],
                }
                for row in rows
            ]

        else:  # PostgreSQL
            rows = await conn.fetch(
                """
                SELECT
                    resolver_id,
                    region,
                    COUNT(*) AS requests,
                    AVG(latency_ms) AS avg_latency,
                    MAX(latency_ms) AS max_latency,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency,
                    SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) AS errors,
                    SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) AS cache_hits
                FROM access_log
                WHERE timestamp > NOW() - INTERVAL '$1 seconds'
                GROUP BY resolver_id, region
                """,
                seconds,
            )

            return [
                {
                    "resolver_id": row["resolver_id"],
                    "region": row["region"] or "local",
                    "requests": row["requests"],
                    "rps": row["requests"] / seconds,
                    "avg_latency_ms": round(float(row["avg_latency"]), 2) if row["avg_latency"] else 0,
                    "max_latency_ms": row["max_latency"] or 0,
                    "p95_latency_ms": round(float(row["p95_latency"]), 2) if row["p95_latency"] else 0,
                    "errors": row["errors"],
                    "cache_hits": row["cache_hits"],
                }
                for row in rows
            ]


async def get_timeseries(
    metric: str = "rps",
    interval: str = "1m",
    hours: int = 1,
) -> list[dict[str, Any]]:
    """Get time-series data for a metric."""
    # Map interval to seconds
    interval_seconds = {
        "10s": 10,
        "1m": 60,
        "5m": 300,
        "1h": 3600,
    }.get(interval, 60)

    async with get_connection() as conn:
        if _db_type == "sqlite":
            # SQLite doesn't have date_trunc, so we'll bucket manually
            if metric == "rps":
                rows = await conn.execute_fetchall(
                    """
                    SELECT
                        datetime(timestamp, 'unixepoch', ?) as bucket,
                        resolver_id,
                        COUNT(*) * 1.0 / ? as value
                    FROM access_log
                    WHERE datetime(timestamp) > datetime('now', '-' || ? || ' hours')
                    GROUP BY bucket, resolver_id
                    ORDER BY bucket ASC
                    """,
                    (f"{interval_seconds} seconds", interval_seconds, hours),
                )

            elif metric == "latency_p95":
                rows = await conn.execute_fetchall(
                    """
                    SELECT
                        datetime(timestamp, 'unixepoch', ?) as bucket,
                        resolver_id,
                        AVG(latency_ms) as value
                    FROM access_log
                    WHERE datetime(timestamp) > datetime('now', '-' || ? || ' hours')
                    GROUP BY bucket, resolver_id
                    ORDER BY bucket ASC
                    """,
                    (f"{interval_seconds} seconds", hours),
                )

            else:
                return []

            return [
                {
                    "timestamp": row[0],
                    "resolver_id": row[1],
                    "value": round(float(row[2]), 2) if row[2] else 0,
                }
                for row in rows
            ]

        else:  # PostgreSQL
            interval_map = {
                "10s": "10 seconds",
                "1m": "1 minute",
                "5m": "5 minutes",
                "1h": "1 hour",
            }

            if metric == "rps":
                rows = await conn.fetch(
                    """
                    SELECT
                        date_trunc($1, timestamp) AS bucket,
                        resolver_id,
                        COUNT(*) / EXTRACT(EPOCH FROM $1::INTERVAL) AS value
                    FROM access_log
                    WHERE timestamp > NOW() - $2::INTERVAL
                    GROUP BY bucket, resolver_id
                    ORDER BY bucket ASC
                    """,
                    interval_map[interval],
                    f"{hours} hours",
                )

            elif metric == "latency_p95":
                rows = await conn.fetch(
                    """
                    SELECT
                        date_trunc($1, timestamp) AS bucket,
                        resolver_id,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS value
                    FROM access_log
                    WHERE timestamp > NOW() - $2::INTERVAL
                    GROUP BY bucket, resolver_id
                    ORDER BY bucket ASC
                    """,
                    interval_map[interval],
                    f"{hours} hours",
                )

            else:
                return []

            return [
                {
                    "timestamp": row["bucket"].isoformat(),
                    "resolver_id": row["resolver_id"],
                    "value": round(float(row["value"]), 2) if row["value"] else 0,
                }
                for row in rows
            ]


async def get_top_monikers(hours: int = 1, limit: int = 10) -> list[dict[str, Any]]:
    """Get top monikers by request count."""
    async with get_connection() as conn:
        if _db_type == "sqlite":
            rows = await conn.execute_fetchall(
                """
                SELECT
                    moniker,
                    COUNT(*) as count,
                    AVG(latency_ms) as avg_latency,
                    SUM(CASE WHEN outcome = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as success_rate
                FROM access_log
                WHERE datetime(timestamp) > datetime('now', '-' || ? || ' hours')
                GROUP BY moniker
                ORDER BY count DESC
                LIMIT ?
                """,
                (hours, limit),
            )

            return [
                {
                    "moniker": row[0],
                    "count": row[1],
                    "avg_latency_ms": round(row[2], 2) if row[2] else 0,
                    "success_rate": round(row[3], 1) if row[3] else 0,
                }
                for row in rows
            ]

        else:  # PostgreSQL
            rows = await conn.fetch(
                """
                SELECT
                    moniker,
                    COUNT(*) as count,
                    AVG(latency_ms) as avg_latency,
                    SUM(CASE WHEN outcome = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as success_rate
                FROM access_log
                WHERE timestamp > NOW() - $1::INTERVAL
                GROUP BY moniker
                ORDER BY count DESC
                LIMIT $2
                """,
                f"{hours} hours",
                limit,
            )

            return [
                {
                    "moniker": row["moniker"],
                    "count": row["count"],
                    "avg_latency_ms": round(float(row["avg_latency"]), 2) if row["avg_latency"] else 0,
                    "success_rate": round(float(row["success_rate"]), 1) if row["success_rate"] else 0,
                }
                for row in rows
            ]


async def get_error_summary(hours: int = 1) -> list[dict[str, Any]]:
    """Get error summary."""
    async with get_connection() as conn:
        if _db_type == "sqlite":
            rows = await conn.execute_fetchall(
                """
                SELECT
                    error_type,
                    COUNT(*) as count,
                    GROUP_CONCAT(DISTINCT moniker, ', ') as affected_monikers
                FROM access_log
                WHERE datetime(timestamp) > datetime('now', '-' || ? || ' hours')
                  AND outcome != 'SUCCESS'
                  AND error_type IS NOT NULL
                GROUP BY error_type
                ORDER BY count DESC
                LIMIT 10
                """,
                (hours,),
            )

            return [
                {
                    "error_type": row[0],
                    "count": row[1],
                    "affected_monikers": row[2].split(", ")[:5] if row[2] else [],
                }
                for row in rows
            ]

        else:  # PostgreSQL
            rows = await conn.fetch(
                """
                SELECT
                    error_type,
                    COUNT(*) as count,
                    ARRAY_AGG(DISTINCT moniker) as affected_monikers
                FROM access_log
                WHERE timestamp > NOW() - $1::INTERVAL
                  AND outcome != 'SUCCESS'
                  AND error_type IS NOT NULL
                GROUP BY error_type
                ORDER BY count DESC
                LIMIT 10
                """,
                f"{hours} hours",
            )

            return [
                {
                    "error_type": row["error_type"],
                    "count": row["count"],
                    "affected_monikers": row["affected_monikers"][:5] if row["affected_monikers"] else [],
                }
                for row in rows
            ]
