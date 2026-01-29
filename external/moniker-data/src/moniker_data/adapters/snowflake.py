"""Mock Snowflake adapter for demos and testing.

Uses SQLite in-memory to simulate Snowflake database responses.
Includes sample data for govies, rates, and other Snowflake-backed domains.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any
import random
import re


# =============================================================================
# Sample Data Configuration
# =============================================================================

TREASURY_TENORS = ["3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
TREASURY_CUSIPS = [
    "912828ZT5", "912828ZU2", "912828ZV0", "912828ZW8", "912828ZX6",
    "912828ZY4", "912828ZZ1", "91282CAA5", "91282CAB3", "91282CAC1",
]
SOVEREIGN_COUNTRIES = ["DE", "GB", "JP", "FR", "IT", "CA", "AU"]
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"]
SWAP_TENORS = ["1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "15Y", "20Y", "30Y"]


# =============================================================================
# Mock Snowflake Adapter
# =============================================================================

class MockSnowflakeAdapter:
    """
    Mock Snowflake adapter using SQLite for demos/testing.

    This adapter doesn't require real Snowflake credentials - it generates
    sample data for demonstration purposes.
    """

    _db: sqlite3.Connection | None = None

    def __init__(self):
        self._ensure_db()

    def _ensure_db(self) -> sqlite3.Connection:
        """Ensure database is initialized with sample data."""
        if MockSnowflakeAdapter._db is None:
            MockSnowflakeAdapter._db = self._create_mock_db()
        return MockSnowflakeAdapter._db

    def _create_mock_db(self) -> sqlite3.Connection:
        """Create an in-memory SQLite database with sample data."""
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Create Treasury securities table
        conn.execute("""
            CREATE TABLE treasury_securities (
                asof_date TEXT,
                cusip TEXT,
                country TEXT,
                tenor TEXT,
                coupon REAL,
                yield REAL,
                price REAL,
                duration REAL,
                convexity REAL
            )
        """)

        # Create Sovereign bonds table
        conn.execute("""
            CREATE TABLE sovereign_bonds (
                asof_date TEXT,
                isin TEXT,
                country TEXT,
                tenor TEXT,
                yield REAL,
                spread_vs_usd REAL,
                price REAL,
                duration REAL
            )
        """)

        # Create Swap rates table
        conn.execute("""
            CREATE TABLE swap_rates (
                asof_date TEXT,
                currency TEXT,
                tenor TEXT,
                par_rate REAL,
                spread_vs_govt REAL,
                dv01 REAL
            )
        """)

        # Create SOFR rates table
        conn.execute("""
            CREATE TABLE sofr_rates (
                asof_date TEXT,
                rate_type TEXT,
                rate REAL
            )
        """)

        # Generate sample data
        random.seed(42)
        base_date = date(2026, 1, 1)

        # Treasury data
        treasury_rows = []
        for day_offset in range(30):
            asof = base_date + timedelta(days=day_offset)
            asof_str = asof.strftime("%Y-%m-%d")

            for i, tenor in enumerate(TREASURY_TENORS):
                cusip = TREASURY_CUSIPS[i % len(TREASURY_CUSIPS)]
                base_yield = 0.03 + (i * 0.002) + random.uniform(-0.001, 0.001)
                coupon = round(base_yield - 0.005, 4)
                price = 100 - (base_yield - coupon) * (i + 1) * 10
                duration = (i + 1) * 0.9
                convexity = duration * 0.1

                treasury_rows.append((
                    asof_str, cusip, "US", tenor,
                    round(coupon, 4), round(base_yield, 4),
                    round(price, 2), round(duration, 2), round(convexity, 3)
                ))

        conn.executemany("""
            INSERT INTO treasury_securities
            (asof_date, cusip, country, tenor, coupon, yield, price, duration, convexity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, treasury_rows)

        # Sovereign data
        sovereign_rows = []
        for day_offset in range(30):
            asof = base_date + timedelta(days=day_offset)
            asof_str = asof.strftime("%Y-%m-%d")

            for country in SOVEREIGN_COUNTRIES:
                for i, tenor in enumerate(["2Y", "5Y", "10Y", "30Y"]):
                    isin = f"{country}000{i}102481"
                    base_yield = 0.02 + (i * 0.003) + random.uniform(-0.002, 0.002)
                    if country == "JP":
                        base_yield -= 0.02
                    spread = random.uniform(-150, 50)
                    price = 100 - (base_yield * (i + 1) * 8)
                    duration = (i + 1) * 2.2

                    sovereign_rows.append((
                        asof_str, isin, country, tenor,
                        round(base_yield, 4), round(spread, 1),
                        round(price, 2), round(duration, 2)
                    ))

        conn.executemany("""
            INSERT INTO sovereign_bonds
            (asof_date, isin, country, tenor, yield, spread_vs_usd, price, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, sovereign_rows)

        # Swap rates data
        swap_rows = []
        for day_offset in range(30):
            asof = base_date + timedelta(days=day_offset)
            asof_str = asof.strftime("%Y-%m-%d")

            for currency in CURRENCIES:
                for i, tenor in enumerate(SWAP_TENORS):
                    base_rate = 0.035 + (i * 0.002) + random.uniform(-0.001, 0.001)
                    if currency == "JPY":
                        base_rate -= 0.03
                    elif currency == "EUR":
                        base_rate -= 0.01
                    spread = random.uniform(5, 25)
                    dv01 = (i + 1) * 90 + random.uniform(-10, 10)

                    swap_rows.append((
                        asof_str, currency, tenor,
                        round(base_rate, 4), round(spread, 1), round(dv01, 2)
                    ))

        conn.executemany("""
            INSERT INTO swap_rates
            (asof_date, currency, tenor, par_rate, spread_vs_govt, dv01)
            VALUES (?, ?, ?, ?, ?, ?)
        """, swap_rows)

        # SOFR rates data
        sofr_rows = []
        for day_offset in range(30):
            asof = base_date + timedelta(days=day_offset)
            asof_str = asof.strftime("%Y-%m-%d")

            base_sofr = 0.043 + random.uniform(-0.001, 0.001)
            for rate_type, adj in [("ON", 0), ("30D_AVG", 0.0002), ("90D_AVG", 0.0004),
                                    ("TERM_1M", 0.0005), ("TERM_3M", 0.001)]:
                sofr_rows.append((
                    asof_str, rate_type, round(base_sofr + adj, 4)
                ))

        conn.executemany("""
            INSERT INTO sofr_rates (asof_date, rate_type, rate)
            VALUES (?, ?, ?)
        """, sofr_rows)

        conn.commit()
        return conn

    def execute(self, query: str) -> list[dict[str, Any]]:
        """Execute query against mock database."""
        sqlite_query = self._translate_snowflake_to_sqlite(query)
        db = self._ensure_db()
        cursor = db.cursor()

        cursor.execute(sqlite_query)
        columns = [desc[0].upper() for desc in cursor.description]
        rows = cursor.fetchall()

        return [dict(zip(columns, tuple(row))) for row in rows]

    def reset(self):
        """Reset the database."""
        MockSnowflakeAdapter._db = None
        self._ensure_db()

    def _translate_snowflake_to_sqlite(self, query: str) -> str:
        """Translate Snowflake SQL syntax to SQLite."""
        translated = query

        # Remove database.schema. prefixes
        translated = re.sub(r"\b\w+\.\w+\.(\w+)", r"\1", translated)

        # Handle TO_DATE with format
        translated = re.sub(
            r"TO_DATE\s*\(\s*'(\d{8})'\s*,\s*'YYYYMMDD'\s*\)",
            lambda m: f"'{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}'",
            translated
        )

        # Handle CURRENT_DATE()
        translated = translated.replace("CURRENT_DATE()", "date('now')")

        # Handle NVL -> COALESCE
        translated = re.sub(r"\bNVL\s*\(", "COALESCE(", translated, flags=re.IGNORECASE)

        # Convert table names to lowercase
        for table in ["TREASURY_SECURITIES", "SOVEREIGN_BONDS", "SWAP_RATES", "SOFR_RATES"]:
            translated = translated.replace(table, table.lower())

        return translated

    def list_tables(self) -> list[str]:
        """List available tables."""
        return ["treasury_securities", "sovereign_bonds", "swap_rates", "sofr_rates"]
