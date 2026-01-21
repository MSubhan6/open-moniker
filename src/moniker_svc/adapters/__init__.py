"""Data source adapters."""

from .base import DataAdapter, AdapterResult, AdapterError
from .registry import AdapterRegistry

__all__ = [
    "DataAdapter",
    "AdapterResult",
    "AdapterError",
    "AdapterRegistry",
]
