"""Main client class and convenience functions."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import ClientConfig
from .adapters import get_adapter


class MonikerError(Exception):
    """Base exception for moniker client errors."""
    pass


class ResolutionError(MonikerError):
    """Failed to resolve moniker."""
    pass


class FetchError(MonikerError):
    """Failed to fetch data from source."""
    pass


class NotFoundError(MonikerError):
    """Moniker path not found."""
    pass


@dataclass
class ResolvedSource:
    """Resolved source information from the service."""
    moniker: str
    path: str
    source_type: str
    connection: dict[str, Any]
    query: str | None
    params: dict[str, Any]
    schema_info: dict[str, Any] | None
    read_only: bool
    ownership: dict[str, Any]
    binding_path: str
    sub_path: str | None


@dataclass
class MonikerClient:
    """
    Client for accessing data via monikers.

    Usage:
        client = MonikerClient()
        data = client.read("market-data/prices/equity/AAPL")

        # Or with custom config
        client = MonikerClient(config=ClientConfig(
            service_url="http://moniker-svc:8000",
            app_id="my-app",
            team="my-team",
        ))
    """
    config: ClientConfig = field(default_factory=ClientConfig)

    # Local cache of resolutions
    _cache: dict[str, tuple[ResolvedSource, float]] = field(default_factory=dict, init=False)

    def read(self, moniker: str, **kwargs) -> Any:
        """
        Read data for a moniker.

        Args:
            moniker: Moniker path (with or without scheme)
            **kwargs: Additional parameters passed to the source adapter

        Returns:
            The data from the source
        """
        start = time.perf_counter()
        outcome = "success"
        error_message = None
        row_count = None
        source_type = None

        try:
            # Normalize moniker
            if not moniker.startswith("moniker://"):
                moniker = f"moniker://{moniker}"

            # Resolve moniker to source info
            resolved = self._resolve(moniker)
            source_type = resolved.source_type

            # Get adapter for source type
            adapter = get_adapter(resolved.source_type)

            # Fetch data directly from source
            data = adapter.fetch(resolved, self.config, **kwargs)

            if isinstance(data, (list, dict)):
                row_count = len(data)

            return data

        except NotFoundError:
            outcome = "not_found"
            raise
        except Exception as e:
            outcome = "error"
            error_message = str(e)
            raise FetchError(f"Failed to fetch {moniker}: {e}") from e

        finally:
            # Report telemetry
            if self.config.report_telemetry:
                latency = (time.perf_counter() - start) * 1000
                self._report_telemetry(
                    moniker=moniker,
                    outcome=outcome,
                    latency_ms=latency,
                    source_type=source_type,
                    row_count=row_count,
                    error_message=error_message,
                )

    def describe(self, moniker: str) -> dict[str, Any]:
        """Get metadata about a moniker path."""
        if not moniker.startswith("moniker://"):
            moniker = f"moniker://{moniker}"

        path = moniker.replace("moniker://", "")

        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.get(
                f"{self.config.service_url}/describe/{path}",
                headers=self._get_headers(),
            )
            if response.status_code == 404:
                raise NotFoundError(f"Path not found: {path}")
            response.raise_for_status()
            return response.json()

    def list_children(self, moniker: str = "") -> list[str]:
        """List children of a moniker path."""
        if moniker and not moniker.startswith("moniker://"):
            moniker = f"moniker://{moniker}"

        path = moniker.replace("moniker://", "") if moniker else ""

        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.get(
                f"{self.config.service_url}/list/{path}",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json().get("children", [])

    def lineage(self, moniker: str) -> dict[str, Any]:
        """Get ownership lineage for a moniker path."""
        if not moniker.startswith("moniker://"):
            moniker = f"moniker://{moniker}"

        path = moniker.replace("moniker://", "")

        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.get(
                f"{self.config.service_url}/lineage/{path}",
                headers=self._get_headers(),
            )
            if response.status_code == 404:
                raise NotFoundError(f"Path not found: {path}")
            response.raise_for_status()
            return response.json()

    def resolve(self, moniker: str) -> ResolvedSource:
        """
        Resolve a moniker to source connection info.

        Usually you don't need this - use read() instead.
        This is useful if you want to manage the connection yourself.
        """
        if not moniker.startswith("moniker://"):
            moniker = f"moniker://{moniker}"
        return self._resolve(moniker)

    def _resolve(self, moniker: str) -> ResolvedSource:
        """Internal resolve with caching."""
        # Check cache
        if self.config.cache_ttl > 0 and moniker in self._cache:
            resolved, cached_at = self._cache[moniker]
            if time.time() - cached_at < self.config.cache_ttl:
                return resolved

        path = moniker.replace("moniker://", "")

        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.get(
                f"{self.config.service_url}/resolve/{path}",
                headers=self._get_headers(),
            )

            if response.status_code == 404:
                raise NotFoundError(f"No source binding for: {path}")

            if response.status_code != 200:
                raise ResolutionError(f"Resolution failed: {response.text}")

            data = response.json()

        resolved = ResolvedSource(
            moniker=data["moniker"],
            path=data["path"],
            source_type=data["source_type"],
            connection=data["connection"],
            query=data.get("query"),
            params=data.get("params", {}),
            schema_info=data.get("schema_info"),
            read_only=data.get("read_only", True),
            ownership=data.get("ownership", {}),
            binding_path=data.get("binding_path", ""),
            sub_path=data.get("sub_path"),
        )

        # Cache
        if self.config.cache_ttl > 0:
            self._cache[moniker] = (resolved, time.time())

        return resolved

    def _get_headers(self) -> dict[str, str]:
        """Build request headers."""
        headers = {}
        if self.config.app_id:
            headers["X-App-ID"] = self.config.app_id
        if self.config.team:
            headers["X-Team"] = self.config.team
        return headers

    def _report_telemetry(
        self,
        moniker: str,
        outcome: str,
        latency_ms: float,
        source_type: str | None,
        row_count: int | None,
        error_message: str | None,
    ) -> None:
        """Report access telemetry back to the service."""
        try:
            with httpx.Client(timeout=5) as client:
                client.post(
                    f"{self.config.service_url}/telemetry/access",
                    headers=self._get_headers(),
                    json={
                        "moniker": moniker,
                        "outcome": outcome,
                        "latency_ms": latency_ms,
                        "source_type": source_type,
                        "row_count": row_count,
                        "error_message": error_message,
                    },
                )
        except Exception:
            # Don't fail the read because telemetry failed
            pass


# Module-level default client
_default_client: MonikerClient | None = None


def _get_client() -> MonikerClient:
    """Get or create the default client."""
    global _default_client
    if _default_client is None:
        _default_client = MonikerClient()
    return _default_client


def read(moniker: str, **kwargs) -> Any:
    """
    Read data for a moniker using the default client.

    Usage:
        from moniker_client import read
        data = read("market-data/prices/equity/AAPL")
    """
    return _get_client().read(moniker, **kwargs)


def describe(moniker: str) -> dict[str, Any]:
    """Get metadata about a moniker path."""
    return _get_client().describe(moniker)


def list_children(moniker: str = "") -> list[str]:
    """List children of a moniker path."""
    return _get_client().list_children(moniker)


def lineage(moniker: str) -> dict[str, Any]:
    """Get ownership lineage for a moniker path."""
    return _get_client().lineage(moniker)
