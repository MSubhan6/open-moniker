"""Configuration for moniker service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .auth.config import AuthConfig


@dataclass
class ServerConfig:
    """HTTP server configuration."""
    host: str = "0.0.0.0"
    port: int = 8050
    workers: int = 4
    reload: bool = False


@dataclass
class TelemetryConfig:
    """Telemetry configuration."""
    enabled: bool = True
    sink_type: str = "console"  # console | file | zmq
    sink_config: dict[str, Any] = field(default_factory=dict)

    # Batching
    batch_size: int = 1000
    flush_interval_seconds: float = 1.0

    # Queue
    max_queue_size: int = 10000


@dataclass
class CacheConfig:
    """Cache configuration."""
    enabled: bool = True
    max_size: int = 10000
    default_ttl_seconds: float = 300.0


@dataclass
class CatalogConfig:
    """Catalog configuration."""
    # Path to catalog definition file (YAML or JSON)
    definition_file: str | None = None

    # Hot reload interval (0 = disabled)
    reload_interval_seconds: float = 0.0


@dataclass
class SqlCatalogConfig:
    """SQL Catalog configuration."""
    enabled: bool = False  # Disabled by default
    db_path: str = "sql_catalog.db"
    source_db_path: str | None = None


@dataclass
class ConfigUIConfig:
    """Config UI configuration."""
    enabled: bool = True
    yaml_output_path: str = "catalog_output.yaml"
    show_file_paths: bool = False  # Show file paths in save success messages (useful for debugging)


@dataclass
class DeprecationConfig:
    """Feature toggle for deprecation / decommissioning features.

    When disabled (default), the service behaves exactly as before:
    - No successor redirect on resolve
    - No validated diff on catalog reload (plain atomic_replace)
    - No deprecation fields in telemetry events
    - API responses still include successor/sunset fields (just always null)
    """
    enabled: bool = False  # Off by default — opt-in to avoid surprises
    redirect_on_resolve: bool = True    # Follow successor chain when resolving deprecated monikers
    validated_reload: bool = True       # Diff + audit on catalog hot-reload
    block_breaking_reload: bool = False # Block reload if breaking changes detected
    deprecation_telemetry: bool = True  # Tag telemetry events with deprecation info


@dataclass
class Config:
    """Main configuration container."""
    server: ServerConfig = field(default_factory=ServerConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    catalog: CatalogConfig = field(default_factory=CatalogConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    sql_catalog: SqlCatalogConfig = field(default_factory=SqlCatalogConfig)
    config_ui: ConfigUIConfig = field(default_factory=ConfigUIConfig)
    deprecation: DeprecationConfig = field(default_factory=DeprecationConfig)

    @classmethod
    def from_dict(cls, data: dict) -> Config:
        """Create config from dictionary."""
        auth_data = data.get("auth", {})
        return cls(
            server=ServerConfig(**data.get("server", {})),
            telemetry=TelemetryConfig(**data.get("telemetry", {})),
            cache=CacheConfig(**data.get("cache", {})),
            catalog=CatalogConfig(**data.get("catalog", {})),
            auth=AuthConfig.from_dict(auth_data) if auth_data else AuthConfig(),
            sql_catalog=SqlCatalogConfig(**data.get("sql_catalog", {})),
            config_ui=ConfigUIConfig(**data.get("config_ui", {})),
            deprecation=DeprecationConfig(**data.get("deprecation", {})),
        )

    @classmethod
    def from_yaml(cls, path: str) -> Config:
        """Load config from YAML file."""
        import yaml
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        return cls.from_dict(data or {})

    @classmethod
    def from_json(cls, path: str) -> Config:
        """Load config from JSON file."""
        import json
        with open(path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)
