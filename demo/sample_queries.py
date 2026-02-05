#!/usr/bin/env python
"""
Sample Queries Demo - Interactive demonstration of the Moniker Service.

Run with: python demo/sample_queries.py
Requires the service to be running: python start.py
"""

import json
import re
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# Initialize colorama for Windows support
from colorama import init, Fore, Back, Style
init(autoreset=True)

BASE_URL = "http://localhost:8050"


# =============================================================================
# Color Shortcuts
# =============================================================================

class C:
    """Color shortcuts using colorama."""
    RESET = Style.RESET_ALL
    BOLD = Style.BRIGHT
    DIM = Style.DIM

    # Colors
    WHITE = Fore.WHITE
    ORANGE = Fore.YELLOW  # Colorama doesn't have orange, use yellow
    RED = Fore.RED
    BLUE = Fore.BLUE
    GREEN = Fore.GREEN
    PURPLE = Fore.MAGENTA
    GRAY = Fore.LIGHTBLACK_EX
    CYAN = Fore.CYAN
    YELLOW = Fore.YELLOW


def colorize_path(path: str) -> str:
    """Colorize a moniker path with semantic highlighting."""
    # Split into parts
    parts = re.split(r'([/@.])', path)
    result = []

    # Patterns
    date_pattern = re.compile(r'^@?\d{8}$')  # @20260101 or 20260101
    tenor_pattern = re.compile(r'^(KRD|DV01|CR01)?\d*[YMWD]$|^KRD\d+[YMWD]?$', re.IGNORECASE)
    keyword_pattern = re.compile(r'^(ALL|LATEST|ANY)$', re.IGNORECASE)
    business_fields = {'AAPL', 'MSFT', 'GOOG', 'TSLA', 'ETH', 'BTC', 'EUR', 'USD', 'GBP', 'DKK',
                       'portfolio', 'fund', 'account', 'ISIN', 'CUSIP', 'SEDOL',
                       'equity', 'bond', 'fx', 'rates', 'credit', 'commodity', 'bitcoin'}
    domain_keywords = {'prices', 'analytics', 'reference', 'holdings', 'indices', 'index',
                       'commodities', 'commods', 'instruments', 'reports', 'risk', 'security',
                       'sovereign', 'derivatives', 'calendars', 'regulatory', 'var', 'views',
                       'global', 'futures', 'digital', 'gov', 'securities'}
    # Sub-resource keywords (paths after @version)
    subresource_keywords = {'details', 'history', 'metadata', 'schema', 'audit', 'corporate', 'actions'}

    for part in parts:
        if not part:
            continue
        elif part in '/@.':
            result.append(C.GRAY + part + C.RESET)
        elif keyword_pattern.match(part):
            result.append(C.RED + C.BOLD + part + C.RESET)
        elif date_pattern.match(part):
            result.append(C.BLUE + part + C.RESET)
        elif tenor_pattern.match(part):
            result.append(C.PURPLE + part + C.RESET)
        elif part.lower() in subresource_keywords:
            result.append(C.CYAN + part + C.RESET)
        elif part.upper() in business_fields or part in business_fields:
            result.append(C.GREEN + part + C.RESET)
        elif part.lower() in domain_keywords:
            result.append(C.ORANGE + part + C.RESET)
        elif part.startswith('US') and len(part) > 8:  # ISIN-like
            result.append(C.GREEN + part + C.RESET)
        else:
            result.append(C.WHITE + part + C.RESET)

    return ''.join(result)


def colorize_moniker(moniker: str) -> str:
    """Colorize a full moniker string."""
    if moniker.startswith('moniker://'):
        return C.GRAY + 'moniker://' + C.RESET + colorize_path(moniker[10:])
    return colorize_path(moniker)


# =============================================================================
# API Functions
# =============================================================================

def fetch(endpoint: str, method: str = "GET", data: dict = None) -> dict | None:
    """Fetch from the API and return JSON response."""
    url = f"{BASE_URL}{endpoint}"
    try:
        req = Request(url, method=method)
        req.add_header("Content-Type", "application/json")
        if data:
            req.data = json.dumps(data).encode()
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        print(f"  {C.RED}HTTP Error {e.code}: {e.reason}{C.RESET}")
        try:
            error_body = json.loads(e.read().decode())
            print(f"  Detail: {error_body.get('detail', 'No detail')}")
        except Exception:
            pass
        return None
    except URLError as e:
        print(f"  {C.RED}Connection Error: {e.reason}{C.RESET}")
        print(f"  Is the service running? Start with: {C.CYAN}python start.py{C.RESET}")
        return None


def print_json(data: dict, indent: int = 2):
    """Pretty print JSON data."""
    print(json.dumps(data, indent=indent, default=str))


def header(title: str):
    """Print a section header."""
    print("\n" + C.CYAN + "=" * 60 + C.RESET)
    print(f"  {C.BOLD}{title}{C.RESET}")
    print(C.CYAN + "=" * 60 + C.RESET)


# =============================================================================
# Menu Options
# =============================================================================

def option_1_health():
    """Health Check"""
    header("1. Health Check")
    print("\nChecking service health...")
    result = fetch("/health")
    if result:
        print(f"\n  Status: {C.GREEN}{result['status']}{C.RESET}")
        print(f"  Cache size: {result['cache']['size']}")
        print(f"  Telemetry emitted: {result['telemetry']['emitted']}")
        print("\n  Full response:")
        print_json(result)


def option_2_resolve_equity():
    """Resolve - Equity Price (Snowflake)"""
    header("2. Resolve Moniker - Equity Price")
    moniker = "prices.equity/AAPL"
    print(f"\nResolving: {colorize_moniker('moniker://' + moniker)}")
    print("This returns connection info for Snowflake - client connects directly.\n")
    result = fetch(f"/resolve/{moniker}")
    if result:
        print(f"  Source Type: {C.ORANGE}{result['source_type']}{C.RESET}")
        print(f"  Binding Path: {colorize_path(result['binding_path'])}")
        print(f"  Connection: {result['connection']}")
        print(f"\n  Query to execute:")
        query = result.get('query', '')
        print(f"  {query[:200]}..." if len(query) > 200 else f"  {query}")


def option_3_resolve_rest():
    """Resolve - Risk VaR (REST API)"""
    header("3. Resolve Moniker - Risk VaR (REST)")
    moniker = "analytics.risk/var/portfolio-123"
    print(f"\nResolving: {colorize_moniker('moniker://' + moniker)}")
    print("This returns REST API connection info.\n")
    result = fetch(f"/resolve/{moniker}")
    if result:
        print(f"  Source Type: {C.ORANGE}{result['source_type']}{C.RESET}")
        print(f"  Base URL: {result['connection'].get('base_url')}")
        print(f"  Auth Type: {result['connection'].get('auth_type')}")
        print(f"  Path: {result['query']}")


def option_4_resolve_oracle():
    """Resolve - Security Master (Oracle)"""
    header("4. Resolve Moniker - Security Master (Oracle)")
    moniker = "reference.security/ISIN/US0378331005"
    print(f"\nResolving: {colorize_moniker('moniker://' + moniker)}")
    print("This returns Oracle connection info.\n")
    result = fetch(f"/resolve/{moniker}")
    if result:
        print(f"  Source Type: {C.ORANGE}{result['source_type']}{C.RESET}")
        print(f"  DSN: {result['connection'].get('dsn')}")
        print(f"\n  Query:")
        print(f"  {result.get('query', 'N/A')}")


def option_5_fetch_equity():
    """Fetch - Equity Price (Server-side execution)"""
    header("5. Fetch Data - Equity Price")
    moniker = "prices.equity/AAPL"
    print(f"\nFetching: {colorize_moniker('moniker://' + moniker)}")
    print("Server executes the query and returns data directly.\n")
    result = fetch(f"/fetch/{moniker}?limit=5")
    if result:
        print(f"  Rows returned: {C.GREEN}{result['row_count']}{C.RESET}")
        print(f"  Columns: {result['columns']}")
        print(f"  Execution time: {result['execution_time_ms']}ms")
        print(f"\n  Data sample:")
        for row in result['data'][:3]:
            print(f"    {row}")


def option_6_fetch_crypto():
    """Fetch - Crypto (REST pass-through)"""
    header("6. Fetch Data - Digital Assets")
    moniker = "commodities.derivatives/crypto/ETH"
    print(f"\nFetching: {colorize_moniker('moniker://' + moniker)}")
    print("Server calls REST API and returns data.\n")
    result = fetch(f"/fetch/{moniker}?limit=5")
    if result:
        print(f"  Source Type: {C.ORANGE}{result['source_type']}{C.RESET}")
        print(f"  Rows: {result['row_count']}")
        if result['data']:
            print(f"\n  Data sample:")
            for row in result['data'][:3]:
                print(f"    {row}")


def option_7_describe():
    """Describe - Get metadata about a path"""
    header("7. Describe Moniker")
    moniker = "analytics"
    print(f"\nDescribing: {colorize_moniker('moniker://' + moniker)}")
    print("Returns metadata, ownership, classification.\n")
    result = fetch(f"/describe/{moniker}")
    if result:
        print(f"  Path: {colorize_path(result['path'])}")
        print(f"  Display Name: {result['display_name']}")
        print(f"  Classification: {C.YELLOW}{result['classification']}{C.RESET}")
        print(f"  Has Source: {result['has_source_binding']}")
        print(f"\n  Ownership:")
        for key, val in result['ownership'].items():
            if val and not key.endswith('_source'):
                print(f"    {key}: {C.GREEN}{val}{C.RESET}")


def option_8_lineage():
    """Lineage - Ownership provenance"""
    header("8. Ownership Lineage")
    moniker = "analytics.risk/var"
    print(f"\nLineage for: {colorize_moniker('moniker://' + moniker)}")
    print("Shows where each ownership field is inherited from.\n")
    result = fetch(f"/lineage/{moniker}")
    if result:
        print(f"  Path: {colorize_path(result['path'])}")
        print(f"\n  Ownership inheritance:")
        for key, val in result['ownership'].items():
            if not key.endswith('_at') and val:
                source = result['ownership'].get(f"{key}_defined_at", "unknown")
                print(f"    {key}: {C.GREEN}{val}{C.RESET} (from: {C.ORANGE}{source}{C.RESET})")


def option_9_list_children():
    """List - Children of a path"""
    header("9. List Children")
    moniker = "reference"
    print(f"\nListing children of: {colorize_moniker('moniker://' + moniker)}")
    result = fetch(f"/list/{moniker}")
    if result:
        print(f"  Path: {colorize_path(result['path'])}")
        children_colored = [colorize_path(c) for c in result['children']]
        print(f"  Children: {children_colored}")


def option_10_sample():
    """Sample - Quick data preview"""
    header("10. Sample Data")
    moniker = "indices.sovereign/developed/EU.GovBondAgg/EUR/ALL"
    print(f"\nSampling: {colorize_moniker('moniker://' + moniker)}")
    print("Quick preview of data structure.\n")
    result = fetch(f"/sample/{moniker}?limit=3")
    if result:
        print(f"  Columns: {result['columns']}")
        print(f"  Row count: {result['row_count']}")
        if result['data']:
            print(f"\n  Sample rows:")
            for row in result['data']:
                print(f"    {row}")


def option_11_metadata():
    """Metadata - AI/Agent discoverability"""
    header("11. Rich Metadata (for AI agents)")
    moniker = "holdings/positions"
    print(f"\nMetadata for: {colorize_moniker('moniker://' + moniker)}")
    print("Returns comprehensive info for AI discoverability.\n")
    result = fetch(f"/metadata/{moniker}")
    if result:
        print(f"  Path: {colorize_path(result['path'])}")
        print(f"  Display Name: {result['display_name']}")
        if result.get('schema'):
            print(f"  Granularity: {result['schema'].get('granularity')}")
        if result.get('ownership'):
            print(f"  Owner: {C.GREEN}{result['ownership'].get('accountable_owner')}{C.RESET}")


def option_12_tree():
    """Tree - Hierarchical view"""
    header("12. Catalog Tree")
    moniker = "analytics"
    print(f"\nTree view of: {colorize_path(moniker)}\n")
    result = fetch(f"/tree/{moniker}")
    if result:
        def print_tree(node, indent=0):
            prefix = "  " * indent
            name = colorize_path(node['name'])
            source = f" [{C.ORANGE}{node.get('source_type')}{C.RESET}]" if node.get('source_type') else ""
            print(f"{prefix}- {name}/{source}")
            for child in node.get('children', []):
                print_tree(child, indent + 1)
        print_tree(result)


def option_13_batch_validate():
    """Batch Validate - Multiple monikers"""
    header("13. Batch Moniker Validation")
    monikers = [
        "prices.equity/AAPL",
        "prices.equity/MSFT@20260115",
        "analytics.risk/var/portfolio-1",
        "reference.security/ISIN/US0378331005",
        "indices.sovereign/developed/ALL/EUR/ALL",
        "invalid/path/does/not/exist",
    ]
    print(f"\nValidating {len(monikers)} monikers...\n")

    for moniker in monikers:
        result = fetch(f"/describe/{moniker}")
        print(f"  {colorize_moniker('moniker://' + moniker)}")
        if result:
            status = f"{C.GREEN}HAS SOURCE{C.RESET}" if result.get('has_source_binding') else f"{C.GRAY}NO SOURCE{C.RESET}"
            print(f"    -> {status}, classification: {result.get('classification', 'N/A')}")
        else:
            print(f"    -> {C.RED}NOT FOUND{C.RESET}")


def option_14_list_domains():
    """List Data Domains - Top-level catalog paths"""
    header("14. List Data Domains")
    print("\nTop-level data domains in the catalog:\n")
    result = fetch("/catalog")
    if result:
        # Extract unique top-level domains
        domains = set()
        for path in result.get('paths', []):
            top = path.split('/')[0].split('.')[0]
            domains.add(top)

        domains = sorted(domains)
        print(f"  Found {C.GREEN}{len(domains)}{C.RESET} top-level domains:\n")
        for i, domain in enumerate(domains, 1):
            # Get domain info
            info = fetch(f"/describe/{domain}")
            if info:
                desc = info.get('description', '')[:50] or info.get('display_name', domain)
                print(f"  {i:2}. {colorize_path(domain):20} - {desc}")
            else:
                print(f"  {i:2}. {colorize_path(domain)}")


def option_15_configure_domains():
    """Configure Domains - View and manage data domains"""
    header("15. Configure Domains")
    print("\nData domains are top-level organizational units with governance metadata.\n")
    result = fetch("/domains")
    if result:
        domains = result.get('domains', [])
        print(f"  Found {C.GREEN}{len(domains)}{C.RESET} configured domains:\n")

        for d in domains:
            color_dot = f"{C.BOLD}●{C.RESET}"  # Placeholder for color
            conf_badge = ""
            if d.get('confidentiality') in ('confidential', 'strictly_confidential'):
                conf_badge = f" [{C.RED}{d['confidentiality'].upper()}{C.RESET}]"
            pii_badge = f" [{C.RED}PII{C.RESET}]" if d.get('pii') else ""

            print(f"  {color_dot} {colorize_path(d['name']):15} {d.get('short_code', ''):5} - {d.get('display_name', '')}{conf_badge}{pii_badge}")
            if d.get('owner'):
                print(f"      Owner: {C.GREEN}{d['owner']}{C.RESET}")

        print(f"\n  {C.BOLD}Domain Config UI:{C.RESET} {C.CYAN}http://localhost:8050/domains/ui{C.RESET}")
        print(f"  {C.BOLD}API Endpoints:{C.RESET}")
        print(f"    GET  /domains        - List all domains")
        print(f"    GET  /domains/{{name}} - Get domain details")
        print(f"    POST /domains        - Create domain")
        print(f"    PUT  /domains/{{name}} - Update domain")
        print(f"    POST /domains/save   - Save to YAML")


def option_16_view_domain():
    """View Domain - Show governance metadata for a specific domain"""
    header("16. View Domain Governance")
    domain_name = "indices"  # Default to indices, could prompt user
    print(f"\nViewing governance metadata for '{colorize_path(domain_name)}' domain:\n")
    result = fetch(f"/domains/{domain_name}")
    if result:
        domain = result.get('domain', {})
        monikers = result.get('moniker_paths', [])

        print(f"  {C.BOLD}Domain:{C.RESET} {domain.get('name')}")
        print(f"  {C.BOLD}Display Name:{C.RESET} {domain.get('display_name')}")
        print(f"  {C.BOLD}Short Code:{C.RESET} {domain.get('short_code')}")
        print(f"  {C.BOLD}Color:{C.RESET} {domain.get('color')}")

        print(f"\n  {C.BOLD}Governance:{C.RESET}")
        print(f"    Owner:           {C.GREEN}{domain.get('owner')}{C.RESET}")
        print(f"    Tech Custodian:  {domain.get('tech_custodian')}")
        print(f"    Business Steward: {domain.get('business_steward')}")

        print(f"\n  {C.BOLD}Classification:{C.RESET}")
        print(f"    Data Category:   {domain.get('data_category')}")
        conf = domain.get('confidentiality', 'internal')
        conf_color = C.RED if conf in ('confidential', 'strictly_confidential') else C.YELLOW
        print(f"    Confidentiality: {conf_color}{conf}{C.RESET}")
        pii = domain.get('pii', False)
        pii_color = C.RED if pii else C.GREEN
        print(f"    Contains PII:    {pii_color}{'Yes' if pii else 'No'}{C.RESET}")

        print(f"\n  {C.BOLD}Support:{C.RESET}")
        print(f"    Help Channel:    {domain.get('help_channel')}")
        print(f"    Wiki Link:       {domain.get('wiki_link')}")

        if domain.get('notes'):
            print(f"\n  {C.BOLD}Notes:{C.RESET} {domain.get('notes')}")

        if monikers:
            print(f"\n  {C.BOLD}Moniker Paths ({len(monikers)}):{C.RESET}")
            for m in monikers[:5]:
                print(f"    - {colorize_path(m)}")
            if len(monikers) > 5:
                print(f"    ... and {len(monikers) - 5} more")


def option_17_list_mappings():
    """List Mappings - Full catalog structure"""
    header("17. Full Catalog Mapping")
    print("\nAll registered paths with source bindings:\n")
    result = fetch("/catalog")
    if result:
        paths = sorted(result.get('paths', []))
        print(f"  Total paths: {C.GREEN}{len(paths)}{C.RESET}\n")

        # Group by top-level domain
        by_domain = {}
        for path in paths:
            domain = path.split('/')[0].split('.')[0]
            if domain not in by_domain:
                by_domain[domain] = []
            by_domain[domain].append(path)

        for domain in sorted(by_domain.keys()):
            print(f"  {colorize_path(domain)}/")
            for path in by_domain[domain]:
                # Check if it has a source binding
                info = fetch(f"/describe/{path}")
                if info and info.get('has_source_binding'):
                    print(f"    -> {colorize_path(path)} [{C.ORANGE}{info.get('source_type')}{C.RESET}]")
                else:
                    print(f"    -> {colorize_path(path)}")


def option_18_complex_index():
    """Complex Index - Multi-segment hierarchy"""
    header("18. Complex Index - Bloomberg Global Treasury")
    moniker = "index.global/BBGGlobalAggTreasury/GBP/MWS_LIBOR"
    print(f"\nResolving: {colorize_moniker('moniker://' + moniker)}")
    print("Multi-segment path: index family / currency / benchmark\n")
    result = fetch(f"/resolve/{moniker}")
    if result:
        print(f"  Source Type: {C.ORANGE}{result['source_type']}{C.RESET}")
        print(f"  Binding Path: {colorize_path(result['binding_path'])}")
    else:
        print(f"\n  {C.GRAY}(No binding - this is an example complex path structure){C.RESET}")
        print(f"  Path segments: index.global / BBGGlobalAggTreasury / GBP / MWS_LIBOR")
        print(f"  Use case: Global treasury indices with currency and benchmark type")


def option_19_gov_rates():
    """Government Rates - Danish Bond with KRD"""
    header("19. Government Rates - Danish Bond KRD")
    moniker = "rates.gov/DKK/DK0.125Mar2026/KRD/KRD12Y"
    print(f"\nResolving: {colorize_moniker('moniker://' + moniker)}")
    print("Path includes: currency / bond ID (opaque) / risk type / tenor\n")
    result = fetch(f"/resolve/{moniker}")
    if result:
        print(f"  Source Type: {C.ORANGE}{result['source_type']}{C.RESET}")
        print(f"  Binding Path: {colorize_path(result['binding_path'])}")
    else:
        print(f"\n  {C.GRAY}(No binding - this shows opaque segment handling){C.RESET}")
        print(f"  Segments:")
        print(f"    [0] {C.GREEN}DKK{C.RESET}            - Currency")
        print(f"    [1] DK0.125Mar2026  - Bond ID (opaque, includes coupon & maturity)")
        print(f"    [2] KRD             - Risk type (Key Rate Duration)")
        print(f"    [3] {C.PURPLE}KRD12Y{C.RESET}         - Tenor (12-year KRD)")


def option_20_versioned_subresource():
    """Versioned Sub-resource - Security details at specific date"""
    header("20. Versioned Sub-resource - Security Details")
    examples = [
        ("securities/012345678@20260101/details", "Single sub-resource"),
        ("securities/012345678@20260101/details.corporate.actions", "Multi-level sub-resource"),
    ]

    for moniker, desc in examples:
        print(f"\n  {C.BOLD}{desc}:{C.RESET}")
        print(f"  Parsing: {colorize_moniker('moniker://' + moniker)}")

        # Parse locally to show components
        result = fetch(f"/describe/{moniker.split('@')[0]}")
        print(f"    Path: securities/012345678")
        print(f"    Version: {C.BLUE}20260101{C.RESET} (type: DATE)")
        sub = moniker.split('/')[-1] if '/' in moniker.split('@')[1] else None
        if sub:
            print(f"    Sub-resource: {C.CYAN}{sub}{C.RESET}")

    print(f"\n  {C.GRAY}Use case: Point-in-time views of security data with specific projections{C.RESET}")


def option_21_temporal_versions():
    """Temporal Version Types - Different version semantics"""
    header("21. Temporal Version Types")
    print(f"\n  The {C.BOLD}@version{C.RESET} suffix supports multiple semantic types:\n")

    examples = [
        ("prices.equity/AAPL@20260115", "DATE", "Specific date (YYYYMMDD)"),
        ("prices.equity/AAPL@latest", "LATEST", "Most recent available data"),
        ("rates.swap/USD/10Y@3M", "TENOR", "Three months lookback"),
        ("risk.cvar/portfolio-123@all", "ALL", "Full time series"),
    ]

    for moniker, vtype, desc in examples:
        color = {
            "DATE": C.BLUE,
            "LATEST": C.RED + C.BOLD,
            "TENOR": C.PURPLE,
            "ALL": C.RED + C.BOLD,
        }.get(vtype, C.WHITE)

        print(f"  {colorize_moniker('moniker://' + moniker)}")
        print(f"    Type: {color}{vtype}{C.RESET} - {desc}")
        print()

    print(f"  {C.GRAY}Version type determines how the source interprets the temporal filter.{C.RESET}")
    print(f"  {C.GRAY}Template placeholders: {{version_type}}, {{is_date}}, {{is_tenor}}, {{tenor_value}}, {{tenor_unit}}{C.RESET}")


def option_space():
    """Space info"""
    header("Moniker Service Info")
    print(f"""
  {C.BOLD}Moniker Service - Data Catalog Resolution{C.RESET}

  The service resolves "monikers" (logical data paths) to actual
  data source connections. It supports:

  - Snowflake, Oracle, REST APIs, Static files, Excel, Bloomberg, etc.
  - Ownership inheritance through path hierarchy
  - Access policies for query guardrails
  - AI/Agent-friendly metadata endpoints

  {C.BOLD}Architecture:{C.RESET}
    Client -> Moniker Service -> Returns connection info
    Client -> Connects directly to data source

  Or for convenience:
    Client -> /fetch endpoint -> Service executes query -> Returns data

  {C.BOLD}Color Legend:{C.RESET}
    {C.ORANGE}Yellow/Orange{C.RESET} - Domain/node names (prices, analytics, risk)
    {C.RED}Red{C.RESET}           - Keywords (ALL, LATEST, ANY)
    {C.BLUE}Blue{C.RESET}          - Dates (@20260101)
    {C.GREEN}Green{C.RESET}         - Business fields (AAPL, EUR, portfolio)
    {C.PURPLE}Purple{C.RESET}        - Tenors (KRD12Y, 5Y, 3M)

  {C.BOLD}URLs:{C.RESET}
    Catalog UI:   {C.CYAN}http://localhost:8050/ui{C.RESET}
    Config UI:    {C.CYAN}http://localhost:8050/config/ui{C.RESET}
    Domains UI:   {C.CYAN}http://localhost:8050/domains/ui{C.RESET}
    Swagger/API:  {C.CYAN}http://localhost:8050/docs{C.RESET}
""")


# =============================================================================
# Main Menu
# =============================================================================

MENU = f"""
  {C.CYAN}{C.BOLD}MONIKER SERVICE DEMO{C.RESET}

  {C.BOLD}1.{C.RESET}  Health Check

  {C.GRAY}--- Resolution (returns connection info) ---{C.RESET}
  {C.BOLD}2.{C.RESET}  Resolve {C.ORANGE}prices{C.RESET}.{C.ORANGE}equity{C.RESET}/{C.GREEN}AAPL{C.RESET}  (Snowflake)
  {C.BOLD}3.{C.RESET}  Resolve {C.ORANGE}analytics{C.RESET}.{C.ORANGE}risk{C.RESET}/{C.ORANGE}var{C.RESET}/portfolio-123  (REST)
  {C.BOLD}4.{C.RESET}  Resolve {C.ORANGE}reference{C.RESET}.{C.ORANGE}security{C.RESET}/{C.GREEN}ISIN{C.RESET}/{C.GREEN}US0378331005{C.RESET}  (Oracle)

  {C.GRAY}--- Fetch (server-side execution) ---{C.RESET}
  {C.BOLD}5.{C.RESET}  Fetch {C.ORANGE}prices{C.RESET}.{C.ORANGE}equity{C.RESET}/{C.GREEN}AAPL{C.RESET}
  {C.BOLD}6.{C.RESET}  Fetch {C.ORANGE}commodities{C.RESET}.{C.ORANGE}derivatives{C.RESET}/crypto/{C.GREEN}ETH{C.RESET}

  {C.GRAY}--- Metadata & Discovery ---{C.RESET}
  {C.BOLD}7.{C.RESET}  Describe {C.ORANGE}analytics{C.RESET}
  {C.BOLD}8.{C.RESET}  Lineage {C.ORANGE}analytics{C.RESET}.{C.ORANGE}risk{C.RESET}/{C.ORANGE}var{C.RESET}
  {C.BOLD}9.{C.RESET}  List {C.ORANGE}reference{C.RESET}  (children)
  {C.BOLD}10.{C.RESET} Sample {C.ORANGE}indices{C.RESET}.{C.ORANGE}sovereign{C.RESET}/developed/EU.GovBondAgg/{C.GREEN}EUR{C.RESET}/{C.RED}{C.BOLD}ALL{C.RESET}
  {C.BOLD}11.{C.RESET} Metadata {C.ORANGE}holdings{C.RESET}/positions
  {C.BOLD}12.{C.RESET} Tree {C.ORANGE}analytics{C.RESET}  (hierarchy)

  {C.GRAY}--- Batch & Catalog ---{C.RESET}
  {C.BOLD}13.{C.RESET} Batch Validate - Multiple monikers
  {C.BOLD}14.{C.RESET} List Data Domains

  {C.GRAY}--- Domain Configuration ---{C.RESET}
  {C.BOLD}15.{C.RESET} Configure Domains - View/manage governance
  {C.BOLD}16.{C.RESET} View Domain {C.ORANGE}indices{C.RESET} - Governance details
  {C.BOLD}17.{C.RESET} List Full Mapping

  {C.GRAY}--- Complex Moniker Patterns ---{C.RESET}
  {C.BOLD}18.{C.RESET} Complex Index {C.ORANGE}index{C.RESET}.{C.ORANGE}global{C.RESET}/BBGGlobalAggTreasury/{C.GREEN}GBP{C.RESET}/MWS_LIBOR
  {C.BOLD}19.{C.RESET} Gov Rates {C.ORANGE}rates{C.RESET}.{C.ORANGE}gov{C.RESET}/{C.GREEN}DKK{C.RESET}/DK0.125Mar2026/KRD/{C.PURPLE}KRD12Y{C.RESET}
  {C.BOLD}20.{C.RESET} Versioned Sub-resource {C.ORANGE}securities{C.RESET}/ID{C.GRAY}@{C.RESET}{C.BLUE}20260101{C.RESET}/{C.CYAN}details{C.RESET}
  {C.BOLD}21.{C.RESET} Temporal Versions ({C.BLUE}@date{C.RESET}, {C.RED}{C.BOLD}@latest{C.RESET}, {C.PURPLE}@3M{C.RESET}, {C.RED}{C.BOLD}@all{C.RESET})

  {C.BOLD}SPACE{C.RESET} - Service Info    {C.BOLD}Q{C.RESET} - Quit
"""


OPTIONS = {
    '1': option_1_health,
    '2': option_2_resolve_equity,
    '3': option_3_resolve_rest,
    '4': option_4_resolve_oracle,
    '5': option_5_fetch_equity,
    '6': option_6_fetch_crypto,
    '7': option_7_describe,
    '8': option_8_lineage,
    '9': option_9_list_children,
    '10': option_10_sample,
    '11': option_11_metadata,
    '12': option_12_tree,
    '13': option_13_batch_validate,
    '14': option_14_list_domains,
    '15': option_15_configure_domains,
    '16': option_16_view_domain,
    '17': option_17_list_mappings,
    '18': option_18_complex_index,
    '19': option_19_gov_rates,
    '20': option_20_versioned_subresource,
    '21': option_21_temporal_versions,
    ' ': option_space,
}


def main():
    print("\n" + C.CYAN + "=" * 60 + C.RESET)
    print(f"  {C.BOLD}Moniker Service Demo{C.RESET}")
    print(f"  Ensure service is running: {C.CYAN}python start.py{C.RESET}")
    print(C.CYAN + "=" * 60 + C.RESET)

    while True:
        print(MENU)
        choice = input(f"  {C.BOLD}Select option:{C.RESET} ").strip().lower()

        if choice == 'q':
            print(f"\n  {C.GREEN}Goodbye!{C.RESET}\n")
            break
        elif choice in OPTIONS:
            OPTIONS[choice]()
            input(f"\n  {C.GRAY}Press Enter to continue...{C.RESET}")
        else:
            print(f"\n  {C.RED}Invalid option: {choice}{C.RESET}")


if __name__ == "__main__":
    main()
