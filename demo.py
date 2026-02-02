#!/usr/bin/env python3
"""
Moniker Service Demo Script

Demonstrates the architecture:
- Service resolves monikers → returns WHERE to get data
- Client connects directly to sources → gets actual data
- Telemetry tracks both resolution and access

Run the service first:
    pip install -e .
    python -m moniker_svc.main

Then run this demo:
    python demo.py
"""

from __future__ import annotations

import sys
import time

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init()
except ImportError:
    print("Install colorama for colored output: pip install colorama")
    class Fore:
        CYAN = YELLOW = GREEN = MAGENTA = BLUE = RED = WHITE = ""
    class Style:
        RESET_ALL = BRIGHT = DIM = ""


def c(text: str, color: str) -> str:
    return f"{color}{text}{Style.RESET_ALL}"


def header(text: str) -> None:
    print(f"\n{c('=' * 60, Style.DIM)}")
    print(c(f"  {text}", Style.BRIGHT))
    print(c('=' * 60, Style.DIM))


def moniker_display(path: str) -> str:
    """Format a moniker path with colors."""
    scheme = c("moniker://", Fore.CYAN)
    segments = path.split("/")

    colors = [Fore.YELLOW, Fore.GREEN, Fore.MAGENTA, Fore.BLUE]
    colored_parts = []

    for i, seg in enumerate(segments):
        colored_parts.append(c(seg, colors[i % len(colors)]))

    return scheme + "/".join(colored_parts)


def demo_architecture():
    """Demonstrate the architecture."""
    header("ARCHITECTURE: RESOLUTION SERVICE + CLIENT LIBRARY")

    print(f"""
  The Moniker Service is a {c('RESOLUTION SERVICE', Style.BRIGHT)}, not a data proxy.

  ┌─────────────────────────────────────────────────────────────────┐
  │  Your Notebook / Script                                         │
  │                                                                 │
  │    {c('from moniker_client import read', Fore.CYAN)}                            │
  │    {c('data = read("market-data/prices/equity/AAPL")', Fore.CYAN)}              │
  │                                                                 │
  └───────────────────────────┬─────────────────────────────────────┘
                              │
                              ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  {c('moniker-client', Style.BRIGHT)} (Python library)                                  │
  │                                                                 │
  │    {c('1. RESOLVE', Fore.YELLOW)} → Calls Moniker Service                           │
  │       GET /resolve/market-data/prices/equity/AAPL               │
  │       Response: source_type=snowflake, query="SELECT..."        │
  │                                                                 │
  │    {c('2. FETCH', Fore.GREEN)} → Connects DIRECTLY to Snowflake                   │
  │       Using YOUR credentials (from environment)                 │
  │       Executes query, gets actual data                          │
  │                                                                 │
  │    {c('3. TELEMETRY', Fore.CYAN)} → Reports access back to service                 │
  │       POST /telemetry/access (non-blocking)                     │
  │                                                                 │
  │    {c('4. RETURN', Fore.MAGENTA)} → Data returned to your code                       │
  │                                                                 │
  └───────────────────────────┬─────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    ┌──────────┐        ┌──────────┐        ┌──────────┐
    │{c('Snowflake', Fore.CYAN)} │        │ {c('Oracle', Fore.GREEN)}  │        │{c('Bloomberg', Fore.YELLOW)}│
    └──────────┘        └──────────┘        └──────────┘
      (direct)            (direct)            (direct)
""")

    print(f"\n  {c('KEY BENEFITS:', Style.BRIGHT)}")
    print(f"  • Service doesn't become bottleneck for ALL firm data")
    print(f"  • Credentials stay local (not sent to service)")
    print(f"  • Data flows directly from source to your code")
    print(f"  • Telemetry tracks {c('who', Fore.YELLOW)} accessed {c('what', Fore.GREEN)}")


def demo_resolution():
    """Demonstrate resolution response."""
    header("WHAT THE SERVICE RETURNS (Resolution)")

    print(f"""
  When you call: {c('read("market-data/prices/equity/AAPL")', Fore.CYAN)}

  The client calls: {c('GET /resolve/market-data/prices/equity/AAPL', Style.DIM)}

  Service returns:
  ┌─────────────────────────────────────────────────────────────────┐
  │ {{                                                                │
  │   "moniker": "moniker://market-data/prices/equity/AAPL",        │
  │   "path": "market-data/prices/equity/AAPL",                     │
  │                                                                 │
  │   {c('"source_type": "snowflake"', Fore.YELLOW)},                                      │
  │   {c('"connection"', Fore.GREEN)}: {{                                                  │
  │     "account": "acme.us-east-1",                                │
  │     "warehouse": "COMPUTE_WH",                                  │
  │     "database": "MARKET_DATA",                                  │
  │     "schema": "PRICES"                                          │
  │   }},                                                            │
  │   {c('"query"', Fore.MAGENTA)}: "SELECT symbol, price FROM EQUITY_PRICES             │
  │            WHERE symbol = 'AAPL'",                              │
  │                                                                 │
  │   {c('"ownership"', Fore.CYAN)}: {{                                                    │
  │     "accountable_owner": "jane.smith@firm.com",                 │
  │     "data_specialist": "market-data-team@firm.com",             │
  │     "support_channel": "#market-data-support"                   │
  │   }}                                                             │
  │ }}                                                                │
  └─────────────────────────────────────────────────────────────────┘

  {c('Notice:', Style.BRIGHT)} No credentials! No actual data! Just {c('WHERE', Fore.YELLOW)} and {c('HOW', Fore.GREEN)}.
""")


def demo_client_usage():
    """Show client usage examples."""
    header("CLIENT LIBRARY USAGE")

    print(f"""
  {c('Simple usage:', Style.BRIGHT)}

    from moniker_client import read, describe

    # Read data
    data = read("market-data/prices/equity/AAPL")
    print(data)
    # [{{'symbol': 'AAPL', 'price': 150.25, 'currency': 'USD'}}]

    # Get ownership info
    info = describe("market-data/prices/equity")
    print(f"Owner: {{info['ownership']['accountable_owner']}}")
    print(f"Support: {{info['ownership']['support_channel']}}")

  {c('Configure via environment:', Style.BRIGHT)}

    export MONIKER_SERVICE_URL=http://moniker-svc:8050
    export MONIKER_APP_ID=my-notebook
    export MONIKER_TEAM=quant-research

    # Database credentials (used by client, NOT sent to service)
    export SNOWFLAKE_USER=your_user
    export SNOWFLAKE_PASSWORD=your_password

  {c('Or configure in code:', Style.BRIGHT)}

    from moniker_client import MonikerClient, ClientConfig

    client = MonikerClient(config=ClientConfig(
        service_url="http://moniker-svc:8050",
        app_id="my-app",
    ))
    data = client.read("market-data/prices/equity/AAPL")
""")


def demo_ownership():
    """Demonstrate ownership hierarchy."""
    header("HIERARCHICAL OWNERSHIP")

    print(f"""
  Ownership is defined at nodes and inherited down:

  {c('market-data/', Fore.YELLOW)} ← {c('Ownership defined here:', Style.BRIGHT)}
  │                   • Accountable Owner: jane.smith@firm.com
  │                   • Data Specialist: market-team@firm.com
  │                   • Support: #market-data-support
  │
  ├── {c('prices/', Fore.GREEN)} ← {c('Inherits all from parent', Style.DIM)}
  │   │
  │   ├── {c('equity/', Fore.MAGENTA)} ← {c('Override:', Style.BRIGHT)} Data Specialist: equity-team@firm.com
  │   │   │           {c('(other fields inherited)', Style.DIM)}
  │   │   │
  │   │   └── {c('AAPL', Fore.BLUE)} ← Inherits from equity/
  │   │
  │   └── {c('bloomberg/', Fore.MAGENTA)} ← {c('Override:', Style.BRIGHT)} Data Specialist: bloomberg-team@firm.com
  │
  └── {c('indices/', Fore.GREEN)}

  {c('The Ownership Triple:', Style.BRIGHT)}
  {c('1. Accountable Owner', Fore.CYAN)} - Executive responsible for data governance
  {c('2. Data Specialist', Fore.CYAN)}   - Technical SME who understands the data
  {c('3. Support Channel', Fore.CYAN)}   - Where to get help (#slack or Teams)
""")


def demo_telemetry():
    """Demonstrate telemetry."""
    header("TELEMETRY: WHO'S USING WHAT")

    print(f"""
  {c('TWO types of telemetry:', Style.BRIGHT)}

  {c('1. Resolution Events', Fore.YELLOW)} (from service)
     When someone {c('asks', Style.BRIGHT)} where data lives

  {c('2. Access Events', Fore.GREEN)} (from client)
     When someone actually {c('fetches', Style.BRIGHT)} data

  ┌─────────────────────────────────────────────────────────────────┐
  │ {c('Access Event:', Style.BRIGHT)}                                                    │
  │                                                                 │
  │ timestamp:     2024-01-15T10:30:45.123Z                         │
  │ request_id:    a1b2c3d4-e5f6-7890                               │
  │                                                                 │
  │ {c('WHO:', Fore.YELLOW)}                                                              │
  │   app_id:      jupyter-notebook-42                              │
  │   team:        quant-research                                   │
  │                                                                 │
  │ {c('WHAT:', Fore.GREEN)}                                                             │
  │   moniker:     market-data/prices/equity/AAPL                   │
  │   operation:   read                                             │
  │   outcome:     success                                          │
  │                                                                 │
  │ {c('HOW:', Fore.CYAN)}                                                               │
  │   source:      snowflake                                        │
  │   latency_ms:  142.5                                            │
  │   row_count:   1                                                │
  │   owner:       jane.smith@firm.com                              │
  └─────────────────────────────────────────────────────────────────┘

  This enables:
  • {c('Data lineage', Fore.YELLOW)} - who accessed what data
  • {c('Usage analytics', Fore.GREEN)} - which datasets are popular
  • {c('Chargeback', Fore.CYAN)} - charge teams for data usage
  • {c('Compliance', Fore.MAGENTA)} - audit trail for regulated data
""")


def main():
    print(c("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   {title}   ║
║                                                              ║
║   Resolution Service + Client Library Architecture           ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""".format(title=c("MONIKER SERVICE", Style.BRIGHT)), Fore.CYAN))

    demo_architecture()
    input(f"\n{c('Press Enter to continue...', Style.DIM)}")

    demo_resolution()
    input(f"\n{c('Press Enter to continue...', Style.DIM)}")

    demo_client_usage()
    input(f"\n{c('Press Enter to continue...', Style.DIM)}")

    demo_ownership()
    input(f"\n{c('Press Enter to continue...', Style.DIM)}")

    demo_telemetry()

    print(f"\n\n{c('Demo complete!', Style.BRIGHT)}")
    print(f"\n{c('To run:', Style.BRIGHT)}")
    print(f"  # Start the service")
    print(f"  {c('cd /path/to/open-moniker-svc', Style.DIM)}")
    print(f"  {c('pip install -e .', Fore.CYAN)}")
    print(f"  {c('python -m moniker_svc.main', Fore.CYAN)}")
    print(f"\n  # Use the client")
    print(f"  {c('cd client && pip install -e .', Style.DIM)}")
    print(f"  {c('python', Fore.CYAN)}")
    print(f"  {c('>>> from moniker_client import read, describe', Fore.GREEN)}")
    print(f"  {c('>>> describe(\"market-data\")', Fore.GREEN)}")


if __name__ == "__main__":
    main()
