"""Snowflake adapter - direct connection to Snowflake warehouse."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import ResolvedSource
    from ..config import ClientConfig

from .base import BaseAdapter


class SnowflakeAdapter(BaseAdapter):
    """
    Adapter for direct Snowflake connection.

    Credentials come from ClientConfig (environment variables).
    """

    def fetch(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
        **kwargs,
    ) -> Any:
        try:
            import snowflake.connector
        except ImportError:
            raise ImportError(
                "snowflake-connector-python required: pip install snowflake-connector-python"
            )

        conn_info = resolved.connection

        # Build connection params
        conn_params = {
            "account": conn_info.get("account"),
            "warehouse": conn_info.get("warehouse"),
            "database": conn_info.get("database"),
            "schema": conn_info.get("schema", "PUBLIC"),
        }

        if conn_info.get("role"):
            conn_params["role"] = conn_info["role"]

        # Get credentials from config
        user = config.get_credential("snowflake", "user")
        password = config.get_credential("snowflake", "password")
        private_key_path = config.get_credential("snowflake", "private_key_path")

        if user and password:
            conn_params["user"] = user
            conn_params["password"] = password
        elif private_key_path:
            conn_params["private_key_file"] = private_key_path
            conn_params["user"] = user
        else:
            raise ValueError(
                "Snowflake credentials not configured. "
                "Set SNOWFLAKE_USER and SNOWFLAKE_PASSWORD environment variables."
            )

        # Execute query
        query = resolved.query
        if not query:
            raise ValueError("No query provided for Snowflake source")

        conn = snowflake.connector.connect(**conn_params)
        try:
            cursor = conn.cursor()
            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            cursor.close()

            # Convert to list of dicts
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()

    def list_children(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
    ) -> list[str]:
        """List tables in the schema."""
        try:
            import snowflake.connector
        except ImportError:
            return []

        conn_info = resolved.connection
        user = config.get_credential("snowflake", "user")
        password = config.get_credential("snowflake", "password")

        if not user or not password:
            return []

        try:
            conn = snowflake.connector.connect(
                account=conn_info.get("account"),
                user=user,
                password=password,
                warehouse=conn_info.get("warehouse"),
                database=conn_info.get("database"),
                schema=conn_info.get("schema", "PUBLIC"),
            )
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            tables = [row[1] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            return tables
        except Exception:
            return []
