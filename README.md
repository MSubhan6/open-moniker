# Moniker Service

A unified data access layer for enterprise data governance. Provides canonical identification for all firm data assets with hierarchical ownership and full access telemetry.

## Architecture

The Moniker Service is a **resolution service**, not a data proxy. This prevents it from becoming a bottleneck for all firm data.

```
┌─────────────────────────────────────────────────────────────────┐
│  Your Notebook / Script                                         │
│                                                                 │
│    from moniker_client import read                              │
│    data = read("market-data/prices/equity/AAPL")                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  moniker-client (Python library)                                │
│                                                                 │
│    1. RESOLVE → GET /resolve/market-data/prices/equity/AAPL     │
│       Returns: source_type, connection, query, ownership        │
│                                                                 │
│    2. FETCH → Connect DIRECTLY to Snowflake/Oracle/Bloomberg    │
│       Using YOUR credentials (from environment)                 │
│                                                                 │
│    3. TELEMETRY → POST /telemetry/access                        │
│       Reports who accessed what (non-blocking)                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   ┌─────────┐         ┌─────────┐        ┌──────────┐
   │Snowflake│         │ Oracle  │        │Bloomberg │
   └─────────┘         └─────────┘        └──────────┘
     (direct)           (direct)           (direct)
```

**Key benefits:**
- Service doesn't become a bottleneck for all firm data
- Credentials stay local (not sent to the service)
- Data flows directly from source to your code
- Telemetry tracks who accessed what

## Components

| Component | Description |
|-----------|-------------|
| `src/moniker_svc/` | Resolution service (FastAPI) |
| `client/moniker_client/` | Python client library |

## Quick Start

### Start the Service

```bash
# Install the service
pip install -e .

# Copy sample config files (customize as needed)
cp config.sample.yaml config.yaml
cp sample_catalog.yaml catalog.yaml

# Run
python -m moniker_svc.main --config config.yaml
```

Service runs at http://localhost:8000

### Use the Client

```bash
# Install the client library
pip install -e client/

# In Python
python
```

```python
from moniker_client import read, describe, lineage

# Read data
data = read("market-data/prices/equity/AAPL")

# Get ownership info
info = describe("market-data/prices/equity")
print(f"Owner: {info['ownership']['accountable_owner']}")
print(f"Support: {info['ownership']['support_channel']}")

# Get full lineage
lin = lineage("market-data/prices/equity/AAPL")
```

### Run the Demo

```bash
pip install colorama
python demo.py
```

## Configuration

### Client Environment Variables

```bash
# Moniker service URL
export MONIKER_SERVICE_URL=http://moniker-svc:8000

# Your identity (for telemetry)
export MONIKER_APP_ID=my-notebook
export MONIKER_TEAM=quant-research

# Database credentials (used by client, NOT sent to service)
export SNOWFLAKE_USER=your_user
export SNOWFLAKE_PASSWORD=your_password

export ORACLE_USER=your_user
export ORACLE_PASSWORD=your_password
```

### Service Configuration

See `config.yaml`:

```yaml
server:
  host: "0.0.0.0"
  port: 8000

telemetry:
  enabled: true
  sink_type: console  # console | file | zmq
  batch_size: 1000
  flush_interval_seconds: 1.0

cache:
  enabled: true
  max_size: 10000
  default_ttl_seconds: 300
```

## Concepts

### Moniker Format

Full moniker format with all optional components:

```
[namespace@]domain.subdomain/path/segments[@version][/vN][?params]
```

| Component | Description | Example |
|-----------|-------------|---------|
| `namespace@` | Access scope or user context | `user@`, `verified@`, `official@` |
| `domain.subdomain` | Data domain with dot notation | `indices.sovereign`, `commodities.derivatives` |
| `/path/segments` | Hierarchical path | `/developed/EUR/ALL` |
| `@version` | Point-in-time or version tag | `@20260115`, `@latest` |
| `/vN` | Schema revision | `/v2`, `/v3` |
| `?params` | Query parameters | `?format=json` |

**Examples:**

```bash
# Simple path
indices.sovereign/developed/EU.GovBondAgg/EUR/ALL

# With version (point-in-time)
commodities.derivatives/crypto/ETH@20260115

# With version and revision
commodities.derivatives/crypto/ETH@20260115/v2

# With namespace (user-scoped view)
user@analytics.risk/views/my-watchlist@20260115/v3

# Official/verified source
verified@reference.security/ISIN/US0378331005@latest

# Positions by date
holdings/positions/20260115/fund_alpha

# With query params
prices.equity/AAPL@20260115?format=json
```

### Ownership Triple

Each node in the hierarchy can define:

| Field | Description |
|-------|-------------|
| **Accountable Owner** | Executive responsible for data governance |
| **Data Specialist** | Technical SME who understands the data |
| **Support Channel** | Slack/Teams channel for help |

Ownership inherits down the hierarchy. Each field inherits independently.

```
indices/                       ← Owner: governance@firm.com, Specialist: quant@firm.com
├── indices.sovereign/         ← Inherits all from parent
│   └── developed/             ← Inherits from indices.sovereign
commodities/                   ← Owner: desk@firm.com
├── commodities.derivatives/   ← Inherits from commodities
│   ├── energy/                ← Inherits from commodities.derivatives
│   └── crypto/                ← Override: Specialist: digital-assets@firm.com
```

### Source Bindings

Map moniker paths to actual data sources:

| Source | Description |
|--------|-------------|
| `snowflake` | Snowflake data warehouse |
| `oracle` | Oracle database |
| `rest` | REST APIs |
| `static` | JSON/CSV/Parquet files |
| `excel` | Excel files |
| `opensearch` | OpenSearch/Elasticsearch |
| `bloomberg` | Bloomberg BLPAPI |
| `refinitiv` | Refinitiv Eikon/RDP |

### Query Templates

Source bindings use template placeholders that get translated at resolution time.

**Raw Value Placeholders:**

| Placeholder | Description |
|-------------|-------------|
| `{path}` | Full sub-path after the binding |
| `{segments[N]}` | Specific path segment (0-indexed) |
| `{version}` | Version from `@suffix` (raw string) |
| `{revision}` | Revision from `/vN` suffix |
| `{namespace}` | Namespace prefix if provided |

**SQL-Translated Placeholders:**

| Placeholder | Description |
|-------------|-------------|
| `{version_date}` | SQL date: `CURRENT_DATE()` if empty, `TO_DATE('20260115','YYYYMMDD')` if date |
| `{filter[N]:column}` | SQL filter: `column = 'value'` or `1=1` if segment is `ALL` |
| `{is_all[N]}` | `"true"` if segment N is `ALL`, else `"false"` |
| `{is_latest}` | `"true"` if version is `latest`, else `"false"` |

**Example - ALL and @latest support:**

```sql
-- For: prices.equity/AAPL@20260115 or prices.equity/ALL@latest
SELECT symbol, close_price, volume
FROM EQUITY_EOD
WHERE {filter[0]:symbol}                    -- "symbol = 'AAPL'" or "1=1" for ALL
  AND trade_date = CASE
    WHEN {is_latest} = 'true' THEN (SELECT MAX(trade_date) FROM EQUITY_EOD)
    ELSE {version_date}                     -- TO_DATE('20260115','YYYYMMDD')
  END
```

**Translation examples:**

| Moniker | `{filter[0]:symbol}` | `{version_date}` | `{is_latest}` |
|---------|---------------------|------------------|---------------|
| `prices.equity/AAPL` | `symbol = 'AAPL'` | `CURRENT_DATE()` | `false` |
| `prices.equity/AAPL@20260115` | `symbol = 'AAPL'` | `TO_DATE('20260115','YYYYMMDD')` | `false` |
| `prices.equity/ALL@latest` | `1=1` | `'__LATEST__'` | `true` |

## API Endpoints

### Resolution Service

| Endpoint | Description |
|----------|-------------|
| `GET /resolve/{path}` | Resolve moniker → source connection info |
| `GET /list/{path}` | List children in catalog |
| `GET /describe/{path}` | Get metadata and ownership |
| `GET /lineage/{path}` | Get full ownership lineage |
| `GET /catalog` | List all catalog paths |
| `POST /telemetry/access` | Report access telemetry from client |
| `GET /health` | Health check |

### Example: Resolve

```bash
# Simple resolve
curl http://localhost:8000/resolve/indices.sovereign/developed/EU.GovBondAgg/EUR

# With version (point-in-time)
curl http://localhost:8000/resolve/prices.equity/AAPL@20260115

# With namespace prefix (user-scoped)
curl http://localhost:8000/resolve/user@analytics.risk/views/my-watchlist@20260115/v3
```

Response:
```json
{
  "moniker": "moniker://indices.sovereign/developed/EU.GovBondAgg/EUR",
  "path": "indices.sovereign/developed/EU.GovBondAgg/EUR",
  "source_type": "snowflake",
  "connection": {
    "account": "firm-prod.us-east-1",
    "warehouse": "ANALYTICS_WH",
    "database": "INDICES",
    "schema": "SOVEREIGN"
  },
  "query": "SELECT index_id, currency, weight, yield FROM DM_SOVEREIGN_INDICES WHERE index_family = 'EU.GovBondAgg' AND currency = 'EUR'",
  "ownership": {
    "accountable_owner": "indices-governance@firm.com",
    "data_specialist": "quant-research@firm.com",
    "support_channel": "#indices-support"
  }
}
```

## Telemetry

Two types of events are tracked:

1. **Resolution Events** (from service) - When someone asks where data lives
2. **Access Events** (from client) - When someone actually fetches data

Events include:
- Timestamp and request ID
- Caller identity (app_id, team)
- Moniker path and operation
- Outcome (success/error/not_found)
- Source type and latency
- Owner at time of access

Telemetry sinks:
- `console` - Print to stdout (development)
- `file` - Rotating JSONL files
- `zmq` - ZeroMQ PUB/SUB streaming

### ZeroMQ Streaming Demo

Stream telemetry events in real-time using ZeroMQ PUB/SUB:

```bash
# Install ZeroMQ
pip install pyzmq

# Terminal 1: Start service with ZMQ telemetry
python -m moniker_svc.main --config config_zmq.yaml

# Terminal 2: Subscribe to telemetry stream
python telemetry_subscriber.py
```

The subscriber shows events as they happen:

```
[14:32:15.123] RESOLVE  success    market-data/prices/equity/AAPL <- my-notebook (2.3ms)
[14:32:15.456] ACCESS   success    market-data/prices/equity/AAPL <- my-notebook (145.2ms) [snowflake]
```

Subscriber options:
```bash
# Show raw JSON
python telemetry_subscriber.py --raw

# Connect to different endpoint
python telemetry_subscriber.py --endpoint tcp://moniker-svc:5556

# Filter by topic
python telemetry_subscriber.py --topic moniker.access

# Verbose output with row counts
python telemetry_subscriber.py -v
```

For production, pipe telemetry to Kafka, Splunk, or your data warehouse by modifying `telemetry_subscriber.py` or implementing a custom sink.

## Catalog Definition

Copy `sample_catalog.yaml` to `catalog.yaml` and customize:

```bash
cp sample_catalog.yaml catalog.yaml
```

Example catalog entry with new moniker format:

```yaml
# Domain with dot notation
prices.equity:
  display_name: Equity Prices
  ownership:
    accountable_owner: market-data-governance@firm.com
    data_specialist: market-data-ops@firm.com
    support_channel: "#market-data"
  source_binding:
    type: snowflake
    config:
      account: firm-prod.us-east-1
      warehouse: MARKET_DATA_WH
      database: PRICES
      schema: EQUITY
      query: |
        SELECT symbol, close_price, volume
        FROM EQUITY_EOD
        WHERE {filter[0]:symbol}
          AND trade_date = CASE
            WHEN {is_latest} = 'true' THEN (SELECT MAX(trade_date) FROM EQUITY_EOD)
            ELSE {version_date}
          END
```

## Project Structure

```
open-moniker-svc/
├── src/moniker_svc/           # Resolution Service
│   ├── main.py                # FastAPI application
│   ├── service.py             # Core resolution logic
│   ├── catalog/               # Hierarchy + ownership
│   │   ├── types.py           # Ownership, SourceBinding, CatalogNode
│   │   └── registry.py        # CatalogRegistry
│   ├── moniker/               # Path parsing
│   │   ├── types.py           # MonikerPath, Moniker
│   │   └── parser.py          # parse_moniker()
│   ├── telemetry/             # Event streaming
│   │   ├── events.py          # UsageEvent, CallerIdentity
│   │   ├── emitter.py         # Non-blocking emitter
│   │   ├── batcher.py         # Batch for efficiency
│   │   └── sinks/             # Console, File, ZMQ
│   ├── identity/              # Caller extraction
│   └── cache/                 # In-memory cache
│
├── client/moniker_client/     # Python Client Library
│   ├── client.py              # MonikerClient, read(), describe()
│   ├── config.py              # ClientConfig
│   └── adapters/              # Direct source connections
│       ├── snowflake.py
│       ├── oracle.py
│       ├── rest.py
│       ├── bloomberg.py
│       └── ...
│
├── examples/                  # Usage examples for notebooks
├── tests/                     # Unit tests
├── demo.py                    # Interactive demo
├── config.sample.yaml         # Service configuration template
├── sample_catalog.yaml        # Sample catalog definition
└── pyproject.toml             # Package configuration
```

## Installation Options

### Service

```bash
pip install -e .                    # Basic
pip install -e ".[dev]"             # With dev tools
```

### Client

```bash
pip install -e client/              # Basic
pip install -e "client/[snowflake]" # With Snowflake
pip install -e "client/[oracle]"    # With Oracle
pip install -e "client/[all]"       # All adapters
```

## License

MIT
