#!/usr/bin/env python3
"""Demo script showing Moniker API capabilities.

Demonstrates:
1. Resolution Mode - Client gets query, executes directly
2. Fetch Mode - Server executes query, returns data
3. AI Metadata - Rich metadata for machine discovery
4. Sample Data - Quick exploration

Run the service first:
    python -m moniker_svc.main

Then run this demo:
    python examples/api_demo.py
"""

import httpx
import json
from pprint import pprint


BASE_URL = "http://localhost:8050"


def print_section(title: str):
    """Print a section header."""
    print("\n" + "=" * 70)
    print(f" {title}")
    print("=" * 70)


def demo_resolution_mode():
    """Demo: Resolution returns query for client-side execution."""
    print_section("1. RESOLUTION MODE - Client executes query")

    print("\nResolving: risk.cvar/758-A/USD/B0YHY8V7")
    print("The service returns connection info and query - client executes.\n")

    resp = httpx.get(f"{BASE_URL}/resolve/risk.cvar/758-A/USD/B0YHY8V7")
    data = resp.json()

    print(f"Source Type: {data['source_type']}")
    print(f"Connection: {json.dumps(data['connection'], indent=2)}")
    print(f"\nGenerated Query:")
    print("-" * 40)
    print(data['query'])
    print("-" * 40)

    print("\n→ Client would now execute this query against Oracle directly.")
    print("  This is efficient for large datasets - no data through service.")


def demo_fetch_mode():
    """Demo: Server executes query and returns data."""
    print_section("2. FETCH MODE - Server executes query, returns data")

    print("\nFetching: fixed_income/govies/treasury/US/10Y/ALL (limit=5)")
    print("The service executes the query and returns actual data.\n")

    resp = httpx.get(f"{BASE_URL}/fetch/fixed_income/govies/treasury/US/10Y/ALL?limit=5")
    data = resp.json()

    print(f"Source Type: {data['source_type']}")
    print(f"Rows Returned: {data['row_count']}")
    print(f"Truncated: {data['truncated']}")
    print(f"Execution Time: {data['execution_time_ms']}ms")
    print(f"\nColumns: {data['columns']}")
    print(f"\nSample Data:")
    for i, row in enumerate(data['data'][:3]):
        print(f"  Row {i+1}: {row}")

    print("\n→ Convenient for small datasets, AI agents, or exploration.")


def demo_metadata_for_ai():
    """Demo: Rich metadata for AI agent discoverability."""
    print_section("3. AI METADATA - Machine-discoverable enrichments")

    print("\nGetting metadata for: risk.cvar")
    print("Optimized for AI agents - semantic tags, relationships, costs.\n")

    resp = httpx.get(f"{BASE_URL}/metadata/risk.cvar")
    data = resp.json()

    print(f"Display Name: {data['display_name']}")
    print(f"\nNatural Language Description:")
    print(f"  {data.get('nl_description', 'N/A')[:200]}...")

    print(f"\nSemantic Tags (for AI classification):")
    print(f"  {data.get('semantic_tags', [])}")

    print(f"\nUse Cases (what questions this data answers):")
    for uc in data.get('use_cases', [])[:3]:
        print(f"  • {uc}")

    print(f"\nData Profile:")
    profile = data.get('data_profile', {})
    if profile:
        print(f"  Estimated Total Rows: {profile.get('estimated_total_rows', 'N/A'):,}")
        print(f"  Cardinality by Dimension: {profile.get('cardinality_by_dimension', [])}")
        print(f"  Max Rows Block: {profile.get('max_rows_block', 'N/A'):,}")

    print(f"\nCost Indicators:")
    cost = data.get('cost_indicators', {})
    if cost:
        print(f"  Query Complexity: {cost.get('query_complexity', 'N/A')}")
        print(f"  Estimated Latency: {cost.get('estimated_latency', 'N/A')}")

    print(f"\nQuery Patterns (guidance for agents):")
    patterns = data.get('query_patterns', {})
    if patterns:
        print(f"  Blocked Patterns: {patterns.get('blocked_patterns', [])}")
        print(f"  Min Filters Required: {patterns.get('min_filters_required', 0)}")

    print(f"\nRelationships:")
    rels = data.get('relationships', {})
    if rels:
        print(f"  Related Monikers: {rels.get('related_monikers', [])[:3]}")
        print(f"  Upstream Dependencies: {rels.get('upstream_dependencies', [])}")

    print(f"\nDocumentation Links:")
    docs = data.get('documentation', {})
    if docs:
        for key, url in list(docs.items())[:3]:
            print(f"  {key}: {url}")


def demo_sample_data():
    """Demo: Quick sample for data exploration."""
    print_section("4. SAMPLE DATA - Quick exploration")

    # Try different data sources
    samples = [
        ("rates.swap/USD/10Y/ALL", "Interest Rate Swaps"),
        ("commods.energy/CL/SPOT/ALL", "Crude Oil Prices"),
    ]

    for path, name in samples:
        print(f"\nSample from {name} ({path}):")
        try:
            resp = httpx.get(f"{BASE_URL}/sample/{path}?limit=3")
            data = resp.json()

            print(f"  Columns: {data['columns'][:5]}...")
            for row in data['data'][:2]:
                # Show first few fields
                subset = {k: v for k, v in list(row.items())[:4]}
                print(f"  → {subset}")
        except Exception as e:
            print(f"  Error: {e}")


def demo_compare_modes():
    """Demo: Compare resolution vs fetch for same moniker."""
    print_section("5. COMPARE MODES - Same moniker, different approaches")

    path = "fixed_income/govies/treasury/US/10Y/ALL"
    print(f"\nMoniker: {path}\n")

    # Resolution mode
    print("A) Resolution Mode (for client-side execution):")
    resp = httpx.get(f"{BASE_URL}/resolve/{path}")
    resolve_data = resp.json()
    print(f"   Returns: connection info + query ({len(resolve_data['query'])} chars)")
    print(f"   Client must: Connect to {resolve_data['source_type']}, execute query")
    print(f"   Best for: Large datasets, production pipelines")

    # Fetch mode
    print("\nB) Fetch Mode (server-side execution):")
    resp = httpx.get(f"{BASE_URL}/fetch/{path}?limit=10")
    fetch_data = resp.json()
    print(f"   Returns: {fetch_data['row_count']} rows of actual data")
    print(f"   Execution time: {fetch_data['execution_time_ms']}ms")
    print(f"   Best for: Small datasets, AI agents, exploration")


def demo_documentation():
    """Demo: Documentation links for humans and AI."""
    print_section("6. DOCUMENTATION - Links for humans and AI")

    domains = ["risk", "govies", "rates", "mortgages"]

    for domain in domains:
        resp = httpx.get(f"{BASE_URL}/metadata/{domain}")
        data = resp.json()

        docs = data.get('documentation', {})
        if docs:
            print(f"\n{domain}:")
            for key in ['glossary', 'runbook', 'data_dictionary']:
                if key in docs:
                    print(f"  {key}: {docs[key]}")


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print(" MONIKER API DEMO")
    print(" Demonstrating Resolution, Fetch, and AI Metadata Endpoints")
    print("=" * 70)

    try:
        # Check if service is running
        resp = httpx.get(f"{BASE_URL}/health")
        if resp.status_code != 200:
            print(f"\nError: Service not healthy. Start it first:")
            print("  python -m moniker_svc.main")
            return
    except httpx.ConnectError:
        print(f"\nError: Cannot connect to {BASE_URL}")
        print("Start the service first:")
        print("  python -m moniker_svc.main")
        return

    # Run demos
    demo_resolution_mode()
    demo_fetch_mode()
    demo_metadata_for_ai()
    demo_sample_data()
    demo_compare_modes()
    demo_documentation()

    print_section("SUMMARY")
    print("""
Key Endpoints:

  /resolve/{path}  - Get query for client-side execution (efficient for large data)
  /fetch/{path}    - Get actual data (convenient for small data, AI agents)
  /metadata/{path} - Rich metadata for AI discoverability
  /sample/{path}   - Quick sample rows for exploration

AI Agent Tips:
  • Use /metadata to understand data before querying
  • Check 'cost_indicators' to avoid expensive queries
  • Use 'semantic_tags' to find relevant data
  • Follow 'query_patterns.blocked_patterns' to avoid errors
  • Use 'relationships' to discover related data
""")


if __name__ == "__main__":
    main()
