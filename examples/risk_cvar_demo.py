#!/usr/bin/env python3
"""
Risk CVaR Demo - Oracle Risk Measures via Moniker Service
==========================================================

This demo shows how to access CVaR (Conditional Value at Risk) data
from an Oracle database using the moniker service.

The demo uses a mock Oracle adapter with sample data, so no real
Oracle connection is needed.

Usage:
    # Start the service in one terminal:
    cd /home/user/open-moniker-svc
    python -m uvicorn moniker_svc.main:app --port 8000

    # Run this demo in another terminal:
    python examples/risk_cvar_demo.py

Or run in standalone mode (starts service automatically):
    python examples/risk_cvar_demo.py --standalone
"""

import sys
import time
import argparse
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "client"))
sys.path.insert(0, str(project_root / "src"))


def run_demo():
    """Run the CVaR demo."""
    print("=" * 60)
    print("Risk CVaR Demo - Moniker Service")
    print("=" * 60)
    print()

    # Enable mock Oracle adapter
    from moniker_client.adapters.mock_oracle import enable_mock_oracle
    enable_mock_oracle()

    # Import client functions
    from moniker_client import MonikerClient, ClientConfig

    # Create client
    config = ClientConfig(
        service_url="http://localhost:8000",
        app_id="risk-cvar-demo",
        team="risk-analytics",
        report_telemetry=False,  # Disable for demo
    )
    client = MonikerClient(config=config)

    # Demo 1: Describe the risk.cvar domain
    print("\n" + "=" * 60)
    print("1. Describe risk.cvar domain")
    print("=" * 60)
    try:
        info = client.describe("risk.cvar")
        print(f"   Display Name: {info.get('display_name')}")
        print(f"   Description:  {info.get('description')}")
        print(f"   Owner:        {info.get('ownership', {}).get('accountable_owner')}")
        print(f"   Specialist:   {info.get('ownership', {}).get('data_specialist')}")
        print(f"   Support:      {info.get('ownership', {}).get('support_channel')}")
    except Exception as e:
        print(f"   Error: {e}")

    # Demo 2: Resolve a moniker to see the generated query
    print("\n" + "=" * 60)
    print("2. Resolve moniker -> see generated SQL")
    print("=" * 60)
    monikers_to_resolve = [
        "risk.cvar/758-A/USD/ALL",
        "risk.cvar/758-A/ALL/ALL",
        "risk.cvar/ALL/USD/B0YHY8V7",
    ]
    for moniker in monikers_to_resolve:
        print(f"\n   Moniker: {moniker}")
        try:
            resolved = client.resolve(moniker)
            print(f"   Source:  {resolved.source_type}")
            print(f"   Binding: {resolved.binding_path}")
            print(f"   Query preview:")
            # Show first few lines of query
            query_lines = resolved.query.strip().split("\n")[:6]
            for line in query_lines:
                print(f"      {line}")
            if len(resolved.query.strip().split("\n")) > 6:
                print("      ...")
        except Exception as e:
            print(f"   Error: {e}")

    # Demo 3: Fetch data for specific portfolio
    print("\n" + "=" * 60)
    print("3. Fetch CVaR data for portfolio 758-A, USD")
    print("=" * 60)
    try:
        data = client.read("risk.cvar/758-A/USD/ALL")
        print(f"   Returned {len(data)} rows")
        if data:
            print(f"   Columns: {list(data[0].keys())}")
            print("\n   Sample rows (first 5):")
            for row in data[:5]:
                print(f"      {row['ASOF_DATE']} | {row['PORT_NO']}-{row['PORT_TYPE']} | "
                      f"{row['SSM_ID']} | {row['BASE_CURRENCY']} | CVAR: {row['CVAR']:.6f}")

            # Show date range
            dates = sorted(set(r['ASOF_DATE'] for r in data))
            print(f"\n   Date range: {dates[0]} to {dates[-1]} ({len(dates)} dates)")
    except Exception as e:
        print(f"   Error: {e}")

    # Demo 4: Fetch data for specific security across all portfolios
    print("\n" + "=" * 60)
    print("4. Fetch CVaR for security B0YHY8V7 across ALL portfolios")
    print("=" * 60)
    try:
        data = client.read("risk.cvar/ALL/ALL/B0YHY8V7")
        print(f"   Returned {len(data)} rows")
        if data:
            # Group by portfolio
            portfolios = set((r['PORT_NO'], r['PORT_TYPE']) for r in data)
            print(f"   Portfolios with this security: {len(portfolios)}")
            for port in sorted(portfolios):
                count = sum(1 for r in data if r['PORT_NO'] == port[0] and r['PORT_TYPE'] == port[1])
                print(f"      {port[0]}-{port[1]}: {count} records")
    except Exception as e:
        print(f"   Error: {e}")

    # Demo 5: Fetch ALL data (dangerous in production!)
    print("\n" + "=" * 60)
    print("5. Fetch ALL/ALL/ALL (full dataset - use with caution!)")
    print("=" * 60)
    try:
        start = time.time()
        data = client.read("risk.cvar/ALL/ALL/ALL")
        elapsed = time.time() - start
        print(f"   Returned {len(data)} rows in {elapsed:.2f}s")

        # Summarize
        portfolios = set((r['PORT_NO'], r['PORT_TYPE']) for r in data)
        currencies = set(r['BASE_CURRENCY'] for r in data)
        securities = set(r['SSM_ID'] for r in data)
        dates = set(r['ASOF_DATE'] for r in data)

        print(f"   Summary:")
        print(f"      Portfolios: {len(portfolios)}")
        print(f"      Currencies: {len(currencies)} - {sorted(currencies)}")
        print(f"      Securities: {len(securities)}")
        print(f"      Dates:      {len(dates)}")
    except Exception as e:
        print(f"   Error: {e}")

    # Demo 6: Use with pandas
    print("\n" + "=" * 60)
    print("6. Convert to pandas DataFrame for analysis")
    print("=" * 60)
    try:
        import pandas as pd

        data = client.read("risk.cvar/758-A/USD/ALL")
        df = pd.DataFrame(data)

        print(f"   DataFrame shape: {df.shape}")
        print(f"\n   CVaR statistics by security:")
        stats = df.groupby('SSM_ID')['CVAR'].agg(['mean', 'std', 'min', 'max'])
        print(stats.to_string(index=True))

        print(f"\n   CVaR over time (daily mean):")
        daily = df.groupby('ASOF_DATE')['CVAR'].mean()
        print(daily.head(10).to_string())

    except ImportError:
        print("   pandas not installed - skipping DataFrame demo")
    except Exception as e:
        print(f"   Error: {e}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


def run_standalone():
    """Run demo with embedded service."""
    import subprocess
    import os
    import tempfile
    import yaml

    print("Starting moniker service...")

    # Create a temporary config file that points to sample_catalog.yaml
    config = {
        "server": {"port": 8000},
        "telemetry": {"enabled": False},
        "cache": {"enabled": True, "max_size": 1000, "default_ttl_seconds": 60},
        "catalog": {"definition_file": str(project_root / "sample_catalog.yaml")},
        "auth": {"enabled": False},
    }

    # Write temp config
    config_file = project_root / ".demo_config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config, f)

    # Set environment variable
    env = os.environ.copy()
    env["MONIKER_CONFIG"] = str(config_file)

    # Start uvicorn in background
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "moniker_svc.main:app",
         "--port", "8000", "--log-level", "warning"],
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    # Wait for service to start
    time.sleep(3)

    try:
        run_demo()
    finally:
        print("\nStopping service...")
        proc.terminate()
        proc.wait(timeout=5)
        # Cleanup temp config
        if config_file.exists():
            config_file.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Risk CVaR Demo")
    parser.add_argument("--standalone", action="store_true",
                        help="Start service automatically")
    args = parser.parse_args()

    if args.standalone:
        run_standalone()
    else:
        run_demo()
