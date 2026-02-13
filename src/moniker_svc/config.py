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
class RedisConfig:
    """Redis configuration for query result caching."""
    enabled: bool = False
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    prefix: str = "moniker:cache:"
    # Connection settings
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0


@dataclass
class CatalogConfig:
    """Catalog configuration."""
    # Path to catalog definition file (YAML or JSON)
    definition_file: str | None = None

    # Hot reload interval (0 = disabled)
    reload_interval_seconds: float = 0.0


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
class ModelsConfig:
    """Business models configuration."""
    enabled: bool = True
    definition_file: str | None = None  # Path to models.yaml


@dataclass
class RequestsConfig:
    """Moniker request & approval workflow configuration."""
    enabled: bool = True
    definition_file: str | None = None  # Path to requests.yaml


@dataclass
class Config:
    """Main configuration container."""
    server: ServerConfig = field(default_factory=ServerConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    catalog: CatalogConfig = field(default_factory=CatalogConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    config_ui: ConfigUIConfig = field(default_factory=ConfigUIConfig)
    deprecation: DeprecationConfig = field(default_factory=DeprecationConfig)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    requests: RequestsConfig = field(default_factory=RequestsConfig)

    @classmethod
    def from_dict(cls, data: dict) -> Config:
        """Create config from dictionary."""
        auth_data = data.get("auth", {})
        return cls(
            server=ServerConfig(**data.get("server", {})),
            telemetry=TelemetryConfig(**data.get("telemetry", {})),
            cache=CacheConfig(**data.get("cache", {})),
            redis=RedisConfig(**data.get("redis", {})),
            catalog=CatalogConfig(**data.get("catalog", {})),
            auth=AuthConfig.from_dict(auth_data) if auth_data else AuthConfig(),
            config_ui=ConfigUIConfig(**data.get("config_ui", {})),
            deprecation=DeprecationConfig(**data.get("deprecation", {})),
            models=ModelsConfig(**data.get("models", {})),
            requests=RequestsConfig(**data.get("requests", {})),
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
