"""Mock Oracle adapter for demos and testing.

Uses SQLite in-memory to simulate Oracle database responses.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from typing import Any, TYPE_CHECKING
import random
import re

if TYPE_CHECKING:
    from ..client import ResolvedSource
    from ..config import ClientConfig

from .base import BaseAdapter


# Sample data configuration
PORTFOLIOS = [
    ("758", "A"),
    ("758", "B"),
    ("622", "A"),
    ("622", "B"),
]

CURRENCIES = ["USD", "EUR", "GBP", "JPY"]

SECURITIES = [
    "B0YHY8V7",
    "3140K1AP1",
    "3140L7Y55",
    "3164XW9F3",
    "353469109",
    "31428XCE4",
    "31417EQ38",
    "35086T109",
]

ACCT_KEYS = [
    "758-IDX-16220-[TPH200010]",
    "758-3938",
    "758-IDX-16480-[MESH20007]",
    "758-IDX-16620-[RTYH20002]",
    "758-IDX-13930-[SW00AA483]",
    "758-IDX-16620-[RTYZ10037]",
]


class MockOracleAdapter(BaseAdapter):
    """
    Mock Oracle adapter using SQLite for demos.

    This adapter doesn't require real Oracle credentials - it generates
    sample CVaR data for demonstration purposes.
    """

    _db: sqlite3.Connection | None = None

    def __init__(self):
        self._ensure_db()

    def _ensure_db(self) -> sqlite3.Connection:
        """Ensure database is initialized with sample data."""
        if MockOracleAdapter._db is None:
            MockOracleAdapter._db = self._create_mock_db()
        return MockOracleAdapter._db

    def _create_mock_db(self) -> sqlite3.Connection:
        """Create an in-memory SQLite database with sample CVaR data."""
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Create the CVaR table
        conn.execute("""
            CREATE TABLE te_stress_tail_risk_pnl (
                report_id INTEGER,
                asof_date TEXT,
                port_no TEXT,
                port_type TEXT,
                ssm_id TEXT,
                base_currency TEXT,
                acct_key TEXT,
                lt_id INTEGER,
                lt_id_2 INTEGER,
                cvar_coeff REAL,
                cvar REAL
            )
        """)

        # Generate sample timeseries data
        random.seed(42)  # Reproducible data
        base_date = date(2021, 12, 1)
        rows = []

        for report_id in [1, 2, 3]:
            for day_offset in range(30):  # 30 days of history
                asof = base_date + timedelta(days=day_offset)
                asof_str = asof.strftime("%Y-%m-%d")

                for port_no, port_type in PORTFOLIOS:
                    for currency in CURRENCIES:
                        # Each portfolio/currency combo has a subset of securities
                        securities_sample = random.sample(SECURITIES, k=random.randint(3, 6))

                        for ssm_id in securities_sample:
                            acct_key = random.choice(ACCT_KEYS)
                            lt_id = random.choice([0, 24])
                            lt_id_2 = random.choice([0, None])

                            # Generate realistic-looking CVaR values
                            cvar_coeff = random.uniform(-0.0001, 0.0001)
                            cvar = random.uniform(-0.02, 0.02)

                            rows.append((
                                report_id,
                                asof_str,
                                port_no,
                                port_type,
                                ssm_id,
                                currency,
                                acct_key,
                                lt_id,
                                lt_id_2,
                                cvar_coeff,
                                cvar,
                            ))

        conn.executemany("""
            INSERT INTO te_stress_tail_risk_pnl
            (report_id, asof_date, port_no, port_type, ssm_id, base_currency,
             acct_key, lt_id, lt_id_2, cvar_coeff, cvar)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)

        conn.commit()
        print(f"[MockOracle] Initialized with {len(rows)} sample CVaR records")
        return conn

    def _translate_oracle_to_sqlite(self, query: str) -> str:
        """Translate Oracle SQL syntax to SQLite."""
        translated = query

        # Remove schema prefixes (e.g., proteus_2_own.table -> table)
        translated = re.sub(r"\b\w+_own\.", "", translated)

        # Handle TO_DATE - SQLite uses strings directly
        translated = re.sub(
            r"TO_DATE\s*\(\s*'(\d{8})'\s*,\s*'YYYYMMDD'\s*\)",
            lambda m: f"'{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}'",
            translated
        )

        # Handle SYSDATE -> date('now')
        translated = translated.replace("SYSDATE", "date('now')")

        # Handle NVL -> COALESCE
        translated = re.sub(r"\bNVL\s*\(", "COALESCE(", translated, flags=re.IGNORECASE)

        return translated

    def fetch(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
        **kwargs,
    ) -> Any:
        """Execute query against mock database."""
        query = resolved.query
        if not query:
            raise ValueError("No query provided for Oracle source")

        # Translate Oracle syntax to SQLite
        sqlite_query = self._translate_oracle_to_sqlite(query)

        db = self._ensure_db()
        cursor = db.cursor()

        try:
            cursor.execute(sqlite_query)
            columns = [desc[0].upper() for desc in cursor.description]
            rows = cursor.fetchall()

            # Convert to list of dicts
            result = [dict(zip(columns, tuple(row))) for row in rows]
            print(f"[MockOracle] Query returned {len(result)} rows")
            return result

        except Exception as e:
            print(f"[MockOracle] Query error: {e}")
            print(f"[MockOracle] Query was: {sqlite_query[:200]}...")
            raise

    def list_children(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
    ) -> list[str]:
        """List available 'tables' (just returns the mock table name)."""
        return ["te_stress_tail_risk_pnl"]


def enable_mock_oracle():
    """
    Replace the Oracle adapter with the mock adapter.

    Call this at the start of your demo script:

        from moniker_client.adapters.mock_oracle import enable_mock_oracle
        enable_mock_oracle()
    """
    from . import register_adapter
    register_adapter("oracle", MockOracleAdapter())
    print("[MockOracle] Mock Oracle adapter enabled")
