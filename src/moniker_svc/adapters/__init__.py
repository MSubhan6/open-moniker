"""Data source adapters."""

from .base import DataAdapter, AdapterResult, AdapterError
from .registry import AdapterRegistry
from .snowflake import SnowflakeAdapter
from .oracle import OracleAdapter
from .mssql import MssqlAdapter

__all__ = [
    "DataAdapter",
    "AdapterResult",
    "AdapterError",
    "AdapterRegistry",
    "SnowflakeAdapter",
    "OracleAdapter",
    "MssqlAdapter",
]
