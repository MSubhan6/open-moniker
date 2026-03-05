"""FastAPI routes for the usage/status dashboard."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from ..catalog.types import NodeStatus
from ..telemetry import db as telemetry_db

if TYPE_CHECKING:
    from ..catalog.registry import CatalogRegistry
    from ..requests.registry import RequestRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Configuration - set during app startup
_catalog_registry: "CatalogRegistry | None" = None
_request_registry: "RequestRegistry | None" = None


def configure(
    catalog_registry: "CatalogRegistry",
    request_registry: "RequestRegistry",
) -> None:
    """Configure the dashboard routes with registries."""
    global _catalog_registry, _request_registry
    _catalog_registry = catalog_registry
    _request_registry = request_registry


def _get_registries():
    """Get registries, raising if not configured."""
    if _catalog_registry is None or _request_registry is None:
        raise HTTPException(status_code=503, detail="Dashboard not initialized")
    return _catalog_registry, _request_registry


@router.get("/api/stats")
async def get_stats() -> dict[str, Any]:
    """Return aggregated stats from in-memory registries."""
    catalog_reg, req_reg = _get_registries()

    # Catalog by_status (drop the synthetic 'total' key)
    raw_counts = catalog_reg.count()
    total = raw_counts.pop("total", 0)
    by_status = {k: v for k, v in raw_counts.items() if v > 0}

    # Active monikers grouped by top-level domain.
    # The catalog uses both "." and "/" as hierarchy separators (mixed).
    # We find the domain by walking each node's ancestor chain toward the root
    # and returning the highest-level ancestor that is explicitly registered —
    # this correctly handles multi-segment domain names like "fixed.income"
    # (whose virtual parent "fixed" is unregistered) as well as single-segment
    # names like "risk" whose sub-paths use dot notation ("risk.var").
    all_nodes = catalog_reg.all_nodes()
    all_registered = {n.path for n in all_nodes}

    def _top_domain(path: str) -> str:
        ancestors: list[str] = []
        p = path
        while True:
            if "/" in p:
                p = p.rsplit("/", 1)[0]
            elif "." in p:
                p = p.rsplit(".", 1)[0]
            else:
                break
            if not p:
                break
            ancestors.append(p)
        # Walk from root toward the node; first registered hit is the domain.
        for anc in reversed(ancestors):
            if anc in all_registered:
                return anc
        return path  # no registered ancestor → node is its own domain

    by_domain: dict[str, int] = {}
    active_val = NodeStatus.ACTIVE.value
    for node in all_nodes:
        status_val = node.status.value if hasattr(node.status, "value") else str(node.status)
        if status_val == active_val:
            domain = _top_domain(node.path)
            by_domain[domain] = by_domain.get(domain, 0) + 1
    by_domain = dict(sorted(by_domain.items(), key=lambda x: x[1], reverse=True))

    # Request counts (drop synthetic 'total' key)
    req_counts = req_reg.count_by_status()
    req_counts.pop("total", 0)
    req_by_status = {k: v for k, v in req_counts.items() if v > 0}

    # Most-recent 10 requests sorted by created_at descending
    all_reqs = sorted(req_reg.all_requests(), key=lambda r: r.created_at, reverse=True)
    recent = [
        {
            "request_id": r.request_id,
            "path": r.path,
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "created_at": r.created_at,
        }
        for r in all_reqs[:10]
    ]

    return {
        "catalog": {
            "total": total,
            "by_status": by_status,
            "by_domain": by_domain,
        },
        "requests": {
            "by_status": req_by_status,
            "recent": recent,
        },
        "usage": None,
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard_ui() -> HTMLResponse:
    """Serve the Dashboard HTML page."""
    static_dir = Path(__file__).parent / "static"
    index_path = static_dir / "index.html"

    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard UI not found")

    return HTMLResponse(content=index_path.read_text(encoding="utf-8"), status_code=200)




@router.websocket("/live")
async def live_telemetry(websocket: WebSocket):
    """WebSocket endpoint for live telemetry updates."""
    await websocket.accept()

    try:
        while True:
            # Query metrics (last 10 seconds)
            metrics = await telemetry_db.get_live_metrics(seconds=10)

            # Send to browser
            await websocket.send_json({
                "timestamp": datetime.utcnow().isoformat(),
                "resolvers": metrics,
            })

            await asyncio.sleep(2)  # Update every 2 seconds

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")


@router.get("/api/timeseries")
async def get_timeseries(
    metric: str = "rps",
    interval: str = "1m",
    hours: int = 1,
):
    """
    Get time-series data for a metric.

    metric: rps, latency_p50, latency_p95, errors, cache_hit_rate
    interval: 10s, 1m, 5m, 1h
    hours: number of hours to query
    """
    try:
        data = await telemetry_db.get_timeseries(metric, interval, hours)
        return data
    except Exception as e:
        logger.error(f"Error fetching timeseries: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/top-monikers")
async def get_top_monikers(hours: int = 1, limit: int = 10):
    """Get top monikers by request count."""
    try:
        data = await telemetry_db.get_top_monikers(hours, limit)
        return data
    except Exception as e:
        logger.error(f"Error fetching top monikers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/errors")
async def get_errors(hours: int = 1):
    """Get error summary."""
    try:
        data = await telemetry_db.get_error_summary(hours)
        return data
    except Exception as e:
        logger.error(f"Error fetching errors: {e}")
        raise HTTPException(status_code=500, detail=str(e))
