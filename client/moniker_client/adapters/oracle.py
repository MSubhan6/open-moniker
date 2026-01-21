"""Oracle adapter - direct connection to Oracle database."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..client import ResolvedSource
    from ..config import ClientConfig

from .base import BaseAdapter


class OracleAdapter(BaseAdapter):
    """
    Adapter for direct Oracle database connection.

    Credentials come from ClientConfig (environment variables).
    """

    def fetch(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
        **kwargs,
    ) -> Any:
        try:
            import oracledb
        except ImportError:
            raise ImportError("oracledb required: pip install oracledb")

        conn_info = resolved.connection

        # Build DSN
        dsn = conn_info.get("dsn")
        if not dsn:
            host = conn_info.get("host", "localhost")
            port = conn_info.get("port", 1521)
            service_name = conn_info.get("service_name")
            if service_name:
                dsn = f"{host}:{port}/{service_name}"
            else:
                raise ValueError("Oracle DSN or host/port/service_name required")

        # Get credentials from config
        user = config.get_credential("oracle", "user")
        password = config.get_credential("oracle", "password")

        if not user or not password:
            raise ValueError(
                "Oracle credentials not configured. "
                "Set ORACLE_USER and ORACLE_PASSWORD environment variables."
            )

        # Execute query
        query = resolved.query
        if not query:
            raise ValueError("No query provided for Oracle source")

        conn = oracledb.connect(user=user, password=password, dsn=dsn)
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
            import oracledb
        except ImportError:
            return []

        conn_info = resolved.connection
        user = config.get_credential("oracle", "user")
        password = config.get_credential("oracle", "password")

        if not user or not password:
            return []

        dsn = conn_info.get("dsn")
        if not dsn:
            host = conn_info.get("host", "localhost")
            port = conn_info.get("port", 1521)
            service_name = conn_info.get("service_name")
            dsn = f"{host}:{port}/{service_name}"

        try:
            conn = oracledb.connect(user=user, password=password, dsn=dsn)
            cursor = conn.cursor()
            cursor.execute("SELECT table_name FROM user_tables ORDER BY table_name")
            tables = [row[0] for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            return tables
        except Exception:
            return []
