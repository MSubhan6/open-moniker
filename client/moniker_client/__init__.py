"""
Moniker Client Library

Provides unified access to firm data via monikers.

Usage:
    # Object-oriented API (recommended)
    from moniker_client import Moniker

    m = Moniker("risk.cvar/DESK_A/20240115/ALL")

    # Get AI-discoverable metadata
    meta = m.metadata()
    print(meta.semantic_tags)
    print(meta.cost_indicators)

    # Fetch data (server-side execution)
    result = m.fetch(limit=100)
    print(result.data)

    # Quick sample
    preview = m.sample(5)

    # Read data (client-side execution)
    data = m.read()

    # Navigate to children
    child = m / "subpath"
    info = child.describe()

    # Functional API (also available)
    from moniker_client import read, fetch, metadata, sample

    data = read("market-data/prices/equity/AAPL")
    meta = metadata("risk.cvar")
    result = fetch("risk.cvar/DESK_A/20240115/ALL", limit=100)
"""

from .client import (
    # Core classes
    Moniker,
    MonikerClient,
    # Convenience functions
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
    # Core classes
    "Moniker",
    "MonikerClient",
    "ClientConfig",
    # Convenience functions
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
