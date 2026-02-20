"""Resolver-only FastAPI entry point (data plane).

Start with:
    PYTHONPATH=src uvicorn moniker_svc.resolver_app:app --host 0.0.0.0 --port 8051

This process serves only the data-plane endpoints:
- /resolve, /describe, /lineage, /list
- /fetch, /metadata
- /catalog, /catalog/search, /catalog/stats
- /tree, /tree/{path}
- /catalog/{path}/status, /catalog/{path}/audit
- /cache/status, /cache/refresh/{path}
- /telemetry/access
- /health
- /ui

It does NOT initialise ModelRegistry, RequestRegistry, config_ui, or
dashboard.  Management routes (/config/*, /domains/*, /models/*,
/requests/*, /dashboard/*) are absent — requests to those paths return 404.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Add external packages path if running from repo
_REPO_ROOT = Path(__file__).parent.parent.parent
_EXTERNAL_DATA = _REPO_ROOT / "external" / "moniker-data" / "src"
if _EXTERNAL_DATA.exists() and str(_EXTERNAL_DATA) not in sys.path:
    sys.path.insert(0, str(_EXTERNAL_DATA))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import _bootstrap as bs
from . import main as _main_mod
from .service import AccessDeniedError, NotFoundError, ResolutionError
from .moniker.parser import MonikerParseError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Resolver-only startup and shutdown."""
    logger.info("Starting resolver service...")

    config, config_path = bs.load_config()

    catalog, catalog_dir, _catalog_definition_path = bs.build_catalog_registry(config, config_path)
    domains, _domains_yaml_path = bs.build_domain_registry()
    adapter_registry = bs.build_adapter_registry(catalog_dir)
    cache = bs.build_cache(config)

    emitter, batcher = await bs.build_telemetry(config)
    await emitter.start()
    telemetry_task = asyncio.create_task(emitter.process_loop())
    batcher_task = asyncio.create_task(batcher.timer_loop())

    service = bs.build_service(catalog, cache, emitter, config)
    service.domain_registry = domains

    rate_limiter = bs.build_rate_limiter(config)
    circuit_breaker = bs.build_circuit_breaker(config)
    if rate_limiter is not None or circuit_breaker is not None:
        logger.info("Governance features initialised (rate limiter, circuit breaker)")
    else:
        logger.info("Governance module not available, running without rate limiting")

    bs.configure_auth(config)

    redis_cache, cache_manager, cache_refresh_task = await bs.setup_redis_and_cache_manager(
        config, catalog, adapter_registry,
    )

    # Wire the globals that the route handlers in main.py read.
    # The handlers are functions defined in main.py; they close over that
    # module's global namespace, so setting values here makes them visible
    # to every incoming request handled by resolver_router.
    _main_mod._set_resolver_globals(
        service=service,
        rate_limiter=rate_limiter,
        circuit_breaker=circuit_breaker,
        adapter_registry=adapter_registry,
        cache_manager=cache_manager,
        redis_cache=redis_cache,
        cache_refresh_task=cache_refresh_task,
        telemetry_task=telemetry_task,
        batcher_task=batcher_task,
        catalog_dir=catalog_dir,
        config=config,
    )
    # The NotFoundError handler in main.py also inspects _domain_registry.
    _main_mod._domain_registry = domains

    logger.info("Resolver service started")
    yield

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    logger.info("Shutting down resolver service...")

    if cache_refresh_task:
        cache_refresh_task.cancel()
        try:
            await cache_refresh_task
        except asyncio.CancelledError:
            pass

    if cache_manager:
        await cache_manager.stop()

    if redis_cache:
        await redis_cache.close()

    telemetry_task.cancel()
    batcher_task.cancel()
    try:
        await asyncio.gather(telemetry_task, batcher_task, return_exceptions=True)
    except asyncio.CancelledError:
        pass

    await emitter.stop()
    await batcher.stop()

    logger.info("Resolver service stopped")


app = FastAPI(
    title="Moniker Resolver",
    description=(
        "Data-plane resolution service.  High-throughput, read-only.\n\n"
        "Management endpoints (`/config/*`, `/domains/*`, `/models/*`, "
        "`/requests/*`, `/dashboard/*`) are not present on this process — "
        "use the management service on port 8052."
    ),
    version="0.2.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Resolution", "description": "Resolve monikers to connection info for client-side execution"},
        {"name": "Data Fetch", "description": "Server-side data retrieval and metadata"},
        {"name": "Catalog", "description": "Browse and explore the moniker catalog"},
        {"name": "Telemetry", "description": "Access tracking and reporting"},
        {"name": "Health", "description": "Service health and diagnostics"},
    ],
)

# Static files (CSS/JS for /ui)
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# All resolver routes live in main.resolver_router — include them here.
app.include_router(_main_mod.resolver_router)


# ---------------------------------------------------------------------------
# Exception handlers — mirror main.py exactly so error shapes are identical.
# ---------------------------------------------------------------------------

@app.exception_handler(MonikerParseError)
async def moniker_parse_error_handler(request: Request, exc: MonikerParseError):
    return JSONResponse(
        status_code=400,
        content={"error": "Invalid moniker", "detail": str(exc)},
    )


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request: Request, exc: NotFoundError):
    content = {"error": "Not found", "detail": str(exc)}
    try:
        path = request.url.path
        for prefix in ["/resolve/", "/describe/", "/list/", "/lineage/", "/fetch/", "/metadata/", "/tree/"]:
            if path.startswith(prefix):
                moniker_path = path[len(prefix):]
                first_segment = moniker_path.split("/")[0].split(".")[0]
                domain_reg = _main_mod._domain_registry
                if domain_reg and first_segment:
                    domain = domain_reg.get(first_segment)
                    if domain:
                        content["domain"] = first_segment
                        if domain.wiki_link:
                            content["documentation"] = domain.wiki_link
                        if domain.help_channel:
                            content["help_channel"] = domain.help_channel
                break
    except Exception:
        pass
    return JSONResponse(status_code=404, content=content)


@app.exception_handler(AccessDeniedError)
async def access_denied_error_handler(request: Request, exc: AccessDeniedError):
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
