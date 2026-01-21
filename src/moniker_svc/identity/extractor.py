"""Identity extraction from requests."""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from starlette.requests import Request

from ..telemetry.events import CallerIdentity


logger = logging.getLogger(__name__)


@dataclass
class IdentityExtractor:
    """
    Extracts caller identity from HTTP requests.

    Supports multiple authentication methods:
    - JWT/OAuth2 tokens (Authorization: Bearer ...)
    - API keys (X-API-Key header)
    - mTLS client certificates
    - Basic auth (for service accounts)
    - Custom headers

    Configure extractors in order of preference.
    """
    # Header names
    jwt_header: str = "Authorization"
    api_key_header: str = "X-API-Key"
    app_id_header: str = "X-App-ID"
    team_header: str = "X-Team"

    # JWT claim mappings
    jwt_user_claim: str = "sub"
    jwt_service_claim: str = "client_id"
    jwt_team_claim: str = "team"

    # Custom extractor function (for complex scenarios)
    custom_extractor: Callable[[Request], CallerIdentity | None] | None = None

    def extract(self, request: Request) -> CallerIdentity:
        """
        Extract caller identity from request.

        Tries multiple methods in order:
        1. Custom extractor (if configured)
        2. JWT token
        3. mTLS certificate
        4. API key + app headers
        5. Basic auth
        6. Anonymous
        """
        # Custom extractor first
        if self.custom_extractor:
            identity = self.custom_extractor(request)
            if identity:
                return identity

        # Try JWT
        identity = self._extract_jwt(request)
        if identity:
            return identity

        # Try mTLS
        identity = self._extract_mtls(request)
        if identity:
            return identity

        # Try API key + headers
        identity = self._extract_api_key(request)
        if identity:
            return identity

        # Try basic auth
        identity = self._extract_basic(request)
        if identity:
            return identity

        # Anonymous with whatever headers we have
        return CallerIdentity(
            app_id=request.headers.get(self.app_id_header),
            team=request.headers.get(self.team_header),
        )

    def _extract_jwt(self, request: Request) -> CallerIdentity | None:
        """Extract identity from JWT Bearer token."""
        auth_header = request.headers.get(self.jwt_header, "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]

        try:
            # Decode JWT payload (without verification - that's done by middleware)
            # JWT format: header.payload.signature
            parts = token.split(".")
            if len(parts) != 3:
                return None

            # Decode payload (add padding if needed)
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding

            payload = json.loads(base64.urlsafe_b64decode(payload_b64))

            return CallerIdentity(
                user_id=payload.get(self.jwt_user_claim),
                service_id=payload.get(self.jwt_service_claim),
                team=payload.get(self.jwt_team_claim),
                app_id=request.headers.get(self.app_id_header),
                claims=payload,
            )

        except Exception as e:
            logger.debug(f"Failed to extract JWT identity: {e}")
            return None

    def _extract_mtls(self, request: Request) -> CallerIdentity | None:
        """Extract identity from mTLS client certificate."""
        # Client cert DN is typically passed by the proxy
        # Common headers: X-SSL-Client-DN, X-Client-Cert-DN
        cert_dn = (
            request.headers.get("X-SSL-Client-DN") or
            request.headers.get("X-Client-Cert-DN") or
            request.headers.get("X-Forwarded-Client-Cert")
        )

        if not cert_dn:
            return None

        # Parse DN to extract CN (common name)
        # Format: CN=service-name,OU=team,O=org
        cn = None
        ou = None
        for part in cert_dn.split(","):
            part = part.strip()
            if part.startswith("CN="):
                cn = part[3:]
            elif part.startswith("OU="):
                ou = part[3:]

        if cn:
            return CallerIdentity(
                service_id=cn,
                team=ou,
                app_id=request.headers.get(self.app_id_header),
            )

        return None

    def _extract_api_key(self, request: Request) -> CallerIdentity | None:
        """Extract identity from API key."""
        api_key = request.headers.get(self.api_key_header)
        if not api_key:
            return None

        # API key could encode service info, or we look up in a registry
        # For now, just use the key as the app_id
        return CallerIdentity(
            app_id=api_key[:20] + "..." if len(api_key) > 20 else api_key,
            team=request.headers.get(self.team_header),
        )

    def _extract_basic(self, request: Request) -> CallerIdentity | None:
        """Extract identity from Basic auth (service accounts)."""
        auth_header = request.headers.get(self.jwt_header, "")
        if not auth_header.startswith("Basic "):
            return None

        try:
            creds_b64 = auth_header[6:]
            creds = base64.b64decode(creds_b64).decode("utf-8")
            username, _ = creds.split(":", 1)

            return CallerIdentity(
                service_id=username,
                team=request.headers.get(self.team_header),
                app_id=request.headers.get(self.app_id_header),
            )

        except Exception as e:
            logger.debug(f"Failed to extract Basic auth identity: {e}")
            return None


# Default extractor instance
_default_extractor = IdentityExtractor()


def extract_identity(request: Request) -> CallerIdentity:
    """Extract identity using default extractor."""
    return _default_extractor.extract(request)
