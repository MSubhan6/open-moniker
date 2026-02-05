#!/usr/bin/env python
"""
Sample Queries Demo - Interactive demonstration of the Moniker Service.

Run with: python demo/sample_queries.py
          python demo/sample_queries.py --url http://myserver:8060

Requires the service to be running: python start.py

ADDING NEW MONIKERS:
Edit demo_monikers.yaml in the project root. Run 'python config.py' to create
it from sample_demo_monikers.yaml if it doesn't exist.
"""

import argparse
import json
import os
import re
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

import yaml
from colorama import init, Fore, Style
init(autoreset=True)

# Default URL - can be overridden by env var or command line
DEFAULT_URL = "http://localhost:8060"
BASE_URL = os.environ.get("MONIKER_SERVICE_URL", DEFAULT_URL)

# Global - populated at startup
DEMO_MONIKERS: list[dict] = []


# =============================================================================
# Color Shortcuts
# =============================================================================

class C:
    """Color shortcuts using colorama."""
    RESET = Style.RESET_ALL
    BOLD = Style.BRIGHT
    DIM = Style.DIM

    WHITE = Fore.WHITE
    ORANGE = Fore.YELLOW
    RED = Fore.RED
    BLUE = Fore.BLUE
    GREEN = Fore.GREEN
    PURPLE = Fore.MAGENTA
    GRAY = Fore.LIGHTBLACK_EX
    CYAN = Fore.CYAN
    YELLOW = Fore.YELLOW


def colorize_path(path: str) -> str:
    """Colorize a moniker path with semantic highlighting."""
    parts = re.split(r'([/@.])', path)
    result = []
    seen_first_segment = False

    date_pattern = re.compile(r'^@?\d{8}$')
    tenor_pattern = re.compile(r'^(KRD|DV01|CR01)?\d*[YMWD]$|^KRD\d+[YMWD]?$', re.IGNORECASE)
    keyword_pattern = re.compile(r'^(ALL|LATEST|ANY)$', re.IGNORECASE)
    business_fields = {'AAPL', 'MSFT', 'GOOG', 'TSLA', 'ETH', 'BTC', 'EUR', 'USD', 'GBP', 'DKK',
                       'portfolio', 'fund', 'account', 'ISIN', 'CUSIP', 'SEDOL',
                       'equity', 'bond', 'fx', 'rates', 'credit', 'commodity', 'bitcoin',
                       'currencies'}
    subresource_keywords = {'details', 'history', 'metadata', 'schema', 'audit', 'corporate', 'actions'}

    for part in parts:
        if not part:
            continue
        elif part in '/@.':
            result.append(C.GRAY + part + C.RESET)
        elif not seen_first_segment and part not in '/@.':
            # First segment (top-level domain) is always yellow
            result.append(C.YELLOW + part + C.RESET)
            seen_first_segment = True
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
        elif part.startswith('US') and len(part) > 8:
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
# Load Demo Monikers from YAML
# =============================================================================

def load_demo_monikers() -> list[dict]:
    """Load demo monikers from YAML config file.

    Looks for (in order):
    1. demo/demo_monikers.yaml (local customizations, not in git)
    2. demo/sample_demo_monikers.yaml (committed sample)
    """
    script_dir = Path(__file__).parent

    config_paths = [
        script_dir / "demo_monikers.yaml",          # Local (not committed)
        script_dir / "sample_demo_monikers.yaml",   # Sample (committed)
    ]

    for config_path in config_paths:
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                monikers = data.get("monikers", [])
                if monikers:
                    print(f"  Loaded {len(monikers)} demo monikers from {config_path.name}")
                    return monikers

    print(f"  {C.YELLOW}Warning: No demo monikers file found, using built-in defaults{C.RESET}")
    return [
        {"moniker": "prices.equity/AAPL", "action": "resolve", "desc": "Equity Price"},
        {"moniker": "analytics", "action": "describe", "desc": "Describe Analytics"},
    ]


# =============================================================================
# API Functions
# =============================================================================

def fetch_api(endpoint: str, method: str = "GET", data: dict = None) -> dict | None:
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


def header(title: str):
    """Print a section header."""
    print("\n" + C.CYAN + "=" * 60 + C.RESET)
    print(f"  {C.BOLD}{title}{C.RESET}")
    print(C.CYAN + "=" * 60 + C.RESET)


# =============================================================================
# Generic Handlers - Display results for each action type
# =============================================================================

def handle_resolve(moniker: str, note: str = ""):
    """Generic resolve handler - works for any source type."""
    print(f"\nResolving: {colorize_moniker('moniker://' + moniker)}")
    if note:
        print(f"{C.GRAY}{note}{C.RESET}\n")

    result = fetch_api(f"/resolve/{moniker}")
    if result:
        print(f"  {C.BOLD}Source Type:{C.RESET} {C.ORANGE}{result['source_type']}{C.RESET}")
        print(f"  {C.BOLD}Binding Path:{C.RESET} {colorize_path(result['binding_path'])}")

        conn = result.get('connection', {})
        print(f"\n  {C.BOLD}Connection:{C.RESET}")
        for key, val in conn.items():
            if val and key not in ('password', 'secret', 'token'):
                print(f"    {key}: {C.GREEN}{val}{C.RESET}")

        query = result.get('query', '')
        if query:
            print(f"\n  {C.BOLD}Query:{C.RESET}")
            if len(query) > 300:
                print(f"    {query[:300]}...")
            else:
                print(f"    {query}")


def handle_fetch(moniker: str, note: str = ""):
    """Generic fetch handler - server-side execution."""
    print(f"\nFetching: {colorize_moniker('moniker://' + moniker)}")
    if note:
        print(f"{C.GRAY}{note}{C.RESET}\n")

    result = fetch_api(f"/fetch/{moniker}?limit=5")
    if result:
        print(f"  {C.BOLD}Source Type:{C.RESET} {C.ORANGE}{result.get('source_type', 'N/A')}{C.RESET}")
        print(f"  {C.BOLD}Rows returned:{C.RESET} {C.GREEN}{result.get('row_count', 0)}{C.RESET}")
        print(f"  {C.BOLD}Columns:{C.RESET} {result.get('columns', [])}")
        if result.get('execution_time_ms'):
            print(f"  {C.BOLD}Execution time:{C.RESET} {result['execution_time_ms']}ms")

        if result.get('data'):
            print(f"\n  {C.BOLD}Data sample:{C.RESET}")
            for row in result['data'][:3]:
                print(f"    {row}")


def handle_describe(moniker: str, note: str = ""):
    """Generic describe handler."""
    print(f"\nDescribing: {colorize_moniker('moniker://' + moniker)}")
    if note:
        print(f"{C.GRAY}{note}{C.RESET}\n")

    result = fetch_api(f"/describe/{moniker}")
    if result:
        print(f"  {C.BOLD}Path:{C.RESET} {colorize_path(result['path'])}")
        print(f"  {C.BOLD}Display Name:{C.RESET} {result.get('display_name', 'N/A')}")
        print(f"  {C.BOLD}Classification:{C.RESET} {C.YELLOW}{result.get('classification', 'N/A')}{C.RESET}")
        print(f"  {C.BOLD}Has Source:{C.RESET} {result.get('has_source_binding', False)}")

        ownership = result.get('ownership', {})
        if ownership:
            print(f"\n  {C.BOLD}Ownership:{C.RESET}")
            for key, val in ownership.items():
                if val and not key.endswith('_source') and not key.endswith('_at'):
                    print(f"    {key}: {C.GREEN}{val}{C.RESET}")


def handle_lineage(moniker: str, note: str = ""):
    """Generic lineage handler."""
    print(f"\nLineage for: {colorize_moniker('moniker://' + moniker)}")
    if note:
        print(f"{C.GRAY}{note}{C.RESET}\n")

    result = fetch_api(f"/lineage/{moniker}")
    if result:
        print(f"  {C.BOLD}Path:{C.RESET} {colorize_path(result['path'])}")
        print(f"\n  {C.BOLD}Ownership inheritance:{C.RESET}")
        for key, val in result.get('ownership', {}).items():
            if not key.endswith('_at') and not key.endswith('_defined_at') and val:
                source = result['ownership'].get(f"{key}_defined_at", "unknown")
                print(f"    {key}: {C.GREEN}{val}{C.RESET} (from: {C.ORANGE}{source}{C.RESET})")


def handle_list(moniker: str, note: str = ""):
    """Generic list handler."""
    print(f"\nListing children of: {colorize_moniker('moniker://' + moniker)}")
    if note:
        print(f"{C.GRAY}{note}{C.RESET}\n")

    result = fetch_api(f"/list/{moniker}")
    if result:
        print(f"  {C.BOLD}Path:{C.RESET} {colorize_path(result['path'])}")
        children = result.get('children', [])
        print(f"  {C.BOLD}Children ({len(children)}):{C.RESET}")
        for child in children:
            print(f"    - {colorize_path(child)}")


def handle_sample(moniker: str, note: str = ""):
    """Generic sample handler."""
    print(f"\nSampling: {colorize_moniker('moniker://' + moniker)}")
    if note:
        print(f"{C.GRAY}{note}{C.RESET}\n")

    result = fetch_api(f"/sample/{moniker}?limit=3")
    if result:
        print(f"  {C.BOLD}Columns:{C.RESET} {result.get('columns', [])}")
        print(f"  {C.BOLD}Row count:{C.RESET} {result.get('row_count', 0)}")

        if result.get('data'):
            print(f"\n  {C.BOLD}Sample rows:{C.RESET}")
            for row in result['data']:
                print(f"    {row}")


def handle_metadata(moniker: str, note: str = ""):
    """Generic metadata handler."""
    print(f"\nMetadata for: {colorize_moniker('moniker://' + moniker)}")
    if note:
        print(f"{C.GRAY}{note}{C.RESET}\n")

    result = fetch_api(f"/metadata/{moniker}")
    if result:
        print(f"  {C.BOLD}Path:{C.RESET} {colorize_path(result['path'])}")
        print(f"  {C.BOLD}Display Name:{C.RESET} {result.get('display_name', 'N/A')}")
        if result.get('schema'):
            print(f"  {C.BOLD}Granularity:{C.RESET} {result['schema'].get('granularity', 'N/A')}")
        if result.get('ownership'):
            print(f"  {C.BOLD}Owner:{C.RESET} {C.GREEN}{result['ownership'].get('accountable_owner', 'N/A')}{C.RESET}")


def handle_tree(moniker: str, note: str = ""):
    """Generic tree handler."""
    print(f"\nTree view of: {colorize_path(moniker)}")
    if note:
        print(f"{C.GRAY}{note}{C.RESET}\n")

    result = fetch_api(f"/tree/{moniker}")
    if result:
        def print_tree(node, indent=0):
            prefix = "  " * indent
            name = colorize_path(node['name'])
            source = f" {C.ORANGE}{node.get('source_type')}{C.RESET}" if node.get('source_type') else ""
            print(f"{prefix}- {name}/{source}")
            for child in node.get('children', []):
                print_tree(child, indent + 1)
        print_tree(result)


HANDLERS = {
    'resolve': handle_resolve,
    'fetch': handle_fetch,
    'describe': handle_describe,
    'lineage': handle_lineage,
    'list': handle_list,
    'sample': handle_sample,
    'metadata': handle_metadata,
    'tree': handle_tree,
}


# =============================================================================
# Special Menu Options
# =============================================================================

def option_health():
    """Health Check"""
    header("Health Check")
    print("\nChecking service health...")
    result = fetch_api("/health")
    if result:
        print(f"\n  {C.BOLD}Status:{C.RESET} {C.GREEN}{result['status']}{C.RESET}")
        print(f"  {C.BOLD}Cache size:{C.RESET} {result['cache']['size']}")
        print(f"  {C.BOLD}Telemetry emitted:{C.RESET} {result['telemetry']['emitted']}")


def option_batch_validate():
    """Batch Validate - Multiple monikers"""
    header("Batch Moniker Validation")

    monikers = [d['moniker'] for d in DEMO_MONIKERS if d['action'] == 'resolve'][:6]
    monikers.append("invalid/path/does/not/exist")

    print(f"\nValidating {len(monikers)} monikers...\n")

    for moniker in monikers:
        result = fetch_api(f"/describe/{moniker}")
        print(f"  {colorize_moniker('moniker://' + moniker)}")
        if result:
            status = f"{C.GREEN}HAS SOURCE{C.RESET}" if result.get('has_source_binding') else f"{C.GRAY}NO SOURCE{C.RESET}"
            print(f"    -> {status}, classification: {result.get('classification', 'N/A')}")
        else:
            print(f"    -> {C.RED}NOT FOUND{C.RESET}")


def option_list_domains():
    """List Data Domains"""
    header("List Data Domains")
    print("\nTop-level data domains in the catalog:\n")
    result = fetch_api("/catalog")
    if result:
        domains = set()
        for path in result.get('paths', []):
            top = path.split('/')[0].split('.')[0]
            domains.add(top)

        domains = sorted(domains)
        print(f"  Found {C.GREEN}{len(domains)}{C.RESET} top-level domains:\n")
        for i, domain in enumerate(domains, 1):
            info = fetch_api(f"/describe/{domain}")
            if info:
                desc = info.get('description', '')[:50] or info.get('display_name', domain)
                print(f"  {i:2}. {colorize_path(domain):20} - {desc}")
            else:
                print(f"  {i:2}. {colorize_path(domain)}")


def option_configure_domains():
    """Configure Domains"""
    header("Configure Domains")
    print("\nData domains are top-level organizational units with governance metadata.\n")
    result = fetch_api("/domains")
    if result:
        domains = result.get('domains', [])
        print(f"  Found {C.GREEN}{len(domains)}{C.RESET} configured domains:\n")

        for d in domains:
            conf_badge = ""
            if d.get('confidentiality') in ('confidential', 'strictly_confidential'):
                conf_badge = f" [{C.RED}{d['confidentiality'].upper()}{C.RESET}]"
            pii_badge = f" [{C.RED}PII{C.RESET}]" if d.get('pii') else ""

            print(f"  - {colorize_path(d['name']):15} {d.get('short_code', ''):5} - {d.get('display_name', '')}{conf_badge}{pii_badge}")

        print(f"\n  {C.BOLD}Domain Config UI:{C.RESET} {C.CYAN}{BASE_URL}/domains/ui{C.RESET}")


def option_info():
    """Service Info"""
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
    Catalog UI:   {C.CYAN}{BASE_URL}/ui{C.RESET}
    Config UI:    {C.CYAN}{BASE_URL}/config/ui{C.RESET}
    Domains UI:   {C.CYAN}{BASE_URL}/domains/ui{C.RESET}
    Swagger/API:  {C.CYAN}{BASE_URL}/docs{C.RESET}
""")


# =============================================================================
# Menu Generation
# =============================================================================

def build_menu():
    """Build menu string and option handlers from DEMO_MONIKERS."""
    lines = [
        f"\n  {C.CYAN}{C.BOLD}MONIKER SERVICE DEMO{C.RESET}",
        "",
        f"  {C.BOLD}H.{C.RESET}  Health Check",
        "",
    ]

    options = {}
    option_num = 1

    for item in DEMO_MONIKERS:
        moniker_colored = colorize_moniker(item['moniker'])
        lines.append(f"  {C.BOLD}{option_num:2}.{C.RESET} {moniker_colored}")

        options[str(option_num)] = (item['action'], item['moniker'], item.get('note', ''), item['desc'])
        option_num += 1

    lines.extend([
        "",
        f"  {C.BOLD}B.{C.RESET}  Batch Validate",
        f"  {C.BOLD}D.{C.RESET}  List Data Domains",
        f"  {C.BOLD}C.{C.RESET}  Configure Domains",
        "",
        f"  {C.BOLD}I.{C.RESET}  Service Info",
        f"  {C.BOLD}Q.{C.RESET}  Quit",
        "",
    ])

    return '\n'.join(lines), options


def run_option(options: dict, choice: str):
    """Run the selected option."""
    if choice in options:
        action, moniker, note, desc = options[choice]
        header(f"{desc}")
        handler = HANDLERS.get(action)
        if handler:
            handler(moniker, note)
        else:
            print(f"  {C.RED}Unknown action: {action}{C.RESET}")
    elif choice == 'h':
        option_health()
    elif choice == 'b':
        option_batch_validate()
    elif choice == 'd':
        option_list_domains()
    elif choice == 'c':
        option_configure_domains()
    elif choice == 'i':
        option_info()
    else:
        print(f"\n  {C.RED}Invalid option: {choice}{C.RESET}")
        return False
    return True


# =============================================================================
# Main
# =============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Interactive demo for the Moniker Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python demo/sample_queries.py
  python demo/sample_queries.py --url http://myserver:8060
  MONIKER_SERVICE_URL=http://myserver:8060 python demo/sample_queries.py
        """
    )
    parser.add_argument(
        "--url", "-u",
        default=None,
        help=f"Service URL (default: $MONIKER_SERVICE_URL or {DEFAULT_URL})"
    )
    return parser.parse_args()


def main():
    global DEMO_MONIKERS, BASE_URL

    args = parse_args()

    # Override BASE_URL if provided via command line
    if args.url:
        BASE_URL = args.url

    print("\n" + C.CYAN + "=" * 60 + C.RESET)
    print(f"  {C.BOLD}Moniker Service Demo{C.RESET}")
    print(f"  Service: {C.CYAN}{BASE_URL}{C.RESET}")
    print(C.CYAN + "=" * 60 + C.RESET)

    # Load monikers from YAML
    DEMO_MONIKERS = load_demo_monikers()

    menu_str, options = build_menu()

    while True:
        print(menu_str)
        choice = input(f"  {C.BOLD}Select option:{C.RESET} ").strip().lower()

        if choice == 'q':
            print(f"\n  {C.GREEN}Goodbye!{C.RESET}\n")
            break
        elif run_option(options, choice):
            input(f"\n  {C.GRAY}Press Enter to continue...{C.RESET}")


if __name__ == "__main__":
    main()
