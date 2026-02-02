# Moniker Service

A unified data access layer for enterprise data governance. Canonical identification for all firm data assets with hierarchical ownership and access telemetry.

## Example: AAPL Price Time Series

```python
from moniker_client import read

# Fetch today's AAPL prices
data = read("prices.equity/AAPL")

# Fetch historical data for a specific date
historical = read("prices.equity/AAPL@20260115")

# Get the latest available snapshot
latest = read("prices.equity/AAPL@latest")
```

**What happens under the hood:**

1. Client calls `GET /resolve/prices.equity/AAPL`
2. Service returns connection info + query template
3. Client executes query against Snowflake/Oracle/etc
4. Data returned as pandas DataFrame or dict

```
┌─────────────────────────────────────────────────────────────────┐
│  Your Code                                                      │
│    data = read("prices.equity/AAPL@20260115")                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ GET /resolve/prices.equity/AAPL@20260115
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Moniker Service                                                │
│    Returns: {                                                   │
│      "source_type": "snowflake",                                │
│      "connection": {"account": "firm.snowflake"},               │
│      "query": "SELECT * FROM PRICES WHERE symbol='AAPL'         │
│               AND trade_date = TO_DATE('20260115','YYYYMMDD')"  │
│    }                                                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │ Client executes query
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Snowflake                                                      │
│    → Returns price data                                         │
└─────────────────────────────────────────────────────────────────┘
```

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
# http://localhost:8050/ui
```

## Try the API

```bash
# Browse the catalog tree
curl http://localhost:8050/tree

# Get metadata for a domain
curl http://localhost:8050/describe/risk.cvar

# Fetch sample data (uses mock Oracle adapter)
curl http://localhost:8050/sample/risk.cvar

# See all endpoints
curl http://localhost:8050/
```

## Using the Client Library

### Simple Read API

```python
from moniker_client import read, describe, lineage

# Read data - returns dict or DataFrame
data = read("prices.equity/AAPL")
data = read("prices.equity/AAPL@20260115")      # Historical date
data = read("prices.equity/AAPL@latest")        # Latest snapshot

# Get metadata and ownership
info = describe("prices.equity/AAPL")
print(info["ownership"]["accountable_owner"])   # market-data-governance@firm.com
print(info["ownership"]["support_channel"])     # #market-data

# Trace data lineage
lin = lineage("prices.equity/AAPL")
print(lin["path_hierarchy"])                    # ['prices', 'prices.equity', ...]
```

### Object-Oriented API

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

### Version and Namespace Syntax

```python
# Date versions (YYYYMMDD format)
read("prices.equity/AAPL@20260115")

# Special versions
read("prices.equity/AAPL@latest")

# User namespace (for user-specific views)
read("user@analytics.risk/views/my-watchlist")

# Schema revision
read("risk.cvar/DESK_A@20260115/v2")
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

Browse the catalog visually at **http://localhost:8050/ui**

- Tree view of all data domains
- Click nodes to see ownership, source type, governance roles
- Links to API endpoints for each node

## Deploy to Render.com

**Option 1: One-click deploy**
1. Fork this repo
2. Go to [render.com/new](https://render.com/new)
3. Connect your GitHub repo
4. Render auto-detects `render.yaml` and deploys

**Option 2: Manual setup**
1. New → Web Service → Connect repo
2. Settings:
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `PYTHONPATH=src:external/moniker-data/src uvicorn moniker_svc.main:app --host 0.0.0.0 --port $PORT`
3. Add environment variable: `PYTHON_VERSION=3.11`

Once deployed, access:
- **Web UI**: `https://your-app.onrender.com/ui`
- **API docs**: `https://your-app.onrender.com/docs`
- **Health check**: `https://your-app.onrender.com/health`

**Test the deployed API:**
```bash
# Get the tree structure
curl https://your-app.onrender.com/tree

# Fetch sample data
curl https://your-app.onrender.com/sample/risk.cvar

# Run tests against deployed instance
MONIKER_SERVICE_URL=https://your-app.onrender.com python -m pytest external/moniker-tests/tests/ -v
```

## License

MIT
