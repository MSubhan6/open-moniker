"""Client-side adapters for direct source connection."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import ResolvedSource
    from ..config import ClientConfig

from .base import BaseAdapter
from .snowflake import SnowflakeAdapter
from .oracle import OracleAdapter
from .rest import RestAdapter
from .static import StaticAdapter
from .excel import ExcelAdapter
from .bloomberg import BloombergAdapter
from .refinitiv import RefinitivAdapter


# Registry of adapters
_adapters: dict[str, BaseAdapter] = {
    "snowflake": SnowflakeAdapter(),
    "oracle": OracleAdapter(),
    "rest": RestAdapter(),
    "static": StaticAdapter(),
    "excel": ExcelAdapter(),
    "bloomberg": BloombergAdapter(),
    "refinitiv": RefinitivAdapter(),
}


def get_adapter(source_type: str) -> BaseAdapter:
    """Get an adapter for a source type."""
    adapter = _adapters.get(source_type)
    if adapter is None:
        raise ValueError(f"No adapter for source type: {source_type}")
    return adapter


def register_adapter(source_type: str, adapter: BaseAdapter) -> None:
    """Register a custom adapter."""
    _adapters[source_type] = adapter


__all__ = [
    "get_adapter",
    "register_adapter",
    "BaseAdapter",
    "SnowflakeAdapter",
    "OracleAdapter",
    "RestAdapter",
    "StaticAdapter",
    "ExcelAdapter",
    "BloombergAdapter",
    "RefinitivAdapter",
]
