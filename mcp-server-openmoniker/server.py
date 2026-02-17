"""
MCP Server for Open Moniker — exposes the moniker catalog, domains,
models, and request workflow over the Model Context Protocol.

Transport: Streamable HTTP (network-accessible)
Auth:      Reads are anonymous.
           Submissions require MCP_SUBMIT_TOKEN.
           Approvals/rejections require MCP_APPROVE_TOKEN.
           Legacy MCP_WRITE_TOKEN grants both if the split tokens are unset.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import TextContent

# ---------------------------------------------------------------------------
# Path setup — import moniker_svc from the parent repo's src/
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
_EXTERNAL_DATA = _REPO_ROOT / "external" / "moniker-data" / "src"
for p in (_SRC, _EXTERNAL_DATA):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from moniker_svc.cache.memory import InMemoryCache
from moniker_svc.catalog.loader import load_catalog
from moniker_svc.catalog.registry import CatalogRegistry
from moniker_svc.catalog.types import NodeStatus
from moniker_svc.config import Config
from moniker_svc.domains import DomainRegistry, load_domains_from_yaml
from moniker_svc.models import ModelRegistry, load_models_from_yaml
from moniker_svc.moniker.parser import MonikerParseError
from moniker_svc.requests import RequestRegistry, load_requests_from_yaml
from moniker_svc.service import (
    AccessDeniedError,
    MonikerService,
    NotFoundError,
)
from moniker_svc.telemetry.emitter import TelemetryEmitter
from moniker_svc.telemetry.events import CallerIdentity

logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger("mcp-openmoniker")
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MCP_PORT = int(os.environ.get("MCP_PORT", "8051"))
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")

# Auth tokens — split by privilege level.
# MCP_SUBMIT_TOKEN  → submit_request, list_requests
# MCP_APPROVE_TOKEN → approve_request, reject_request, update_node_status
# MCP_WRITE_TOKEN   → legacy fallback, grants both if split tokens are unset.
SUBMIT_TOKEN = os.environ.get("MCP_SUBMIT_TOKEN", "")
APPROVE_TOKEN = os.environ.get("MCP_APPROVE_TOKEN", "")
WRITE_TOKEN = os.environ.get("MCP_WRITE_TOKEN", "")

# Paths to YAML configs (relative to repo root)
CATALOG_YAML = os.environ.get("CATALOG_YAML", str(_REPO_ROOT / "catalog.yaml"))
DOMAINS_YAML = os.environ.get("DOMAINS_YAML", str(_REPO_ROOT / "domains.yaml"))
MODELS_YAML = os.environ.get("MODELS_YAML", str(_REPO_ROOT / "models.yaml"))
CONFIG_YAML = os.environ.get("CONFIG_YAML", str(_REPO_ROOT / "config.yaml"))
REQUESTS_YAML = os.environ.get("REQUESTS_YAML", "")


# ---------------------------------------------------------------------------
# Shared state — populated during lifespan
# ---------------------------------------------------------------------------

@dataclass
class AppState:
    catalog: CatalogRegistry
    domain_registry: DomainRegistry
    model_registry: ModelRegistry
    request_registry: RequestRegistry
    service: MonikerService
    config: Config
    submit_token: str
    approve_token: str


_state: AppState | None = None


def _require_state() -> AppState:
    if _state is None:
        raise RuntimeError("Server not yet initialised")
    return _state


def _check_submit_token(token: str) -> bool:
    """Constant-time check for submission privilege."""
    s = _require_state()
    return secrets.compare_digest(token, s.submit_token)


def _check_approve_token(token: str) -> bool:
    """Constant-time check for approval privilege."""
    s = _require_state()
    return secrets.compare_digest(token, s.approve_token)


# ---------------------------------------------------------------------------
# Lifespan — load catalog, domains, models once on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(server: FastMCP):
    global _state, SUBMIT_TOKEN, APPROVE_TOKEN, WRITE_TOKEN

    # Resolve tokens: explicit split tokens take priority, then legacy
    # fallback, then auto-generate.
    if not SUBMIT_TOKEN:
        SUBMIT_TOKEN = WRITE_TOKEN or secrets.token_urlsafe(32)
    if not APPROVE_TOKEN:
        APPROVE_TOKEN = WRITE_TOKEN or secrets.token_urlsafe(32)

    if SUBMIT_TOKEN == APPROVE_TOKEN:
        logger.warning("Submit and approve tokens are the same — set MCP_SUBMIT_TOKEN "
                        "and MCP_APPROVE_TOKEN separately for separation of duties")
    logger.info("Submit token (MCP_SUBMIT_TOKEN):   %s…", SUBMIT_TOKEN[:8])
    logger.info("Approve token (MCP_APPROVE_TOKEN): %s…", APPROVE_TOKEN[:8])

    # Validate required config files exist
    _required = {"CATALOG_YAML": CATALOG_YAML, "DOMAINS_YAML": DOMAINS_YAML,
                  "MODELS_YAML": MODELS_YAML, "CONFIG_YAML": CONFIG_YAML}
    _missing = {k: v for k, v in _required.items() if not Path(v).exists()}
    if _missing:
        for env_var, path in _missing.items():
            sample = path.replace(".yaml", "").rsplit("/", 1)
            sample_path = path.replace(".yaml", "").rsplit("/", 1)[0] + "/sample_" + Path(path).name
            logger.error(f"Required config not found: {path}")
            logger.error(f"  Copy from sample:  cp {sample_path} {path}")
            logger.error(f"  Or set env var:    {env_var}=/path/to/your/file.yaml")
        raise SystemExit(
            "Missing config files. Copy from sample_* files or run the config script. "
            "See errors above for details."
        )

    # Load config
    config = Config.from_yaml(CONFIG_YAML)

    # Load catalog
    catalog = load_catalog(CATALOG_YAML)
    logger.info(f"Loaded catalog: {len(catalog.all_paths())} paths from {CATALOG_YAML}")

    # Load domains
    domain_registry = DomainRegistry()
    domains_list = load_domains_from_yaml(DOMAINS_YAML, domain_registry)
    logger.info(f"Loaded domains: {domain_registry.count()} from {DOMAINS_YAML}")

    # Load models
    model_registry = ModelRegistry()
    load_models_from_yaml(MODELS_YAML, model_registry)
    logger.info(f"Loaded models: {model_registry.count()} from {MODELS_YAML}")

    # Load requests (if file exists)
    request_registry = RequestRegistry()
    if REQUESTS_YAML and Path(REQUESTS_YAML).exists():
        load_requests_from_yaml(REQUESTS_YAML, request_registry)

    # Build service
    telemetry = TelemetryEmitter()
    cache = InMemoryCache(max_size=config.cache.max_size, default_ttl_seconds=config.cache.default_ttl_seconds)
    service = MonikerService(
        catalog=catalog,
        cache=cache,
        telemetry=telemetry,
        config=config,
        domain_registry=domain_registry,
    )

    _state = AppState(
        catalog=catalog,
        domain_registry=domain_registry,
        model_registry=model_registry,
        request_registry=request_registry,
        service=service,
        config=config,
        submit_token=SUBMIT_TOKEN,
        approve_token=APPROVE_TOKEN,
    )

    logger.info(f"MCP Open Moniker server ready on {MCP_HOST}:{MCP_PORT}")
    yield
    logger.info("MCP Open Moniker server shutting down")


# ---------------------------------------------------------------------------
# Create the FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="open-moniker",
    instructions=(
        "Open Moniker MCP Server — a unified data catalog and governance layer. "
        "Use the tools below to resolve monikers to source connection info, "
        "browse the catalog hierarchy, search for data assets, inspect ownership "
        "lineage, and manage moniker creation requests. "
        "Read operations are anonymous. Submissions require a submit token "
        "(MCP_SUBMIT_TOKEN). Approvals, rejections, and status changes require "
        "a separate approve token (MCP_APPROVE_TOKEN)."
    ),
    host=MCP_HOST,
    port=MCP_PORT,
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Helper: anonymous caller identity for read tools
# ---------------------------------------------------------------------------

_MCP_CALLER = CallerIdentity(
    service_id="mcp-server",
    user_id=None,
    app_id="mcp-openmoniker",
    team=None,
    claims={},
)


def _node_to_dict(node) -> dict[str, Any]:
    """Serialise a CatalogNode to a JSON-friendly dict."""
    d: dict[str, Any] = {
        "path": node.path,
        "display_name": node.display_name,
        "description": node.description,
        "status": node.status.value if hasattr(node.status, "value") else str(node.status),
        "is_leaf": node.is_leaf,
    }
    if node.ownership:
        d["ownership"] = {}
        for attr in ("accountable_owner", "data_specialist", "support_channel", "adop", "ads", "adal"):
            v = getattr(node.ownership, attr, None)
            if v:
                d["ownership"][attr] = v
    if node.source_binding:
        d["source_type"] = node.source_binding.source_type.value
    if node.classification:
        d["classification"] = node.classification
    if node.tags:
        d["tags"] = list(node.tags)
    if node.successor:
        d["successor"] = node.successor
    if node.deprecation_message:
        d["deprecation_message"] = node.deprecation_message
    return d


def _ownership_to_dict(ownership) -> dict[str, Any]:
    """Serialise ResolvedOwnership to dict."""
    d: dict[str, Any] = {}
    for attr in (
        "accountable_owner", "accountable_owner_source",
        "data_specialist", "data_specialist_source",
        "support_channel", "support_channel_source",
        "adop", "adop_source", "ads", "ads_source", "adal", "adal_source",
    ):
        v = getattr(ownership, attr, None)
        if v:
            d[attr] = v
    return d


# ===================================================================
# READ TOOLS  (anonymous)
# ===================================================================

@mcp.tool(
    name="resolve_moniker",
    description=(
        "Resolve a moniker path to source connection info. "
        "Returns source_type, connection parameters, query, ownership, "
        "and binding metadata.  Example: resolve_moniker('risk.cvar/758-A/USD/ALL')"
    ),
)
async def resolve_moniker(moniker: str) -> str:
    """Resolve a moniker to its source connection info."""
    s = _require_state()
    try:
        result = await s.service.resolve(moniker, _MCP_CALLER)
        return json.dumps({
            "moniker": result.moniker,
            "path": result.path,
            "source_type": result.source.source_type,
            "connection": result.source.connection,
            "query": result.source.query,
            "params": result.source.params,
            "read_only": result.source.read_only,
            "ownership": _ownership_to_dict(result.ownership),
            "binding_path": result.binding_path,
            "sub_path": result.sub_path,
            "redirected_from": result.redirected_from,
        }, indent=2)
    except NotFoundError as e:
        return json.dumps({"error": "not_found", "message": str(e)})
    except AccessDeniedError as e:
        return json.dumps({"error": "access_denied", "message": str(e), "estimated_rows": e.estimated_rows})
    except MonikerParseError as e:
        return json.dumps({"error": "parse_error", "message": str(e)})


@mcp.tool(
    name="list_children",
    description=(
        "List the direct children of a moniker path in the catalog. "
        "Example: list_children('risk') → ['cvar', 'greeks', 'limits', ...]"
    ),
)
async def list_children(path: str) -> str:
    """List children of a catalog path."""
    s = _require_state()
    try:
        result = await s.service.list_children(path, _MCP_CALLER)
        return json.dumps({
            "path": result.path,
            "children": result.children,
            "count": len(result.children),
        }, indent=2)
    except MonikerParseError as e:
        return json.dumps({"error": "parse_error", "message": str(e)})


@mcp.tool(
    name="describe_moniker",
    description=(
        "Get metadata for a moniker path: display name, description, ownership, "
        "source type, data quality, schema, documentation links, and related models. "
        "Example: describe_moniker('fixed_income/govies/treasury')"
    ),
)
async def describe_moniker(path: str) -> str:
    """Describe a moniker path's metadata."""
    s = _require_state()
    try:
        result = await s.service.describe(path, _MCP_CALLER)
        d: dict[str, Any] = {
            "path": result.path,
            "has_source_binding": result.has_source_binding,
            "source_type": result.source_type,
            "ownership": _ownership_to_dict(result.ownership),
        }
        if result.node:
            d["display_name"] = result.node.display_name
            d["description"] = result.node.description
            d["status"] = result.node.status.value if hasattr(result.node.status, "value") else str(result.node.status)
            if result.node.classification:
                d["classification"] = result.node.classification
            if result.node.tags:
                d["tags"] = list(result.node.tags)
            if result.node.data_quality:
                dq = result.node.data_quality
                d["data_quality"] = {
                    "dq_owner": dq.dq_owner,
                    "quality_score": dq.quality_score,
                    "known_issues": list(dq.known_issues) if dq.known_issues else [],
                }
            if result.node.schema:
                d["schema"] = {
                    "columns": [
                        {"name": c.name, "type": c.type, "description": c.description, "semantic_type": c.semantic_type}
                        for c in result.node.schema.columns
                    ] if result.node.schema.columns else [],
                    "semantic_tags": list(result.node.schema.semantic_tags) if result.node.schema.semantic_tags else [],
                }
            if result.node.documentation:
                doc = result.node.documentation
                d["documentation"] = {}
                for attr in ("glossary", "runbook", "data_dictionary", "onboarding"):
                    v = getattr(doc, attr, None)
                    if v:
                        d["documentation"][attr] = v
            if result.node.successor:
                d["successor"] = result.node.successor
            if result.node.deprecation_message:
                d["deprecation_message"] = result.node.deprecation_message
        # Models that appear in this moniker
        models = s.model_registry.models_for_moniker(result.path)
        if models:
            d["models"] = [
                {"path": m.path, "display_name": m.display_name, "unit": m.unit, "formula": m.formula}
                for m in models
            ]
        return json.dumps(d, indent=2)
    except MonikerParseError as e:
        return json.dumps({"error": "parse_error", "message": str(e)})


@mcp.tool(
    name="search_catalog",
    description=(
        "Full-text search across the catalog by path, display name, description, "
        "or tags.  Returns up to `limit` matching nodes. "
        "Example: search_catalog('treasury') or search_catalog('credit risk')"
    ),
)
async def search_catalog(query: str, limit: int = 20) -> str:
    """Search catalog nodes."""
    s = _require_state()
    results = s.catalog.search(query, limit=limit)
    return json.dumps({
        "query": query,
        "results": [_node_to_dict(n) for n in results],
        "count": len(results),
    }, indent=2)


@mcp.tool(
    name="get_lineage",
    description=(
        "Get the ownership lineage for a moniker path — shows the full path "
        "hierarchy and where each ownership field was defined. "
        "Example: get_lineage('risk.cvar')"
    ),
)
async def get_lineage(path: str) -> str:
    """Get ownership lineage for a path."""
    s = _require_state()
    try:
        result = await s.service.lineage(path, _MCP_CALLER)
        return json.dumps(result, indent=2)
    except MonikerParseError as e:
        return json.dumps({"error": "parse_error", "message": str(e)})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool(
    name="get_catalog_tree",
    description=(
        "Get the catalog as a tree rooted at an optional path. "
        "Returns nested children for browsing.  Call with no args for the "
        "full top-level tree, or pass a path to get a subtree."
    ),
)
async def get_catalog_tree(root_path: str = "") -> str:
    """Get catalog tree from a given root."""
    s = _require_state()

    def _build_tree(path: str) -> list[dict[str, Any]]:
        children_paths = s.catalog.children_paths(path)
        nodes = []
        for cp in sorted(children_paths):
            node = s.catalog.get(cp)
            if not node:
                continue
            entry: dict[str, Any] = {
                "path": cp,
                "name": cp.split("/")[-1].split(".")[-1],
                "display_name": node.display_name,
                "is_leaf": node.is_leaf,
            }
            if node.source_binding:
                entry["source_type"] = node.source_binding.source_type.value
            sub = _build_tree(cp)
            if sub:
                entry["children"] = sub
            nodes.append(entry)
        return nodes

    tree = _build_tree(root_path)
    return json.dumps({"root": root_path or "(top)", "tree": tree, "count": len(tree)}, indent=2)


@mcp.tool(
    name="get_catalog_stats",
    description="Get summary statistics for the catalog: total monikers, counts by status and source type.",
)
async def get_catalog_stats() -> str:
    """Get catalog statistics."""
    s = _require_state()
    counts = s.catalog.count()
    # Source type breakdown
    source_types: dict[str, int] = {}
    for node in s.catalog.all_nodes():
        if node.source_binding:
            st = node.source_binding.source_type.value
            source_types[st] = source_types.get(st, 0) + 1
    return json.dumps({
        "status_counts": counts,
        "source_type_counts": source_types,
        "domain_count": s.domain_registry.count(),
        "model_count": s.model_registry.count(),
    }, indent=2)


@mcp.tool(
    name="get_domains",
    description="List all data domains with their metadata (owner, category, confidentiality, etc.).",
)
async def get_domains() -> str:
    """List all domains."""
    s = _require_state()
    domains = s.domain_registry.all_domains()
    return json.dumps({
        "domains": [
            {
                "name": d.name,
                "display_name": d.display_name,
                "short_code": d.short_code,
                "data_category": d.data_category,
                "owner": d.owner,
                "tech_custodian": d.tech_custodian,
                "confidentiality": d.confidentiality,
                "help_channel": d.help_channel,
            }
            for d in domains
        ],
        "count": len(domains),
    }, indent=2)


@mcp.tool(
    name="get_models",
    description=(
        "List all business models/measures registered in the catalog. "
        "Each model describes a metric (like DV01, Alpha, Sharpe) that can "
        "appear across multiple monikers."
    ),
)
async def get_models() -> str:
    """List all business models."""
    s = _require_state()
    models = s.model_registry.all_models()
    return json.dumps({
        "models": [
            {
                "path": m.path,
                "display_name": m.display_name,
                "description": m.description,
                "formula": m.formula,
                "unit": m.unit,
                "semantic_tags": list(m.semantic_tags),
            }
            for m in models
        ],
        "count": len(models),
    }, indent=2)


@mcp.tool(
    name="get_model_detail",
    description=(
        "Get full details for a specific business model, including formula, "
        "ownership, and the moniker patterns where it appears. "
        "Example: get_model_detail('risk.analytics/dv01')"
    ),
)
async def get_model_detail(model_path: str) -> str:
    """Get a single model's details."""
    s = _require_state()
    model = s.model_registry.get(model_path)
    if model is None:
        return json.dumps({"error": "not_found", "message": f"Model not found: {model_path}"})
    return json.dumps({
        "path": model.path,
        "display_name": model.display_name,
        "description": model.description,
        "formula": model.formula,
        "unit": model.unit,
        "data_type": model.data_type,
        "ownership": {
            "methodology_owner": model.ownership.methodology_owner if model.ownership else None,
            "business_steward": model.ownership.business_steward if model.ownership else None,
        },
        "documentation_url": model.documentation_url,
        "appears_in": [
            {"moniker_pattern": link.moniker_pattern, "column_name": link.column_name, "notes": link.notes}
            for link in model.appears_in
        ],
        "semantic_tags": list(model.semantic_tags),
    }, indent=2)


# ===================================================================
# WRITE TOOLS  (require bearer token)
# ===================================================================

def _submit_auth_error() -> str:
    return json.dumps({"error": "unauthorized", "message": "Invalid or missing submit token. Pass the value of MCP_SUBMIT_TOKEN."})


def _approve_auth_error() -> str:
    return json.dumps({"error": "unauthorized", "message": "Invalid or missing approve token. Pass the value of MCP_APPROVE_TOKEN."})


@mcp.tool(
    name="submit_request",
    description=(
        "Submit a new moniker creation request for governance review.  "
        "REQUIRES a valid submit token (MCP_SUBMIT_TOKEN).  Provide the moniker path, "
        "display name, description, justification, and optionally proposed ownership "
        "and source binding."
    ),
)
async def submit_request(
    token: str,
    path: str,
    display_name: str,
    description: str,
    justification: str,
    requester_name: str = "mcp-user",
    requester_email: str = "",
    adop: str | None = None,
    ads: str | None = None,
    adal: str | None = None,
    source_binding_type: str | None = None,
    tags: str = "",
) -> str:
    """Submit a moniker creation request."""
    if not _check_submit_token(token):
        return _submit_auth_error()

    s = _require_state()

    # Check duplicate in catalog
    clean_path = path.strip().strip("/")
    if s.catalog.exists(clean_path):
        return json.dumps({"error": "conflict", "message": f"Path already exists in catalog: {clean_path}"})
    if s.request_registry.path_has_pending_request(clean_path):
        return json.dumps({"error": "conflict", "message": f"Pending request already exists for: {clean_path}"})

    from moniker_svc.catalog.types import CatalogNode, Ownership
    from moniker_svc.requests.types import DomainLevel, MonikerRequest, RequestStatus, RequesterInfo

    segments = clean_path.split("/")
    top_level = segments[0].split(".")[0] if "." in segments[0] else segments[0]

    if len(segments) == 1 and "." not in clean_path:
        domain_level = DomainLevel.TOP_LEVEL
    else:
        domain_level = DomainLevel.SUB_PATH
        if not s.catalog.exists(segments[0]):
            return json.dumps({"error": "bad_request", "message": f"Top-level domain '{segments[0]}' does not exist."})

    ownership = Ownership(adop=adop, ads=ads, adal=adal)
    node = CatalogNode(
        path=clean_path,
        display_name=display_name,
        description=description,
        ownership=ownership,
        tags=frozenset(t.strip() for t in tags.split(",") if t.strip()),
        status=NodeStatus.PENDING_REVIEW,
    )
    s.catalog.register(node)

    requester = RequesterInfo(name=requester_name, email=requester_email)
    request = MonikerRequest(
        request_id="",
        path=clean_path,
        display_name=display_name,
        description=description,
        requester=requester,
        justification=justification,
        adop=adop,
        ads=ads,
        adal=adal,
        source_binding_type=source_binding_type,
        source_binding_config={},
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        status=RequestStatus.PENDING_REVIEW,
        domain_level=domain_level,
    )

    request = s.request_registry.submit(request)
    return json.dumps({
        "request_id": request.request_id,
        "path": request.path,
        "status": request.status.value,
        "message": "Request submitted for governance review",
    }, indent=2)


@mcp.tool(
    name="list_requests",
    description=(
        "List moniker creation/approval requests, optionally filtered by status.  "
        "Statuses: pending_review, approved, rejected, active"
    ),
)
async def list_requests_tool(status: str | None = None) -> str:
    """List moniker requests."""
    s = _require_state()
    from moniker_svc.requests.types import RequestStatus

    if status:
        try:
            filter_status = RequestStatus(status)
            requests = s.request_registry.find_by_status(filter_status)
        except ValueError:
            return json.dumps({"error": "bad_request", "message": f"Invalid status: {status}"})
    else:
        requests = s.request_registry.all_requests()

    return json.dumps({
        "requests": [
            {
                "request_id": r.request_id,
                "path": r.path,
                "display_name": r.display_name,
                "status": r.status.value,
                "requester": r.requester.name if r.requester else None,
                "justification": r.justification,
                "created_at": r.created_at,
            }
            for r in requests
        ],
        "count": len(requests),
        "by_status": s.request_registry.count_by_status(),
    }, indent=2)


@mcp.tool(
    name="approve_request",
    description=(
        "Approve a pending moniker request and activate it in the catalog.  "
        "REQUIRES a valid approve token (MCP_APPROVE_TOKEN)."
    ),
)
async def approve_request(token: str, request_id: str, actor: str = "mcp-admin", reason: str = "Approved via MCP") -> str:
    """Approve a moniker request."""
    if not _check_approve_token(token):
        return _approve_auth_error()

    s = _require_state()
    from datetime import datetime, timezone
    from moniker_svc.catalog.types import AuditEntry
    from moniker_svc.requests.types import RequestStatus, ReviewComment

    request = s.request_registry.get(request_id)
    if request is None:
        return json.dumps({"error": "not_found", "message": f"Request not found: {request_id}"})
    if request.status != RequestStatus.PENDING_REVIEW:
        return json.dumps({"error": "bad_request", "message": f"Request is not pending (status: {request.status.value})"})

    now = datetime.now(timezone.utc).isoformat()

    s.request_registry.update_status(request_id, RequestStatus.APPROVED, actor=actor)
    s.request_registry.add_comment(request_id, ReviewComment(
        timestamp=now, author=actor, content=reason, action="approve",
    ))
    s.catalog.update_status(request.path, NodeStatus.ACTIVE, actor=actor)
    s.catalog.add_audit_entry(AuditEntry(
        timestamp=now, path=request.path, action="request_approved", actor=actor,
        details=f"Request {request_id} approved via MCP",
    ))

    return json.dumps({
        "request_id": request_id,
        "path": request.path,
        "status": "approved",
        "message": f"Request approved and moniker '{request.path}' activated",
    }, indent=2)


@mcp.tool(
    name="reject_request",
    description=(
        "Reject a pending moniker request.  "
        "REQUIRES a valid approve token (MCP_APPROVE_TOKEN)."
    ),
)
async def reject_request(token: str, request_id: str, actor: str = "mcp-admin", reason: str = "Rejected via MCP") -> str:
    """Reject a moniker request."""
    if not _check_approve_token(token):
        return _approve_auth_error()

    s = _require_state()
    from datetime import datetime, timezone
    from moniker_svc.catalog.types import AuditEntry
    from moniker_svc.requests.types import RequestStatus, ReviewComment

    request = s.request_registry.get(request_id)
    if request is None:
        return json.dumps({"error": "not_found", "message": f"Request not found: {request_id}"})
    if request.status != RequestStatus.PENDING_REVIEW:
        return json.dumps({"error": "bad_request", "message": f"Request is not pending (status: {request.status.value})"})

    now = datetime.now(timezone.utc).isoformat()

    s.request_registry.update_status(request_id, RequestStatus.REJECTED, actor=actor, reason=reason)
    s.request_registry.add_comment(request_id, ReviewComment(
        timestamp=now, author=actor, content=reason, action="reject",
    ))
    s.catalog.update_status(request.path, NodeStatus.DRAFT, actor=actor)
    s.catalog.add_audit_entry(AuditEntry(
        timestamp=now, path=request.path, action="request_rejected", actor=actor,
        details=f"Request {request_id} rejected via MCP: {reason}",
    ))

    return json.dumps({
        "request_id": request_id,
        "path": request.path,
        "status": "rejected",
        "reason": reason,
    }, indent=2)


@mcp.tool(
    name="update_node_status",
    description=(
        "Update the lifecycle status of a catalog node.  "
        "Valid statuses: draft, pending_review, approved, active, deprecated, archived. "
        "REQUIRES a valid approve token (MCP_APPROVE_TOKEN)."
    ),
)
async def update_node_status(token: str, path: str, new_status: str, actor: str = "mcp-admin") -> str:
    """Update a catalog node's status."""
    if not _check_approve_token(token):
        return _approve_auth_error()

    s = _require_state()
    try:
        status_enum = NodeStatus(new_status)
    except ValueError:
        valid = [st.value for st in NodeStatus]
        return json.dumps({"error": "bad_request", "message": f"Invalid status '{new_status}'. Valid: {valid}"})

    node = s.catalog.update_status(path, status_enum, actor=actor)
    if node is None:
        return json.dumps({"error": "not_found", "message": f"Path not found: {path}"})

    return json.dumps({
        "path": path,
        "new_status": new_status,
        "message": f"Status updated to '{new_status}'",
    }, indent=2)


# ===================================================================
# RESOURCES  (browseable data for MCP clients)
# ===================================================================

@mcp.resource(
    "moniker://catalog",
    name="catalog_overview",
    description="Overview of all catalog paths with status counts",
    mime_type="application/json",
)
async def catalog_overview() -> str:
    s = _require_state()
    paths = sorted(s.catalog.all_paths())
    counts = s.catalog.count()
    return json.dumps({"paths": paths, "counts": counts}, indent=2)


@mcp.resource(
    "moniker://catalog/{path}",
    name="catalog_node",
    description="Detailed info for a specific catalog node",
    mime_type="application/json",
)
async def catalog_node(path: str) -> str:
    s = _require_state()
    node = s.catalog.get(path)
    if node is None:
        return json.dumps({"error": "not_found", "path": path})
    d = _node_to_dict(node)
    # Add children
    children = s.catalog.children_paths(path)
    if children:
        d["children"] = sorted(children)
    # Add ownership lineage
    ownership = s.catalog.resolve_ownership(path, s.domain_registry)
    d["resolved_ownership"] = _ownership_to_dict(ownership)
    return json.dumps(d, indent=2)


@mcp.resource(
    "moniker://domains",
    name="domains_list",
    description="All registered data domains",
    mime_type="application/json",
)
async def domains_list() -> str:
    s = _require_state()
    domains = s.domain_registry.all_domains()
    return json.dumps({
        "domains": [
            {
                "name": d.name,
                "display_name": d.display_name,
                "short_code": d.short_code,
                "data_category": d.data_category,
                "color": d.color,
                "owner": d.owner,
                "tech_custodian": d.tech_custodian,
                "business_steward": d.business_steward,
                "confidentiality": d.confidentiality,
                "pii": d.pii,
                "help_channel": d.help_channel,
                "wiki_link": d.wiki_link,
                "notes": d.notes,
            }
            for d in domains
        ],
    }, indent=2)


@mcp.resource(
    "moniker://models",
    name="models_list",
    description="All registered business models/measures",
    mime_type="application/json",
)
async def models_list() -> str:
    s = _require_state()
    models = s.model_registry.all_models()
    return json.dumps({
        "models": [
            {
                "path": m.path,
                "display_name": m.display_name,
                "description": m.description,
                "formula": m.formula,
                "unit": m.unit,
                "semantic_tags": list(m.semantic_tags),
                "appears_in_count": len(m.appears_in),
            }
            for m in models
        ],
    }, indent=2)


# ===================================================================
# PROMPTS  (reusable conversation templates)
# ===================================================================

@mcp.prompt(
    name="explore_domain",
    description="Walk through a data domain — lists its monikers, ownership, and source types.",
)
async def explore_domain_prompt(domain_name: str) -> str:
    return (
        f"I'd like to explore the **{domain_name}** data domain.\n\n"
        f"1. First, call `get_domains` to see if '{domain_name}' exists and get its metadata.\n"
        f"2. Then call `get_catalog_tree(root_path='{domain_name}')` to see all monikers under it.\n"
        f"3. For any interesting leaf moniker, call `describe_moniker` to see its schema and ownership.\n"
        f"4. If you want connection details, call `resolve_moniker` on a specific path.\n\n"
        f"Please summarise what data is available under {domain_name}, who owns it, "
        f"and what source systems it comes from."
    )


@mcp.prompt(
    name="find_data",
    description="Help find a specific data asset by keyword or description.",
)
async def find_data_prompt(keyword: str) -> str:
    return (
        f"I'm looking for data related to **{keyword}**.\n\n"
        f"1. Call `search_catalog(query='{keyword}')` to find matching monikers.\n"
        f"2. For each result, call `describe_moniker` to get ownership and schema details.\n"
        f"3. If the data has related business models, call `get_models` filtered by relevant tags.\n\n"
        f"Please summarise what you find: the moniker paths, what data they contain, "
        f"who owns them, and how to access them."
    )


@mcp.prompt(
    name="check_ownership",
    description="Investigate who is responsible for a particular moniker or domain.",
)
async def check_ownership_prompt(path: str) -> str:
    return (
        f"I need to understand ownership for **{path}**.\n\n"
        f"1. Call `get_lineage(path='{path}')` to see the full ownership chain.\n"
        f"2. Note where each role (ADOP, ADS, ADAL, accountable_owner) is defined.\n"
        f"3. If the ownership comes from a domain fallback, note that.\n\n"
        f"Please present the ownership hierarchy clearly, showing which fields are "
        f"inherited and from where."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MCP Server for Open Moniker")
    parser.add_argument("--host", default=MCP_HOST, help="Bind address")
    parser.add_argument("--port", type=int, default=MCP_PORT, help="Port")
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="streamable-http")
    args = parser.parse_args()

    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.run(transport=args.transport)
