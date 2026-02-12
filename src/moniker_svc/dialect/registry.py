"""Dialect registry for looking up dialects by source type."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import VersionDialect


class DialectRegistry:
    """Registry for version dialect implementations.

    Provides a singleton-like access pattern for dialect lookup by source type.
    Dialects are lazily instantiated on first use.
    """

    _instance: "DialectRegistry | None" = None
    _dialects: dict[str, "VersionDialect"]

    def __init__(self) -> None:
        self._dialects = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in dialects."""
        from .snowflake import SnowflakeDialect
        from .oracle import OracleDialect
        from .rest import RestDialect
        from .mssql import MSSQLDialect

        self.register(SnowflakeDialect())
        self.register(OracleDialect())
        self.register(RestDialect())
        self.register(MSSQLDialect())

    def register(self, dialect: "VersionDialect") -> None:
        """Register a dialect by its name."""
        self._dialects[dialect.name] = dialect

    def get(self, source_type: str) -> "VersionDialect":
        """Get dialect for a source type.

        Args:
            source_type: The source type (e.g., 'snowflake', 'oracle', 'rest')

        Returns:
            The dialect implementation, or SnowflakeDialect as default

        Notes:
            - Defaults to Snowflake dialect for unknown source types
            - Source types are case-insensitive
        """
        source_lower = source_type.lower()
        if source_lower in self._dialects:
            return self._dialects[source_lower]
        # Default to Snowflake for SQL-like sources
        return self._dialects.get("snowflake", self._dialects["snowflake"])

    def list_dialects(self) -> list[str]:
        """Return list of registered dialect names."""
        return list(self._dialects.keys())

    @classmethod
    def instance(cls) -> "DialectRegistry":
        """Get the singleton registry instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


def get_dialect(source_type: str) -> "VersionDialect":
    """Convenience function to get a dialect by source type.

    Args:
        source_type: The source type (e.g., 'snowflake', 'oracle', 'rest')

    Returns:
        The dialect implementation
    """
    return DialectRegistry.instance().get(source_type)
