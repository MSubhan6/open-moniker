"""Client configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClientConfig:
    """
    Configuration for the moniker client.

    Can be set via:
    - Constructor arguments
    - Environment variables (MONIKER_*)
    - Config file
    """
    # Moniker service URL
    service_url: str = field(
        default_factory=lambda: os.environ.get("MONIKER_SERVICE_URL", "http://localhost:8000")
    )

    # Identity headers
    app_id: str | None = field(
        default_factory=lambda: os.environ.get("MONIKER_APP_ID")
    )
    team: str | None = field(
        default_factory=lambda: os.environ.get("MONIKER_TEAM")
    )

    # Request timeout (seconds)
    timeout: float = field(
        default_factory=lambda: float(os.environ.get("MONIKER_TIMEOUT", "30"))
    )

    # Report telemetry back to service
    report_telemetry: bool = field(
        default_factory=lambda: os.environ.get("MONIKER_REPORT_TELEMETRY", "true").lower() == "true"
    )

    # Cache resolved connections locally (seconds, 0 = disabled)
    cache_ttl: float = field(
        default_factory=lambda: float(os.environ.get("MONIKER_CACHE_TTL", "60"))
    )

    # Database credentials (not from service for security)
    # These are used by the client when connecting to sources
    snowflake_user: str | None = field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_USER")
    )
    snowflake_password: str | None = field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_PASSWORD")
    )
    snowflake_private_key_path: str | None = field(
        default_factory=lambda: os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    )

    oracle_user: str | None = field(
        default_factory=lambda: os.environ.get("ORACLE_USER")
    )
    oracle_password: str | None = field(
        default_factory=lambda: os.environ.get("ORACLE_PASSWORD")
    )

    # Additional credentials as dict
    credentials: dict[str, Any] = field(default_factory=dict)

    def get_credential(self, source_type: str, key: str) -> str | None:
        """Get a credential for a source type."""
        # Check specific attributes first
        if source_type == "snowflake":
            if key == "user":
                return self.snowflake_user
            if key == "password":
                return self.snowflake_password
            if key == "private_key_path":
                return self.snowflake_private_key_path
        elif source_type == "oracle":
            if key == "user":
                return self.oracle_user
            if key == "password":
                return self.oracle_password

        # Check credentials dict
        return self.credentials.get(f"{source_type}_{key}")
