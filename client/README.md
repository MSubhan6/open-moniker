# Moniker Client

Python client library for the Moniker Service - unified data access across the firm.

## Installation

```bash
pip install moniker-client

# With specific adapters
pip install moniker-client[snowflake]
pip install moniker-client[oracle]
pip install moniker-client[all]
```

## Quick Start

```python
from moniker_client import read, describe

# Read data using a moniker
data = read("prices.equity/AAPL")
print(data)

# Read with version (point-in-time)
historical = read("prices.equity/AAPL@20260115")

# Read all data (matrix instead of vector)
all_prices = read("prices.equity/ALL@latest")

# Get ownership info
info = describe("prices.equity")
print(f"Owner: {info['ownership']['accountable_owner']}")
print(f"Support: {info['ownership']['support_channel']}")
```

## Configuration

Set environment variables:

```bash
# Moniker service URL
export MONIKER_SERVICE_URL=http://moniker-svc:8050

# Your identity (for telemetry)
export MONIKER_APP_ID=my-notebook
export MONIKER_TEAM=quant-research

# Database credentials (used by client, not sent to service)
export SNOWFLAKE_USER=your_user
export SNOWFLAKE_PASSWORD=your_password

export ORACLE_USER=your_user
export ORACLE_PASSWORD=your_password
```

Or configure programmatically:

```python
from moniker_client import MonikerClient, ClientConfig

config = ClientConfig(
    service_url="http://moniker-svc:8050",
    app_id="my-notebook",
    team="quant-research",
)

client = MonikerClient(config=config)
data = client.read("prices.equity/AAPL@20260115")
```

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  Your Code                                                  │
│    data = read("market-data/prices/equity/AAPL")            │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  moniker-client                                             │
│                                                             │
│    1. Resolve moniker → GET /resolve/market-data/...        │
│       Returns: source_type=snowflake, query="SELECT..."     │
│                                                             │
│    2. Connect DIRECTLY to Snowflake                         │
│       Execute query, get results                            │
│                                                             │
│    3. Report telemetry → POST /telemetry/access             │
│       (non-blocking, best-effort)                           │
│                                                             │
│    4. Return data to your code                              │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
                      ┌──────────┐
                      │Snowflake │  (direct connection)
                      └──────────┘
```

**Key points:**
- The Moniker Service only resolves paths → it doesn't proxy data
- Your credentials stay local (not sent to the service)
- Data flows directly from source to your code
- Telemetry tracks who accessed what

## API Reference

### read(moniker)

Fetch data for a moniker.

```python
# Simple read (today's date)
data = read("prices.equity/AAPL")

# With version (point-in-time)
data = read("prices.equity/AAPL@20260115")

# Latest available data
data = read("prices.equity/AAPL@latest")

# All items (returns matrix)
all_data = read("prices.equity/ALL@20260115")

# With namespace (user-scoped data)
my_view = read("user@analytics.risk/views/my-watchlist@latest/v3")
```

### describe(moniker)

Get metadata about a path.

```python
info = describe("prices.equity")
# Returns: display_name, ownership, source_type, classification, etc.
```

### list_children(moniker)

List children of a path.

```python
children = list_children("prices")
# Returns: ["equity", "fx", "fixed-income"]
```

### lineage(moniker)

Get full ownership lineage.

```python
lineage_info = lineage("prices.equity/AAPL")
# Returns: ownership at each level, source binding location
```

## Supported Sources

| Source | Adapter | Package |
|--------|---------|---------|
| Snowflake | `snowflake` | `snowflake-connector-python` |
| Oracle | `oracle` | `oracledb` |
| REST APIs | `rest` | (built-in) |
| Static files | `static` | (built-in) |
| Excel | `excel` | `openpyxl` |
| Bloomberg | `bloomberg` | `blpapi` |
| Refinitiv | `refinitiv` | `eikon`, `refinitiv-data` |

## Custom Adapters

Register custom adapters for internal systems:

```python
from moniker_client.adapters import BaseAdapter, register_adapter

class MyInternalAdapter(BaseAdapter):
    def fetch(self, resolved, config, **kwargs):
        # Connect to your internal system
        # Use resolved.connection for connection info
        # Use resolved.query for the query
        return data

register_adapter("my-internal", MyInternalAdapter())
```
