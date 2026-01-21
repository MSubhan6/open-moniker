"""Core service layer - RESOLUTION service, not data proxy.

The moniker service resolves monikers to source connection info.
It does NOT fetch the actual data - that's done by the client library.

Flow:
1. Client calls /resolve with a moniker
2. Service returns: source_type, connection_info, query/path, ownership
3. Client connects DIRECTLY to the source using returned info
4. Client reports access telemetry back to service
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .cache.memory import InMemoryCache
from .catalog.registry import CatalogRegistry
from .catalog.types import CatalogNode, ResolvedOwnership, SourceBinding
from .config import Config
from .moniker.parser import parse_moniker, MonikerParseError
from .moniker.types import Moniker
from .telemetry.emitter import TelemetryEmitter
from .telemetry.events import UsageEvent, CallerIdentity, EventOutcome, Operation


logger = logging.getLogger(__name__)


class ResolutionError(Exception):
    """Raised when moniker resolution fails."""
    pass


class NotFoundError(ResolutionError):
    """Raised when moniker path has no source binding."""
    pass


@dataclass(frozen=True)
class ResolvedSource:
    """
    Result of resolving a moniker - tells client WHERE and HOW to get data.

    This is returned to the client library, which then connects directly
    to the source.
    """
    # Source type (snowflake, oracle, rest, bloomberg, etc.)
    source_type: str

    # Connection information (client uses this to connect)
    # Contents depend on source_type
    connection: dict[str, Any]

    # Query or path to execute/fetch
    # For SQL: the query string
    # For REST: the URL path
    # For files: the file path
    query: str | None = None

    # Additional parameters
    params: dict[str, Any] = field(default_factory=dict)

    # Schema information (if available)
    schema: dict[str, Any] | None = None

    # Is this read-only?
    read_only: bool = True


@dataclass
class ResolveResult:
    """Full resolution result including ownership and metadata."""
    moniker: str
    path: str
    source: ResolvedSource
    ownership: ResolvedOwnership
    node: CatalogNode | None = None

    # Where in the hierarchy the binding was found
    binding_path: str = ""

    # Sub-path relative to binding (for hierarchical sources)
    sub_path: str | None = None


@dataclass
class ListResult:
    """Result of a moniker list operation."""
    children: list[str]
    moniker: str
    path: str
    ownership: ResolvedOwnership | None = None


@dataclass
class DescribeResult:
    """Result of a moniker describe operation."""
    node: CatalogNode | None
    ownership: ResolvedOwnership
    moniker: str = ""
    path: str = ""
    has_source_binding: bool = False
    source_type: str | None = None


@dataclass
class MonikerService:
    """
    Moniker Resolution Service.

    This service RESOLVES monikers to source connection info.
    It does NOT fetch data - that's the client library's job.

    Responsibilities:
    - Resolve moniker path → source binding
    - Resolve ownership hierarchy
    - Track resolution telemetry
    - Receive access telemetry from clients
    """
    catalog: CatalogRegistry
    cache: InMemoryCache
    telemetry: TelemetryEmitter
    config: Config

    # Cache resolution results
    cache_enabled: bool = field(default=True, init=False)

    def __post_init__(self):
        self.cache_enabled = self.config.cache.enabled

    async def resolve(
        self,
        moniker_str: str,
        caller: CallerIdentity,
    ) -> ResolveResult:
        """
        Resolve a moniker to source connection info.

        This is the main entry point. Returns everything the client
        needs to connect directly to the data source.
        """
        start = time.perf_counter()
        outcome = EventOutcome.SUCCESS
        error_message: str | None = None
        result: ResolveResult | None = None

        try:
            # Parse moniker
            moniker = parse_moniker(moniker_str)
            path_str = str(moniker.path)

            # Check cache for resolution
            cache_key = f"resolve:{path_str}"
            cached_result = None
            if self.cache_enabled:
                cached_result = self.cache.get(cache_key)

            if cached_result is not None:
                # Rebuild result from cache
                result = cached_result
            else:
                # Find source binding
                binding_info = self.catalog.find_source_binding(path_str)
                if binding_info is None:
                    raise NotFoundError(f"No source binding for: {path_str}")

                binding, binding_path = binding_info

                # Calculate sub-path (path relative to binding)
                sub_path = None
                if binding_path != path_str and path_str.startswith(binding_path):
                    sub_path = path_str[len(binding_path):].lstrip("/")

                # Build resolved source
                resolved_source = self._build_resolved_source(binding, moniker, sub_path)

                # Resolve ownership
                ownership = self.catalog.resolve_ownership(path_str)

                # Get catalog node
                node = self.catalog.get(path_str)

                result = ResolveResult(
                    moniker=moniker_str,
                    path=path_str,
                    source=resolved_source,
                    ownership=ownership,
                    node=node,
                    binding_path=binding_path,
                    sub_path=sub_path,
                )

                # Cache the resolution
                if self.cache_enabled:
                    await self.cache.set(cache_key, result)

            return result

        except MonikerParseError as e:
            outcome = EventOutcome.ERROR
            error_message = str(e)
            raise
        except NotFoundError as e:
            outcome = EventOutcome.NOT_FOUND
            error_message = str(e)
            raise
        except Exception as e:
            outcome = EventOutcome.ERROR
            error_message = str(e)
            logger.exception(f"Unexpected error in resolve: {e}")
            raise

        finally:
            # Emit resolution telemetry (non-blocking)
            latency = (time.perf_counter() - start) * 1000
            self._emit_resolution_telemetry(
                moniker_str=moniker_str,
                caller=caller,
                outcome=outcome,
                latency_ms=latency,
                error_message=error_message,
                result=result,
            )

    def _build_resolved_source(
        self,
        binding: SourceBinding,
        moniker: Moniker,
        sub_path: str | None,
    ) -> ResolvedSource:
        """Build the resolved source info from a binding."""
        config = binding.config
        source_type = binding.source_type.value

        # Extract connection info (remove query/sensitive bits)
        connection: dict[str, Any] = {}
        query: str | None = None
        params: dict[str, Any] = {}

        if source_type == "snowflake":
            connection = {
                "account": config.get("account"),
                "warehouse": config.get("warehouse"),
                "database": config.get("database"),
                "schema": config.get("schema", "PUBLIC"),
                "role": config.get("role"),
            }
            # Build query
            if config.get("query"):
                query = config["query"].format(
                    path=sub_path or str(moniker.path),
                    moniker=str(moniker),
                )
            elif config.get("table"):
                table = config["table"].format(path=sub_path or str(moniker.path))
                query = f"SELECT * FROM {table}"

        elif source_type == "oracle":
            connection = {
                "dsn": config.get("dsn"),
                "host": config.get("host"),
                "port": config.get("port"),
                "service_name": config.get("service_name"),
            }
            if config.get("query"):
                query = config["query"].format(
                    path=sub_path or str(moniker.path),
                    moniker=str(moniker),
                )
            elif config.get("table"):
                table = config["table"].format(path=sub_path or str(moniker.path))
                query = f"SELECT * FROM {table}"

        elif source_type == "rest":
            connection = {
                "base_url": config.get("base_url"),
                "auth_type": config.get("auth_type", "none"),
                "headers": config.get("headers", {}),
            }
            path_template = config.get("path_template", "/{path}")
            query = path_template.format(
                path=sub_path or str(moniker.path),
                moniker=str(moniker),
            )
            params = {
                "method": config.get("method", "GET"),
                "response_path": config.get("response_path"),
            }

        elif source_type == "static":
            connection = {
                "base_path": config.get("base_path", "."),
            }
            file_pattern = config.get("file_pattern", "{path}.json")
            query = file_pattern.format(path=sub_path or str(moniker.path))
            params = {
                "format": config.get("format", "json"),
                "encoding": config.get("encoding", "utf-8"),
            }

        elif source_type == "excel":
            connection = {
                "base_path": config.get("base_path", "."),
            }
            file_pattern = config.get("file_pattern", "{path}.xlsx")
            query = file_pattern.format(path=sub_path or str(moniker.path))
            params = {
                "sheet": config.get("sheet"),
                "header_row": config.get("header_row", 1),
            }

        elif source_type == "bloomberg":
            connection = {
                "host": config.get("host", "localhost"),
                "port": config.get("port", 8194),
                "api_type": config.get("api_type", "blpapi"),
            }
            params = {
                "fields": config.get("fields", ["PX_LAST"]),
                "securities": config.get("securities", [sub_path or str(moniker.path)]),
            }

        elif source_type == "refinitiv":
            connection = {
                "api_type": config.get("api_type", "eikon"),
            }
            params = {
                "fields": config.get("fields", []),
                "instruments": config.get("instruments", [sub_path or str(moniker.path)]),
            }

        else:
            # Generic - pass through config
            connection = {k: v for k, v in config.items() if k not in ("query", "table")}
            query = config.get("query") or config.get("table")

        # Add moniker query params
        if moniker.params:
            params["moniker_params"] = dict(moniker.params.params)

        return ResolvedSource(
            source_type=source_type,
            connection=connection,
            query=query,
            params=params,
            schema=binding.schema,
            read_only=binding.read_only,
        )

    async def record_access(
        self,
        moniker_str: str,
        caller: CallerIdentity,
        outcome: EventOutcome,
        latency_ms: float,
        source_type: str | None = None,
        row_count: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """
        Record an access event from a client.

        Clients call this after fetching data to report telemetry.
        """
        try:
            moniker = parse_moniker(moniker_str)
            path_str = str(moniker.path)
        except Exception:
            path_str = moniker_str

        ownership = self.catalog.resolve_ownership(path_str)

        event = UsageEvent.create(
            moniker=moniker_str,
            moniker_path=path_str,
            operation=Operation.READ,
            caller=caller,
            outcome=outcome,
            latency_ms=latency_ms,
            error_message=error_message,
            resolved_source_type=source_type,
            owner_at_access=ownership.accountable_owner,
            result_count=row_count,
        )

        self.telemetry.emit(event)

    async def list_children(
        self,
        moniker_str: str,
        caller: CallerIdentity,
    ) -> ListResult:
        """List children of a moniker path (from catalog only)."""
        start = time.perf_counter()
        outcome = EventOutcome.SUCCESS
        error_message: str | None = None

        try:
            moniker = parse_moniker(moniker_str)
            path_str = str(moniker.path)

            # Get children from catalog only
            # (actual source children are discovered by client)
            catalog_children = self.catalog.children_paths(path_str)

            # Extract just the leaf names
            children = [p.split("/")[-1] for p in catalog_children]

            ownership = self.catalog.resolve_ownership(path_str)

            return ListResult(
                children=sorted(set(children)),
                moniker=moniker_str,
                path=path_str,
                ownership=ownership,
            )

        except MonikerParseError as e:
            outcome = EventOutcome.ERROR
            error_message = str(e)
            raise
        except Exception as e:
            outcome = EventOutcome.ERROR
            error_message = str(e)
            raise

        finally:
            latency = (time.perf_counter() - start) * 1000
            self._emit_resolution_telemetry(
                moniker_str=moniker_str,
                caller=caller,
                outcome=outcome,
                latency_ms=latency,
                error_message=error_message,
                operation=Operation.LIST,
            )

    async def describe(
        self,
        moniker_str: str,
        caller: CallerIdentity,
    ) -> DescribeResult:
        """Get metadata about a moniker path (without resolving full source)."""
        start = time.perf_counter()
        outcome = EventOutcome.SUCCESS
        error_message: str | None = None

        try:
            moniker = parse_moniker(moniker_str)
            path_str = str(moniker.path)

            # Get catalog node
            node = self.catalog.get(path_str)

            # Resolve ownership
            ownership = self.catalog.resolve_ownership(path_str)

            # Check if there's a source binding (but don't return details)
            binding_info = self.catalog.find_source_binding(path_str)
            has_binding = binding_info is not None
            source_type = binding_info[0].source_type.value if binding_info else None

            return DescribeResult(
                node=node,
                ownership=ownership,
                moniker=moniker_str,
                path=path_str,
                has_source_binding=has_binding,
                source_type=source_type,
            )

        except MonikerParseError as e:
            outcome = EventOutcome.ERROR
            error_message = str(e)
            raise
        except Exception as e:
            outcome = EventOutcome.ERROR
            error_message = str(e)
            raise

        finally:
            latency = (time.perf_counter() - start) * 1000
            self._emit_resolution_telemetry(
                moniker_str=moniker_str,
                caller=caller,
                outcome=outcome,
                latency_ms=latency,
                error_message=error_message,
                operation=Operation.DESCRIBE,
            )

    async def lineage(
        self,
        moniker_str: str,
        caller: CallerIdentity,
    ) -> dict[str, Any]:
        """Get full lineage information for a moniker."""
        start = time.perf_counter()
        outcome = EventOutcome.SUCCESS
        error_message: str | None = None

        try:
            moniker = parse_moniker(moniker_str)
            path_str = str(moniker.path)

            # Get ownership with provenance
            ownership = self.catalog.resolve_ownership(path_str)

            # Get binding info
            binding_info = self.catalog.find_source_binding(path_str)
            source_type = None
            source_binding_path = None
            if binding_info:
                binding, source_binding_path = binding_info
                source_type = binding.source_type.value

            # Build lineage response
            return {
                "moniker": moniker_str,
                "path": path_str,
                "ownership": {
                    "accountable_owner": ownership.accountable_owner,
                    "accountable_owner_defined_at": ownership.accountable_owner_source,
                    "data_specialist": ownership.data_specialist,
                    "data_specialist_defined_at": ownership.data_specialist_source,
                    "support_channel": ownership.support_channel,
                    "support_channel_defined_at": ownership.support_channel_source,
                },
                "source": {
                    "type": source_type,
                    "binding_defined_at": source_binding_path,
                },
                "path_hierarchy": [str(moniker.path.root())] + [
                    str(a) for a in moniker.path.ancestors()
                ] + [path_str],
            }

        except Exception as e:
            outcome = EventOutcome.ERROR
            error_message = str(e)
            raise

        finally:
            latency = (time.perf_counter() - start) * 1000
            self._emit_resolution_telemetry(
                moniker_str=moniker_str,
                caller=caller,
                outcome=outcome,
                latency_ms=latency,
                error_message=error_message,
                operation=Operation.LINEAGE,
            )

    def _emit_resolution_telemetry(
        self,
        moniker_str: str,
        caller: CallerIdentity,
        outcome: EventOutcome,
        latency_ms: float,
        error_message: str | None = None,
        result: ResolveResult | None = None,
        operation: Operation = Operation.READ,
    ) -> None:
        """Emit a resolution telemetry event (non-blocking)."""
        try:
            moniker = parse_moniker(moniker_str)
            path_str = str(moniker.path)
        except Exception:
            path_str = moniker_str

        event = UsageEvent.create(
            moniker=moniker_str,
            moniker_path=path_str,
            operation=operation,
            caller=caller,
            outcome=outcome,
            latency_ms=latency_ms,
            error_message=error_message,
            resolved_source_type=result.source.source_type if result else None,
            owner_at_access=result.ownership.accountable_owner if result else None,
            metadata={"event_type": "resolution"},
        )

        self.telemetry.emit(event)
