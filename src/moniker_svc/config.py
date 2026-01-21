"""Configuration for moniker service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ServerConfig:
    """HTTP server configuration."""
    host: str = "0.0.0.0"
    port: int = 8000
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
class Config:
    """Main configuration container."""
    server: ServerConfig = field(default_factory=ServerConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    catalog: CatalogConfig = field(default_factory=CatalogConfig)

    @classmethod
    def from_dict(cls, data: dict) -> Config:
        """Create config from dictionary."""
        return cls(
            server=ServerConfig(**data.get("server", {})),
            telemetry=TelemetryConfig(**data.get("telemetry", {})),
            cache=CacheConfig(**data.get("cache", {})),
            catalog=CatalogConfig(**data.get("catalog", {})),
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
