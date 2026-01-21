"""Adapter registry - maps source types to adapter instances."""

from __future__ import annotations

from ..catalog.types import SourceType
from .base import DataAdapter, AdapterError


class AdapterRegistry:
    """
    Registry of data adapters by source type.

    Adapters are registered at startup and looked up when
    processing requests.
    """

    def __init__(self):
        self._adapters: dict[SourceType, DataAdapter] = {}

    def register(self, adapter: DataAdapter) -> None:
        """Register an adapter for its source type."""
        self._adapters[adapter.source_type] = adapter

    def get(self, source_type: SourceType) -> DataAdapter:
        """
        Get adapter for a source type.

        Raises:
            AdapterError: If no adapter is registered for the type
        """
        adapter = self._adapters.get(source_type)
        if adapter is None:
            raise AdapterError(
                f"No adapter registered for source type: {source_type.value}"
            )
        return adapter

    def has(self, source_type: SourceType) -> bool:
        """Check if an adapter is registered for a source type."""
        return source_type in self._adapters

    def all_types(self) -> list[SourceType]:
        """Get all registered source types."""
        return list(self._adapters.keys())
