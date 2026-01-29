"""FastAPI application - Moniker Resolution Service.

This service RESOLVES monikers to source connection info.
It does NOT fetch data - clients use the returned info to connect directly.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .auth import create_composite_authenticator, get_caller_identity, set_authenticator
from .cache.memory import InMemoryCache
from .catalog.registry import CatalogRegistry
from .catalog.loader import load_catalog
from .catalog.types import CatalogNode, Ownership, SourceBinding, SourceType
from .config import Config
from .identity.extractor import extract_identity
from .moniker.parser import MonikerParseError
from .service import MonikerService, AccessDeniedError, NotFoundError, ResolutionError
from .telemetry.batcher import TelemetryBatcher, create_batched_consumer
from .telemetry.emitter import TelemetryEmitter
from .telemetry.events import CallerIdentity, EventOutcome
from .telemetry.sinks.console import ConsoleSink
from .telemetry.sinks.file import RotatingFileSink
from .telemetry.sinks.zmq import ZmqSink


logger = logging.getLogger(__name__)


# Response models
class ResolveResponse(BaseModel):
    """Response from /resolve - tells client how to connect to source."""
    moniker: str
    path: str
    source_type: str
    connection: dict[str, Any]
    query: str | None = None
    params: dict[str, Any] = {}
    schema_info: dict[str, Any] | None = None
    read_only: bool = True
    ownership: dict[str, Any]
    binding_path: str
    sub_path: str | None = None


class ListResponse(BaseModel):
    children: list[str]
    moniker: str
    path: str


class DescribeResponse(BaseModel):
    path: str
    display_name: str | None = None
    description: str | None = None
    ownership: dict[str, Any]
    has_source_binding: bool = False
    source_type: str | None = None
    classification: str | None = None
    tags: list[str] = []

    # Data governance fields
    data_quality: dict[str, Any] | None = None
    sla: dict[str, Any] | None = None
    freshness: dict[str, Any] | None = None

    # Machine-readable schema for AI agents
    schema: dict[str, Any] | None = None


class LineageResponse(BaseModel):
    moniker: str
    path: str
    ownership: dict[str, Any]
    source: dict[str, Any]
    path_hierarchy: list[str]


class AccessReport(BaseModel):
    """Client reports access telemetry back to service."""
    moniker: str
    outcome: str  # success | error | not_found
    latency_ms: float
    source_type: str | None = None
    row_count: int | None = None
    error_message: str | None = None


class HealthResponse(BaseModel):
    status: str
    telemetry: dict[str, Any]
    cache: dict[str, Any]


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


# Global service instance (initialized in lifespan)
_service: MonikerService | None = None
_telemetry_task: asyncio.Task | None = None
_batcher_task: asyncio.Task | None = None


def create_demo_catalog() -> CatalogRegistry:
    """Create a demo catalog with sample source bindings using new format."""
    registry = CatalogRegistry()

    # ==========================================================================
    # INDICES - Benchmark indices with dot notation
    # ==========================================================================
    registry.register(CatalogNode(
        path="indices",
        display_name="Market Indices",
        description="Benchmark indices, aggregates, and composites",
        ownership=Ownership(
            accountable_owner="indices-governance@firm.com",
            data_specialist="quant-research@firm.com",
            support_channel="#indices-support",
        ),
    ))

    registry.register(CatalogNode(
        path="indices.sovereign",
        display_name="Sovereign Indices",
        description="Government bond indices by region",
    ))

    # Example: indices.sovereign/developed/EU.GovBondAgg/EUR/ALL
    registry.register(CatalogNode(
        path="indices.sovereign/developed",
        display_name="Developed Markets Sovereign",
        source_binding=SourceBinding(
            source_type=SourceType.SNOWFLAKE,
            config={
                "account": "firm-prod.us-east-1",
                "warehouse": "ANALYTICS_WH",
                "database": "INDICES",
                "schema": "SOVEREIGN",
                "query": """SELECT index_id, currency, weight, yield, duration
                    FROM DM_SOVEREIGN_INDICES
                    WHERE index_family = '{segments[0]}'
                    AND currency = '{segments[1]}'
                    AND as_of_date = COALESCE(TO_DATE('{version}', 'YYYYMMDD'), CURRENT_DATE())""",
            },
        ),
        is_leaf=True,
    ))

    # ==========================================================================
    # COMMODITIES - Derivatives with REST API
    # ==========================================================================
    registry.register(CatalogNode(
        path="commodities",
        display_name="Commodities",
        description="Commodity futures, spot prices, and derivatives",
        ownership=Ownership(
            accountable_owner="commodities-desk@firm.com",
            data_specialist="commodities-quant@firm.com",
            support_channel="#commodities-data",
        ),
    ))

    registry.register(CatalogNode(
        path="commodities.derivatives",
        display_name="Commodity Derivatives",
    ))

    # Example: commodities.derivatives/energy/ALL
    registry.register(CatalogNode(
        path="commodities.derivatives/energy",
        display_name="Energy Derivatives",
        source_binding=SourceBinding(
            source_type=SourceType.REST,
            config={
                "base_url": "https://market-data.internal.firm.com",
                "path_template": "/api/v2/commodities/energy/{path}",
                "method": "GET",
                "auth_type": "bearer",
            },
        ),
        is_leaf=True,
    ))

    # Example: commodities.derivatives/crypto/ETH@20260115/v2
    registry.register(CatalogNode(
        path="commodities.derivatives/crypto",
        display_name="Digital Assets",
        ownership=Ownership(data_specialist="digital-assets@firm.com"),
        source_binding=SourceBinding(
            source_type=SourceType.REST,
            config={
                "base_url": "https://crypto-data.internal.firm.com",
                "path_template": "/api/v3/assets/{segments[0]}",
                "method": "GET",
                "auth_type": "api_key",
                "query_params": {
                    "as_of": "{version}",
                    "schema_version": "{revision}",
                },
            },
        ),
        is_leaf=True,
    ))

    # ==========================================================================
    # REFERENCE - Security master with Oracle + OpenSearch
    # ==========================================================================
    registry.register(CatalogNode(
        path="reference",
        display_name="Reference Data",
        description="Security master, calendars, and static reference",
        ownership=Ownership(
            accountable_owner="ref-data-governance@firm.com",
            data_specialist="ref-data-ops@firm.com",
            support_channel="#reference-data",
        ),
    ))

    registry.register(CatalogNode(
        path="reference.security",
        display_name="Security Master",
    ))

    # Example: verified@reference.security/ISIN/US0378331005@latest
    registry.register(CatalogNode(
        path="reference.security/ISIN",
        display_name="ISIN Lookup",
        source_binding=SourceBinding(
            source_type=SourceType.ORACLE,
            config={
                "dsn": "secmaster.firm.com:1521/SECMASTER",
                "query": """SELECT isin, cusip, sedol, ticker, issuer_name
                    FROM SECURITY_MASTER
                    WHERE isin = '{segments[0]}'
                    AND effective_date = NVL(TO_DATE('{version}', 'YYYYMMDD'), TRUNC(SYSDATE))""",
            },
        ),
        is_leaf=True,
    ))

    registry.register(CatalogNode(
        path="reference.calendars",
        display_name="Trading Calendars",
    ))

    registry.register(CatalogNode(
        path="reference.calendars/exchange",
        display_name="Exchange Calendars",
        source_binding=SourceBinding(
            source_type=SourceType.STATIC,
            config={
                "base_path": "/data/reference/calendars/exchange",
                "file_pattern": "{segments[0]}.json",
                "format": "json",
            },
        ),
        is_leaf=True,
    ))

    # ==========================================================================
    # INSTRUMENTS - OpenSearch
    # ==========================================================================
    registry.register(CatalogNode(
        path="instruments",
        display_name="Instrument Details",
        ownership=Ownership(
            accountable_owner="ref-data-governance@firm.com",
            data_specialist="security-ops@firm.com",
            support_channel="#instruments",
        ),
    ))

    # Example: instruments/US0378331005/metadata
    registry.register(CatalogNode(
        path="instruments/metadata",
        display_name="Instrument Metadata",
        source_binding=SourceBinding(
            source_type=SourceType.OPENSEARCH,
            config={
                "hosts": ["https://search.internal.firm.com:9200"],
                "index": "instruments-v2",
                "query": '{"query":{"term":{"security_id":"{segments[0]}"}}}',
            },
        ),
        is_leaf=True,
    ))

    # ==========================================================================
    # ANALYTICS - Risk with user views
    # ==========================================================================
    registry.register(CatalogNode(
        path="analytics",
        display_name="Analytics",
        ownership=Ownership(
            accountable_owner="risk-governance@firm.com",
            data_specialist="quant-analytics@firm.com",
            support_channel="#analytics-support",
        ),
        classification="confidential",
    ))

    registry.register(CatalogNode(
        path="analytics.risk",
        display_name="Risk Analytics",
    ))

    registry.register(CatalogNode(
        path="analytics.risk/var",
        display_name="Value at Risk",
        source_binding=SourceBinding(
            source_type=SourceType.REST,
            config={
                "base_url": "https://risk-engine.internal.firm.com",
                "path_template": "/api/v2/var/{path}",
                "method": "GET",
                "auth_type": "bearer",
            },
        ),
        is_leaf=True,
    ))

    # Example: user@analytics.risk/views/my-watchlist@20260115/v3
    registry.register(CatalogNode(
        path="analytics.risk/views",
        display_name="User Risk Views",
        source_binding=SourceBinding(
            source_type=SourceType.REST,
            config={
                "base_url": "https://risk-engine.internal.firm.com",
                "path_template": "/api/v2/views/{namespace}/{segments[0]}",
                "method": "GET",
                "auth_type": "bearer",
                "query_params": {
                    "as_of": "{version}",
                    "version": "{revision}",
                },
            },
        ),
        is_leaf=True,
    ))

    # ==========================================================================
    # HOLDINGS - Positions by date
    # ==========================================================================
    registry.register(CatalogNode(
        path="holdings",
        display_name="Holdings & Positions",
        ownership=Ownership(
            accountable_owner="portfolio-ops@firm.com",
            data_specialist="position-management@firm.com",
            support_channel="#positions",
        ),
        classification="confidential",
    ))

    # Example: holdings/20260115/fund_alpha
    registry.register(CatalogNode(
        path="holdings/positions",
        display_name="Position Data",
        source_binding=SourceBinding(
            source_type=SourceType.SNOWFLAKE,
            config={
                "account": "firm-prod.us-east-1",
                "warehouse": "POSITIONS_WH",
                "database": "HOLDINGS",
                "schema": "POSITIONS",
                "query": """SELECT portfolio_id, security_id, quantity, market_value
                    FROM DAILY_POSITIONS
                    WHERE as_of_date = TO_DATE('{segments[0]}', 'YYYYMMDD')
                    AND portfolio_id = '{segments[1]}'""",
            },
        ),
        is_leaf=True,
    ))

    # ==========================================================================
    # PRICES - Equity prices
    # ==========================================================================
    registry.register(CatalogNode(
        path="prices",
        display_name="Market Prices",
        ownership=Ownership(
            accountable_owner="market-data-governance@firm.com",
            data_specialist="market-data-ops@firm.com",
            support_channel="#market-data",
        ),
    ))

    registry.register(CatalogNode(
        path="prices.equity",
        display_name="Equity Prices",
        source_binding=SourceBinding(
            source_type=SourceType.SNOWFLAKE,
            config={
                "account": "firm-prod.us-east-1",
                "warehouse": "MARKET_DATA_WH",
                "database": "PRICES",
                "schema": "EQUITY",
                "query": """SELECT symbol, open_price, high_price, low_price, close_price, volume
                    FROM EQUITY_EOD
                    WHERE symbol = '{segments[0]}'
                    AND trade_date = COALESCE(TO_DATE('{version}', 'YYYYMMDD'), CURRENT_DATE())""",
            },
        ),
        is_leaf=True,
    ))

    # ==========================================================================
    # REPORTS - Excel files
    # ==========================================================================
    registry.register(CatalogNode(
        path="reports",
        display_name="Reports",
        ownership=Ownership(
            accountable_owner="reporting-ops@firm.com",
            data_specialist="report-dev@firm.com",
            support_channel="#reporting",
        ),
    ))

    registry.register(CatalogNode(
        path="reports/regulatory",
        display_name="Regulatory Reports",
        classification="restricted",
        source_binding=SourceBinding(
            source_type=SourceType.EXCEL,
            config={
                "base_path": "/data/reports/regulatory",
                "file_pattern": "{segments[0]}/{segments[1]}.xlsx",
                "sheet": "Summary",
            },
        ),
        is_leaf=True,
    ))

    return registry


async def create_telemetry(config: Config) -> tuple[TelemetryEmitter, TelemetryBatcher]:
    """Create telemetry emitter and batcher."""
    emitter = TelemetryEmitter(
        max_queue_size=config.telemetry.max_queue_size,
    )

    # Create sink based on config
    sink_type = config.telemetry.sink_type
    sink_config = config.telemetry.sink_config

    if sink_type == "console":
        sink = ConsoleSink(**sink_config)
    elif sink_type == "file":
        sink = RotatingFileSink(**sink_config)
    elif sink_type == "zmq":
        sink = ZmqSink(**sink_config)
        await sink.start()
    else:
        sink = ConsoleSink()

    # Create batcher
    batcher = TelemetryBatcher(
        batch_size=config.telemetry.batch_size,
        flush_interval_seconds=config.telemetry.flush_interval_seconds,
        sink=sink.send,
    )

    # Wire emitter to batcher
    emitter.add_consumer(create_batched_consumer(batcher))

    return emitter, batcher


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown."""
    import os
    from pathlib import Path

    global _service, _telemetry_task, _batcher_task

    logger.info("Starting moniker resolution service...")

    # Load config from file or use defaults
    config_path = os.environ.get("MONIKER_CONFIG", "config.yaml")
    if Path(config_path).exists():
        config = Config.from_yaml(config_path)
        logger.info(f"Loaded config from {config_path}")
    else:
        config = Config()
        logger.info("Using default config")

    # Load catalog from file or use demo
    if config.catalog.definition_file:
        logger.info(f"Loading catalog from: {config.catalog.definition_file}")
        catalog = load_catalog(config.catalog.definition_file)
    else:
        logger.info("Using demo catalog (no definition_file configured)")
        catalog = create_demo_catalog()

    logger.info(f"Catalog loaded with {len(catalog.all_paths())} paths")

    cache = InMemoryCache(
        max_size=config.cache.max_size,
        default_ttl_seconds=config.cache.default_ttl_seconds,
    )

    # Create telemetry
    emitter, batcher = await create_telemetry(config)
    await emitter.start()

    # Start background tasks
    _telemetry_task = asyncio.create_task(emitter.process_loop())
    _batcher_task = asyncio.create_task(batcher.timer_loop())

    # Create service (no adapters needed - we're resolution only)
    _service = MonikerService(
        catalog=catalog,
        cache=cache,
        telemetry=emitter,
        config=config,
    )

    # Initialize authentication if enabled
    if config.auth.enabled:
        authenticator = create_composite_authenticator(config.auth)
        set_authenticator(authenticator)
        logger.info(f"Authentication enabled (enforce={config.auth.enforce})")
    else:
        set_authenticator(None)
        logger.info("Authentication disabled")

    logger.info("Moniker resolution service started")

    yield

    # Shutdown
    logger.info("Shutting down moniker resolution service...")

    if _telemetry_task:
        _telemetry_task.cancel()
        try:
            await _telemetry_task
        except asyncio.CancelledError:
            pass

    if _batcher_task:
        _batcher_task.cancel()
        try:
            await _batcher_task
        except asyncio.CancelledError:
            pass

    await emitter.stop()
    await batcher.stop()

    logger.info("Moniker resolution service stopped")


# Create FastAPI app
app = FastAPI(
    title="Moniker Resolution Service",
    description="Resolves monikers to source connection info. Does NOT proxy data - clients connect directly to sources.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(MonikerParseError)
async def moniker_parse_error_handler(request: Request, exc: MonikerParseError):
    return JSONResponse(
        status_code=400,
        content={"error": "Invalid moniker", "detail": str(exc)},
    )


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request: Request, exc: NotFoundError):
    return JSONResponse(
        status_code=404,
        content={"error": "Not found", "detail": str(exc)},
    )


@app.exception_handler(AccessDeniedError)
async def access_denied_error_handler(request: Request, exc: AccessDeniedError):
    """Handle access policy violations - returns 403 Forbidden."""
    return JSONResponse(
        status_code=403,
        content={
            "error": "Access denied",
            "detail": str(exc),
            "estimated_rows": exc.estimated_rows,
        },
    )


@app.exception_handler(ResolutionError)
async def resolution_error_handler(request: Request, exc: ResolutionError):
    return JSONResponse(
        status_code=500,
        content={"error": "Resolution error", "detail": str(exc)},
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        telemetry=_service.telemetry.stats if _service else {},
        cache=_service.cache.stats if _service else {},
    )


@app.get("/resolve/{path:path}", response_model=ResolveResponse)
async def resolve_moniker(
    request: Request,
    path: str,
    caller: Annotated[CallerIdentity, Depends(get_caller_identity)],
):
    """
    Resolve a moniker to source connection info.

    Returns everything the client needs to connect directly to the data source:
    - source_type: snowflake, oracle, rest, bloomberg, etc.
    - connection: Connection parameters
    - query: SQL query or path to fetch
    - ownership: Who owns this data

    The client then connects directly to the source - we don't proxy data.
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Build full moniker string
    moniker_str = f"moniker://{path}"
    if request.query_params:
        params = list(request.query_params.items())
        if params:
            moniker_str += "?" + "&".join(f"{k}={v}" for k, v in params)

    result = await _service.resolve(moniker_str, caller)

    return ResolveResponse(
        moniker=result.moniker,
        path=result.path,
        source_type=result.source.source_type,
        connection=result.source.connection,
        query=result.source.query,
        params=result.source.params,
        schema_info=result.source.schema,
        read_only=result.source.read_only,
        ownership={
            "accountable_owner": result.ownership.accountable_owner,
            "accountable_owner_source": result.ownership.accountable_owner_source,
            "data_specialist": result.ownership.data_specialist,
            "data_specialist_source": result.ownership.data_specialist_source,
            "support_channel": result.ownership.support_channel,
            "support_channel_source": result.ownership.support_channel_source,
            # Formal governance roles
            "adop": result.ownership.adop,
            "adop_source": result.ownership.adop_source,
            "ads": result.ownership.ads,
            "ads_source": result.ownership.ads_source,
            "adal": result.ownership.adal,
            "adal_source": result.ownership.adal_source,
        },
        binding_path=result.binding_path,
        sub_path=result.sub_path,
    )


@app.get("/list/{path:path}", response_model=ListResponse)
async def list_children(
    path: str = "",
    caller: Annotated[CallerIdentity, Depends(get_caller_identity)] = None,
):
    """List children of a moniker path (from catalog)."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    moniker_str = f"moniker://{path}" if path else "moniker://"

    result = await _service.list_children(moniker_str, caller)
    return ListResponse(
        children=result.children,
        moniker=result.moniker,
        path=result.path,
    )


@app.get("/describe/{path:path}", response_model=DescribeResponse)
async def describe_moniker(
    path: str,
    caller: Annotated[CallerIdentity, Depends(get_caller_identity)],
):
    """Get metadata about a moniker path (ownership, classification, etc.)."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    moniker_str = f"moniker://{path}"

    result = await _service.describe(moniker_str, caller)

    # Build data quality dict if present
    data_quality = None
    if result.node and result.node.data_quality:
        dq = result.node.data_quality
        data_quality = {
            "dq_owner": dq.dq_owner,
            "quality_score": dq.quality_score,
            "validation_rules": list(dq.validation_rules),
            "known_issues": list(dq.known_issues),
            "last_validated": dq.last_validated,
        }

    # Build SLA dict if present
    sla = None
    if result.node and result.node.sla:
        s = result.node.sla
        sla = {
            "freshness": s.freshness,
            "availability": s.availability,
            "support_hours": s.support_hours,
            "escalation_contact": s.escalation_contact,
        }

    # Build freshness dict if present
    freshness = None
    if result.node and result.node.freshness:
        f = result.node.freshness
        freshness = {
            "last_loaded": f.last_loaded,
            "refresh_schedule": f.refresh_schedule,
            "source_system": f.source_system,
            "upstream_dependencies": list(f.upstream_dependencies),
        }

    # Build schema dict if present (AI-readable metadata)
    schema = None
    if result.node and result.node.data_schema:
        ds = result.node.data_schema
        schema = {
            "description": ds.description,
            "semantic_tags": list(ds.semantic_tags),
            "granularity": ds.granularity,
            "typical_row_count": ds.typical_row_count,
            "update_frequency": ds.update_frequency,
            "primary_key": list(ds.primary_key),
            "columns": [
                {
                    "name": col.name,
                    "type": col.data_type,
                    "description": col.description,
                    "semantic_type": col.semantic_type,
                    "example": col.example,
                    "nullable": col.nullable,
                    "primary_key": col.primary_key,
                    "foreign_key": col.foreign_key,
                }
                for col in ds.columns
            ],
            "use_cases": list(ds.use_cases),
            "examples": list(ds.examples),
            "related_monikers": list(ds.related_monikers),
        }

    return DescribeResponse(
        path=result.path,
        display_name=result.node.display_name if result.node else None,
        description=result.node.description if result.node else None,
        ownership={
            "accountable_owner": result.ownership.accountable_owner,
            "accountable_owner_source": result.ownership.accountable_owner_source,
            "data_specialist": result.ownership.data_specialist,
            "data_specialist_source": result.ownership.data_specialist_source,
            "support_channel": result.ownership.support_channel,
            "support_channel_source": result.ownership.support_channel_source,
            # Formal governance roles
            "adop": result.ownership.adop,
            "adop_source": result.ownership.adop_source,
            "ads": result.ownership.ads,
            "ads_source": result.ownership.ads_source,
            "adal": result.ownership.adal,
            "adal_source": result.ownership.adal_source,
        },
        has_source_binding=result.has_source_binding,
        source_type=result.source_type,
        classification=result.node.classification if result.node else None,
        tags=list(result.node.tags) if result.node else [],
        data_quality=data_quality,
        sla=sla,
        freshness=freshness,
        schema=schema,
    )


@app.get("/lineage/{path:path}", response_model=LineageResponse)
async def get_lineage(
    path: str,
    caller: Annotated[CallerIdentity, Depends(get_caller_identity)],
):
    """Get full ownership lineage for a moniker path."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    moniker_str = f"moniker://{path}"

    result = await _service.lineage(moniker_str, caller)
    return LineageResponse(**result)


@app.post("/telemetry/access")
async def report_access(
    report: AccessReport,
    caller: Annotated[CallerIdentity, Depends(get_caller_identity)],
):
    """
    Client reports access telemetry after fetching data.

    This allows us to track actual data access, not just resolutions.
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Map string outcome to enum
    outcome_map = {
        "success": EventOutcome.SUCCESS,
        "error": EventOutcome.ERROR,
        "not_found": EventOutcome.NOT_FOUND,
    }
    outcome = outcome_map.get(report.outcome, EventOutcome.ERROR)

    await _service.record_access(
        moniker_str=report.moniker,
        caller=caller,
        outcome=outcome,
        latency_ms=report.latency_ms,
        source_type=report.source_type,
        row_count=report.row_count,
        error_message=report.error_message,
    )

    return {"status": "recorded"}


@app.get("/catalog")
async def list_catalog():
    """List all registered catalog paths."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    paths = _service.catalog.all_paths()
    return {"paths": sorted(paths)}


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "Moniker Resolution Service",
        "version": "0.1.0",
        "description": "Resolves monikers to source connection info. Clients connect directly to sources.",
        "endpoints": {
            "/resolve/{path}": "Resolve moniker to source connection info",
            "/list/{path}": "List children in catalog",
            "/describe/{path}": "Get metadata and ownership",
            "/lineage/{path}": "Get full ownership lineage",
            "/catalog": "List all catalog paths",
            "/telemetry/access": "POST - Report access telemetry from client",
            "/health": "Health check",
        },
        "client_library": "pip install moniker-client",
    }


def run():
    """Run the service with uvicorn."""
    import argparse
    import os
    import uvicorn

    parser = argparse.ArgumentParser(description="Moniker Resolution Service")
    parser.add_argument(
        "--config", "-c",
        default=os.environ.get("MONIKER_CONFIG", "config.yaml"),
        help="Path to config file (default: config.yaml or MONIKER_CONFIG env var)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Override host (default: from config)",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=None,
        help="Override port (default: from config)",
    )
    args = parser.parse_args()

    # Store config path in environment for lifespan to pick up
    os.environ["MONIKER_CONFIG"] = args.config

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Load config to get host/port
    from pathlib import Path
    config_path = Path(args.config)
    if config_path.exists():
        config = Config.from_yaml(str(config_path))
        logger.info(f"Loaded config from {config_path}")
    else:
        config = Config()
        logger.info("Using default config (no config file found)")

    host = args.host or config.server.host
    port = args.port or config.server.port

    uvicorn.run(
        "moniker_svc.main:app",
        host=host,
        port=port,
        reload=config.server.reload,
    )


if __name__ == "__main__":
    run()
