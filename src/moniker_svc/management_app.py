"""Management-only FastAPI entry point (control plane).

Start with:
    PYTHONPATH=src uvicorn moniker_svc.management_app:app --host 0.0.0.0 --port 8052

This process serves only the management/control-plane endpoints:
- /config/*    — catalog CRUD + save/reload
- /domains/*   — domain CRUD
- /models/*    — business model CRUD
- /requests/*  — request/approval workflow
- /dashboard/* — observability dashboard
- GET /        — landing page

It does NOT initialise AdapterRegistry, InMemoryCache, RateLimiter,
TelemetryEmitter, or the cached-query refresh loop.  Resolver endpoints
(/resolve/*, /fetch/*, /catalog, /tree, /health, etc.) are absent — requests
to those paths return 404.
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Add external packages path if running from repo
_REPO_ROOT = Path(__file__).parent.parent.parent
_EXTERNAL_DATA = _REPO_ROOT / "external" / "moniker-data" / "src"
if _EXTERNAL_DATA.exists() and str(_EXTERNAL_DATA) not in sys.path:
    sys.path.insert(0, str(_EXTERNAL_DATA))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import _bootstrap as bs
from .config_ui import routes as config_ui_routes
from .domains import routes as domain_routes
from .models import routes as model_routes
from .requests import routes as request_routes
from .dashboard import routes as dashboard_routes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Management-only startup (no adapters, no telemetry, no cache)."""
    logger.info("Starting management service...")

    config, config_path = bs.load_config()

    # Store config on app state for route handlers
    app.state.config = config

    catalog, _catalog_dir, catalog_definition_path = bs.build_catalog_registry(config, config_path)
    domain_registry, domains_yaml_path = bs.build_domain_registry()
    model_registry, models_yaml_path = bs.build_model_registry(config)
    request_registry, requests_yaml_path = bs.build_request_registry(config)

    # Wire each management sub-router with its runtime dependencies.
    domain_routes.configure(
        domain_registry=domain_registry,
        catalog_registry=catalog,
        domains_yaml_path=domains_yaml_path,
    )
    logger.info("Domain configuration enabled")

    if config.config_ui.enabled:
        config_ui_routes.configure(
            catalog=catalog,
            yaml_output_path=config.config_ui.yaml_output_path,
            catalog_definition_file=str(catalog_definition_path) if catalog_definition_path else None,
            service_cache=None,          # no in-memory cache on management process
            show_file_paths=config.config_ui.show_file_paths,
            domain_registry=domain_registry,
        )
        logger.info("Config UI enabled (catalog_file=%s)", catalog_definition_path)

    if config.models.enabled:
        model_routes.configure(
            model_registry=model_registry,
            catalog_registry=catalog,
            models_yaml_path=models_yaml_path,
        )
        logger.info("Business models configuration enabled")

    if config.requests.enabled:
        request_routes.configure(
            request_registry=request_registry,
            catalog_registry=catalog,
            domain_registry=domain_registry,
            yaml_path=requests_yaml_path,
        )
        logger.info("Request & approval workflow enabled")

    dashboard_routes.configure(
        catalog_registry=catalog,
        request_registry=request_registry,
    )
    logger.info("Dashboard enabled")

    logger.info("Management service started")
    yield

    logger.info("Management service stopped")


app = FastAPI(
    title="Moniker Management",
    description=(
        "Control-plane service.  Low-traffic, write-heavy.\n\n"
        "Resolver endpoints (`/resolve/*`, `/fetch/*`, `/health`, etc.) "
        "are not present on this process — use the resolver service on port 8051."
    ),
    version="0.2.0",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Config", "description": "Catalog configuration management"},
        {"name": "Domains", "description": "Domain governance and configuration"},
        {"name": "Models", "description": "Business models / measures"},
        {"name": "Requests", "description": "Moniker request submission and approval workflow"},
        {"name": "Dashboard", "description": "Observability dashboard"},
        {"name": "Health", "description": "Landing page"},
    ],
)

# Static files (shared CSS/JS — config UI and dashboard use them)
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# Management sub-routers
app.include_router(config_ui_routes.router)
app.include_router(domain_routes.router)
app.include_router(model_routes.router)
app.include_router(request_routes.router)
app.include_router(dashboard_routes.router)


# ---------------------------------------------------------------------------
# Landing page — dynamic version with configurable project name
# ---------------------------------------------------------------------------

from fastapi import Request  # noqa: E402  (after app definition for clarity)


@app.get("/", response_class=HTMLResponse, tags=["Health"])
async def root(request: Request):
    """Landing page with links to all management UIs and documentation."""
    project_name = request.app.state.config.project_name

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_name}</title>
    <style>
        :root {{
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
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: var(--font-sans);
            font-size: var(--fs-700);
            background: var(--color-bg);
            color: var(--color-text);
            line-height: 1.45;
        }}
        header {{
            background: var(--c-navy);
            padding: var(--sp-5);
            border-bottom: 3px solid var(--c-peacock);
        }}
        header h1 {{
            font-size: var(--fs-900);
            color: white;
            max-width: 1200px;
            margin: 0 auto;
        }}
        header p {{
            color: rgba(255,255,255,0.8);
            max-width: 1200px;
            margin: var(--sp-2) auto 0;
            font-size: var(--fs-600);
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: var(--sp-5);
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: var(--sp-5);
            margin-top: var(--sp-5);
        }}
        .card {{
            background: var(--color-surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-2);
            padding: var(--sp-5);
            transition: box-shadow 0.2s, transform 0.2s;
        }}
        .card:hover {{
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            transform: translateY(-2px);
        }}
        .card h2 {{
            font-size: var(--fs-800);
            color: var(--c-navy);
            margin-bottom: var(--sp-2);
            display: flex;
            align-items: center;
            gap: var(--sp-2);
        }}
        .card p {{
            color: var(--color-muted);
            font-size: var(--fs-600);
            margin-bottom: var(--sp-4);
        }}
        .card a {{
            display: inline-block;
            background: var(--c-peacock);
            color: white;
            padding: var(--sp-2) var(--sp-4);
            border-radius: var(--radius-1);
            text-decoration: none;
            font-weight: var(--fw-bold);
            font-size: var(--fs-600);
            transition: filter 0.2s;
        }}
        .card a:hover {{ filter: brightness(0.9); }}
        .card.docs a {{ background: var(--c-olive); }}
        .card.api a {{ background: var(--c-teal); }}
        .section-title {{
            font-size: var(--fs-800);
            color: var(--c-navy);
            margin-top: var(--sp-6);
            padding-bottom: var(--sp-2);
            border-bottom: 2px solid var(--c-peacock);
        }}
        footer {{
            text-align: center;
            padding: var(--sp-5);
            color: var(--color-muted);
            font-size: var(--fs-500);
        }}
    </style>
</head>
<body>
    <header>
        <h1>{project_name}</h1>
        <p>Management API - Control Plane</p>
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
                <h2>Business Models</h2>
                <p>Manage business models (measures, metrics, fields) that appear across monikers.</p>
                <a href="/models/ui">Models Browser</a>
            </div>
            <div class="card">
                <h2>Review Queue</h2>
                <p>Review and approve moniker requests. Manage the governance approval workflow.</p>
                <a href="/requests/ui">Open Review Queue</a>
                <a href="/docs" style="margin-left:12px">Swagger</a>
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
                <h2>Models</h2>
                <p>List all business models with their moniker mappings.</p>
                <a href="/models">Models API</a>
            </div>
            <div class="card api">
                <h2>Catalog Paths</h2>
                <p>List all registered catalog paths.</p>
                <a href="/catalog">Catalog API</a>
            </div>
        </div>
    </div>

    <footer>
        <p>&copy; 2024 {project_name}. All rights reserved.</p>
    </footer>
</body>
</html>
"""
    return HTMLResponse(content=html)
