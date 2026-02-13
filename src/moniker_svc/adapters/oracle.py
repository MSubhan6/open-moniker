"""Oracle database adapter."""

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


class OracleAdapter(DataAdapter):
    """
    Adapter for Oracle database.

    Config:
        # Connection options (one of):
        dsn: TNS name or Easy Connect string
        host/port/service_name: Individual connection params

        user: Username
        password: Password

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
        return SourceType.ORACLE

    async def fetch(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> AdapterResult:
        start = time.perf_counter()

        try:
            import oracledb
        except ImportError:
            raise AdapterError("oracledb required: pip install oracledb")

        config = binding.config
        path_str = sub_path or str(moniker.path)

        # Build connection
        dsn = config.get("dsn")
        if not dsn:
            host = config.get("host", "localhost")
            port = config.get("port", 1521)
            service_name = config.get("service_name")
            if service_name:
                dsn = f"{host}:{port}/{service_name}"
            else:
                raise AdapterError("Either 'dsn' or 'host/port/service_name' required")

        # Build query using resolve_query helper
        format_vars = {"path": path_str, "moniker": str(moniker)}
        query = self.resolve_query(config, format_vars, self._catalog_dir)

        # Add query params as filters
        if moniker.params:
            filters = []
            for key, value in moniker.params.params.items():
                if key not in ("version", "as_of"):
                    filters.append(f"{key} = '{value}'")
            if filters:
                query = f"SELECT * FROM ({query}) WHERE {' AND '.join(filters)}"

        # Handle as_of with Oracle Flashback
        if moniker.params and moniker.params.as_of:
            query = query.replace(
                "FROM ",
                f"FROM ... AS OF TIMESTAMP TO_TIMESTAMP('{moniker.params.as_of}', 'YYYY-MM-DD') "
            )

        try:
            conn = oracledb.connect(
                user=config.get("user"),
                password=config.get("password"),
                dsn=dsn,
            )
            cursor = conn.cursor()

            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            data = [dict(zip(columns, row)) for row in rows]

            cursor.close()
            conn.close()

        except oracledb.DatabaseError as e:
            error_msg = str(e)
            if "ORA-00942" in error_msg:  # table or view does not exist
                raise AdapterNotFoundError(f"Table or view not found")
            raise AdapterError(f"Oracle query error: {e}") from e
        except Exception as e:
            raise AdapterConnectionError(f"Oracle connection error: {e}") from e

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
        """List tables in the schema."""
        try:
            import oracledb
        except ImportError:
            return []

        config = binding.config
        dsn = config.get("dsn", f"{config.get('host')}:{config.get('port')}/{config.get('service_name')}")

        try:
            conn = oracledb.connect(
                user=config.get("user"),
                password=config.get("password"),
                dsn=dsn,
            )
            cursor = conn.cursor()
            cursor.execute("SELECT table_name FROM user_tables ORDER BY table_name")
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
        info["dsn"] = binding.config.get("dsn")
        info["table"] = binding.config.get("table")
        return info

    async def health_check(self, binding: SourceBinding) -> bool:
        try:
            import oracledb
            config = binding.config
            dsn = config.get("dsn", f"{config.get('host')}:{config.get('port')}/{config.get('service_name')}")
            conn = oracledb.connect(
                user=config.get("user"),
                password=config.get("password"),
                dsn=dsn,
            )
            conn.cursor().execute("SELECT 1 FROM DUAL")
            conn.close()
            return True
        except Exception:
            return False
