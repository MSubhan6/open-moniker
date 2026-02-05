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
from .moniker.types import Moniker, VersionType
from .telemetry.emitter import TelemetryEmitter
from .telemetry.events import UsageEvent, CallerIdentity, EventOutcome, Operation


logger = logging.getLogger(__name__)


class ResolutionError(Exception):
    """Raised when moniker resolution fails."""
    pass


class NotFoundError(ResolutionError):
    """Raised when moniker path has no source binding."""
    pass


class AccessDeniedError(ResolutionError):
    """Raised when access policy blocks the query."""

    def __init__(self, message: str, estimated_rows: int | None = None):
        super().__init__(message)
        self.estimated_rows = estimated_rows


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

                # Check access policy
                binding_node = self.catalog.get(binding_path)
                if binding_node and binding_node.access_policy:
                    segments = sub_path.split("/") if sub_path else []
                    is_allowed, error_or_warning, estimated_rows = binding_node.access_policy.validate(segments)

                    if not is_allowed:
                        raise AccessDeniedError(error_or_warning or "Access denied by policy", estimated_rows)

                    # Log warning if present
                    if error_or_warning:
                        logger.warning(f"Access policy warning for {path_str}: {error_or_warning}")

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
        except AccessDeniedError as e:
            outcome = EventOutcome.ERROR
            error_message = str(e)
            logger.warning(f"Access denied for {moniker_str}: {e}")
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

    def _format_template(
        self,
        template: str,
        moniker: Moniker,
        sub_path: str | None,
        source_type: str = "snowflake",
    ) -> str:
        """
        Format a template string with moniker components.

        Supported placeholders:
            Raw values:
                {path}              - Full sub-path after the binding
                {segments[N]}       - Specific path segment (0-indexed)
                {version}           - Version from @suffix (raw string)
                {revision}          - Revision from /vN suffix
                {namespace}         - Namespace prefix if provided
                {moniker}           - Full moniker string
                {sub_resource}      - Sub-resource path after @version (e.g., "details.corporate.actions")

            Version type placeholders:
                {version_type}      - Semantic type: "date", "latest", "tenor", "all", "custom", or ""
                {is_date}           - "true" if version is a date (YYYYMMDD), else "false"
                {is_latest}         - "true" if version is "latest", else "false"
                {is_tenor}          - "true" if version is a tenor (3M, 12Y), else "false"
                {is_all}            - "true" if version is "all", else "false"
                {tenor_value}       - Numeric part of tenor (e.g., "3" from "3M"), or ""
                {tenor_unit}        - Unit part of tenor (Y/M/W/D), or ""

            SQL-translated values:
                {version_date}      - SQL date expression for version
                                      "" → CURRENT_DATE / SYSDATE
                                      "latest" → subquery placeholder
                                      "20260115" → TO_DATE('20260115','YYYYMMDD')
                {filter[N]:col}     - SQL filter for segment N on column col
                                      "ALL" → "1=1" (match all)
                                      "AAPL" → "col = 'AAPL'"
                {is_all[N]}         - "true" if segment N is "ALL", else "false"
        """
        import re

        path = sub_path or str(moniker.path)
        segments = path.split("/") if path else []
        version = moniker.version or ""

        # Determine SQL dialect
        is_oracle = source_type == "oracle"

        # SQL date translation
        if not version:
            version_date = "SYSDATE" if is_oracle else "CURRENT_DATE()"
        elif version.lower() == "latest":
            # Placeholder - query author should use MAX() subquery
            version_date = "'__LATEST__'"
        elif version.isdigit() and len(version) == 8:
            if is_oracle:
                version_date = f"TO_DATE('{version}', 'YYYYMMDD')"
            else:
                version_date = f"TO_DATE('{version}', 'YYYYMMDD')"
        else:
            version_date = f"'{version}'"

        # Compute version type flags
        version_type = moniker.version_type
        is_date = version_type == VersionType.DATE
        is_latest = version_type == VersionType.LATEST
        is_tenor = version_type == VersionType.TENOR
        is_all_version = version_type == VersionType.ALL

        # Extract tenor components if applicable
        tenor_value = ""
        tenor_unit = ""
        if is_tenor and moniker.version_tenor:
            tenor_value = str(moniker.version_tenor[0])
            tenor_unit = moniker.version_tenor[1]

        # Build substitution dict
        subs = {
            "path": path,
            "version": version,
            "version_date": version_date,
            "revision": str(moniker.revision) if moniker.revision is not None else "",
            "namespace": moniker.namespace or "",
            "moniker": str(moniker),
            "sub_resource": moniker.sub_resource or "",
            # Version type placeholders
            "version_type": version_type.value if version_type else "",
            "is_date": "true" if is_date else "false",
            "is_latest": "true" if is_latest else "false",
            "is_tenor": "true" if is_tenor else "false",
            "is_all": "true" if is_all_version else "false",
            "tenor_value": tenor_value,
            "tenor_unit": tenor_unit,
        }

        result = template

        # Handle {segments[N]} patterns
        def replace_segment(match: re.Match) -> str:
            idx = int(match.group(1))
            if 0 <= idx < len(segments):
                return segments[idx]
            return ""

        result = re.sub(r"\{segments\[(\d+)\]\}", replace_segment, result)

        # Handle {is_all[N]} patterns
        def replace_is_all(match: re.Match) -> str:
            idx = int(match.group(1))
            if 0 <= idx < len(segments):
                return "true" if segments[idx].upper() == "ALL" else "false"
            return "false"

        result = re.sub(r"\{is_all\[(\d+)\]\}", replace_is_all, result)

        # Handle {filter[N]:column} patterns - generates SQL WHERE clause fragment
        def replace_filter(match: re.Match) -> str:
            idx = int(match.group(1))
            col = match.group(2)
            if 0 <= idx < len(segments):
                seg_value = segments[idx]
                if seg_value.upper() == "ALL":
                    return "1=1"  # Match everything
                else:
                    return f"{col} = '{seg_value}'"
            return "1=1"

        result = re.sub(r"\{filter\[(\d+)\]:(\w+)\}", replace_filter, result)

        # Handle simple placeholders
        for key, value in subs.items():
            result = result.replace(f"{{{key}}}", value)

        return result

    def _build_resolved_source(
        self,
        binding: SourceBinding,
        moniker: Moniker,
        sub_path: str | None,
    ) -> ResolvedSource:
        """Build the resolved source info from a binding."""
        config = binding.config
        source_type = binding.source_type.value

        # Helper to format templates with SQL dialect awareness
        def fmt(template: str) -> str:
            return self._format_template(template, moniker, sub_path, source_type)

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
                query = fmt(config["query"])
            elif config.get("table"):
                table = fmt(config["table"])
                query = f"SELECT * FROM {table}"

        elif source_type == "oracle":
            connection = {
                "dsn": config.get("dsn"),
                "host": config.get("host"),
                "port": config.get("port"),
                "service_name": config.get("service_name"),
            }
            if config.get("query"):
                query = fmt(config["query"])
            elif config.get("table"):
                table = fmt(config["table"])
                query = f"SELECT * FROM {table}"

        elif source_type == "rest":
            connection = {
                "base_url": config.get("base_url"),
                "auth_type": config.get("auth_type", "none"),
                "headers": config.get("headers", {}),
            }
            path_template = config.get("path_template", "/{path}")
            query = fmt(path_template)
            params = {
                "method": config.get("method", "GET"),
                "response_path": config.get("response_path"),
            }
            # Format query_params if present
            if config.get("query_params"):
                params["query_params"] = {
                    k: fmt(v) for k, v in config["query_params"].items()
                }

        elif source_type == "static":
            connection = {
                "base_path": config.get("base_path", "."),
            }
            file_pattern = config.get("file_pattern", "{path}.json")
            query = fmt(file_pattern)
            params = {
                "format": config.get("format", "json"),
                "encoding": config.get("encoding", "utf-8"),
            }

        elif source_type == "excel":
            connection = {
                "base_path": config.get("base_path", "."),
            }
            file_pattern = config.get("file_pattern", "{path}.xlsx")
            query = fmt(file_pattern)
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
            securities = config.get("securities", "{path}")
            params = {
                "fields": config.get("fields", ["PX_LAST"]),
                "securities": fmt(securities) if isinstance(securities, str) else securities,
            }

        elif source_type == "refinitiv":
            connection = {
                "api_type": config.get("api_type", "eikon"),
            }
            instruments = config.get("instruments", "{path}")
            params = {
                "fields": config.get("fields", []),
                "instruments": fmt(instruments) if isinstance(instruments, str) else instruments,
            }

        elif source_type == "opensearch":
            connection = {
                "hosts": config.get("hosts", []),
                "index": config.get("index"),
            }
            if config.get("query"):
                query = fmt(config["query"])

        else:
            # Generic - pass through config with template formatting
            connection = {}
            for k, v in config.items():
                if k not in ("query", "table"):
                    connection[k] = fmt(v) if isinstance(v, str) else v
            if config.get("query"):
                query = fmt(config["query"])
            elif config.get("table"):
                query = fmt(config["table"])

        # Add moniker metadata to params
        params["moniker_version"] = moniker.version
        params["moniker_revision"] = moniker.revision
        params["moniker_namespace"] = moniker.namespace

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
                # Formal governance roles (BCBS 239 / DAMA style)
                "governance_roles": {
                    "adop": {
                        "value": ownership.adop,
                        "defined_at": ownership.adop_source,
                        "description": "Accountable Data Owner/Principal - business executive with ultimate accountability",
                    },
                    "ads": {
                        "value": ownership.ads,
                        "defined_at": ownership.ads_source,
                        "description": "Accountable Data Steward - day-to-day data quality and standards",
                    },
                    "adal": {
                        "value": ownership.adal,
                        "defined_at": ownership.adal_source,
                        "description": "Accountable Data Access Lead - controls access and permissions",
                    },
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

    def reload_catalog(self, new_catalog: CatalogRegistry) -> int:
        """
        Hot-reload the catalog with a new set of nodes.

        This atomically replaces the catalog contents, allowing for
        live updates without service restart.

        Args:
            new_catalog: The new catalog registry to use

        Returns:
            Number of nodes in the new catalog
        """
        # Get all nodes from the new catalog
        new_nodes = new_catalog.all_nodes()

        # Atomically replace the catalog contents
        self.catalog.atomic_replace(new_nodes)

        # Clear the cache since catalog changed
        self.cache.clear()

        logger.info(f"Catalog hot-reloaded with {len(new_nodes)} nodes")

        return len(new_nodes)
