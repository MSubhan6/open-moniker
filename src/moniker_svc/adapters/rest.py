"""REST API adapter."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

from ..catalog.types import SourceBinding, SourceType
from ..moniker.types import Moniker
from .base import (
    AdapterConnectionError,
    AdapterError,
    AdapterNotFoundError,
    AdapterResult,
    DataAdapter,
)


class RestApiAdapter(DataAdapter):
    """
    Adapter for REST APIs.

    Config:
        base_url: Base URL for the API
        path_template: URL path template (can include {path}, {moniker} placeholders)
        method: HTTP method (default: GET)
        headers: Additional headers
        auth_type: none | bearer | basic | api_key
        auth_config: Auth-specific config (token, username/password, key location)
        timeout: Request timeout in seconds
        response_path: JSON path to extract data from response (e.g., "data.items")
    """

    @property
    def source_type(self) -> SourceType:
        return SourceType.REST

    async def fetch(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> AdapterResult:
        start = time.perf_counter()

        try:
            import httpx
        except ImportError:
            raise AdapterError("httpx required for REST adapter: pip install httpx")

        base_url = binding.config.get("base_url")
        if not base_url:
            raise AdapterError("base_url is required for REST adapter")

        path_template = binding.config.get("path_template", "/{path}")
        method = binding.config.get("method", "GET").upper()
        headers = dict(binding.config.get("headers", {}))
        timeout = binding.config.get("timeout", 30)
        response_path = binding.config.get("response_path")

        # Build URL
        path_str = sub_path or str(moniker.path)
        url_path = path_template.format(path=path_str, moniker=str(moniker))
        url = urljoin(base_url, url_path)

        # Apply auth
        self._apply_auth(headers, binding.config)

        # Add query params from moniker
        params = dict(moniker.params.params) if moniker.params else {}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, headers=headers, params=params)

                if response.status_code == 404:
                    raise AdapterNotFoundError(f"Resource not found: {url}")
                if response.status_code >= 400:
                    raise AdapterError(
                        f"REST API error: {response.status_code} - {response.text[:200]}"
                    )

                data = response.json()

        except httpx.ConnectError as e:
            raise AdapterConnectionError(f"Failed to connect to {base_url}: {e}") from e
        except httpx.TimeoutException as e:
            raise AdapterError(f"Request timeout: {url}") from e
        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError(f"REST request failed: {e}") from e

        # Extract nested data if response_path is set
        if response_path:
            data = self._extract_path(data, response_path)

        elapsed = (time.perf_counter() - start) * 1000

        return AdapterResult(
            data=data,
            source_type=self.source_type,
            source_path=url,
            query_ms=elapsed,
            row_count=len(data) if isinstance(data, (list, dict)) else None,
        )

    def _apply_auth(self, headers: dict, config: dict) -> None:
        """Apply authentication to headers."""
        auth_type = config.get("auth_type", "none")
        auth_config = config.get("auth_config", {})

        if auth_type == "bearer":
            token = auth_config.get("token")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key":
            key = auth_config.get("key")
            header_name = auth_config.get("header", "X-API-Key")
            if key:
                headers[header_name] = key
        elif auth_type == "basic":
            import base64
            username = auth_config.get("username", "")
            password = auth_config.get("password", "")
            creds = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"

    def _extract_path(self, data: Any, path: str) -> Any:
        """Extract nested data using dot notation."""
        for key in path.split("."):
            if isinstance(data, dict):
                data = data.get(key)
            elif isinstance(data, list) and key.isdigit():
                idx = int(key)
                data = data[idx] if 0 <= idx < len(data) else None
            else:
                return None
        return data

    async def list_children(
        self,
        moniker: Moniker,
        binding: SourceBinding,
        sub_path: str | None = None,
    ) -> list[str]:
        # REST APIs typically don't support listing
        # Could be implemented with a specific endpoint pattern
        children_endpoint = binding.config.get("children_endpoint")
        if not children_endpoint:
            return []

        # Fetch from children endpoint
        modified_config = dict(binding.config)
        modified_config["path_template"] = children_endpoint
        modified_binding = SourceBinding(
            source_type=binding.source_type,
            config=modified_config,
        )

        try:
            result = await self.fetch(moniker, modified_binding, sub_path)
            if isinstance(result.data, list):
                return [str(item) for item in result.data]
            return []
        except AdapterError:
            return []

    async def health_check(self, binding: SourceBinding) -> bool:
        """Check if the REST API is reachable."""
        try:
            import httpx
            base_url = binding.config.get("base_url")
            health_path = binding.config.get("health_path", "/health")
            timeout = binding.config.get("timeout", 5)

            url = urljoin(base_url, health_path)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                return response.status_code < 500
        except Exception:
            return False
