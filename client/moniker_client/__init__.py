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
"""

from .client import MonikerClient, read, describe, list_children, lineage
from .config import ClientConfig

__version__ = "0.1.0"

__all__ = [
    "MonikerClient",
    "ClientConfig",
    "read",
    "describe",
    "list_children",
    "lineage",
]
