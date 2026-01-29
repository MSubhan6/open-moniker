"""Mock REST adapter for demos and testing.

Simulates REST API responses for commodities (NEFA) and other REST-backed sources.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, TYPE_CHECKING
import random
import re

if TYPE_CHECKING:
    from ..client import ResolvedSource
    from ..config import ClientConfig

from .base import BaseAdapter


# Energy commodities sample data
ENERGY_SYMBOLS = {
    "CL": {"name": "WTI Crude Oil", "unit": "barrel", "base_price": 78.50},
    "BZ": {"name": "Brent Crude", "unit": "barrel", "base_price": 82.30},
    "NG": {"name": "Natural Gas", "unit": "MMBtu", "base_price": 2.85},
    "HO": {"name": "Heating Oil", "unit": "gallon", "base_price": 2.65},
    "RB": {"name": "RBOB Gasoline", "unit": "gallon", "base_price": 2.45},
}

# Metals commodities sample data
METALS_SYMBOLS = {
    "GC": {"name": "Gold", "unit": "troy oz", "base_price": 2045.30},
    "SI": {"name": "Silver", "unit": "troy oz", "base_price": 24.50},
    "HG": {"name": "Copper", "unit": "lb", "base_price": 3.85},
    "PL": {"name": "Platinum", "unit": "troy oz", "base_price": 985.00},
    "PA": {"name": "Palladium", "unit": "troy oz", "base_price": 1025.00},
}

CONTRACTS = ["SPOT", "F1", "F2", "F3", "F4", "F5", "F6"]


class MockRestAdapter(BaseAdapter):
    """
    Mock REST adapter for demos.

    Simulates responses from the NEFA commodities API and other REST sources.
    """

    def __init__(self):
        random.seed(42)

    def _generate_energy_data(self, symbol: str, contract: str) -> list[dict]:
        """Generate sample energy commodity data."""
        if symbol not in ENERGY_SYMBOLS and symbol != "ALL":
            return []

        symbols = [symbol] if symbol != "ALL" else list(ENERGY_SYMBOLS.keys())
        contracts = [contract] if contract != "ALL" else CONTRACTS

        results = []
        base_time = datetime(2026, 1, 28, 14, 30, 0)

        for sym in symbols:
            info = ENERGY_SYMBOLS[sym]
            for cont in contracts:
                # Add contango/backwardation structure
                contract_adj = 0
                if cont.startswith("F"):
                    month = int(cont[1:])
                    contract_adj = month * 0.15  # Slight contango

                for i in range(24):  # 24 hours of history
                    timestamp = base_time - timedelta(hours=i)
                    price = info["base_price"] + contract_adj + random.uniform(-2, 2)
                    prior_close = info["base_price"] + contract_adj
                    change = price - prior_close
                    change_pct = (change / prior_close) * 100

                    results.append({
                        "TIMESTAMP": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "SYMBOL": sym,
                        "CONTRACT": cont,
                        "NAME": info["name"],
                        "UNIT": info["unit"],
                        "PRICE": round(price, 2),
                        "CHANGE": round(change, 2),
                        "CHANGE_PCT": round(change_pct, 2),
                        "VOLUME": random.randint(50000, 200000),
                        "OPEN_INTEREST": random.randint(300000, 600000),
                        "BID": round(price - 0.02, 2),
                        "ASK": round(price + 0.02, 2),
                    })

        return results

    def _generate_metals_data(self, symbol: str, contract: str) -> list[dict]:
        """Generate sample metals commodity data."""
        if symbol not in METALS_SYMBOLS and symbol != "ALL":
            return []

        symbols = [symbol] if symbol != "ALL" else list(METALS_SYMBOLS.keys())
        contracts = [contract] if contract != "ALL" else ["SPOT", "F1", "F2", "F3"]

        results = []
        base_time = datetime(2026, 1, 28, 14, 30, 0)

        for sym in symbols:
            info = METALS_SYMBOLS[sym]
            for cont in contracts:
                contract_adj = 0
                if cont.startswith("F"):
                    month = int(cont[1:])
                    contract_adj = info["base_price"] * month * 0.001  # Small contango

                for i in range(24):
                    timestamp = base_time - timedelta(hours=i)
                    price = info["base_price"] + contract_adj + random.uniform(
                        -info["base_price"] * 0.01,
                        info["base_price"] * 0.01
                    )
                    prior_close = info["base_price"] + contract_adj
                    change = price - prior_close
                    change_pct = (change / prior_close) * 100

                    results.append({
                        "TIMESTAMP": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "SYMBOL": sym,
                        "CONTRACT": cont,
                        "NAME": info["name"],
                        "UNIT": info["unit"],
                        "PRICE": round(price, 2),
                        "CHANGE": round(change, 2),
                        "CHANGE_PCT": round(change_pct, 3),
                        "VOLUME": random.randint(20000, 100000),
                        "OPEN_INTEREST": random.randint(100000, 300000),
                        "CURRENCY": "USD",
                    })

        return results

    def fetch(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
        **kwargs,
    ) -> Any:
        """Fetch data from mock REST API."""
        path = resolved.query or ""
        connection = resolved.connection

        # Parse the path to determine what data to return
        # Expected format: /v2/commodities/energy/{symbol}/{contract}
        #               or /v2/commodities/metals/{symbol}/{contract}

        path_parts = path.strip("/").split("/")

        # Check for NEFA API patterns
        if "energy" in path.lower() or "energy" in str(connection.get("base_url", "")):
            symbol = path_parts[-2] if len(path_parts) >= 2 else "ALL"
            contract = path_parts[-1] if len(path_parts) >= 1 else "ALL"
            result = self._generate_energy_data(symbol.upper(), contract.upper())
            print(f"[MockRest/NEFA] Energy query: {symbol}/{contract} -> {len(result)} rows")
            return result

        elif "metals" in path.lower() or "metals" in str(connection.get("base_url", "")):
            symbol = path_parts[-2] if len(path_parts) >= 2 else "ALL"
            contract = path_parts[-1] if len(path_parts) >= 1 else "ALL"
            result = self._generate_metals_data(symbol.upper(), contract.upper())
            print(f"[MockRest/NEFA] Metals query: {symbol}/{contract} -> {len(result)} rows")
            return result

        # Default: return empty list for unknown endpoints
        print(f"[MockRest] Unknown endpoint: {path}")
        return []

    def list_children(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
    ) -> list[str]:
        """List available endpoints."""
        return ["energy", "metals"]


def enable_mock_rest():
    """
    Replace the REST adapter with the mock adapter.

    Call this at the start of your demo script:

        from moniker_client.adapters.mock_rest import enable_mock_rest
        enable_mock_rest()
    """
    from . import register_adapter
    register_adapter("rest", MockRestAdapter())
    print("[MockRest] Mock REST adapter enabled")
