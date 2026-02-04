"""
Domain Configuration Layer

Provides domain-level governance and metadata for the moniker catalog.
Domains are top-level organizational units (e.g., "indices", "commodities")
that sit above the moniker tree.
"""

from .types import Domain
from .registry import DomainRegistry
from .loader import load_domains_from_yaml, load_domains_from_csv
from .serializer import save_domains_to_yaml

__all__ = [
    "Domain",
    "DomainRegistry",
    "load_domains_from_yaml",
    "load_domains_from_csv",
    "save_domains_to_yaml",
]
