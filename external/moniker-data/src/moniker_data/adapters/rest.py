"""Mock REST adapter for demos and testing.

Simulates REST API responses for commodities (NEFA) and other REST-backed sources.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
import random


# =============================================================================
# Sample Data Configuration
# =============================================================================

ENERGY_SYMBOLS = {
    "CL": {"name": "WTI Crude Oil", "unit": "barrel", "base_price": 78.50},
    "BZ": {"name": "Brent Crude", "unit": "barrel", "base_price": 82.30},
    "NG": {"name": "Natural Gas", "unit": "MMBtu", "base_price": 2.85},
    "HO": {"name": "Heating Oil", "unit": "gallon", "base_price": 2.65},
    "RB": {"name": "RBOB Gasoline", "unit": "gallon", "base_price": 2.45},
}

METALS_SYMBOLS = {
    "GC": {"name": "Gold", "unit": "troy oz", "base_price": 2045.30},
    "SI": {"name": "Silver", "unit": "troy oz", "base_price": 24.50},
    "HG": {"name": "Copper", "unit": "lb", "base_price": 3.85},
    "PL": {"name": "Platinum", "unit": "troy oz", "base_price": 985.00},
    "PA": {"name": "Palladium", "unit": "troy oz", "base_price": 1025.00},
}

CONTRACTS = ["SPOT", "F1", "F2", "F3", "F4", "F5", "F6"]


# =============================================================================
# Mock REST Adapter
# =============================================================================

class MockRestAdapter:
    """
    Mock REST adapter for demos.

    Simulates responses from the NEFA commodities API and other REST sources.
    """

    def __init__(self, seed: int = 42):
        random.seed(seed)

    def get_energy(self, symbol: str = "ALL", contract: str = "ALL") -> list[dict[str, Any]]:
        """Get energy commodity data."""
        if symbol not in ENERGY_SYMBOLS and symbol != "ALL":
            return []

        symbols = [symbol] if symbol != "ALL" else list(ENERGY_SYMBOLS.keys())
        contracts = [contract] if contract != "ALL" else CONTRACTS

        results = []
        base_time = datetime(2026, 1, 28, 14, 30, 0)

        for sym in symbols:
            info = ENERGY_SYMBOLS[sym]
            for cont in contracts:
                contract_adj = 0
                if cont.startswith("F"):
                    month = int(cont[1:])
                    contract_adj = month * 0.15

                for i in range(24):
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

    def get_metals(self, symbol: str = "ALL", contract: str = "ALL") -> list[dict[str, Any]]:
        """Get metals commodity data."""
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
                    contract_adj = info["base_price"] * month * 0.001

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

    def fetch(self, path: str, **kwargs) -> list[dict[str, Any]]:
        """Fetch data based on path."""
        path_parts = path.strip("/").split("/")

        if "energy" in path.lower():
            symbol = path_parts[-2] if len(path_parts) >= 2 else "ALL"
            contract = path_parts[-1] if len(path_parts) >= 1 else "ALL"
            return self.get_energy(symbol.upper(), contract.upper())

        elif "metals" in path.lower():
            symbol = path_parts[-2] if len(path_parts) >= 2 else "ALL"
            contract = path_parts[-1] if len(path_parts) >= 1 else "ALL"
            return self.get_metals(symbol.upper(), contract.upper())

        return []

    def list_endpoints(self) -> list[str]:
        """List available endpoints."""
        return ["energy", "metals"]
