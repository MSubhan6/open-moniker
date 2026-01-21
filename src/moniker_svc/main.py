"""FastAPI application - Moniker Resolution Service.

This service RESOLVES monikers to source connection info.
It does NOT fetch data - clients use the returned info to connect directly.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .cache.memory import InMemoryCache
from .catalog.registry import CatalogRegistry
from .catalog.types import CatalogNode, Ownership, SourceBinding, SourceType
from .config import Config
from .identity.extractor import extract_identity
from .moniker.parser import MonikerParseError
from .service import MonikerService, NotFoundError, ResolutionError
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
    """Create a demo catalog with sample source bindings."""
    registry = CatalogRegistry()

    # Market data domain
    registry.register(CatalogNode(
        path="market-data",
        display_name="Market Data",
        description="Real-time and historical market data",
        ownership=Ownership(
            accountable_owner="jane.smith@firm.com",
            data_specialist="market-data-team@firm.com",
            support_channel="#market-data-support",
        ),
    ))

    registry.register(CatalogNode(
        path="market-data/prices",
        display_name="Prices",
        description="Security prices from various sources",
    ))

    # Equity prices from Snowflake
    registry.register(CatalogNode(
        path="market-data/prices/equity",
        display_name="Equity Prices",
        source_binding=SourceBinding(
            source_type=SourceType.SNOWFLAKE,
            config={
                "account": "acme.us-east-1",
                "warehouse": "COMPUTE_WH",
                "database": "MARKET_DATA",
                "schema": "PRICES",
                "table": "EQUITY_PRICES",
                "query": "SELECT symbol, price, currency, timestamp FROM EQUITY_PRICES WHERE symbol = '{path}'",
            },
        ),
        is_leaf=True,
    ))

    # Bloomberg prices
    registry.register(CatalogNode(
        path="market-data/prices/bloomberg",
        display_name="Bloomberg Prices",
        ownership=Ownership(
            data_specialist="bloomberg-team@firm.com",
        ),
        source_binding=SourceBinding(
            source_type=SourceType.BLOOMBERG,
            config={
                "host": "localhost",
                "port": 8194,
                "api_type": "blpapi",
                "fields": ["PX_LAST", "PX_BID", "PX_ASK", "VOLUME"],
                "securities": "{path} Equity",
            },
        ),
        is_leaf=True,
    ))

    # Reference data domain
    registry.register(CatalogNode(
        path="reference",
        display_name="Reference Data",
        description="Static reference data",
        ownership=Ownership(
            accountable_owner="bob.jones@firm.com",
            data_specialist="ref-data-team@firm.com",
            support_channel="#reference-data",
        ),
    ))

    registry.register(CatalogNode(
        path="reference/calendars",
        display_name="Trading Calendars",
    ))

    # Calendars from static JSON files
    registry.register(CatalogNode(
        path="reference/calendars/trading",
        display_name="Exchange Trading Calendars",
        source_binding=SourceBinding(
            source_type=SourceType.STATIC,
            config={
                "base_path": "/data/reference/calendars",
                "file_pattern": "{path}.json",
                "format": "json",
            },
        ),
        is_leaf=True,
    ))

    # Instruments from Oracle
    registry.register(CatalogNode(
        path="reference/instruments",
        display_name="Financial Instruments",
        ownership=Ownership(
            data_specialist="instruments-team@firm.com",
        ),
    ))

    registry.register(CatalogNode(
        path="reference/instruments/equity",
        display_name="Equity Instruments",
        source_binding=SourceBinding(
            source_type=SourceType.ORACLE,
            config={
                "dsn": "refdata.firm.com:1521/REFDATA",
                "table": "EQUITY_INSTRUMENTS",
                "query": "SELECT * FROM EQUITY_INSTRUMENTS WHERE symbol = '{path}'",
            },
        ),
        is_leaf=True,
    ))

    # Risk data from REST API
    registry.register(CatalogNode(
        path="risk",
        display_name="Risk Data",
        description="Risk analytics and positions",
        ownership=Ownership(
            accountable_owner="sarah.chen@firm.com",
            data_specialist="risk-tech@firm.com",
            support_channel="#risk-support",
        ),
        classification="confidential",
    ))

    registry.register(CatalogNode(
        path="risk/var",
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
    global _service, _telemetry_task, _batcher_task

    logger.info("Starting moniker resolution service...")

    # Load config (from environment or defaults)
    config = Config()

    # Create components
    catalog = create_demo_catalog()
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

    # Extract caller identity
    caller = extract_identity(request)

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
        },
        binding_path=result.binding_path,
        sub_path=result.sub_path,
    )


@app.get("/list/{path:path}", response_model=ListResponse)
async def list_children(
    request: Request,
    path: str = "",
):
    """List children of a moniker path (from catalog)."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    caller = extract_identity(request)
    moniker_str = f"moniker://{path}" if path else "moniker://"

    result = await _service.list_children(moniker_str, caller)
    return ListResponse(
        children=result.children,
        moniker=result.moniker,
        path=result.path,
    )


@app.get("/describe/{path:path}", response_model=DescribeResponse)
async def describe_moniker(
    request: Request,
    path: str,
):
    """Get metadata about a moniker path (ownership, classification, etc.)."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    caller = extract_identity(request)
    moniker_str = f"moniker://{path}"

    result = await _service.describe(moniker_str, caller)
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
        },
        has_source_binding=result.has_source_binding,
        source_type=result.source_type,
        classification=result.node.classification if result.node else None,
        tags=list(result.node.tags) if result.node else [],
    )


@app.get("/lineage/{path:path}", response_model=LineageResponse)
async def get_lineage(
    request: Request,
    path: str,
):
    """Get full ownership lineage for a moniker path."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    caller = extract_identity(request)
    moniker_str = f"moniker://{path}"

    result = await _service.lineage(moniker_str, caller)
    return LineageResponse(**result)


@app.post("/telemetry/access")
async def report_access(
    request: Request,
    report: AccessReport,
):
    """
    Client reports access telemetry after fetching data.

    This allows us to track actual data access, not just resolutions.
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    caller = extract_identity(request)

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
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    uvicorn.run(
        "moniker_svc.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    run()
