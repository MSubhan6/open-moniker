"""Base adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
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

    def resolve_query(
        self,
        config: dict[str, Any],
        format_vars: dict[str, str] | None = None,
        catalog_dir: Path | None = None,
    ) -> str:
        """
        Resolve query from config - either inline or from file.

        Checks for 'query_file' first, then 'query', then 'table'.
        Applies format_vars to the query string.

        Args:
            config: Source binding config dictionary
            format_vars: Variables to substitute in query (e.g., {path}, {moniker})
            catalog_dir: Base directory for resolving relative query_file paths

        Returns:
            The resolved query string

        Raises:
            AdapterError: If no query source is found
        """
        format_vars = format_vars or {}

        # Check for query_file first (external SQL file)
        if config.get("query_file"):
            query_path = Path(config["query_file"])
            if catalog_dir and not query_path.is_absolute():
                query_path = catalog_dir / query_path
            if not query_path.exists():
                raise AdapterError(f"Query file not found: {query_path}")
            query = query_path.read_text()
        elif config.get("query"):
            query = config["query"]
        elif config.get("table"):
            table = config["table"]
            # Apply format vars to table name if it has placeholders
            if format_vars:
                try:
                    table = table.format(**format_vars)
                except KeyError:
                    pass  # Ignore missing placeholders in table name
            return f"SELECT * FROM {table}"
        else:
            raise AdapterError("Either 'query', 'query_file', or 'table' required in config")

        # Apply format vars to query
        if format_vars:
            try:
                query = query.format(**format_vars)
            except KeyError as e:
                raise AdapterError(f"Missing format variable in query: {e}")

        return query


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
