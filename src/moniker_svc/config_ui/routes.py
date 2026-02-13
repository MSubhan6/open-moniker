"""FastAPI routes for Config UI API."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from ..catalog.loader import load_catalog
from ..catalog.registry import CatalogRegistry
from ..catalog.serializer import CatalogSerializer
from ..catalog.types import (
    AccessPolicy, CatalogNode, ColumnSchema, DataQuality, DataSchema,
    Documentation, Freshness, Ownership, SLA, SourceBinding, SourceType,
)
from .models import (
    CatalogNodeModel,
    CreateNodeRequest,
    DeleteResponse,
    NodeListResponse,
    NodeWithOwnershipModel,
    OwnershipModel,
    ReloadResponse,
    ResolvedOwnershipModel,
    SaveResponse,
    SourceBindingModel,
    SourceTypeInfo,
    SourceTypesResponse,
    UpdateNodeRequest,
)

if TYPE_CHECKING:
    from ..domains.registry import DomainRegistry

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/config", tags=["Config UI"])

# Configuration - will be set during app startup
_catalog: CatalogRegistry | None = None
_yaml_output_path: str = "catalog_output.yaml"
_catalog_definition_file: str | None = None
_service_cache = None  # Optional cache to clear on changes
_show_file_paths: bool = False  # Show file paths in save messages
_domain_registry: "DomainRegistry | None" = None  # For ownership inheritance


def configure(
    catalog: CatalogRegistry,
    yaml_output_path: str = "catalog_output.yaml",
    catalog_definition_file: str | None = None,
    service_cache=None,
    show_file_paths: bool = False,
    domain_registry: "DomainRegistry | None" = None,
) -> None:
    """Configure the Config UI routes.

    Args:
        catalog: The catalog registry to manage
        yaml_output_path: Path for YAML output file
        catalog_definition_file: Path to catalog definition file for reload
        service_cache: Optional cache to clear when catalog changes
        show_file_paths: Show file paths in save success messages
        domain_registry: Optional domain registry for ownership inheritance
    """
    global _catalog, _yaml_output_path, _catalog_definition_file, _service_cache, _show_file_paths, _domain_registry
    _catalog = catalog
    _yaml_output_path = yaml_output_path
    _catalog_definition_file = catalog_definition_file
    _service_cache = service_cache
    _show_file_paths = show_file_paths
    _domain_registry = domain_registry


def _clear_cache():
    """Clear the service cache if configured."""
    if _service_cache is not None:
        _service_cache.clear()
        logger.debug("Cleared service cache after catalog change")


def _get_catalog() -> CatalogRegistry:
    """Get the catalog registry, raising if not configured."""
    if _catalog is None:
        raise HTTPException(status_code=503, detail="Config UI not initialized")
    return _catalog


# =============================================================================
# Helper Functions
# =============================================================================

def _node_to_model(node: CatalogNode) -> CatalogNodeModel:
    """Convert CatalogNode to Pydantic model."""
    ownership = None
    if node.ownership and not node.ownership.is_empty():
        ownership = OwnershipModel(
            accountable_owner=node.ownership.accountable_owner,
            data_specialist=node.ownership.data_specialist,
            support_channel=node.ownership.support_channel,
            adop=node.ownership.adop,
            ads=node.ownership.ads,
            adal=node.ownership.adal,
            adop_name=node.ownership.adop_name,
            ads_name=node.ownership.ads_name,
            adal_name=node.ownership.adal_name,
            ui=node.ownership.ui,
        )

    source_binding = None
    if node.source_binding:
        source_binding = SourceBindingModel(
            type=node.source_binding.source_type.value,
            config=node.source_binding.config,
            allowed_operations=list(node.source_binding.allowed_operations) if node.source_binding.allowed_operations else None,
            schema_def=node.source_binding.schema,
            read_only=node.source_binding.read_only,
        )

    return CatalogNodeModel(
        path=node.path,
        display_name=node.display_name,
        description=node.description,
        domain=node.domain,
        ownership=ownership,
        source_binding=source_binding,
        classification=node.classification,
        tags=list(node.tags) if node.tags else [],
        metadata=node.metadata,
        is_leaf=node.is_leaf,
        status=node.status.value if hasattr(node.status, 'value') else str(node.status),
    )


def _model_to_ownership(model: OwnershipModel | None) -> Ownership:
    """Convert Pydantic model to Ownership dataclass."""
    if model is None:
        return Ownership()
    return Ownership(
        accountable_owner=model.accountable_owner,
        data_specialist=model.data_specialist,
        support_channel=model.support_channel,
        adop=model.adop,
        ads=model.ads,
        adal=model.adal,
        adop_name=model.adop_name,
        ads_name=model.ads_name,
        adal_name=model.adal_name,
        ui=model.ui,
    )


def _model_to_source_binding(model: SourceBindingModel | None) -> SourceBinding | None:
    """Convert Pydantic model to SourceBinding dataclass."""
    if model is None:
        return None

    try:
        source_type = SourceType(model.type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid source type: {model.type}")

    return SourceBinding(
        source_type=source_type,
        config=model.config,
        allowed_operations=frozenset(model.allowed_operations) if model.allowed_operations else None,
        schema=model.schema_def,
        read_only=model.read_only,
    )


def _request_to_node(path: str, request: CreateNodeRequest | UpdateNodeRequest, existing: CatalogNode | None = None) -> CatalogNode:
    """Convert a request to a CatalogNode."""
    # For update requests, start with existing values
    if existing and isinstance(request, UpdateNodeRequest):
        display_name = request.display_name if request.display_name is not None else existing.display_name
        description = request.description if request.description is not None else existing.description
        domain = request.domain if request.domain is not None else existing.domain
        ownership = _model_to_ownership(request.ownership) if request.ownership is not None else existing.ownership
        source_binding = _model_to_source_binding(request.source_binding) if request.source_binding is not None else existing.source_binding
        classification = request.classification if request.classification is not None else existing.classification
        tags = frozenset(request.tags) if request.tags is not None else existing.tags
        metadata = request.metadata if request.metadata is not None else existing.metadata
    else:
        # Create request - use defaults
        display_name = request.display_name if hasattr(request, 'display_name') else ""
        description = request.description if hasattr(request, 'description') else ""
        domain = request.domain if hasattr(request, 'domain') else None
        ownership = _model_to_ownership(request.ownership)
        source_binding = _model_to_source_binding(request.source_binding)
        classification = request.classification if hasattr(request, 'classification') else "internal"
        tags = frozenset(request.tags) if request.tags else frozenset()
        metadata = request.metadata if request.metadata else {}

    return CatalogNode(
        path=path,
        display_name=display_name,
        description=description,
        domain=domain,
        ownership=ownership,
        source_binding=source_binding,
        classification=classification,
        tags=tags,
        metadata=metadata,
        is_leaf=source_binding is not None,
    )


# =============================================================================
# UI Endpoint
# =============================================================================

@router.get("/ui", response_class=HTMLResponse)
async def config_ui():
    """Serve the Config UI HTML."""
    static_dir = Path(__file__).parent / "static"
    index_path = static_dir / "index.html"

    if not index_path.exists():
        raise HTTPException(status_code=404, detail="UI not found")

    return HTMLResponse(content=index_path.read_text(encoding="utf-8"), status_code=200)


# =============================================================================
# Node CRUD Endpoints
# =============================================================================

@router.get("/nodes", response_model=NodeListResponse)
async def list_nodes():
    """List all monikers."""
    catalog = _get_catalog()
    nodes = catalog.all_nodes()

    return NodeListResponse(
        nodes=[_node_to_model(n) for n in sorted(nodes, key=lambda x: x.path)],
        total=len(nodes),
    )


@router.get("/search")
async def search_nodes(q: str = ""):
    """
    Full text search over monikers.

    Searches across path, display_name, description, and tags.
    """
    catalog = _get_catalog()

    if not q or len(q) < 2:
        return {"results": [], "total": 0, "query": q}

    query_lower = q.lower()
    nodes = catalog.all_nodes()
    results = []

    for node in nodes:
        # Search in path
        if query_lower in node.path.lower():
            results.append({"path": node.path, "match": "path", "display_name": node.display_name or ""})
            continue

        # Search in display_name
        if node.display_name and query_lower in node.display_name.lower():
            results.append({"path": node.path, "match": "display_name", "display_name": node.display_name})
            continue

        # Search in description
        if node.description and query_lower in node.description.lower():
            results.append({"path": node.path, "match": "description", "display_name": node.display_name or ""})
            continue

        # Search in tags
        if node.tags:
            for tag in node.tags:
                if query_lower in tag.lower():
                    results.append({"path": node.path, "match": "tag", "display_name": node.display_name or ""})
                    break

    # Sort by path
    results.sort(key=lambda x: x["path"])

    return {"results": results[:50], "total": len(results), "query": q}


@router.get("/nodes/{path:path}", response_model=NodeWithOwnershipModel)
async def get_node(path: str):
    """Get a node with resolved ownership."""
    catalog = _get_catalog()

    node = catalog.get(path)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node not found: {path}")

    # Resolve ownership through hierarchy (with domain fallback)
    resolved = catalog.resolve_ownership(path, _domain_registry)

    return NodeWithOwnershipModel(
        node=_node_to_model(node),
        resolved_ownership=ResolvedOwnershipModel(
            accountable_owner=resolved.accountable_owner,
            accountable_owner_source=resolved.accountable_owner_source,
            data_specialist=resolved.data_specialist,
            data_specialist_source=resolved.data_specialist_source,
            support_channel=resolved.support_channel,
            support_channel_source=resolved.support_channel_source,
            adop=resolved.adop,
            adop_source=resolved.adop_source,
            adop_name=resolved.adop_name,
            adop_name_source=resolved.adop_name_source,
            ads=resolved.ads,
            ads_source=resolved.ads_source,
            ads_name=resolved.ads_name,
            ads_name_source=resolved.ads_name_source,
            adal=resolved.adal,
            adal_source=resolved.adal_source,
            adal_name=resolved.adal_name,
            adal_name_source=resolved.adal_name_source,
            ui=resolved.ui,
            ui_source=resolved.ui_source,
        ),
    )


@router.post("/nodes", response_model=CatalogNodeModel)
async def create_node(request: CreateNodeRequest):
    """Create a new moniker."""
    catalog = _get_catalog()

    # Check if node already exists
    if catalog.exists(request.path):
        raise HTTPException(status_code=409, detail=f"Node already exists: {request.path}")

    # Create the node
    node = _request_to_node(request.path, request)

    # Register it
    catalog.register(node)
    _clear_cache()

    logger.info(f"Created node: {request.path}")

    return _node_to_model(node)


@router.put("/nodes/{path:path}", response_model=CatalogNodeModel)
async def update_node(path: str, request: UpdateNodeRequest):
    """Update an existing moniker."""
    catalog = _get_catalog()

    # Get existing node
    existing = catalog.get(path)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Node not found: {path}")

    # Create updated node
    node = _request_to_node(path, request, existing)

    # Re-register (overwrites)
    catalog.register(node)
    _clear_cache()

    logger.info(f"Updated node: {path}")

    return _node_to_model(node)


@router.delete("/nodes/{path:path}", response_model=DeleteResponse)
async def delete_node(path: str):
    """Delete a moniker."""
    catalog = _get_catalog()

    # Check node exists
    if not catalog.exists(path):
        raise HTTPException(status_code=404, detail=f"Node not found: {path}")

    # Check for children
    children = catalog.children_paths(path)
    if children:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete node with children. Delete children first: {children}"
        )

    # Remove from the internal dict (using lock for thread safety)
    with catalog._lock:
        if path in catalog._nodes:
            del catalog._nodes[path]
            # Also remove from parent's children set
            parent_path = catalog._parent_path(path)
            if parent_path is not None and parent_path in catalog._children:
                catalog._children[parent_path].discard(path)

    _clear_cache()
    logger.info(f"Deleted node: {path}")

    return DeleteResponse(
        success=True,
        path=path,
        message=f"Node deleted: {path}",
    )


# =============================================================================
# Save/Reload Endpoints
# =============================================================================

@router.post("/save", response_model=SaveResponse)
async def save_to_yaml():
    """Save the current catalog to YAML file."""
    catalog = _get_catalog()

    serializer = CatalogSerializer()
    nodes = catalog.all_nodes()
    catalog_dict = serializer.serialize_catalog(nodes)

    # Write to the same file we loaded from (catalog.yaml), not catalog_output.yaml
    output_path = Path(_catalog_definition_file or _yaml_output_path)
    abs_path = output_path.resolve()

    logger.info(f"[SAVE] definition_file={_catalog_definition_file}, output_path={_yaml_output_path}")
    logger.info(f"[SAVE] Writing {len(nodes)} nodes to: {abs_path}")

    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            yaml.dump(catalog_dict, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            f.flush()
            os.fsync(f.fileno())

        logger.info(f"[SAVE] SUCCESS - wrote to {abs_path}")

        # Build message based on config
        if _show_file_paths:
            message = f"Saved {len(nodes)} monikers to {abs_path}"
        else:
            message = f"Saved {len(nodes)} monikers"

        return SaveResponse(
            success=True,
            path=str(abs_path) if _show_file_paths else "",
            moniker_count=len(nodes),
            message=message,
        )
    except Exception as e:
        logger.error(f"Failed to save catalog: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


@router.post("/reload", response_model=ReloadResponse)
async def reload_from_yaml():
    """Hot-reload catalog from YAML file."""
    catalog = _get_catalog()

    # Determine which file to load from
    # DEBUG: Log which files we're considering
    logger.info(f"Reload: _catalog_definition_file={_catalog_definition_file}, _yaml_output_path={_yaml_output_path}")
    source_path = _catalog_definition_file or _yaml_output_path

    if not Path(source_path).exists():
        raise HTTPException(status_code=404, detail=f"Catalog file not found: {source_path}")

    try:
        # Load new catalog
        new_catalog = load_catalog(source_path)
        new_nodes = new_catalog.all_nodes()

        # Atomic replace
        catalog.atomic_replace(new_nodes)

        logger.info(f"Reloaded catalog from {source_path} ({len(new_nodes)} nodes)")

        return ReloadResponse(
            success=True,
            moniker_count=len(new_nodes),
            message=f"Reloaded {len(new_nodes)} monikers from {source_path}",
        )
    except Exception as e:
        logger.error(f"Failed to reload catalog: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reload: {str(e)}")


# =============================================================================
# Source Types Endpoint
# =============================================================================

# Source type configuration schemas
SOURCE_TYPE_SCHEMAS: dict[str, dict[str, Any]] = {
    "snowflake": {
        "display_name": "Snowflake",
        "execution_mode": "client",
        "execution_hint": "Client connects directly to Snowflake and executes the query",
        "config_schema": {
            "account": {"type": "string", "required": True, "description": "Snowflake account identifier"},
            "warehouse": {"type": "string", "required": True, "description": "Warehouse to use"},
            "database": {"type": "string", "required": True, "description": "Database name"},
            "schema": {"type": "string", "required": False, "description": "Schema name (default: PUBLIC)"},
            "role": {"type": "string", "required": False, "description": "Role to use"},
            "segment_names": {"type": "string", "required": False, "description": "Comma-separated path segment names (e.g., date,account,security)"},
            "query": {"type": "sql", "required": False, "description": "SQL query template with placeholders like {segments[0]}, {filter[N]:COL}"},
            "table": {"type": "string", "required": False, "description": "Table name (if no query)"},
        },
    },
    "oracle": {
        "display_name": "Oracle",
        "execution_mode": "client",
        "execution_hint": "Client connects directly to Oracle and executes the query",
        "config_schema": {
            "dsn": {"type": "string", "required": False, "description": "Oracle DSN string"},
            "host": {"type": "string", "required": False, "description": "Database host"},
            "port": {"type": "number", "required": False, "description": "Database port"},
            "service_name": {"type": "string", "required": False, "description": "Oracle service name"},
            "segment_names": {"type": "string", "required": False, "description": "Comma-separated path segment names (e.g., date,account,security)"},
            "query": {"type": "sql", "required": False, "description": "SQL query template with placeholders like {segments[0]}, {filter[N]:COL}"},
            "table": {"type": "string", "required": False, "description": "Table name (if no query)"},
        },
    },
    "rest": {
        "display_name": "REST API",
        "execution_mode": "server",
        "execution_hint": "Service proxies the request and returns data",
        "config_schema": {
            "base_url": {"type": "string", "required": True, "description": "Base URL for the API"},
            "path_template": {"type": "string", "required": True, "description": "Path template (e.g., /api/v2/{path})"},
            "method": {"type": "select", "required": False, "description": "HTTP method", "options": ["GET", "POST", "PUT", "DELETE"]},
            "auth_type": {"type": "select", "required": False, "description": "Authentication type", "options": ["none", "bearer", "api_key", "basic"]},
            "headers": {"type": "json", "required": False, "description": "Additional headers (JSON object)"},
            "query_params": {"type": "json", "required": False, "description": "Query parameters (JSON object)"},
        },
    },
    "static": {
        "display_name": "Static Files",
        "execution_mode": "server",
        "execution_hint": "Service reads files and returns data",
        "config_schema": {
            "base_path": {"type": "string", "required": True, "description": "Base directory path"},
            "file_pattern": {"type": "string", "required": True, "description": "File pattern template"},
            "format": {"type": "select", "required": False, "description": "File format", "options": ["json", "csv", "parquet"]},
            "encoding": {"type": "string", "required": False, "description": "File encoding (default: utf-8)"},
        },
    },
    "excel": {
        "display_name": "Excel",
        "execution_mode": "server",
        "execution_hint": "Service reads Excel files and returns data",
        "config_schema": {
            "base_path": {"type": "string", "required": True, "description": "Base directory path"},
            "file_pattern": {"type": "string", "required": True, "description": "File pattern template"},
            "sheet": {"type": "string", "required": False, "description": "Sheet name to read"},
            "header_row": {"type": "number", "required": False, "description": "Header row number (default: 1)"},
        },
    },
    "bloomberg": {
        "display_name": "Bloomberg",
        "execution_mode": "client",
        "execution_hint": "Client connects to Bloomberg Terminal/API",
        "config_schema": {
            "host": {"type": "string", "required": False, "description": "Bloomberg API host"},
            "port": {"type": "number", "required": False, "description": "Bloomberg API port"},
            "api_type": {"type": "select", "required": False, "description": "API type", "options": ["blpapi", "bqnt"]},
            "securities": {"type": "string", "required": False, "description": "Securities template"},
            "fields": {"type": "json", "required": False, "description": "Fields to retrieve (JSON array)"},
        },
    },
    "refinitiv": {
        "display_name": "Refinitiv",
        "execution_mode": "client",
        "execution_hint": "Client connects to Refinitiv Eikon/RDP",
        "config_schema": {
            "api_type": {"type": "select", "required": False, "description": "API type", "options": ["eikon", "rdp"]},
            "instruments": {"type": "string", "required": False, "description": "Instruments template"},
            "fields": {"type": "json", "required": False, "description": "Fields to retrieve (JSON array)"},
        },
    },
    "opensearch": {
        "display_name": "OpenSearch",
        "execution_mode": "server",
        "execution_hint": "Service queries OpenSearch and returns data",
        "config_schema": {
            "hosts": {"type": "json", "required": True, "description": "List of host URLs (JSON array)"},
            "index": {"type": "string", "required": True, "description": "Index name"},
            "query": {"type": "text", "required": False, "description": "Query template (JSON)"},
        },
    },
    "composite": {
        "display_name": "Composite",
        "execution_mode": "server",
        "execution_hint": "Service combines multiple sources",
        "config_schema": {
            "sources": {"type": "json", "required": True, "description": "List of source monikers to combine"},
            "join_strategy": {"type": "select", "required": False, "description": "How to combine sources", "options": ["merge", "union", "join"]},
        },
    },
    "derived": {
        "display_name": "Derived",
        "execution_mode": "server",
        "execution_hint": "Service transforms data from another source",
        "config_schema": {
            "source_moniker": {"type": "string", "required": True, "description": "Source moniker to derive from"},
            "transform": {"type": "text", "required": False, "description": "Transformation expression"},
        },
    },
}


@router.get("/source-types", response_model=SourceTypesResponse)
async def list_source_types():
    """List all source types with their configuration schemas."""
    source_types = []

    for type_value in SourceType:
        schema_info = SOURCE_TYPE_SCHEMAS.get(type_value.value, {
            "display_name": type_value.value.title(),
            "config_schema": {},
            "execution_mode": "server",
            "execution_hint": "",
        })

        source_types.append(SourceTypeInfo(
            type=type_value.value,
            display_name=schema_info["display_name"],
            config_schema=schema_info["config_schema"],
            execution_mode=schema_info.get("execution_mode", "server"),
            execution_hint=schema_info.get("execution_hint", ""),
        ))

    return SourceTypesResponse(source_types=source_types)
