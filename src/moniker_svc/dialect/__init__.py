"""Dialect module for SQL/API translation by source type."""

from .base import VersionDialect
from .registry import DialectRegistry, get_dialect
from .snowflake import SnowflakeDialect
from .oracle import OracleDialect
from .rest import RestDialect
from .mssql import MSSQLDialect
from .placeholders import (
    PLACEHOLDERS,
    PLACEHOLDER_ALIASES,
    PlaceholderInfo,
    get_placeholder_help,
    list_placeholders,
    format_placeholder_reference,
    get_pattern,
)

__all__ = [
    # Dialect classes
    "VersionDialect",
    "DialectRegistry",
    "get_dialect",
    "SnowflakeDialect",
    "OracleDialect",
    "RestDialect",
    "MSSQLDialect",
    # Placeholder helpers
    "PLACEHOLDERS",
    "PLACEHOLDER_ALIASES",
    "PlaceholderInfo",
    "get_placeholder_help",
    "list_placeholders",
    "format_placeholder_reference",
    "get_pattern",
]
