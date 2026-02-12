"""FastAPI application - Moniker Resolution Service.

This service RESOLVES monikers to source connection info.
It also provides /fetch for server-side query execution.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

# Add external packages path if running from repo
_REPO_ROOT = Path(__file__).parent.parent.parent
_EXTERNAL_DATA = _REPO_ROOT / "external" / "moniker-data" / "src"
if _EXTERNAL_DATA.exists() and str(_EXTERNAL_DATA) not in sys.path:
    sys.path.insert(0, str(_EXTERNAL_DATA))

from fastapi import Depends, FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import create_composite_authenticator, get_caller_identity, set_authenticator
from .cache.memory import InMemoryCache
from .catalog.registry import CatalogRegistry
from .catalog.loader import load_catalog
from .catalog.types import (
    CatalogNode, Ownership, SourceBinding, SourceType,
    DataSchema, ColumnSchema, DataQuality, Freshness, SLA, AccessPolicy, Documentation,
)
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
from .sql_catalog import routes as sql_catalog_routes
from .config_ui import routes as config_ui_routes
from .domains import routes as domain_routes
from .domains import DomainRegistry, load_domains_from_yaml


logger = logging.getLogger(__name__)

# Domain registry - global singleton
_domain_registry: DomainRegistry | None = None


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
    # Enterprise additions
    status: str | None = None            # Node lifecycle status
    deprecation_message: str | None = None  # Warning if deprecated
    successor: str | None = None         # Path to replacement moniker
    sunset_deadline: str | None = None   # ISO date after which archived
    migration_guide_url: str | None = None  # URL to migration docs
    redirected_from: str | None = None   # Original path if redirected via successor
    cache_ttl_hint: int = 300            # Suggested client cache TTL in seconds


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

    # Documentation links (Confluence, runbooks, etc.)
    documentation: dict[str, Any] | None = None


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
    rate_limiter: dict[str, Any] | None = None
    circuit_breaker: dict[str, Any] | None = None
    catalog_counts: dict[str, int] | None = None


# Enterprise pagination and batch models
class PaginatedCatalogResponse(BaseModel):
    """Paginated catalog listing with cursor-based pagination."""
    paths: list[str]
    total_count: int | None = None
    next_cursor: str | None = None
    has_more: bool = False


class CatalogSearchResponse(BaseModel):
    """Search results from catalog."""
    results: list[dict[str, Any]]
    query: str
    total_results: int


class BatchResolveRequest(BaseModel):
    """Request to resolve multiple monikers in one call."""
    monikers: list[str]


class BatchResolveResponse(BaseModel):
    """Batch resolution results."""
    results: list[ResolveResponse]
    errors: dict[str, str] = {}  # moniker -> error message


class GovernanceStatusRequest(BaseModel):
    """Request to update a node's governance status."""
    status: str  # draft, pending_review, approved, active, deprecated, archived
    actor: str
    reason: str | None = None
    deprecation_message: str | None = None
    successor: str | None = None
    sunset_deadline: str | None = None
    migration_guide_url: str | None = None


class AuditLogResponse(BaseModel):
    """Audit log entries for governance tracking."""
    entries: list[dict[str, Any]]
    path: str | None = None
    total_entries: int


class CatalogStatsResponse(BaseModel):
    """Catalog statistics and health overview."""
    total_monikers: int
    by_status: dict[str, int]
    by_source_type: dict[str, int]
    by_classification: dict[str, int]
    ownership_coverage: dict[str, Any]


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


class FetchResponse(BaseModel):
    """Response from /fetch - returns actual data from source."""
    moniker: str
    path: str
    source_type: str
    row_count: int
    columns: list[str]
    data: list[dict[str, Any]]
    truncated: bool = False
    query_executed: str | None = None
    execution_time_ms: float | None = None


class MetadataResponse(BaseModel):
    """Rich metadata for AI/agent discoverability."""
    moniker: str
    path: str
    display_name: str | None = None
    description: str | None = None

    # Data characteristics
    data_profile: dict[str, Any] | None = None  # row count, cardinality, size estimates

    # Temporal coverage
    temporal_coverage: dict[str, Any] | None = None  # min/max dates, freshness

    # Relationship graph
    relationships: dict[str, Any] | None = None  # upstream, downstream, joins

    # Schema and semantics
    schema: dict[str, Any] | None = None
    semantic_tags: list[str] = []

    # Quality and governance
    data_quality: dict[str, Any] | None = None
    ownership: dict[str, Any] | None = None
    documentation: dict[str, Any] | None = None

    # Query guidance for AI
    query_patterns: dict[str, Any] | None = None  # common filters, suggested queries
    cost_indicators: dict[str, Any] | None = None  # estimated cost, latency

    # Natural language
    nl_description: str | None = None  # What questions can this data answer?
    use_cases: list[str] = []


class TreeNodeResponse(BaseModel):
    """A node in the catalog tree hierarchy."""
    path: str
    name: str
    children: list["TreeNodeResponse"] = []
    ownership: dict[str, Any] | None = None
    source_type: str | None = None
    has_source_binding: bool = False
    description: str | None = None
    domain: str | None = None


# Enable self-referencing in TreeNodeResponse
TreeNodeResponse.model_rebuild()


# Global service instance (initialized in lifespan)
_service: MonikerService | None = None
_telemetry_task: asyncio.Task | None = None
_batcher_task: asyncio.Task | None = None

# Enterprise governance singletons
_rate_limiter = None
_circuit_breaker = None


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

    # ==========================================================================
    # CREDIT - Credit Risk (MS-SQL)
    # ==========================================================================
    registry.register(CatalogNode(
        path="credit",
        display_name="Credit Risk",
        description="Counterparty credit exposures, limits, and risk metrics from the Credit Risk Engine (SQL Server)",
        ownership=Ownership(
            accountable_owner="credit-risk-governance@firm.com",
            data_specialist="credit-analytics@firm.com",
            support_channel="#credit-risk-data",
        ),
    ))

    registry.register(CatalogNode(
        path="credit.exposures",
        display_name="Credit Exposures",
        description="Daily counterparty credit exposure snapshots including notional, MTM, PFE, CVA, and expected loss by exposure type",
        source_binding=SourceBinding(
            source_type=SourceType.MSSQL,
            config={
                "server": "credit-risk-sql.firm.com",
                "port": 1433,
                "database": "CreditRisk",
                "driver": "ODBC Driver 17 for SQL Server",
                "query": """SELECT ASOF_DATE, COUNTERPARTY_ID, COUNTERPARTY_NAME,
                    SECTOR, RATING, COUNTRY, EXPOSURE_TYPE, NOTIONAL,
                    MARK_TO_MARKET, PFE, CVA, LGD, PD, EXPECTED_LOSS, CURRENCY
                    FROM [dbo].[credit_exposures]
                    WHERE ASOF_DATE >= DATEADD(DAY, -30, GETDATE())""",
            },
        ),
        is_leaf=True,
        data_schema=DataSchema(
            columns=(
                ColumnSchema(name="ASOF_DATE", data_type="date", description="Business date of the exposure snapshot", semantic_type="timestamp", example="2026-01-15"),
                ColumnSchema(name="COUNTERPARTY_ID", data_type="string", description="Unique counterparty identifier", semantic_type="identifier", example="CP001"),
                ColumnSchema(name="COUNTERPARTY_NAME", data_type="string", description="Legal entity name", semantic_type="dimension", example="Goldman Sachs Group"),
                ColumnSchema(name="SECTOR", data_type="string", description="Industry sector classification", semantic_type="dimension", example="Financials"),
                ColumnSchema(name="RATING", data_type="string", description="Credit rating (S&P scale)", semantic_type="dimension", example="AA-"),
                ColumnSchema(name="COUNTRY", data_type="string", description="Country of incorporation (ISO 3166-1 alpha-2)", semantic_type="dimension", example="US"),
                ColumnSchema(name="EXPOSURE_TYPE", data_type="string", description="Type of credit exposure", semantic_type="dimension", example="Derivative"),
                ColumnSchema(name="NOTIONAL", data_type="float", description="Notional amount of the exposure", semantic_type="measure", example="150000000.00"),
                ColumnSchema(name="MARK_TO_MARKET", data_type="float", description="Current mark-to-market value", semantic_type="measure", example="2350000.50"),
                ColumnSchema(name="PFE", data_type="float", description="Potential Future Exposure at 97.5% confidence", semantic_type="measure", example="12500000.00"),
                ColumnSchema(name="CVA", data_type="float", description="Credit Valuation Adjustment", semantic_type="measure", example="45000.00"),
                ColumnSchema(name="LGD", data_type="float", description="Loss Given Default (0-1)", semantic_type="measure", example="0.45"),
                ColumnSchema(name="PD", data_type="float", description="Probability of Default (annualized)", semantic_type="measure", example="0.002"),
                ColumnSchema(name="EXPECTED_LOSS", data_type="float", description="Expected loss = Notional x LGD x PD", semantic_type="measure", example="135000.00"),
                ColumnSchema(name="CURRENCY", data_type="string", description="Exposure currency (ISO 4217)", semantic_type="dimension", example="USD"),
            ),
            description="Daily counterparty credit exposure snapshots with full risk metrics",
            semantic_tags=("credit", "risk", "counterparty", "exposure", "timeseries"),
            primary_key=("ASOF_DATE", "COUNTERPARTY_ID", "EXPOSURE_TYPE"),
            use_cases=(
                "counterparty risk monitoring",
                "limit utilization analysis",
                "CVA desk hedging",
                "regulatory reporting (SA-CCR)",
                "concentration risk assessment",
            ),
            related_monikers=("credit.limits",),
            granularity="daily per-counterparty per-exposure-type",
        ),
        data_quality=DataQuality(
            dq_owner="credit-dq@firm.com",
            quality_score=92,
            known_issues=(
                "Weekend gaps in timeseries — no weekend data points",
                "Petrobras (CP006) rating may lag by 1 business day",
            ),
            validation_rules=(
                "NOTIONAL > 0",
                "LGD BETWEEN 0 AND 1",
                "PD BETWEEN 0 AND 1",
                "EXPECTED_LOSS ≈ NOTIONAL × LGD × PD (±5%)",
            ),
            last_validated="2026-01-28T06:30:00Z",
        ),
        freshness=Freshness(
            last_loaded="2026-01-28T07:15:00Z",
            refresh_schedule="07:00 ET daily",
            source_system="Credit Risk Engine (SQL Server)",
        ),
        sla=SLA(
            freshness="T+1",
            availability="99.5%",
            support_hours="business hours ET",
            escalation_contact="credit-risk-oncall@firm.com",
        ),
        access_policy=AccessPolicy(
            base_row_count=960,
            cardinality_multipliers=(8, 4, 30),
            max_rows_warn=5000,
            max_rows_block=50000,
        ),
        documentation=Documentation(
            glossary_url="https://wiki.firm.com/credit-risk/glossary",
            runbook_url="https://wiki.firm.com/credit-risk/runbook",
            data_dictionary_url="https://wiki.firm.com/credit-risk/exposure-schema",
        ),
        tags=frozenset({"credit", "risk", "mssql", "counterparty", "timeseries"}),
    ))

    registry.register(CatalogNode(
        path="credit.limits",
        display_name="Credit Limits",
        description="Counterparty credit limits with utilization, approval, and expiry information",
        source_binding=SourceBinding(
            source_type=SourceType.MSSQL,
            config={
                "server": "credit-risk-sql.firm.com",
                "port": 1433,
                "database": "CreditRisk",
                "driver": "ODBC Driver 17 for SQL Server",
                "query": """SELECT COUNTERPARTY_ID, LIMIT_TYPE, LIMIT_AMOUNT,
                    UTILIZED, AVAILABLE, APPROVED_BY, EXPIRY_DATE
                    FROM [dbo].[credit_limits]""",
            },
        ),
        is_leaf=True,
        data_schema=DataSchema(
            columns=(
                ColumnSchema(name="COUNTERPARTY_ID", data_type="string", description="Unique counterparty identifier", semantic_type="identifier", example="CP001"),
                ColumnSchema(name="LIMIT_TYPE", data_type="string", description="Type of credit limit", semantic_type="dimension", example="SingleName"),
                ColumnSchema(name="LIMIT_AMOUNT", data_type="float", description="Approved credit limit", semantic_type="measure", example="500000000.00"),
                ColumnSchema(name="UTILIZED", data_type="float", description="Amount currently utilized", semantic_type="measure", example="350000000.00"),
                ColumnSchema(name="AVAILABLE", data_type="float", description="Remaining available limit", semantic_type="measure", example="150000000.00"),
                ColumnSchema(name="APPROVED_BY", data_type="string", description="Approver name and title", semantic_type="dimension", example="J. Smith (CRO)"),
                ColumnSchema(name="EXPIRY_DATE", data_type="date", description="Limit expiry date", semantic_type="timestamp", example="2027-06-15"),
            ),
            description="Counterparty credit limits by type with utilization tracking",
            semantic_tags=("credit", "limits", "counterparty", "governance"),
            primary_key=("COUNTERPARTY_ID", "LIMIT_TYPE"),
            use_cases=(
                "limit utilization monitoring",
                "limit breach alerts",
                "counterparty onboarding",
                "credit committee reporting",
            ),
            related_monikers=("credit.exposures",),
            granularity="per-counterparty per-limit-type",
        ),
        data_quality=DataQuality(
            dq_owner="credit-dq@firm.com",
            quality_score=98,
            known_issues=(),
            validation_rules=(
                "LIMIT_AMOUNT > 0",
                "UTILIZED >= 0",
                "AVAILABLE = LIMIT_AMOUNT - UTILIZED",
                "EXPIRY_DATE > current_date",
            ),
            last_validated="2026-01-28T06:30:00Z",
        ),
        freshness=Freshness(
            last_loaded="2026-01-28T07:15:00Z",
            refresh_schedule="07:00 ET daily",
            source_system="Credit Risk Engine (SQL Server)",
        ),
        sla=SLA(
            freshness="T+0 (intraday updates)",
            availability="99.9%",
            support_hours="24/7",
            escalation_contact="credit-risk-oncall@firm.com",
        ),
        documentation=Documentation(
            glossary_url="https://wiki.firm.com/credit-risk/glossary",
            runbook_url="https://wiki.firm.com/credit-risk/runbook",
            data_dictionary_url="https://wiki.firm.com/credit-risk/limits-schema",
        ),
        tags=frozenset({"credit", "risk", "mssql", "limits", "governance"}),
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
    # Resolve catalog path relative to config file location
    catalog_definition_path = None
    if config.catalog.definition_file:
        config_dir = Path(config_path).parent.resolve()
        catalog_definition_path = (config_dir / config.catalog.definition_file).resolve()
        logger.info(f"Loading catalog from: {catalog_definition_path}")
        catalog = load_catalog(str(catalog_definition_path))
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

    # Initialize enterprise governance features
    global _rate_limiter, _circuit_breaker
    try:
        from .governance.rate_limiter import RateLimiter, RateLimiterConfig
        from .governance.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
        _rate_limiter = RateLimiter(config=RateLimiterConfig())
        _circuit_breaker = CircuitBreaker(config=CircuitBreakerConfig())
        logger.info("Enterprise governance features initialized (rate limiter, circuit breaker)")
    except ImportError:
        logger.info("Governance module not available, running without rate limiting")

    # Initialize authentication if enabled
    if config.auth.enabled:
        authenticator = create_composite_authenticator(config.auth)
        set_authenticator(authenticator)
        logger.info(f"Authentication enabled (enforce={config.auth.enforce})")
    else:
        set_authenticator(None)
        logger.info("Authentication disabled")

    # Initialize SQL Catalog if enabled
    if config.sql_catalog.enabled:
        sql_catalog_routes.configure(
            db_path=config.sql_catalog.db_path,
            source_db_path=config.sql_catalog.source_db_path,
        )
        logger.info(f"SQL Catalog enabled (db_path={config.sql_catalog.db_path})")

    # Initialize Config UI if enabled (will get domain_registry later)
    config_ui_enabled = config.config_ui.enabled
    if config_ui_enabled:
        logger.info(f"Config UI enabled (catalog_file={catalog_definition_path})")

    # Initialize Domain Configuration
    global _domain_registry
    _domain_registry = DomainRegistry()
    domains_yaml_path = os.environ.get("DOMAINS_CONFIG", "domains.yaml")
    if Path(domains_yaml_path).exists():
        domains = load_domains_from_yaml(domains_yaml_path, _domain_registry)
        logger.info(f"Loaded {len(domains)} domains from {domains_yaml_path}")
    else:
        logger.info(f"No domains config found at {domains_yaml_path}, starting with empty registry")

    domain_routes.configure(
        domain_registry=_domain_registry,
        catalog_registry=catalog,
        domains_yaml_path=domains_yaml_path,
    )
    logger.info("Domain configuration enabled")

    # Set domain_registry on service for ownership inheritance
    _service.domain_registry = _domain_registry

    # Now configure Config UI with domain registry for ownership inheritance
    if config_ui_enabled:
        config_ui_routes.configure(
            catalog=catalog,
            yaml_output_path=config.config_ui.yaml_output_path,
            catalog_definition_file=str(catalog_definition_path) if catalog_definition_path else None,
            service_cache=cache,
            show_file_paths=config.config_ui.show_file_paths,
            domain_registry=_domain_registry,
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


# Create FastAPI app with enhanced OpenAPI documentation
app = FastAPI(
    title="Moniker Resolution Service",
    description="""
## Overview

Resolves monikers (semantic data paths) to source connection info.

## Key Concepts

- **Domains**: Top-level organizational units (indices, commodities, reference, etc.) with governance metadata
- **Monikers**: Hierarchical paths to data assets (e.g., `indices/equity/sp500`)
- **Resolution**: Maps monikers to connection parameters and query templates

## Execution Models

- **Client-side** (`/resolve`): Returns connection info for direct client execution
- **Server-side** (`/fetch`): Executes queries and returns data directly

## Documentation

- Swagger UI: `/docs`
- OpenAPI JSON: `/openapi.json`
    """,
    version="0.2.0",
    contact={"name": "Data Platform Team"},
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Resolution", "description": "Resolve monikers to connection info for client-side execution"},
        {"name": "Data Fetch", "description": "Server-side data retrieval and metadata"},
        {"name": "Catalog", "description": "Browse and explore the moniker catalog"},
        {"name": "Domains", "description": "Domain governance and configuration"},
        {"name": "SQL Catalog", "description": "SQL statement discovery and cataloging"},
        {"name": "Config", "description": "Catalog configuration management"},
        {"name": "Telemetry", "description": "Access tracking and reporting"},
        {"name": "Health", "description": "Service health and diagnostics"},
    ],
)

# Mount shared static files
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# Mount routers
app.include_router(sql_catalog_routes.router)
app.include_router(config_ui_routes.router)
app.include_router(domain_routes.router)


@app.exception_handler(MonikerParseError)
async def moniker_parse_error_handler(request: Request, exc: MonikerParseError):
    return JSONResponse(
        status_code=400,
        content={"error": "Invalid moniker", "detail": str(exc)},
    )


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request: Request, exc: NotFoundError):
    content = {"error": "Not found", "detail": str(exc)}

    # Try to extract domain documentation hint from path
    try:
        path = request.url.path
        # Extract moniker path from URL (after /resolve/, /describe/, etc.)
        for prefix in ["/resolve/", "/describe/", "/list/", "/lineage/", "/fetch/", "/metadata/", "/tree/"]:
            if path.startswith(prefix):
                moniker_path = path[len(prefix):]
                # Get first segment (before / or .)
                first_segment = moniker_path.split("/")[0].split(".")[0]
                if _domain_registry and first_segment:
                    domain = _domain_registry.get(first_segment)
                    if domain:
                        content["domain"] = first_segment
                        if domain.wiki_link:
                            content["documentation"] = domain.wiki_link
                        if domain.help_channel:
                            content["help_channel"] = domain.help_channel
                break
    except Exception:
        pass  # Don't fail the 404 response if hint extraction fails

    return JSONResponse(status_code=404, content=content)


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


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    """Health check endpoint with telemetry, cache, rate limiter, and circuit breaker statistics."""
    return HealthResponse(
        status="healthy",
        telemetry=_service.telemetry.stats if _service else {},
        cache=_service.cache.stats if _service else {},
        rate_limiter=_rate_limiter.stats if _rate_limiter else None,
        circuit_breaker=_circuit_breaker.stats if _circuit_breaker else None,
        catalog_counts=_service.catalog.count() if _service else None,
    )


@app.get("/resolve/{path:path}", response_model=ResolveResponse, tags=["Resolution"])
async def resolve_moniker(
    request: Request,
    path: str,
    caller: Annotated[CallerIdentity, Depends(get_caller_identity)],
):
    """
    Resolve a moniker to source connection info.

    Returns everything the client needs to connect directly to the data source:
    - **source_type**: snowflake, oracle, rest, bloomberg, etc.
    - **connection**: Connection parameters (account, warehouse, etc.)
    - **query**: SQL query or API path to execute
    - **ownership**: Who owns this data

    The client then connects directly to the source - this service does NOT proxy data.
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Rate limiting
    if _rate_limiter:
        try:
            caller_id = caller.app_id or caller.user_id or "anonymous"
            _rate_limiter.check(caller_id)
        except Exception as e:
            raise HTTPException(
                status_code=429,
                detail=str(e),
                headers={"Retry-After": str(getattr(e, 'retry_after_seconds', 1))},
            )

    # Get full path from request URL (preserves unencoded slashes)
    full_path = request.url.path
    if full_path.startswith("/resolve/"):
        path = full_path[9:]  # Strip "/resolve/"

    # Build full moniker string
    moniker_str = f"moniker://{path}"
    if request.query_params:
        params = list(request.query_params.items())
        if params:
            moniker_str += "?" + "&".join(f"{k}={v}" for k, v in params)

    result = await _service.resolve(moniker_str, caller)

    # Check for deprecation warning
    node = result.node
    status_val = None
    deprecation_msg = None
    successor = None
    sunset_deadline = None
    migration_guide_url = None
    if node:
        if hasattr(node, 'status') and hasattr(node.status, 'value'):
            status_val = node.status.value
        deprecation_msg = getattr(node, 'deprecation_message', None)
        successor = getattr(node, 'successor', None)
        sunset_deadline = getattr(node, 'sunset_deadline', None)
        migration_guide_url = getattr(node, 'migration_guide_url', None)

    response = ResolveResponse(
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
        status=status_val,
        deprecation_message=deprecation_msg,
        successor=successor,
        sunset_deadline=sunset_deadline,
        migration_guide_url=migration_guide_url,
        redirected_from=result.redirected_from,
    )

    # Add deprecation/redirect headers
    headers = {}
    if status_val == "deprecated":
        headers["X-Moniker-Deprecated"] = deprecation_msg or "This moniker is deprecated"
    if successor:
        headers["X-Moniker-Successor"] = successor
    if result.redirected_from:
        headers["X-Moniker-Redirected-From"] = result.redirected_from

    if headers:
        return JSONResponse(
            content=response.model_dump(),
            headers=headers,
        )

    return response


@app.get("/list/{path:path}", response_model=ListResponse, tags=["Catalog"])
async def list_children(
    request: Request,
    path: str = "",
    caller: Annotated[CallerIdentity, Depends(get_caller_identity)] = None,
):
    """List children of a moniker path in the catalog hierarchy."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Get full path from request URL (preserves unencoded slashes)
    full_path = request.url.path
    if full_path.startswith("/list/"):
        path = full_path[6:]  # Strip "/list/"

    moniker_str = f"moniker://{path}" if path else "moniker://"

    result = await _service.list_children(moniker_str, caller)
    return ListResponse(
        children=result.children,
        moniker=result.moniker,
        path=result.path,
    )


@app.get("/describe/{path:path}", response_model=DescribeResponse, tags=["Resolution"])
async def describe_moniker(
    request: Request,
    path: str,
    caller: Annotated[CallerIdentity, Depends(get_caller_identity)],
):
    """Get metadata about a moniker path including ownership, classification, and data quality info."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Get full path from request URL (preserves unencoded slashes)
    full_path = request.url.path
    if full_path.startswith("/describe/"):
        path = full_path[10:]  # Strip "/describe/"

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

    # Build documentation dict if present
    documentation = None
    if result.node and result.node.documentation:
        documentation = result.node.documentation.to_dict()

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
        documentation=documentation,
    )


@app.get("/lineage/{path:path}", response_model=LineageResponse, tags=["Resolution"])
async def get_lineage(
    request: Request,
    path: str,
    caller: Annotated[CallerIdentity, Depends(get_caller_identity)],
):
    """Get full ownership lineage for a moniker path showing inheritance chain."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Get full path from request URL (preserves unencoded slashes)
    full_path = request.url.path
    if full_path.startswith("/lineage/"):
        path = full_path[9:]  # Strip "/lineage/"

    moniker_str = f"moniker://{path}"

    result = await _service.lineage(moniker_str, caller)
    return LineageResponse(**result)


@app.post("/telemetry/access", tags=["Telemetry"])
async def report_access(
    report: AccessReport,
    caller: Annotated[CallerIdentity, Depends(get_caller_identity)],
):
    """
    Client reports access telemetry after fetching data.

    This allows tracking actual data access patterns, not just resolutions.
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


@app.get("/catalog", tags=["Catalog"])
async def list_catalog(
    cursor: str | None = Query(default=None, description="Cursor for pagination (last path from previous page)"),
    limit: int = Query(default=100, le=1000, description="Maximum paths to return"),
    status: str | None = Query(default=None, description="Filter by status: active, deprecated, draft, etc."),
):
    """
    List catalog paths with cursor-based pagination.

    For catalogs with thousands of monikers, use cursor-based pagination:
    1. First call: GET /catalog?limit=100
    2. Next page: GET /catalog?limit=100&cursor=<next_cursor from response>
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Apply rate limiting
    if _rate_limiter:
        try:
            _rate_limiter.check("catalog_list")
        except Exception as e:
            raise HTTPException(
                status_code=429,
                detail=str(e),
                headers={"Retry-After": str(getattr(e, 'retry_after_seconds', 1))},
            )

    from .catalog.types import NodeStatus
    status_filter = None
    if status:
        try:
            status_filter = NodeStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    paths, next_cursor = _service.catalog.paginated_paths(
        cursor=cursor, limit=limit, status=status_filter,
    )

    return PaginatedCatalogResponse(
        paths=paths,
        total_count=len(_service.catalog.all_paths()),
        next_cursor=next_cursor,
        has_more=next_cursor is not None,
    )


@app.get("/catalog/search", response_model=CatalogSearchResponse, tags=["Catalog"])
async def search_catalog(
    q: str = Query(description="Search query (matches path, name, description, tags)"),
    status: str | None = Query(default=None, description="Filter by lifecycle status"),
    limit: int = Query(default=50, le=200, description="Maximum results"),
):
    """
    Search the catalog by path, display name, description, or tags.

    Useful for discovering monikers in a large catalog.
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    from .catalog.types import NodeStatus
    status_filter = None
    if status:
        try:
            status_filter = NodeStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    results = _service.catalog.search(q, status=status_filter, limit=limit)

    return CatalogSearchResponse(
        results=[
            {
                "path": n.path,
                "display_name": n.display_name,
                "description": n.description,
                "status": n.status.value if hasattr(n.status, 'value') else str(n.status),
                "has_source_binding": n.source_binding is not None,
                "classification": n.classification,
                "tags": list(n.tags),
            }
            for n in results
        ],
        query=q,
        total_results=len(results),
    )


@app.get("/catalog/stats", response_model=CatalogStatsResponse, tags=["Catalog"])
async def catalog_stats():
    """Get catalog statistics - moniker counts by status, source type, and classification."""
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    nodes = _service.catalog.all_nodes()

    by_status: dict[str, int] = {}
    by_source_type: dict[str, int] = {}
    by_classification: dict[str, int] = {}
    has_owner = 0
    has_governance = 0

    for node in nodes:
        # Count by status
        status_key = node.status.value if hasattr(node.status, 'value') else "active"
        by_status[status_key] = by_status.get(status_key, 0) + 1

        # Count by source type
        if node.source_binding:
            st = node.source_binding.source_type.value
            by_source_type[st] = by_source_type.get(st, 0) + 1

        # Count by classification
        by_classification[node.classification] = by_classification.get(node.classification, 0) + 1

        # Ownership coverage
        if not node.ownership.is_empty():
            has_owner += 1
        if node.ownership.has_governance_roles():
            has_governance += 1

    return CatalogStatsResponse(
        total_monikers=len(nodes),
        by_status=by_status,
        by_source_type=by_source_type,
        by_classification=by_classification,
        ownership_coverage={
            "has_ownership": has_owner,
            "has_governance_roles": has_governance,
            "coverage_percent": round(has_owner / max(len(nodes), 1) * 100, 1),
        },
    )


# =============================================================================
# BATCH RESOLUTION - Enterprise-scale multi-moniker resolution
# =============================================================================

@app.post("/resolve/batch", response_model=BatchResolveResponse, tags=["Resolution"])
async def batch_resolve(
    request_body: BatchResolveRequest,
    caller: Annotated[CallerIdentity, Depends(get_caller_identity)],
):
    """
    Resolve multiple monikers in a single request.

    Much more efficient than individual /resolve calls when you need
    connection info for many monikers (e.g., batch data pipelines).

    Maximum 100 monikers per request.
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    if len(request_body.monikers) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 monikers per batch request")

    # Apply rate limiting (counts as N requests)
    if _rate_limiter:
        try:
            caller_id = caller.app_id or caller.user_id or "anonymous"
            for _ in request_body.monikers:
                _rate_limiter.check(caller_id)
        except Exception as e:
            raise HTTPException(
                status_code=429,
                detail=str(e),
                headers={"Retry-After": str(getattr(e, 'retry_after_seconds', 1))},
            )

    results = []
    errors = {}

    for moniker_str in request_body.monikers:
        try:
            result = await _service.resolve(moniker_str, caller)
            node = result.node

            results.append(ResolveResponse(
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
                    "data_specialist": result.ownership.data_specialist,
                    "support_channel": result.ownership.support_channel,
                },
                binding_path=result.binding_path,
                sub_path=result.sub_path,
                status=node.status.value if node and hasattr(node.status, 'value') else None,
                deprecation_message=node.deprecation_message if node and hasattr(node, 'deprecation_message') else None,
            ))
        except Exception as e:
            errors[moniker_str] = str(e)

    return BatchResolveResponse(results=results, errors=errors)


# =============================================================================
# GOVERNANCE ENDPOINTS - Lifecycle management and audit trail
# =============================================================================

@app.put("/catalog/{path:path}/status", tags=["Catalog"])
async def update_catalog_status(
    request: Request,
    path: str,
    body: GovernanceStatusRequest,
):
    """
    Update the governance lifecycle status of a moniker.

    Valid transitions:
    - draft -> pending_review -> approved -> active
    - active -> deprecated -> archived
    - Any status -> draft (reset)
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    full_path = request.url.path
    if full_path.startswith("/catalog/") and full_path.endswith("/status"):
        path = full_path[9:-7]  # Strip "/catalog/" and "/status"

    from .catalog.types import NodeStatus
    try:
        new_status = NodeStatus(body.status)
    except ValueError:
        valid = [s.value for s in NodeStatus]
        raise HTTPException(status_code=400, detail=f"Invalid status '{body.status}'. Valid: {valid}")

    node = _service.catalog.update_status(path, new_status, body.actor)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node not found: {path}")

    # If deprecating, set the message and successor fields
    if new_status == NodeStatus.DEPRECATED and body.deprecation_message:
        node.deprecation_message = body.deprecation_message
    if body.successor is not None:
        node.successor = body.successor
    if body.sunset_deadline is not None:
        node.sunset_deadline = body.sunset_deadline
    if body.migration_guide_url is not None:
        node.migration_guide_url = body.migration_guide_url

    return {
        "path": path,
        "status": new_status.value,
        "updated_by": body.actor,
        "message": f"Status changed to {new_status.value}",
    }


@app.get("/catalog/{path:path}/audit", response_model=AuditLogResponse, tags=["Catalog"])
async def get_audit_log(
    request: Request,
    path: str,
    limit: int = Query(default=100, le=1000, description="Maximum entries"),
):
    """
    Get the audit trail for a moniker.

    Shows all governance actions: status changes, ownership updates, etc.
    Essential for compliance and regulatory reporting.
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    full_path = request.url.path
    if full_path.startswith("/catalog/") and full_path.endswith("/audit"):
        path = full_path[9:-6]  # Strip "/catalog/" and "/audit"

    entries = _service.catalog.get_audit_log(path=path, limit=limit)

    return AuditLogResponse(
        entries=[
            {
                "timestamp": e.timestamp,
                "path": e.path,
                "action": e.action,
                "actor": e.actor,
                "old_value": e.old_value,
                "new_value": e.new_value,
                "details": e.details,
            }
            for e in entries
        ],
        path=path,
        total_entries=len(entries),
    )


# =============================================================================
# DATA FETCH ENDPOINTS - Server-side query execution
# =============================================================================

@app.get("/fetch/{path:path}", response_model=FetchResponse, tags=["Data Fetch"])
async def fetch_data(
    request: Request,
    path: str,
    caller: Annotated[CallerIdentity, Depends(get_caller_identity)],
    limit: int = Query(default=100, le=10000, description="Max rows to return"),
):
    """
    Fetch actual data by executing the query server-side.

    Unlike `/resolve` which returns connection info for client-side execution,
    this endpoint executes the query and returns the data directly.

    **Use cases:**
    - Small datasets where direct fetch is convenient
    - AI agents that need data without managing connections
    - Demos and exploration

    For large datasets, use /resolve and execute client-side.
    """
    import time
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Get full path from request URL (preserves unencoded slashes)
    full_path = request.url.path
    if full_path.startswith("/fetch/"):
        path = full_path[7:]  # Strip "/fetch/"

    moniker_str = f"moniker://{path}"
    start_time = time.time()

    # First resolve the moniker
    result = await _service.resolve(moniker_str, caller)

    # Execute the query using appropriate mock adapter
    # In production, this would use real adapters
    data = []
    columns = []

    try:
        if result.source.source_type == "oracle":
            from moniker_data.adapters.oracle import execute_query
            data = execute_query(result.source.query)
        elif result.source.source_type == "snowflake":
            from moniker_data.adapters.snowflake import MockSnowflakeAdapter
            adapter = MockSnowflakeAdapter()
            data = adapter.execute(result.source.query)
        elif result.source.source_type == "rest":
            from moniker_data.adapters.rest import MockRestAdapter
            adapter = MockRestAdapter()
            data = adapter.fetch(result.source.query or result.sub_path or "")
        elif result.source.source_type == "excel":
            from moniker_data.adapters.excel import MockExcelAdapter
            adapter = MockExcelAdapter()
            data = adapter.fetch(result.source.query or "")
        elif result.source.source_type == "mssql":
            from moniker_data.adapters.mssql import execute_query as mssql_execute_query
            data = mssql_execute_query(result.source.query)
        else:
            raise HTTPException(
                status_code=501,
                detail=f"Fetch not implemented for source type: {result.source.source_type}"
            )
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Mock adapters not available. Install moniker-data package."
        )

    # Apply limit and track truncation
    truncated = len(data) > limit
    data = data[:limit]

    # Extract columns from first row
    if data:
        columns = list(data[0].keys())

    execution_time = (time.time() - start_time) * 1000

    return FetchResponse(
        moniker=moniker_str,
        path=result.path,
        source_type=result.source.source_type,
        row_count=len(data),
        columns=columns,
        data=data,
        truncated=truncated,
        query_executed=result.source.query,
        execution_time_ms=round(execution_time, 2),
    )


@app.get("/metadata/{path:path}", response_model=MetadataResponse, tags=["Data Fetch"])
async def get_metadata(
    request: Request,
    path: str,
    caller: Annotated[CallerIdentity, Depends(get_caller_identity)],
):
    """
    Get rich metadata for AI/agent discoverability.

    Returns comprehensive information about a data source including:
    - **Data profile**: Row counts, cardinality estimates
    - **Temporal coverage**: Date ranges, freshness indicators
    - **Relationships**: Upstream/downstream dependencies
    - **Schema**: Column definitions with semantic annotations
    - **Query patterns**: Cost indicators and optimization hints
    - **Descriptions**: Natural language descriptions for AI understanding

    This endpoint is optimized for machine discovery and AI agents.
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Get full path from request URL (preserves unencoded slashes)
    full_path = request.url.path
    if full_path.startswith("/metadata/"):
        path = full_path[10:]  # Strip "/metadata/"

    moniker_str = f"moniker://{path}"

    # Get describe info
    describe_result = await _service.describe(moniker_str, caller)
    node = describe_result.node

    # Build data profile from access policy cardinality info
    data_profile = None
    if node and node.access_policy:
        ap = node.access_policy
        data_profile = {
            "estimated_total_rows": ap.base_row_count * (
                ap.cardinality_multipliers[0] if ap.cardinality_multipliers else 1
            ) * (
                ap.cardinality_multipliers[1] if len(ap.cardinality_multipliers) > 1 else 1
            ) * (
                ap.cardinality_multipliers[2] if len(ap.cardinality_multipliers) > 2 else 1
            ),
            "base_row_count": ap.base_row_count,
            "cardinality_by_dimension": list(ap.cardinality_multipliers) if ap.cardinality_multipliers else [],
            "max_rows_warn": ap.max_rows_warn,
            "max_rows_block": ap.max_rows_block,
        }

    # Build temporal coverage from freshness info
    temporal_coverage = None
    if node and node.freshness:
        f = node.freshness
        temporal_coverage = {
            "last_loaded": f.last_loaded,
            "refresh_schedule": f.refresh_schedule,
            "source_system": f.source_system,
            "upstream_dependencies": list(f.upstream_dependencies) if f.upstream_dependencies else [],
        }

    # Build relationships from schema related_monikers
    relationships = None
    if node and node.data_schema:
        ds = node.data_schema
        relationships = {
            "related_monikers": list(ds.related_monikers) if ds.related_monikers else [],
            "upstream_dependencies": list(node.freshness.upstream_dependencies) if node.freshness and node.freshness.upstream_dependencies else [],
            "foreign_keys": [
                {"column": col.name, "references": col.foreign_key}
                for col in ds.columns if col.foreign_key
            ] if ds.columns else [],
        }

    # Build schema info
    schema = None
    semantic_tags = []
    use_cases = []
    nl_description = None

    if node and node.data_schema:
        ds = node.data_schema
        semantic_tags = list(ds.semantic_tags) if ds.semantic_tags else []
        use_cases = list(ds.use_cases) if ds.use_cases else []
        nl_description = ds.description

        schema = {
            "description": ds.description,
            "granularity": ds.granularity,
            "typical_row_count": ds.typical_row_count,
            "update_frequency": ds.update_frequency,
            "primary_key": list(ds.primary_key) if ds.primary_key else [],
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
            ] if ds.columns else [],
            "examples": list(ds.examples) if ds.examples else [],
        }

    # Build query patterns / cost indicators
    query_patterns = None
    cost_indicators = None
    if node and node.access_policy:
        ap = node.access_policy
        query_patterns = {
            "blocked_patterns": list(ap.blocked_patterns) if ap.blocked_patterns else [],
            "min_filters_required": ap.min_filters,
            "suggested_queries": list(node.data_schema.examples) if node.data_schema and node.data_schema.examples else [],
        }
        cost_indicators = {
            "query_complexity": "high" if ap.max_rows_block and ap.max_rows_block > 100_000_000 else "medium" if ap.max_rows_warn else "low",
            "estimated_latency": "high" if data_profile and data_profile.get("estimated_total_rows", 0) > 1_000_000_000 else "medium" if data_profile and data_profile.get("estimated_total_rows", 0) > 1_000_000 else "low",
        }

    # Build data quality info
    data_quality = None
    if node and node.data_quality:
        dq = node.data_quality
        data_quality = {
            "quality_score": dq.quality_score,
            "dq_owner": dq.dq_owner,
            "validation_rules": list(dq.validation_rules) if dq.validation_rules else [],
            "known_issues": list(dq.known_issues) if dq.known_issues else [],
            "last_validated": dq.last_validated,
        }

    # Build ownership info
    ownership = None
    if describe_result.ownership:
        o = describe_result.ownership
        ownership = {
            "accountable_owner": o.accountable_owner,
            "data_specialist": o.data_specialist,
            "support_channel": o.support_channel,
            "adop": o.adop,
            "ads": o.ads,
            "adal": o.adal,
        }

    # Build documentation
    documentation = None
    if node and node.documentation:
        documentation = node.documentation.to_dict()

    return MetadataResponse(
        moniker=moniker_str,
        path=describe_result.path,
        display_name=node.display_name if node else None,
        description=node.description if node else None,
        data_profile=data_profile,
        temporal_coverage=temporal_coverage,
        relationships=relationships,
        schema=schema,
        semantic_tags=semantic_tags,
        data_quality=data_quality,
        ownership=ownership,
        documentation=documentation,
        query_patterns=query_patterns,
        cost_indicators=cost_indicators,
        nl_description=nl_description,
        use_cases=use_cases,
    )


@app.get("/tree/{path:path}", response_model=TreeNodeResponse, tags=["Catalog"])
async def get_tree(
    request: Request,
    path: str,
    depth: int | None = Query(default=None, description="Maximum depth to traverse"),
):
    """
    Get the catalog tree structure starting from a path.

    Returns a hierarchical view of the catalog with metadata at each node.
    Useful for understanding available data domains and their organization.
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # Get full path from request URL (preserves unencoded slashes)
    full_path = request.url.path
    if full_path.startswith("/tree/"):
        path = full_path[6:]  # Strip "/tree/"

    def build_tree_node(node_path: str, current_depth: int = 0) -> TreeNodeResponse:
        # Check depth limit
        if depth is not None and current_depth > depth:
            return None

        # Get node info
        node = _service.catalog.get(node_path)
        if node is None:
            return None

        # Get name (last segment of path)
        name = node_path.split("/")[-1] if "/" in node_path else node_path

        # Get ownership
        ownership = None
        if node.ownership:
            ownership = {
                "accountable_owner": node.ownership.accountable_owner,
                "data_specialist": node.ownership.data_specialist,
                "support_channel": node.ownership.support_channel,
            }
            # Also include governance roles if set
            if node.ownership.adop:
                ownership["adop"] = node.ownership.adop
            if node.ownership.ads:
                ownership["ads"] = node.ownership.ads
            if node.ownership.adal:
                ownership["adal"] = node.ownership.adal
            if node.ownership.ui:
                ownership["ui"] = node.ownership.ui

        # Get source type
        source_type = None
        has_source_binding = False
        if node.source_binding:
            has_source_binding = True
            source_type = node.source_binding.source_type.value

        # Build children recursively (sorted alphabetically)
        children = []
        if depth is None or current_depth < depth:
            child_paths = _service.catalog.children_paths(node_path)
            for child_path in sorted(child_paths, key=str.lower):
                child_node = build_tree_node(child_path, current_depth + 1)
                if child_node:
                    children.append(child_node)

        return TreeNodeResponse(
            path=node_path,
            name=name,
            children=children,
            ownership=ownership,
            source_type=source_type,
            has_source_binding=has_source_binding,
            description=node.description,
            domain=node.domain,
        )

    tree = build_tree_node(path)
    if tree is None:
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")

    return tree


@app.get("/tree", response_model=list[TreeNodeResponse], tags=["Catalog"])
async def get_tree_root(
    depth: int | None = Query(default=None, description="Maximum depth to traverse"),
):
    """
    Get the catalog tree structure from the root.

    Returns all top-level domains with their hierarchical structure and metadata.
    """
    if not _service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    def build_tree_node(node_path: str, current_depth: int = 0) -> TreeNodeResponse:
        # Check depth limit
        if depth is not None and current_depth > depth:
            return None

        # Get node info
        node = _service.catalog.get(node_path)
        if node is None:
            return None

        # Get name (last segment of path)
        name = node_path.split("/")[-1] if "/" in node_path else node_path

        # Get ownership
        ownership = None
        if node.ownership:
            ownership = {
                "accountable_owner": node.ownership.accountable_owner,
                "data_specialist": node.ownership.data_specialist,
                "support_channel": node.ownership.support_channel,
            }
            if node.ownership.adop:
                ownership["adop"] = node.ownership.adop
            if node.ownership.ads:
                ownership["ads"] = node.ownership.ads
            if node.ownership.adal:
                ownership["adal"] = node.ownership.adal
            if node.ownership.ui:
                ownership["ui"] = node.ownership.ui

        # Get source type
        source_type = None
        has_source_binding = False
        if node.source_binding:
            has_source_binding = True
            source_type = node.source_binding.source_type.value

        # Build children recursively
        children = []
        if depth is None or current_depth < depth:
            child_paths = _service.catalog.children_paths(node_path)
            for child_path in sorted(child_paths, key=str.lower):
                child_node = build_tree_node(child_path, current_depth + 1)
                if child_node:
                    children.append(child_node)

        return TreeNodeResponse(
            path=node_path,
            name=name,
            children=children,
            ownership=ownership,
            source_type=source_type,
            has_source_binding=has_source_binding,
            description=node.description,
            domain=node.domain,
        )

    # Get root-level nodes (sorted alphabetically)
    root_children = _service.catalog.children_paths("")
    trees = []
    for child_path in sorted(root_children, key=str.lower):
        tree = build_tree_node(child_path)
        if tree:
            trees.append(tree)

    return trees


_LANDING_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Moniker Service</title>
    <style>
        :root {
            --font-sans: Arial, Helvetica, sans-serif;
            --fs-900: 20px;
            --fs-800: 18px;
            --fs-700: 16px;
            --fs-600: 14px;
            --fs-500: 12px;
            --fw-regular: 400;
            --fw-bold: 700;
            --sp-1: 4px;
            --sp-2: 8px;
            --sp-3: 12px;
            --sp-4: 16px;
            --sp-5: 24px;
            --sp-6: 32px;
            --radius-1: 4px;
            --radius-2: 8px;
            --c-navy: #022D5E;
            --c-gray: #53565A;
            --c-peacock: #005587;
            --c-teal: #00897B;
            --c-olive: #789D4A;
            --c-cerulean: #008BCD;
            --c-red: #D0002B;
            --c-green: #009639;
            --color-bg: #f8f9fa;
            --color-surface: #ffffff;
            --color-text: #111111;
            --color-muted: var(--c-gray);
            --border: rgba(83, 86, 90, 0.25);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: var(--font-sans);
            font-size: var(--fs-700);
            background: var(--color-bg);
            color: var(--color-text);
            line-height: 1.45;
        }
        header {
            background: var(--c-navy);
            padding: var(--sp-5);
            border-bottom: 3px solid var(--c-peacock);
        }
        header h1 {
            font-size: var(--fs-900);
            color: white;
            max-width: 1200px;
            margin: 0 auto;
        }
        header p {
            color: rgba(255,255,255,0.8);
            max-width: 1200px;
            margin: var(--sp-2) auto 0;
            font-size: var(--fs-600);
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: var(--sp-5);
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: var(--sp-5);
            margin-top: var(--sp-5);
        }
        .card {
            background: var(--color-surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-2);
            padding: var(--sp-5);
            transition: box-shadow 0.2s, transform 0.2s;
        }
        .card:hover {
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            transform: translateY(-2px);
        }
        .card h2 {
            font-size: var(--fs-800);
            color: var(--c-navy);
            margin-bottom: var(--sp-2);
            display: flex;
            align-items: center;
            gap: var(--sp-2);
        }
        .card p {
            color: var(--color-muted);
            font-size: var(--fs-600);
            margin-bottom: var(--sp-4);
        }
        .card a {
            display: inline-block;
            background: var(--c-peacock);
            color: white;
            padding: var(--sp-2) var(--sp-4);
            border-radius: var(--radius-1);
            text-decoration: none;
            font-weight: var(--fw-bold);
            font-size: var(--fs-600);
            transition: filter 0.2s;
        }
        .card a:hover { filter: brightness(0.9); }
        .card.docs a { background: var(--c-olive); }
        .card.api a { background: var(--c-teal); }
        .section-title {
            font-size: var(--fs-800);
            color: var(--c-navy);
            margin-top: var(--sp-6);
            padding-bottom: var(--sp-2);
            border-bottom: 2px solid var(--c-peacock);
        }
        .icon { font-size: 24px; }
        footer {
            text-align: center;
            padding: var(--sp-5);
            color: var(--color-muted);
            font-size: var(--fs-500);
        }
    </style>
</head>
<body>
    <header>
        <h1>Moniker Service</h1>
        <p>Data catalog resolution and governance platform</p>
    </header>

    <div class="container">
        <h3 class="section-title">Administration</h3>
        <div class="grid">
            <div class="card">
                <h2>Domain Configuration</h2>
                <p>Manage data domains with governance metadata: ownership, confidentiality, PII flags.</p>
                <a href="/domains/ui">Configure Domains</a>
            </div>
            <div class="card">
                <h2>Catalog Config</h2>
                <p>Edit monikers, source bindings, and ownership configuration.</p>
                <a href="/config/ui">Catalog Config UI</a>
            </div>
            <div class="card">
                <h2>Catalog Browser</h2>
                <p>Browse the moniker catalog hierarchy, view ownership and metadata for data assets.</p>
                <a href="/ui">Open Catalog Browser</a>
            </div>
            <div class="card">
                <h2>SQL Catalog</h2>
                <p>Browse discovered SQL statements, schemas, and table relationships.</p>
                <a href="/sql/ui">SQL Catalog Browser</a>
            </div>
        </div>

        <h3 class="section-title">API Documentation</h3>
        <div class="grid">
            <div class="card docs">
                <h2>Swagger UI</h2>
                <p>Interactive API documentation with try-it-out functionality.</p>
                <a href="/docs">Open Swagger</a>
            </div>
        </div>

        <h3 class="section-title">API Endpoints</h3>
        <div class="grid">
            <div class="card api">
                <h2>Catalog Tree</h2>
                <p>View full catalog hierarchy as JSON tree structure.</p>
                <a href="/tree">View Tree API</a>
            </div>
            <div class="card api">
                <h2>Domains</h2>
                <p>List all configured data domains with governance info.</p>
                <a href="/domains">Domains API</a>
            </div>
            <div class="card api">
                <h2>Catalog Paths</h2>
                <p>List all registered catalog paths.</p>
                <a href="/catalog">Catalog API</a>
            </div>
            <div class="card api">
                <h2>OpenAPI Schema</h2>
                <p>Raw OpenAPI 3.0 specification in JSON format.</p>
                <a href="/openapi.json">View Schema</a>
            </div>
            <div class="card api">
                <h2>Health Check</h2>
                <p>Service health, telemetry stats, and cache metrics.</p>
                <a href="/health">Check Health</a>
            </div>
        </div>
    </div>

    <footer>
        Moniker Service v0.2.0 &mdash; Data Catalog Resolution Platform
    </footer>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse, tags=["Health"])
async def root():
    """Landing page with links to all UIs and documentation."""
    return HTMLResponse(content=_LANDING_HTML)


# Simple HTML UI for tree visualization
_UI_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Moniker Catalog</title>
    <style>
        /* Corporate Design Tokens */
        :root {
            --font-sans: Arial, Helvetica, sans-serif;
            --c-navy: #022D5E;
            --c-gray: #53565A;
            --c-peacock: #005587;
            --c-olive: #789D4A;
            --c-green: #009639;
            --c-red: #D0002B;
            --color-bg: #f8f9fa;
            --color-surface: #ffffff;
            --color-text: #111111;
            --border: rgba(83, 86, 90, 0.25);
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: var(--font-sans);
            background: var(--color-bg);
            color: var(--color-text);
            padding: 0;
            display: flex;
            flex-direction: column;
            height: 100vh;
        }

        /* Header */
        .header {
            background: var(--c-navy);
            padding: 16px 24px;
            border-bottom: 3px solid var(--c-peacock);
        }
        .header h1 {
            font-size: 20px;
            font-weight: 700;
            color: white;
            margin: 0;
        }

        /* Main content */
        .main {
            display: flex;
            flex: 1;
            padding: 24px;
            gap: 24px;
            overflow: hidden;
        }

        .panel {
            background: var(--color-surface);
            border-radius: 8px;
            border: 1px solid var(--border);
            overflow: auto;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
        }
        .tree-panel { flex: 1; }
        .detail-panel { width: 420px; }

        .panel-header {
            background: var(--c-navy);
            padding: 12px 16px;
            font-weight: 700;
            font-size: 14px;
            color: white;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header-actions {
            display: flex;
            gap: 8px;
        }
        .btn-small {
            background: var(--c-peacock);
            color: white;
            border: none;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 700;
            font-family: var(--font-sans);
            cursor: pointer;
            transition: filter 0.2s;
        }
        .btn-small:hover {
            filter: brightness(0.9);
        }
        .panel-content {
            padding: 16px;
        }

        /* Tree styles */
        .tree { font-size: 14px; line-height: 1.6; }
        .tree ul { list-style: none; padding-left: 20px; }
        .tree > ul { padding-left: 0; }
        .tree li { position: relative; }
        .tree li::before {
            content: ''; position: absolute; left: -14px; top: 0;
            border-left: 1px solid var(--border); height: 100%;
        }
        .tree li::after {
            content: ''; position: absolute; left: -14px; top: 12px;
            border-top: 1px solid var(--border); width: 10px;
        }
        .tree li:last-child::before { height: 12px; }
        .tree > ul > li::before, .tree > ul > li::after { display: none; }

        .node {
            cursor: pointer; padding: 4px 8px; border-radius: 4px;
            display: inline-block; transition: background 0.2s;
        }
        .node:hover { background: rgba(0, 85, 135, 0.08); }
        .node.selected { background: var(--c-peacock); color: white; }
        .node-name { font-weight: 700; color: var(--c-navy); }
        .node.selected .node-name { color: white; }
        .node-badge {
            font-size: 10px; padding: 2px 6px; border-radius: 3px;
            margin-left: 6px; background: var(--color-bg); color: var(--c-gray);
            font-weight: 700;
        }
        .node-badge.source { background: rgba(0, 150, 57, 0.15); color: var(--c-green); }
        .node-badge.owner { background: rgba(98, 18, 68, 0.15); color: #621244; }
        .node-badge.ui-link { background: rgba(0, 85, 135, 0.15); color: var(--c-peacock); cursor: pointer; text-decoration: none; }
        .node-badge.ui-link:hover { background: rgba(0, 85, 135, 0.25); text-decoration: none; }
        .node.selected .node-badge { background: rgba(255,255,255,0.2); color: white; }

        .toggle {
            display: inline-block; width: 16px; text-align: center;
            color: var(--c-gray); cursor: pointer; user-select: none;
        }
        .toggle:hover { color: var(--c-peacock); }
        .collapsed > ul { display: none; }
        .collapsed > .node .toggle { transform: rotate(-90deg); }

        /* Detail panel */
        .detail-section { margin-bottom: 16px; }
        .detail-section h3 {
            font-size: 11px;
            color: var(--c-navy);
            margin-bottom: 8px;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.5px;
        }
        .detail-row {
            font-size: 13px;
            padding: 6px 0;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
        }
        .detail-row span:first-child { color: var(--c-gray); }
        .detail-row span:last-child { color: var(--c-navy); font-weight: 700; }
        .path-display {
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 12px;
            background: var(--c-navy);
            color: white;
            padding: 10px 12px;
            border-radius: 4px;
            word-break: break-all;
            margin-bottom: 16px;
        }
        .empty { color: var(--c-gray); font-style: italic; }

        /* Links */
        a { color: var(--c-peacock); text-decoration: none; font-weight: 700; }
        a:hover { text-decoration: underline; }

        /* Loading */
        .loading { text-align: center; padding: 40px; color: var(--c-gray); }

        /* Search */
        .search-box {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border);
            position: relative;
        }
        .search-box input {
            width: 100%;
            padding: 8px 12px;
            border: 1px solid var(--border);
            border-radius: 4px;
            font-size: 14px;
            font-family: var(--font-sans);
        }
        .search-box input:focus {
            outline: none;
            border-color: var(--c-peacock);
            box-shadow: 0 0 0 3px rgba(0, 85, 135, 0.15);
        }
        .search-results {
            position: absolute;
            left: 16px;
            right: 16px;
            top: 100%;
            background: white;
            border: 1px solid var(--border);
            border-radius: 4px;
            max-height: 300px;
            overflow-y: auto;
            z-index: 100;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            display: none;
        }
        .search-result {
            padding: 10px 12px;
            cursor: pointer;
            border-bottom: 1px solid var(--border);
            font-size: 13px;
        }
        .search-result:last-child { border-bottom: none; }
        .search-result:hover { background: rgba(0, 85, 135, 0.08); }
        .search-result-path { font-weight: 700; color: var(--c-navy); }
        .search-result-match { font-size: 11px; color: var(--c-gray); margin-top: 2px; }

        /* Filter styles */
        .filtered-out { display: none !important; }
        .category-hidden { display: none !important; }
        .filter-match > .node .node-name { background: rgba(255, 209, 0, 0.3); padding: 0 4px; border-radius: 2px; }
        .filter-active-indicator {
            display: none;
            padding: 6px 12px;
            background: rgba(255, 209, 0, 0.15);
            border-bottom: 1px solid var(--border);
            font-size: 13px;
            color: var(--c-gray);
        }
        .filter-active-indicator.visible { display: flex; justify-content: space-between; align-items: center; }
        .filter-active-indicator button {
            background: none;
            border: 1px solid var(--border);
            padding: 2px 8px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        .filter-active-indicator button:hover { background: var(--color-bg); }

        /* Category filter chips */
        .category-bar {
            padding: 8px 12px;
            border-bottom: 1px solid var(--border);
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            background: var(--color-bg);
        }
        .category-chip {
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 700;
            cursor: pointer;
            border: 1px solid var(--border);
            background: white;
            color: var(--c-gray);
            transition: all 0.15s;
        }
        .category-chip:hover {
            border-color: var(--c-peacock);
            color: var(--c-peacock);
        }
        .category-chip.active {
            background: var(--c-peacock);
            border-color: var(--c-peacock);
            color: white;
        }
        .category-chip.all {
            background: var(--c-navy);
            border-color: var(--c-navy);
            color: white;
        }
        .category-chip.all:not(.active) {
            background: white;
            color: var(--c-navy);
            border-color: var(--c-navy);
        }
    </style>
    <script src="/static/shared.js"></script>
</head>
<body>
    <div class="header" style="display: flex; align-items: center; gap: 12px;">
        <a href="/" class="btn-small" title="Home" style="padding: 8px; background: rgba(255,255,255,0.15); display: flex;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
                <polyline points="9 22 9 12 15 12 15 22"></polyline>
            </svg>
        </a>
        <h1>Moniker Catalog</h1>
    </div>
    <div class="main">
        <div class="panel tree-panel">
            <div class="panel-header">
                <span>Catalog Tree</span>
                <div class="header-actions">
                    <button class="btn-small" onclick="expandAll()">Expand All</button>
                    <button class="btn-small" onclick="collapseAll()">Collapse All</button>
                </div>
            </div>
            <div id="category-bar" class="category-bar" style="display: none;">
                <!-- Categories populated by JS -->
            </div>
            <div class="search-box">
                <input type="text" id="search-input" placeholder="Search catalog... (Enter to filter)"
                       oninput="handleSearch(this.value)"
                       onkeydown="handleSearchKeydown(event)">
                <div id="search-results" class="search-results"></div>
            </div>
            <div id="filter-indicator" class="filter-active-indicator">
                <span>Filtered: <strong id="filter-term"></strong> (<span id="filter-count"></span> matches)</span>
                <button onclick="clearFilter()">Clear filter</button>
            </div>
            <div class="panel-content">
                <div id="tree" class="tree"><div class="loading">Loading...</div></div>
            </div>
        </div>
        <div class="panel detail-panel">
            <div class="panel-header">Node Details</div>
            <div class="panel-content">
                <div id="details"><p class="empty">Click a node to view details</p></div>
            </div>
        </div>
    </div>

    <script>
        let selectedNode = null;

        async function loadTree() {
            const res = await fetch('/tree');
            const data = await res.json();
            document.getElementById('tree').innerHTML = '<ul>' + data.map(renderNode).join('') + '</ul>';
        }

        function renderNode(node) {
            const hasChildren = node.children && node.children.length > 0;
            const badges = [];
            if (node.source_type) badges.push(`<span class="node-badge source">${node.source_type}</span>`);
            if (node.ownership?.accountable_owner) {
                const owner = node.ownership.accountable_owner.split('@')[0];
                badges.push(`<span class="node-badge owner">${owner}</span>`);
            }
            if (node.ownership?.ui) {
                badges.push(`<a href="${node.ownership.ui}" target="_blank" class="node-badge ui-link" onclick="event.stopPropagation()">UI</a>`);
            }

            return `
                <li data-path="${node.path}" data-node='${JSON.stringify(node).replace(/'/g, "&#39;")}'>
                    <span class="node" onclick="selectNode(this)">
                        ${hasChildren ? '<span class="toggle" onclick="toggleNode(event, this)">▼</span>' : '<span class="toggle"></span>'}
                        <span class="node-name">${node.name}/</span>
                        ${badges.join('')}
                    </span>
                    ${hasChildren ? '<ul>' + node.children.map(renderNode).join('') + '</ul>' : ''}
                </li>
            `;
        }

        function toggleNode(e, el) {
            e.stopPropagation();
            el.closest('li').classList.toggle('collapsed');
        }

        function selectNode(el) {
            if (selectedNode) selectedNode.classList.remove('selected');
            el.classList.add('selected');
            selectedNode = el;

            const li = el.closest('li');
            const node = JSON.parse(li.dataset.node);
            showDetails(node);
        }

        function showDetails(node) {
            const ownership = node.ownership || {};
            const html = `
                <div class="path-display">moniker://${node.path}</div>

                <div class="detail-section">
                    <h3>Basic Info</h3>
                    ${detailRow('Name', node.name)}
                    ${detailRow('Path', node.path)}
                    ${detailRow('Description', node.description || '-')}
                </div>

                <div class="detail-section">
                    <h3>Source</h3>
                    ${detailRow('Has Binding', node.has_source_binding ? 'Yes' : 'No')}
                    ${detailRow('Type', node.source_type || '-')}
                </div>

                <div class="detail-section">
                    <h3>Ownership</h3>
                    ${detailRow('Owner', ownership.accountable_owner || ownership.adop || '-')}
                    ${detailRow('Specialist', ownership.data_specialist || ownership.ads || '-')}
                    ${detailRow('Support', ownership.support_channel || '-')}
                </div>

                <div class="detail-section">
                    <h3>Governance Roles</h3>
                    ${detailRow('ADOP', ownership.adop || '-')}
                    ${detailRow('ADS', ownership.ads || '-')}
                    ${detailRow('ADAL', ownership.adal || '-')}
                </div>

                <div class="detail-section">
                    <h3>API</h3>
                    <div class="detail-row" style="border:none">
                        <a href="/describe/${node.path}" target="_blank">/describe/${node.path}</a>
                    </div>
                    ${node.has_source_binding ? `
                        <div class="detail-row" style="border:none">
                            <a href="/resolve/${node.path}" target="_blank">/resolve/${node.path}</a>
                        </div>
                        <div class="detail-row" style="border:none">
                            <a href="/metadata/${node.path}" target="_blank">/metadata/${node.path}</a>
                        </div>
                    ` : ''}
                </div>

                <div class="detail-section">
                    <h3>Quick Links</h3>
                    ${ownership.ui ? `
                        <div class="detail-row" style="border:none">
                            <a href="${ownership.ui}" target="_blank">🖥️ Open UI</a>
                        </div>
                    ` : ''}
                    ${ownership.adal ? `
                        <div class="detail-row" style="border:none">
                            <a href="${ownership.adal}" target="_blank">📋 ADAL Documentation</a>
                        </div>
                    ` : ''}
                    <div class="detail-row" style="border:none">
                        <a href="/config/ui#${node.path}" target="_blank">⚙️ Edit in Config</a>
                    </div>
                </div>
            `;
            document.getElementById('details').innerHTML = html;
        }

        function detailRow(label, value) {
            return `<div class="detail-row"><span>${label}</span><span>${value}</span></div>`;
        }

        function expandAll() {
            document.querySelectorAll('.tree li.collapsed').forEach(el => el.classList.remove('collapsed'));
        }

        function collapseAll() {
            document.querySelectorAll('.tree li').forEach(el => {
                if (el.querySelector('ul')) el.classList.add('collapsed');
            });
        }

        // Search functionality
        let searchTimeout = null;

        async function handleSearch(query) {
            const resultsDiv = document.getElementById('search-results');
            const inputEl = document.getElementById('search-input');

            if (searchTimeout) clearTimeout(searchTimeout);

            if (!query || query.length < 2) {
                resultsDiv.style.display = 'none';
                return;
            }

            searchTimeout = setTimeout(async () => {
                try {
                    const res = await fetch('/config/search?q=' + encodeURIComponent(query));
                    const data = await res.json();

                    if (data.results && data.results.length > 0) {
                        resultsDiv.innerHTML = data.results.map(r => `
                            <div class="search-result" onclick="selectSearchResult('${r.path.replace(/'/g, "\\\\'")}')">
                                <div class="search-result-path">${r.path}</div>
                                <div class="search-result-match">Match: ${r.match}${r.display_name ? ' • ' + r.display_name : ''}</div>
                            </div>
                        `).join('');
                        resultsDiv.style.display = 'block';
                    } else {
                        resultsDiv.innerHTML = '<div class="search-result" style="color: var(--c-gray);">No results found</div>';
                        resultsDiv.style.display = 'block';
                    }
                } catch (e) {
                    console.error('Search failed:', e);
                    resultsDiv.style.display = 'none';
                }
            }, 200);
        }

        function selectSearchResult(path) {
            document.getElementById('search-input').value = '';
            document.getElementById('search-results').style.display = 'none';
            expandToPath(path);
            // Find and select the node
            const li = document.querySelector(`li[data-path="${path}"]`);
            if (li) {
                const nodeEl = li.querySelector('.node');
                if (nodeEl) selectNode(nodeEl);
            }
        }

        function expandToPath(path) {
            const parts = path.split('/');
            let currentPath = '';
            for (let i = 0; i < parts.length; i++) {
                currentPath = parts.slice(0, i + 1).join('/');
                const li = document.querySelector(`li[data-path="${currentPath}"]`);
                if (li) li.classList.remove('collapsed');
            }
        }

        // Close search results when clicking outside
        document.addEventListener('click', (e) => {
            const searchBox = document.querySelector('.search-box');
            if (searchBox && !searchBox.contains(e.target)) {
                document.getElementById('search-results').style.display = 'none';
            }
        });

        // Filter functionality (Enter key)
        function handleSearchKeydown(e) {
            if (e.key === 'Enter') {
                const query = e.target.value.trim();
                if (query.length >= 2) {
                    filterTree(query);
                    document.getElementById('search-results').style.display = 'none';
                }
            } else if (e.key === 'Escape') {
                clearFilter();
                e.target.value = '';
                document.getElementById('search-results').style.display = 'none';
            }
        }

        function filterTree(query) {
            const queryLower = query.toLowerCase();
            const allNodes = document.querySelectorAll('.tree li');
            let matchCount = 0;

            // First pass: mark all as filtered out, find matches
            allNodes.forEach(li => {
                li.classList.add('filtered-out');
                li.classList.remove('filter-match');

                const node = JSON.parse(li.dataset.node);
                const searchText = [
                    node.path,
                    node.name,
                    node.description || '',
                    node.display_name || '',
                    (node.tags || []).join(' ')
                ].join(' ').toLowerCase();

                if (searchText.includes(queryLower)) {
                    li.classList.add('filter-match');
                    matchCount++;
                }
            });

            // Second pass: show matches and their ancestors
            document.querySelectorAll('.tree li.filter-match').forEach(li => {
                // Show this node
                li.classList.remove('filtered-out');
                li.classList.remove('collapsed');

                // Show all ancestors
                let parent = li.parentElement;
                while (parent) {
                    if (parent.tagName === 'LI') {
                        parent.classList.remove('filtered-out');
                        parent.classList.remove('collapsed');
                    }
                    parent = parent.parentElement;
                }

                // Also show direct children (one level down)
                li.querySelectorAll(':scope > ul > li').forEach(child => {
                    child.classList.remove('filtered-out');
                });
            });

            // Show filter indicator
            document.getElementById('filter-term').textContent = query;
            document.getElementById('filter-count').textContent = matchCount;
            document.getElementById('filter-indicator').classList.add('visible');
        }

        function clearFilter() {
            document.querySelectorAll('.tree li').forEach(li => {
                li.classList.remove('filtered-out');
                li.classList.remove('filter-match');
            });
            document.getElementById('filter-indicator').classList.remove('visible');
            document.getElementById('search-input').value = '';
        }

        // Category filtering
        let domainData = {};  // domain name -> {category, ...}
        let activeCategory = null;

        async function loadCategories() {
            try {
                const res = await fetch('/domains');
                const data = await res.json();
                if (!data.domains || data.domains.length === 0) return;

                // Build domain lookup
                data.domains.forEach(d => {
                    domainData[d.name] = d;
                });

                // Build category map using shared utility
                const categories = MonikerUtils.buildCategoryMap(data.domains);

                // Render category chips if we have multiple categories
                if (categories.size > 1) {
                    const bar = document.getElementById('category-bar');
                    bar.innerHTML = MonikerUtils.renderCategoryChips(categories);
                    bar.style.display = 'flex';
                }
            } catch (e) {
                console.error('Failed to load categories:', e);
            }
        }

        function filterByCategory(category) {
            activeCategory = category;

            // Update chip styles using shared utility
            MonikerUtils.updateCategoryChipStyles(category);

            // Get domains in this category using shared utility
            const allowedDomains = category
                ? MonikerUtils.getDomainsInCategory(Object.values(domainData), category)
                : null;

            // Filter tree nodes
            const allNodes = document.querySelectorAll('.tree li');
            allNodes.forEach(li => {
                const node = JSON.parse(li.dataset.node);
                li.classList.remove('category-hidden');

                if (allowedDomains !== null) {
                    // Get domain using shared utility
                    const nodeDomain = MonikerUtils.getDomain(node, node.path);
                    if (!allowedDomains.has(nodeDomain)) {
                        li.classList.add('category-hidden');
                    }
                }
            });

            // Show parents of visible nodes
            document.querySelectorAll('.tree li:not(.category-hidden)').forEach(li => {
                let parent = li.parentElement;
                while (parent) {
                    if (parent.tagName === 'LI') {
                        parent.classList.remove('category-hidden');
                    }
                    parent = parent.parentElement;
                }
            });
        }

        loadTree();
        loadCategories();
    </script>
</body>
</html>
"""


@app.get("/ui", response_class=HTMLResponse, tags=["Catalog"])
async def ui():
    """Simple web UI for browsing the moniker catalog."""
    return _UI_HTML


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
