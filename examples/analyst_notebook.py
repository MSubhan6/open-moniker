"""
Moniker Client - Analyst Notebook Examples
==========================================

This script shows common patterns for accessing firm data using monikers.
Can be run as a script or converted to Jupyter notebook cells.

Setup:
    pip install moniker-client[snowflake]  # or [all] for all adapters

Environment variables (set these before running):
    export MONIKER_SERVICE_URL=http://moniker-svc:8050
    export MONIKER_APP_ID=my-notebook
    export MONIKER_TEAM=quant-research
    export SNOWFLAKE_USER=your_user
    export SNOWFLAKE_PASSWORD=your_password
"""

# %% [markdown]
# # Moniker Client - Unified Data Access
#
# Access any firm data using canonical monikers instead of connection strings.

# %% Setup
from moniker_client import read, describe, lineage, list_children

# %% [markdown]
# ## 1. Basic Data Access
#
# Read data using simple moniker paths:

# %% Read equity prices
# Simple read - uses today's date by default
prices = read("prices.equity/AAPL")
print(f"Got {len(prices)} price records")
print(prices[0] if prices else "No data")

# %% Read with specific date (@version)
historical_prices = read("prices.equity/AAPL@20260115")
print(f"Historical prices for 2026-01-15: {len(historical_prices)} records")

# %% Read latest available data (@latest)
latest_prices = read("prices.equity/AAPL@latest")
print(f"Latest available: {latest_prices}")

# %% [markdown]
# ## 2. Bulk Data Access (ALL keyword)
#
# Use `ALL` to get multiple items in one query:

# %% Get all equity prices for a date
all_prices = read("prices.equity/ALL@20260115")
print(f"All equity prices: {len(all_prices)} records")

# Convert to DataFrame for analysis
import pandas as pd
df = pd.DataFrame(all_prices)
print(df.head())

# %% Get all index constituents
index_data = read("indices.sovereign/developed/EU.GovBondAgg/EUR/ALL")
print(f"Index constituents: {len(index_data)} records")

# %% [markdown]
# ## 3. Reference Data Lookups
#
# Security master and instrument metadata:

# %% Look up security by ISIN
security = read("reference.security/ISIN/US0378331005")
print(f"Security: {security}")

# %% Get the "official" version (verified namespace)
official_security = read("verified@reference.security/ISIN/US0378331005@latest")
print(f"Official record: {official_security}")

# %% Look up instrument metadata
metadata = read("instruments/US0378331005/metadata")
print(f"Instrument metadata: {metadata}")

# %% [markdown]
# ## 4. Portfolio & Holdings Data
#
# Access position data by date and portfolio:

# %% Get positions for a specific date and portfolio
positions = read("holdings/positions/20260115/fund_alpha")
print(f"Positions: {len(positions)} holdings")

# Convert to DataFrame
positions_df = pd.DataFrame(positions)
print(positions_df[['security_id', 'quantity', 'market_value']].head())

# %% Get exposure breakdown
exposures = read("holdings/exposures/20260115/fund_alpha")
print(f"Exposure breakdown: {exposures}")

# %% [markdown]
# ## 5. Risk Analytics
#
# Access risk metrics and user-defined views:

# %% Get VaR for a desk
var_data = read("analytics.risk/var/desk/equity")
print(f"VaR data: {var_data}")

# %% Access a saved user view (requires namespace)
# The 'user@' prefix scopes to your saved views
my_view = read("user@analytics.risk/views/my-watchlist@20260115/v3")
print(f"My watchlist: {my_view}")

# %% [markdown]
# ## 6. Ownership & Lineage
#
# Find out who owns the data and how to get help:

# %% Describe a data path
info = describe("prices.equity")
print(f"Display name: {info['display_name']}")
print(f"Owner: {info['ownership']['accountable_owner']}")
print(f"Specialist: {info['ownership']['data_specialist']}")
print(f"Support: {info['ownership']['support_channel']}")

# %% Get full lineage
lin = lineage("prices.equity/AAPL")
print(f"Ownership lineage:")
print(f"  Owner defined at: {lin['ownership']['accountable_owner_defined_at']}")
print(f"  Source binding at: {lin['source']['binding_defined_at']}")

# %% [markdown]
# ## 7. Exploring the Catalog
#
# Discover what data is available:

# %% List top-level domains
domains = list_children("")
print(f"Top-level domains: {domains}")

# %% List children of a domain
price_types = list_children("prices")
print(f"Price categories: {price_types}")

# %% List reference data
ref_data = list_children("reference")
print(f"Reference data categories: {ref_data}")

# %% [markdown]
# ## 8. Working with DataFrames
#
# Common patterns for analysis:

# %%
import pandas as pd

# Read and convert to DataFrame in one line
def read_df(moniker: str) -> pd.DataFrame:
    """Read moniker data as a pandas DataFrame."""
    data = read(moniker)
    if isinstance(data, list):
        return pd.DataFrame(data)
    elif isinstance(data, dict):
        return pd.DataFrame([data])
    return pd.DataFrame()

# Example usage
prices_df = read_df("prices.equity/ALL@20260115")
print(prices_df.describe())

# %% Pivot and analyze
if not prices_df.empty and 'symbol' in prices_df.columns:
    # Calculate daily returns
    prices_df['mid'] = (prices_df['high_price'] + prices_df['low_price']) / 2
    top_volume = prices_df.nlargest(10, 'volume')[['symbol', 'close_price', 'volume']]
    print("Top 10 by volume:")
    print(top_volume)

# %% [markdown]
# ## 9. Error Handling
#
# Handle common error cases:

# %%
from moniker_client import NotFoundError, FetchError

def safe_read(moniker: str):
    """Read with error handling."""
    try:
        return read(moniker)
    except NotFoundError:
        print(f"Path not found: {moniker}")
        print(f"Check the path or contact data team")
        # Get ownership info for support
        try:
            parent = "/".join(moniker.split("/")[:-1])
            info = describe(parent)
            print(f"Support channel: {info['ownership'].get('support_channel', 'N/A')}")
        except:
            pass
        return None
    except FetchError as e:
        print(f"Failed to fetch data: {e}")
        return None

# Example
data = safe_read("nonexistent/path/here")

# %% [markdown]
# ## 10. Advanced: Custom Configuration
#
# For non-standard setups:

# %%
from moniker_client import MonikerClient, ClientConfig

# Create client with custom config
config = ClientConfig(
    service_url="http://moniker-svc:8050",
    app_id="research-notebook",
    team="quant-research",
    timeout=60.0,  # Longer timeout for large queries
    cache_ttl=300,  # Cache resolutions for 5 minutes
)

client = MonikerClient(config=config)

# Use the custom client
data = client.read("prices.equity/AAPL")
info = client.describe("prices.equity")

# %% [markdown]
# ## Quick Reference
#
# ### Moniker Format
# ```
# [namespace@]domain.subdomain/path/segments[@version][/vN]
# ```
#
# ### Examples
# | Moniker | Description |
# |---------|-------------|
# | `prices.equity/AAPL` | Apple stock price (today) |
# | `prices.equity/AAPL@20260115` | Apple price on specific date |
# | `prices.equity/ALL@latest` | All equity prices, latest available |
# | `verified@reference.security/ISIN/US0378331005@latest` | Official security master record |
# | `user@analytics.risk/views/my-watchlist@20260115/v3` | User's saved view, version 3 |
# | `holdings/positions/20260115/fund_alpha` | Portfolio positions by date |
#
# ### Key Functions
# - `read(moniker)` - Fetch data
# - `describe(moniker)` - Get metadata and ownership
# - `lineage(moniker)` - Full ownership chain
# - `list_children(path)` - Explore catalog
