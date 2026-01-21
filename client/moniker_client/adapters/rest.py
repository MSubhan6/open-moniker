"""REST API adapter - direct HTTP calls."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING
from urllib.parse import urljoin

if TYPE_CHECKING:
    from ..client import ResolvedSource
    from ..config import ClientConfig

from .base import BaseAdapter


class RestAdapter(BaseAdapter):
    """
    Adapter for REST API sources.

    Makes HTTP calls directly to the configured endpoint.
    """

    def fetch(
        self,
        resolved: ResolvedSource,
        config: ClientConfig,
        **kwargs,
    ) -> Any:
        import httpx

        conn_info = resolved.connection
        params = resolved.params

        base_url = conn_info.get("base_url")
        if not base_url:
            raise ValueError("base_url required for REST source")

        # Build URL
        url_path = resolved.query or ""
        url = urljoin(base_url, url_path)

        # Method
        method = params.get("method", "GET").upper()

        # Headers
        headers = dict(conn_info.get("headers", {}))

        # Apply auth
        auth_type = conn_info.get("auth_type", "none")
        self._apply_auth(headers, auth_type, config, resolved)

        # Query params from moniker
        query_params = params.get("moniker_params", {})

        # Make request
        with httpx.Client(timeout=config.timeout) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                params=query_params,
            )

            if response.status_code == 404:
                from ..client import NotFoundError
                raise NotFoundError(f"Resource not found: {url}")

            response.raise_for_status()
            data = response.json()

        # Extract nested data if response_path is set
        response_path = params.get("response_path")
        if response_path:
            data = self._extract_path(data, response_path)

        return data

    def _apply_auth(
        self,
        headers: dict,
        auth_type: str,
        config: ClientConfig,
        resolved: ResolvedSource,
    ) -> None:
        """Apply authentication to headers."""
        if auth_type == "bearer":
            # Get token from config
            token = config.credentials.get("rest_bearer_token")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "api_key":
            key = config.credentials.get("rest_api_key")
            header_name = resolved.connection.get("api_key_header", "X-API-Key")
            if key:
                headers[header_name] = key
        elif auth_type == "basic":
            import base64
            username = config.credentials.get("rest_username", "")
            password = config.credentials.get("rest_password", "")
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
