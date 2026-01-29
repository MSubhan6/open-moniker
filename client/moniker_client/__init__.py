"""
Moniker Client Library

Provides unified access to firm data via monikers.

Usage:
    from moniker_client import read, describe, MonikerClient

    # Simple read
    data = read("moniker://market-data/prices/equity/AAPL")

    # With options
    client = MonikerClient(service_url="http://moniker-svc:8000")
    data = client.read("market-data/prices/equity/AAPL")

    # Get ownership info
    info = describe("market-data/prices/equity")

    # Server-side fetch (returns data directly)
    from moniker_client import fetch
    result = fetch("risk.cvar/DESK_A/20240115/ALL")
    print(result.data)

    # AI-discoverable metadata
    from moniker_client import metadata
    meta = metadata("risk.cvar")
    print(meta.semantic_tags)
    print(meta.cost_indicators)

    # Quick data sampling
    from moniker_client import sample
    preview = sample("govies.treasury/US/10Y/ALL")
"""

from .client import (
    MonikerClient,
    read,
    describe,
    list_children,
    lineage,
    fetch,
    metadata,
    sample,
    # Result types
    FetchResult,
    MetadataResult,
    SampleResult,
    ResolvedSource,
    # Exceptions
    MonikerError,
    ResolutionError,
    FetchError,
    NotFoundError,
    AccessDeniedError,
)
from .config import ClientConfig

__version__ = "0.1.0"

__all__ = [
    # Client
    "MonikerClient",
    "ClientConfig",
    # Functions
    "read",
    "describe",
    "list_children",
    "lineage",
    "fetch",
    "metadata",
    "sample",
    # Result types
    "FetchResult",
    "MetadataResult",
    "SampleResult",
    "ResolvedSource",
    # Exceptions
    "MonikerError",
    "ResolutionError",
    "FetchError",
    "NotFoundError",
    "AccessDeniedError",
]
