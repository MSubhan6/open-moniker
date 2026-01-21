"""Snowflake adapter."""

from __future__ import annotations

import time
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


class SnowflakeAdapter(DataAdapter):
    """
    Adapter for Snowflake data warehouse.

    Config:
        account: Snowflake account identifier
        warehouse: Warehouse name
        database: Database name
        schema: Schema name (default: PUBLIC)
        role: Role to use

        # Auth options (one of):
        user/password: Username and password
        private_key_path: Path to private key file
        authenticator: externalbrowser, oauth, etc.

        # Query options:
        table: Table or view name (can include {path} placeholder)
        query: Custom SQL query (can include {path}, {moniker} placeholders)
        timeout: Query timeout in seconds
    """

    @property
    def source_type(self) -> SourceType:
        return SourceType.SNOWFLAKE

    async def fetch(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> AdapterResult:
        start = time.perf_counter()

        try:
            import snowflake.connector
        except ImportError:
            raise AdapterError(
                "snowflake-connector-python required: pip install snowflake-connector-python"
            )

        config = binding.config
        path_str = sub_path or str(moniker.path)

        # Build connection params
        conn_params = {
            "account": config.get("account"),
            "warehouse": config.get("warehouse"),
            "database": config.get("database"),
            "schema": config.get("schema", "PUBLIC"),
        }

        if config.get("role"):
            conn_params["role"] = config["role"]

        # Auth
        if config.get("user") and config.get("password"):
            conn_params["user"] = config["user"]
            conn_params["password"] = config["password"]
        elif config.get("private_key_path"):
            conn_params["private_key_file"] = config["private_key_path"]
            conn_params["user"] = config.get("user")
        elif config.get("authenticator"):
            conn_params["authenticator"] = config["authenticator"]
            conn_params["user"] = config.get("user")

        # Build query
        if config.get("query"):
            query = config["query"].format(path=path_str, moniker=str(moniker))
        elif config.get("table"):
            table = config["table"].format(path=path_str)
            query = f"SELECT * FROM {table}"
        else:
            raise AdapterError("Either 'query' or 'table' must be specified")

        # Add query params as filters
        if moniker.params:
            filters = []
            for key, value in moniker.params.params.items():
                if key not in ("version", "as_of"):  # Reserved params
                    filters.append(f"{key} = '{value}'")
            if filters:
                query = f"SELECT * FROM ({query}) WHERE {' AND '.join(filters)}"

        # Handle version/as_of
        if moniker.params and moniker.params.as_of:
            # Time travel
            query = query.replace("FROM ", f"FROM ... AT(TIMESTAMP => '{moniker.params.as_of}') ")

        try:
            conn = snowflake.connector.connect(**conn_params)
            cursor = conn.cursor()

            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()

            data = [dict(zip(columns, row)) for row in rows]

            cursor.close()
            conn.close()

        except snowflake.connector.errors.ProgrammingError as e:
            if "does not exist" in str(e).lower():
                raise AdapterNotFoundError(f"Table or view not found: {e}")
            raise AdapterError(f"Snowflake query error: {e}") from e
        except Exception as e:
            raise AdapterConnectionError(f"Snowflake connection error: {e}") from e

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
        """List tables/views in the schema."""
        try:
            import snowflake.connector
        except ImportError:
            return []

        config = binding.config
        conn_params = {
            "account": config.get("account"),
            "warehouse": config.get("warehouse"),
            "database": config.get("database"),
            "schema": config.get("schema", "PUBLIC"),
            "user": config.get("user"),
            "password": config.get("password"),
        }

        try:
            conn = snowflake.connector.connect(**conn_params)
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            tables = [row[1] for row in cursor.fetchall()]
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
        """Get schema information."""
        info = await super().describe(moniker, binding, sub_path)
        info["database"] = binding.config.get("database")
        info["schema"] = binding.config.get("schema", "PUBLIC")
        info["table"] = binding.config.get("table")
        return info

    async def health_check(self, binding: SourceBinding) -> bool:
        """Check Snowflake connectivity."""
        try:
            import snowflake.connector
            config = binding.config
            conn = snowflake.connector.connect(
                account=config.get("account"),
                user=config.get("user"),
                password=config.get("password"),
            )
            conn.cursor().execute("SELECT 1")
            conn.close()
            return True
        except Exception:
            return False
