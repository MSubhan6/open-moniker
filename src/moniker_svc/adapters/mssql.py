"""Microsoft SQL Server adapter."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..catalog.types import SourceBinding, SourceType
from ..moniker.types import Moniker
from .base import (
    AdapterConnectionError,
    AdapterError,
    AdapterNotFoundError,
    AdapterResult,
    DataAdapter,
)


class MssqlAdapter(DataAdapter):
    """
    Adapter for Microsoft SQL Server.

    Config:
        # Connection options (one of):
        connection_string: Full ODBC connection string
        # OR individual params:
        server: Server hostname or IP
        database: Database name
        driver: ODBC driver name (default: "ODBC Driver 17 for SQL Server")

        # Auth options (one of):
        user/password: SQL authentication
        trusted_connection: true for Windows integrated auth

        # Query options:
        table: Table or view name (can include {path} placeholder)
        query: Custom SQL query (can include {path}, {moniker} placeholders)
        query_file: Path to external .sql file
        timeout: Query timeout in seconds
    """

    def __init__(self, catalog_dir: Path | None = None):
        """
        Initialize adapter with optional catalog directory for query_file resolution.

        Args:
            catalog_dir: Base directory for resolving relative query_file paths
        """
        self._catalog_dir = catalog_dir

    @property
    def source_type(self) -> SourceType:
        return SourceType.MSSQL

    async def fetch(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> AdapterResult:
        start = time.perf_counter()

        try:
            import pyodbc
        except ImportError:
            raise AdapterError("pyodbc required: pip install pyodbc")

        config = binding.config
        path_str = sub_path or str(moniker.path)

        # Build connection string
        conn_str = config.get("connection_string")
        if not conn_str:
            driver = config.get("driver", "ODBC Driver 17 for SQL Server")
            server = config.get("server")
            database = config.get("database")

            if not server:
                raise AdapterError("Either 'connection_string' or 'server' required")

            conn_str = f"DRIVER={{{driver}}};SERVER={server}"

            if database:
                conn_str += f";DATABASE={database}"

            # Auth
            if config.get("trusted_connection"):
                conn_str += ";Trusted_Connection=yes"
            elif config.get("user") and config.get("password"):
                conn_str += f";UID={config['user']};PWD={config['password']}"

        # Build query using resolve_query helper
        format_vars = {"path": path_str, "moniker": str(moniker)}
        query = self.resolve_query(config, format_vars, self._catalog_dir)

        # Add query params as filters
        if moniker.params:
            filters = []
            for key, value in moniker.params.params.items():
                if key not in ("version", "as_of"):  # Reserved params
                    filters.append(f"{key} = '{value}'")
            if filters:
                query = f"SELECT * FROM ({query}) AS subq WHERE {' AND '.join(filters)}"

        # Handle as_of with temporal tables (SQL Server 2016+)
        if moniker.params and moniker.params.as_of:
            # This requires the table to be system-versioned
            # For non-temporal tables, this will fail gracefully
            pass  # Temporal query handling would go here

        try:
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()

            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            data = [dict(zip(columns, row)) for row in rows]

            cursor.close()
            conn.close()

        except pyodbc.ProgrammingError as e:
            error_msg = str(e)
            if "Invalid object name" in error_msg:
                raise AdapterNotFoundError(f"Table or view not found: {e}")
            raise AdapterError(f"MSSQL query error: {e}") from e
        except pyodbc.Error as e:
            raise AdapterConnectionError(f"MSSQL connection error: {e}") from e
        except Exception as e:
            raise AdapterConnectionError(f"MSSQL error: {e}") from e

        elapsed = (time.perf_counter() - start) * 1000

        return AdapterResult(
            data=data,
            source_type=self.source_type,
            source_path=query[:200],
            query_ms=elapsed,
            row_count=len(data),
            metadata={"columns": columns},
        )

    async def list_children(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> list[str]:
        """List tables in the database."""
        try:
            import pyodbc
        except ImportError:
            return []

        config = binding.config
        conn_str = config.get("connection_string")
        if not conn_str:
            driver = config.get("driver", "ODBC Driver 17 for SQL Server")
            server = config.get("server")
            database = config.get("database")
            conn_str = f"DRIVER={{{driver}}};SERVER={server}"
            if database:
                conn_str += f";DATABASE={database}"
            if config.get("trusted_connection"):
                conn_str += ";Trusted_Connection=yes"
            elif config.get("user") and config.get("password"):
                conn_str += f";UID={config['user']};PWD={config['password']}"

        try:
            conn = pyodbc.connect(conn_str)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME"
            )
            tables = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            return tables
        except Exception:
            return []

    async def describe(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> dict[str, Any]:
        info = await super().describe(moniker, binding, sub_path)
        info["server"] = binding.config.get("server")
        info["database"] = binding.config.get("database")
        info["table"] = binding.config.get("table")
        return info

    async def health_check(self, binding: SourceBinding) -> bool:
        try:
            import pyodbc
            config = binding.config
            conn_str = config.get("connection_string")
            if not conn_str:
                driver = config.get("driver", "ODBC Driver 17 for SQL Server")
                server = config.get("server")
                conn_str = f"DRIVER={{{driver}}};SERVER={server}"
                if config.get("trusted_connection"):
                    conn_str += ";Trusted_Connection=yes"
                elif config.get("user") and config.get("password"):
                    conn_str += f";UID={config['user']};PWD={config['password']}"

            conn = pyodbc.connect(conn_str)
            conn.cursor().execute("SELECT 1")
            conn.close()
            return True
        except Exception:
            return False
