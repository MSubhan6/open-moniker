"""Base adapter interface for client-side data fetching."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import ResolvedSource
    from ..config import ClientConfig


class BaseAdapter(ABC):
    """
    Base class for client-side data adapters.

    Each adapter connects directly to a data source type
    and fetches the data.
    """

    @abstractmethod
    def fetch(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
        **kwargs,
    ) -> Any:
        """
        Fetch data from the source.

        Args:
            resolved: Resolved source info from the moniker service
            config: Client configuration (includes credentials)
            **kwargs: Additional adapter-specific parameters

        Returns:
            The fetched data (usually list of dicts or dict)
        """
        ...

    def list_children(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
    ) -> list[str]:
        """
        List children at the source level.

        Default returns empty - override for sources that support it.
        """
        return []
