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
    python -m uvicorn moniker_svc.main:app --port 8050

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
        service_url="http://localhost:8050",
        app_id="risk-cvar-demo",
        team="risk-analytics",
        report_telemetry=False,  # Disable for demo
    )
    client = MonikerClient(config=config)

    # Demo 1: Describe the risk.cvar domain (basic info)
    print("\n" + "=" * 60)
    print("1. Describe risk.cvar domain - Basic Info")
    print("=" * 60)
    try:
        info = client.describe("risk.cvar")
        print(f"   Display Name:    {info.get('display_name')}")
        print(f"   Description:     {info.get('description')}")
        print(f"   Classification:  {info.get('classification')}")
        print(f"\n   Ownership:")
        print(f"      Owner:        {info.get('ownership', {}).get('accountable_owner')}")
        print(f"      Specialist:   {info.get('ownership', {}).get('data_specialist')}")
        print(f"      Support:      {info.get('ownership', {}).get('support_channel')}")
    except Exception as e:
        print(f"   Error: {e}")

    # Demo 1b: Data Governance - SLA, DQ, Freshness
    print("\n" + "=" * 60)
    print("1b. Data Governance - SLA, Quality, Freshness")
    print("=" * 60)
    try:
        info = client.describe("risk.cvar")

        # SLA information
        sla = info.get('sla')
        if sla:
            print(f"\n   SLA Commitments:")
            print(f"      Freshness:    {sla.get('freshness')}")
            print(f"      Availability: {sla.get('availability')}")
            print(f"      Support:      {sla.get('support_hours')}")
            print(f"      Escalation:   {sla.get('escalation_contact')}")
        else:
            print(f"\n   SLA: Not defined")

        # Data Quality
        dq = info.get('data_quality')
        if dq:
            print(f"\n   Data Quality:")
            print(f"      DQ Owner:     {dq.get('dq_owner')}")
            print(f"      Score:        {dq.get('quality_score')}%")
            print(f"      Last Check:   {dq.get('last_validated')}")
            rules = dq.get('validation_rules', [])
            if rules:
                print(f"      Rules ({len(rules)}):")
                for rule in rules[:3]:
                    print(f"         - {rule}")
            issues = dq.get('known_issues', [])
            if issues:
                print(f"      Known Issues ({len(issues)}):")
                for issue in issues:
                    print(f"         - {issue}")
        else:
            print(f"\n   Data Quality: Not defined")

        # Freshness
        fresh = info.get('freshness')
        if fresh:
            print(f"\n   Data Freshness:")
            print(f"      Last Loaded:  {fresh.get('last_loaded')}")
            print(f"      Schedule:     {fresh.get('refresh_schedule')}")
            print(f"      Source:       {fresh.get('source_system')}")
            deps = fresh.get('upstream_dependencies', [])
            if deps:
                print(f"      Depends on:   {', '.join(deps)}")
        else:
            print(f"\n   Freshness: Not defined")

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

    # Demo 6: Show ownership lineage with governance roles
    print("\n" + "=" * 60)
    print("6. Ownership Lineage with Governance Roles (ADOP, ADS, ADAL)")
    print("=" * 60)
    try:
        lineage_info = client.lineage("risk.cvar")
        print(f"\n   Path: {lineage_info.get('path')}")

        # Simplified ownership
        ownership = lineage_info.get('ownership', {})
        print(f"\n   Simplified Ownership:")
        print(f"      Owner:       {ownership.get('accountable_owner')}")
        print(f"         defined at: {ownership.get('accountable_owner_defined_at')}")
        print(f"      Specialist:  {ownership.get('data_specialist')}")
        print(f"         defined at: {ownership.get('data_specialist_defined_at')}")
        print(f"      Support:     {ownership.get('support_channel')}")
        print(f"         defined at: {ownership.get('support_channel_defined_at')}")

        # Formal governance roles
        gov_roles = lineage_info.get('governance_roles', {})
        print(f"\n   Formal Governance Roles (BCBS 239 / DAMA):")

        adop = gov_roles.get('adop', {})
        print(f"      ADOP (Accountable Data Owner/Principal):")
        print(f"         {adop.get('value')}")
        print(f"         defined at: {adop.get('defined_at')}")

        ads = gov_roles.get('ads', {})
        print(f"      ADS (Accountable Data Steward):")
        print(f"         {ads.get('value')}")
        print(f"         defined at: {ads.get('defined_at')}")

        adal = gov_roles.get('adal', {})
        print(f"      ADAL (Accountable Data Access Lead):")
        print(f"         {adal.get('value')}")
        print(f"         defined at: {adal.get('defined_at')}")

        # Source binding info
        source = lineage_info.get('source', {})
        print(f"\n   Source Binding:")
        print(f"      Type:        {source.get('type')}")
        print(f"      Defined at:  {source.get('binding_defined_at')}")

        # Path hierarchy
        hierarchy = lineage_info.get('path_hierarchy', [])
        print(f"\n   Path Hierarchy:")
        for h in hierarchy:
            print(f"      -> {h}")

    except Exception as e:
        print(f"   Error: {e}")

    # Demo 7: Machine-readable schema for AI agents
    print("\n" + "=" * 60)
    print("7. Machine-Readable Schema (for AI Agent Discovery)")
    print("=" * 60)
    try:
        info = client.describe("risk.cvar")
        schema = info.get('schema', {})

        if schema:
            print(f"\n   Description:")
            desc_lines = schema.get('description', '').strip().split('\n')
            for line in desc_lines[:2]:
                print(f"      {line}")

            print(f"\n   Semantic Tags (for AI search):")
            tags = schema.get('semantic_tags', [])
            print(f"      {', '.join(tags)}")

            print(f"\n   Data Profile:")
            print(f"      Granularity:       {schema.get('granularity')}")
            print(f"      Update Frequency:  {schema.get('update_frequency')}")
            print(f"      Typical Row Count: {schema.get('typical_row_count')}")

            print(f"\n   Columns ({len(schema.get('columns', []))} total):")
            for col in schema.get('columns', [])[:4]:
                pk = " [PK]" if col.get('primary_key') else ""
                fk = f" -> {col.get('foreign_key')}" if col.get('foreign_key') else ""
                print(f"      {col['name']}{pk} ({col['type']}, {col.get('semantic_type', 'N/A')})")
                print(f"         {col.get('description', '')[:60]}")
                if fk:
                    print(f"         Foreign key: {fk}")
            print(f"      ... and {len(schema.get('columns', [])) - 4} more columns")

            print(f"\n   Use Cases (AI can suggest appropriate queries):")
            for uc in schema.get('use_cases', [])[:3]:
                print(f"      - {uc}")

            print(f"\n   Example Monikers:")
            for ex in schema.get('examples', [])[:3]:
                print(f"      {ex}")

            print(f"\n   Related Monikers (for joins/enrichment):")
            for rel in schema.get('related_monikers', [])[:3]:
                print(f"      - {rel}")
        else:
            print("   No schema defined")

    except Exception as e:
        print(f"   Error: {e}")

    # Demo 8: Use with pandas
    print("\n" + "=" * 60)
    print("8. Convert to pandas DataFrame for analysis")
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
    parser = argparse.ArgumentParser(description="Risk CVaR Demo")
    parser.add_argument("--standalone", action="store_true",
                        help="Start service automatically")
    args = parser.parse_args()

    if args.standalone:
        run_standalone()
    else:
        run_demo()
