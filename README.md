# Moniker Service

A unified data access layer for enterprise data governance. Canonical identification for all firm data assets with hierarchical ownership and access telemetry.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Your Notebook / Script                                         │
│    from moniker_client import Moniker                           │
│    m = Moniker("risk.cvar/DESK_A/20240115/USD")                 │
│    data = m.fetch()                                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Moniker Service (this repo)                                    │
│    - Resolves monikers → source connection info                 │
│    - Tracks ownership hierarchy                                 │
│    - Records access telemetry                                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   ┌─────────┐         ┌─────────┐        ┌──────────┐
   │Snowflake│         │ Oracle  │        │  REST    │
   └─────────┘         └─────────┘        └──────────┘
```

## Quick Start

```bash
# 1. Clone and install
git clone <repo-url> && cd open-moniker-svc
pip install -e .
pip install -e client/

# 2. Start the server (uses built-in demo catalog with mock data)
# Linux/Mac:
PYTHONPATH="$PWD/src:$PWD/external/moniker-data/src" uvicorn moniker_svc.main:app --reload

# Windows PowerShell:
$env:PYTHONPATH="$PWD\src;$PWD\external\moniker-data\src"; uvicorn moniker_svc.main:app --reload

# 3. Open the web UI
# http://localhost:8000/ui
```

## Try the API

```bash
# Browse the catalog tree
curl http://localhost:8000/tree

# Get metadata for a domain
curl http://localhost:8000/describe/risk.cvar

# Fetch sample data (uses mock Oracle adapter)
curl http://localhost:8000/sample/risk.cvar

# See all endpoints
curl http://localhost:8000/
```

## Use the Client Library

```python
from moniker_client import Moniker

# Navigate the catalog
m = Moniker("risk.cvar")
print(m.describe())           # Ownership, documentation, governance roles
print(m.children())           # ['DESK_A', 'DESK_B', ...]

# Fetch data
result = m.fetch(limit=10)
print(result.columns)         # ['portfolio_id', 'currency', 'cvar_95', ...]
print(result.data)            # [{'portfolio_id': 'DESK_A', ...}, ...]

# AI-friendly metadata
meta = m.metadata()
print(meta.semantic_tags)     # ['risk', 'cvar', 'portfolio-risk']
print(meta.cost_indicators)   # {'row_estimate': 50000}
```

## Run Tests

```bash
# Set PYTHONPATH (Linux/Mac)
export PYTHONPATH="$PWD/src:$PWD/client:$PWD/external/moniker-data/src"

# Windows PowerShell
$env:PYTHONPATH="$PWD\src;$PWD\client;$PWD\external\moniker-data\src"

# Run all tests
python -m pytest tests/ external/moniker-tests/tests/ -v
```

## Mock Data Adapters

The `external/moniker-data/` package provides mock adapters for testing without real databases. Example Oracle mock for CVaR risk data:

```python
# external/moniker-data/src/moniker_data/adapters/oracle.py
class MockOracleAdapter:
    """Returns realistic CVaR data from SQLite instead of Oracle."""

    def execute(self, query, params):
        # Generates test data: portfolios, currencies, securities, dates
        # with realistic CVaR/VaR values
        return [
            {"portfolio_id": "DESK_A", "currency": "USD", "security_id": "AAPL",
             "cvar_95": -125000.50, "cvar_99": -187500.75, "var_95": -100000.00},
            ...
        ]
```

These mocks will move to a separate `open-moniker-data` repo.

## Configure Your Own Catalog

Edit `sample_catalog.yaml` to define your data domains:

```yaml
risk.cvar:
  display_name: "CVaR Risk Measures"
  description: "Daily CVaR calculations by portfolio"

  ownership:
    accountable_owner: risk-governance@firm.com
    data_specialist: risk-quants@firm.com
    support_channel: "#risk-data"

  # Governance roles (optional)
  adop: jane.smith@firm.com      # Accountable Data Owner Partner
  ads: john.doe@firm.com         # Accountable Data Steward

  source_binding:
    type: oracle
    config:
      host: risk-db.firm.com
      service_name: RISKPROD
      query: |
        SELECT portfolio_id, currency, security_id,
               cvar_95, cvar_99, var_95, calculation_date
        FROM RISK.DAILY_CVAR
        WHERE portfolio_id = '{segments[0]}'
          AND currency = '{segments[2]}'
          AND calculation_date = TO_DATE('{segments[1]}', 'YYYYMMDD')

  documentation:
    glossary_url: https://confluence.firm.com/risk/cvar-glossary
    runbook_url: https://confluence.firm.com/risk/cvar-runbook
```

## Project Structure

```
open-moniker-svc/
├── src/moniker_svc/           # FastAPI service
├── client/moniker_client/     # Python client library
├── external/                  # Will become separate repos
│   ├── moniker-data/          # Mock adapters for testing
│   └── moniker-tests/         # Integration tests
├── tests/                     # Unit tests
└── sample_catalog.yaml        # Example catalog definition
```

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Moniker** | Canonical path like `risk.cvar/DESK_A/20240115/USD` |
| **Ownership** | Who's accountable (ADOP), who knows the data (ADS), where to get help |
| **Source Binding** | Maps moniker paths to actual databases/APIs |
| **Access Policy** | Rules that block expensive queries (e.g., "no SELECT * on 10M rows") |

## Web UI

Browse the catalog visually at **http://localhost:8000/ui**

- Tree view of all data domains
- Click nodes to see ownership, source type, governance roles
- Links to API endpoints for each node

## License

MIT
