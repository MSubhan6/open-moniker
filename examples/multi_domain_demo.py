#!/usr/bin/env python3
"""
Multi-Domain Demo - Govies, Commods, Rates, Mortgages
=====================================================

This demo shows how to access multiple data domains using the moniker service:
- Govies (Government Bonds) - Snowflake source
- Commods (Commodities) - REST API (NEFA) source
- Rates (Interest Rates) - Snowflake source
- Mortgages (MBS) - Excel source

Each domain uses a different data source type, demonstrating the
unified access pattern provided by the moniker service.

Usage:
    # Start the service in one terminal:
    cd /home/user/open-moniker-svc
    python -m uvicorn moniker_svc.main:app --port 8050

    # Run this demo in another terminal:
    python examples/multi_domain_demo.py

Or run in standalone mode (starts service automatically):
    python examples/multi_domain_demo.py --standalone
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
    """Run the multi-domain demo."""
    print("=" * 70)
    print("Multi-Domain Demo - Unified Data Access via Monikers")
    print("=" * 70)
    print()

    # Enable all mock adapters
    from moniker_client.adapters.mock_oracle import enable_mock_oracle
    from moniker_client.adapters.mock_snowflake import enable_mock_snowflake
    from moniker_client.adapters.mock_rest import enable_mock_rest
    from moniker_client.adapters.mock_excel import enable_mock_excel

    enable_mock_oracle()
    enable_mock_snowflake()
    enable_mock_rest()
    enable_mock_excel()

    # Import client functions
    from moniker_client import MonikerClient, ClientConfig

    # Create client
    config = ClientConfig(
        service_url="http://localhost:8050",
        app_id="multi-domain-demo",
        team="data-platform",
        report_telemetry=False,
    )
    client = MonikerClient(config=config)

    # =========================================================================
    # GOVIES - Government Bonds (Snowflake)
    # =========================================================================
    print("\n" + "=" * 70)
    print("1. GOVIES - US Treasury Data (Snowflake)")
    print("=" * 70)

    try:
        # Describe the domain
        info = client.describe("govies.treasury")
        print(f"\n   Domain: {info.get('display_name')}")
        print(f"   Description: {info.get('description')}")
        print(f"   Source: {info.get('source_type')}")

        # Show schema info
        schema = info.get('schema', {})
        if schema:
            print(f"\n   Semantic Tags: {', '.join(schema.get('semantic_tags', [])[:5])}")
            print(f"   Granularity: {schema.get('granularity')}")

        # Fetch 10Y Treasury data
        print("\n   Fetching 10Y US Treasury data...")
        data = client.read("govies.treasury/US/10Y/ALL")
        print(f"   Retrieved {len(data)} rows")

        if data:
            print("\n   Sample Treasury Data (first 5 rows):")
            print(f"   {'DATE':<12} {'CUSIP':<12} {'TENOR':<6} {'YIELD':>8} {'PRICE':>8} {'DURATION':>8}")
            print("   " + "-" * 56)
            for row in data[:5]:
                print(f"   {row['ASOF_DATE']:<12} {row['CUSIP']:<12} {row['TENOR']:<6} "
                      f"{row['YIELD']:>8.4f} {row['PRICE']:>8.2f} {row['DURATION']:>8.2f}")

    except Exception as e:
        print(f"   Error: {e}")

    # =========================================================================
    # COMMODS - Commodities (REST API / NEFA)
    # =========================================================================
    print("\n" + "=" * 70)
    print("2. COMMODS - Energy Commodities (REST API / NEFA)")
    print("=" * 70)

    try:
        # Describe the domain
        info = client.describe("commods.energy")
        print(f"\n   Domain: {info.get('display_name')}")
        print(f"   Source: {info.get('source_type')}")

        schema = info.get('schema', {})
        if schema:
            print(f"   Update Frequency: {schema.get('update_frequency')}")

        # Fetch crude oil spot prices
        print("\n   Fetching WTI Crude Oil spot prices...")
        data = client.read("commods.energy/CL/SPOT/ALL")
        print(f"   Retrieved {len(data)} rows")

        if data:
            print("\n   Sample Crude Oil Data (first 5 rows):")
            print(f"   {'TIMESTAMP':<22} {'SYMBOL':<6} {'CONTRACT':<8} {'PRICE':>8} {'CHANGE':>8} {'VOLUME':>10}")
            print("   " + "-" * 66)
            for row in data[:5]:
                print(f"   {row['TIMESTAMP']:<22} {row['SYMBOL']:<6} {row['CONTRACT']:<8} "
                      f"{row['PRICE']:>8.2f} {row['CHANGE']:>8.2f} {row['VOLUME']:>10,}")

    except Exception as e:
        print(f"   Error: {e}")

    # =========================================================================
    # COMMODS - Metals
    # =========================================================================
    print("\n" + "=" * 70)
    print("3. COMMODS - Precious Metals (REST API / NEFA)")
    print("=" * 70)

    try:
        # Fetch gold spot prices
        print("\n   Fetching Gold spot prices...")
        data = client.read("commods.metals/GC/SPOT/ALL")
        print(f"   Retrieved {len(data)} rows")

        if data:
            print("\n   Sample Gold Data (first 5 rows):")
            print(f"   {'TIMESTAMP':<22} {'SYMBOL':<6} {'PRICE':>10} {'CHANGE':>8} {'VOLUME':>10}")
            print("   " + "-" * 58)
            for row in data[:5]:
                print(f"   {row['TIMESTAMP']:<22} {row['SYMBOL']:<6} "
                      f"{row['PRICE']:>10.2f} {row['CHANGE']:>8.2f} {row['VOLUME']:>10,}")

    except Exception as e:
        print(f"   Error: {e}")

    # =========================================================================
    # RATES - Interest Rate Swaps (Snowflake)
    # =========================================================================
    print("\n" + "=" * 70)
    print("4. RATES - Interest Rate Swaps (Snowflake)")
    print("=" * 70)

    try:
        # Describe the domain
        info = client.describe("rates.swap")
        print(f"\n   Domain: {info.get('display_name')}")
        print(f"   Source: {info.get('source_type')}")

        # Show governance info
        ownership = info.get('ownership', {})
        print(f"\n   ADOP: {ownership.get('adop')}")
        print(f"   ADS: {ownership.get('ads')}")

        # Fetch USD swap curve
        print("\n   Fetching USD swap curve...")
        data = client.read("rates.swap/USD/ALL/ALL")
        print(f"   Retrieved {len(data)} rows")

        if data:
            # Get latest date
            latest_date = max(row['ASOF_DATE'] for row in data)
            latest_data = [row for row in data if row['ASOF_DATE'] == latest_date]

            print(f"\n   USD Swap Curve as of {latest_date}:")
            print(f"   {'TENOR':<8} {'PAR_RATE':>10} {'SPREAD':>8} {'DV01':>10}")
            print("   " + "-" * 38)
            for row in sorted(latest_data, key=lambda x: ['1Y', '2Y', '3Y', '5Y', '7Y', '10Y', '15Y', '20Y', '30Y'].index(x['TENOR']) if x['TENOR'] in ['1Y', '2Y', '3Y', '5Y', '7Y', '10Y', '15Y', '20Y', '30Y'] else 99):
                print(f"   {row['TENOR']:<8} {row['PAR_RATE']:>10.4f} {row['SPREAD_VS_GOVT']:>8.1f} {row['DV01']:>10.2f}")

    except Exception as e:
        print(f"   Error: {e}")

    # =========================================================================
    # MORTGAGES - MBS Pool Data (Excel)
    # =========================================================================
    print("\n" + "=" * 70)
    print("5. MORTGAGES - MBS Pool Data (Excel)")
    print("=" * 70)

    try:
        # Describe the domain
        info = client.describe("mortgages.pools")
        print(f"\n   Domain: {info.get('display_name')}")
        print(f"   Source: {info.get('source_type')}")

        # Show data quality info
        dq = info.get('data_quality', {})
        if dq:
            print(f"   Quality Score: {dq.get('quality_score')}%")
            print(f"   Known Issues: {dq.get('known_issues', ['None'])[0]}")

        # Fetch Fannie Mae 30Y pools
        print("\n   Fetching Fannie Mae 30Y pool data...")
        data = client.read("mortgages.pools/FNMA/30Y/ALL")
        print(f"   Retrieved {len(data)} rows")

        if data:
            print("\n   Sample MBS Pool Data (first 5 rows):")
            print(f"   {'DATE':<12} {'POOL_ID':<12} {'WAC':>6} {'WAM':>5} {'FACTOR':>7} {'CPR_1M':>7} {'OAS':>6}")
            print("   " + "-" * 58)
            for row in data[:5]:
                print(f"   {row['ASOF_DATE']:<12} {row['POOL_ID']:<12} "
                      f"{row['WAC']:>6.4f} {row['WAM']:>5} {row['POOL_FACTOR']:>7.4f} "
                      f"{row['CPR_1M']:>7.1f} {row['OAS']:>6.1f}")

    except Exception as e:
        print(f"   Error: {e}")

    # =========================================================================
    # Cross-Domain Analysis Example
    # =========================================================================
    print("\n" + "=" * 70)
    print("6. Cross-Domain Analysis Example")
    print("=" * 70)

    try:
        import pandas as pd

        print("\n   Loading data from multiple domains for analysis...")

        # Load data
        treasury_data = client.read("govies.treasury/US/10Y/ALL")
        swap_data = client.read("rates.swap/USD/10Y/ALL")

        # Convert to DataFrames
        treasury_df = pd.DataFrame(treasury_data)
        swap_df = pd.DataFrame(swap_data)

        # Join on date
        treasury_df = treasury_df.rename(columns={'YIELD': 'TREASURY_YIELD'})
        swap_df = swap_df.rename(columns={'PAR_RATE': 'SWAP_RATE'})

        merged = pd.merge(
            treasury_df[['ASOF_DATE', 'TREASURY_YIELD']].drop_duplicates(),
            swap_df[['ASOF_DATE', 'SWAP_RATE']].drop_duplicates(),
            on='ASOF_DATE'
        )
        merged['SWAP_SPREAD'] = (merged['SWAP_RATE'] - merged['TREASURY_YIELD']) * 10000  # bps

        print(f"\n   10Y Treasury vs Swap Spread Analysis:")
        print(f"   {'DATE':<12} {'TREASURY':>10} {'SWAP':>10} {'SPREAD (bps)':>12}")
        print("   " + "-" * 46)
        for _, row in merged.head(5).iterrows():
            print(f"   {row['ASOF_DATE']:<12} {row['TREASURY_YIELD']:>10.4f} "
                  f"{row['SWAP_RATE']:>10.4f} {row['SWAP_SPREAD']:>12.1f}")

        print(f"\n   Spread Statistics:")
        print(f"   Mean: {merged['SWAP_SPREAD'].mean():.1f} bps")
        print(f"   Min:  {merged['SWAP_SPREAD'].min():.1f} bps")
        print(f"   Max:  {merged['SWAP_SPREAD'].max():.1f} bps")

    except ImportError:
        print("   pandas not installed - skipping cross-domain analysis")
    except Exception as e:
        print(f"   Error: {e}")

    # =========================================================================
    # Show Lineage for Multiple Domains
    # =========================================================================
    print("\n" + "=" * 70)
    print("7. Data Lineage Across Domains")
    print("=" * 70)

    domains = ["govies.treasury", "commods.energy", "rates.swap", "mortgages.pools"]

    for domain in domains:
        try:
            lineage = client.lineage(domain)
            gov_roles = lineage.get('governance_roles', {})
            adop = gov_roles.get('adop', {}).get('value', 'N/A')
            source = lineage.get('source', {}).get('type', 'N/A')

            print(f"\n   {domain}:")
            print(f"      ADOP: {adop}")
            print(f"      Source: {source}")
        except Exception as e:
            print(f"\n   {domain}: Error - {e}")

    print("\n" + "=" * 70)
    print("Demo complete!")
    print("=" * 70)


def run_standalone():
    """Run demo with embedded service."""
    import subprocess
    import os
    import yaml

    print("Starting moniker service...")

    # Create a temporary config file
    config = {
        "server": {"port": 8050},
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
         "--port", "8050", "--log-level", "warning"],
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
    parser = argparse.ArgumentParser(description="Multi-Domain Demo")
    parser.add_argument("--standalone", action="store_true",
                        help="Start service automatically")
    args = parser.parse_args()

    if args.standalone:
        run_standalone()
    else:
        run_demo()
