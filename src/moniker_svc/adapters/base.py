"""Base adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..catalog.types import SourceBinding, SourceType
from ..moniker.types import Moniker


class AdapterError(Exception):
    """Base exception for adapter errors."""
    pass


class AdapterConnectionError(AdapterError):
    """Raised when connection to data source fails."""
    pass


class AdapterQueryError(AdapterError):
    """Raised when query execution fails."""
    pass


class AdapterNotFoundError(AdapterError):
    """Raised when requested data is not found."""
    pass


@dataclass(frozen=True, slots=True)
class AdapterResult:
    """
    Result from a data adapter query.

    Designed to be serializable to JSON for the API response.
    """
    data: Any  # The actual data (dict, list, or scalar)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Source information (for lineage)
    source_type: SourceType | None = None
    source_path: str | None = None  # e.g., table name, API endpoint

    # Timing
    query_ms: float = 0.0
    cached: bool = False

    # Row/record count if applicable
    row_count: int | None = None


class DataAdapter(ABC):
    """
    Abstract base class for data source adapters.

    Each adapter type (Snowflake, Oracle, REST, etc.) implements this interface.
    Adapters are stateless - connection details come from the SourceBinding.
    """

    @property
    @abstractmethod
    def source_type(self) -> SourceType:
        """The source type this adapter handles."""
        ...

    @abstractmethod
    async def fetch(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> AdapterResult:
        """
        Fetch data for a moniker.

        Args:
            moniker: The full moniker being requested
            binding: The source binding with connection config
            sub_path: If the binding is on an ancestor, this is the remaining path

        Returns:
            AdapterResult with the data

        Raises:
            AdapterError: On fetch failure
        """
        ...

    @abstractmethod
    async def list_children(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> list[str]:
        """
        List available children under a path.

        Returns list of child names (not full paths).
        """
        ...

    async def describe(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Get metadata about a data source.

        Default implementation returns basic info from the binding.
        Override for source-specific schema/metadata.
        """
        return {
            "source_type": self.source_type.value,
            "config_keys": list(binding.config.keys()),
            "schema": binding.schema,
            "read_only": binding.read_only,
        }

    async def health_check(self, binding: SourceBinding) -> bool:
        """
        Check if the data source is healthy/reachable.

        Default returns True. Override for actual health checks.
        """
        return True


class InMemoryAdapter(DataAdapter):
    """
    Adapter for in-memory data (for testing and static lookups).

    Config:
        data: The actual data to return
        children: List of child names (for list operation)
    """

    @property
    def source_type(self) -> SourceType:
        return SourceType.STATIC

    async def fetch(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> AdapterResult:
        data = binding.config.get("data")
        if data is None:
            raise AdapterNotFoundError(f"No data configured for {moniker}")

        # If there's a sub_path, try to navigate into the data
        if sub_path and isinstance(data, dict):
            for segment in sub_path.split("/"):
                if segment and isinstance(data, dict):
                    data = data.get(segment)
                    if data is None:
                        raise AdapterNotFoundError(
                            f"Path segment '{segment}' not found in {moniker}"
                        )

        return AdapterResult(
            data=data,
            source_type=self.source_type,
            source_path=str(moniker.path),
        )

    async def list_children(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> list[str]:
        children = binding.config.get("children", [])
        data = binding.config.get("data")

        # If data is a dict, keys are children
        if isinstance(data, dict) and not children:
            children = list(data.keys())

        return children
