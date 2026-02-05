"""Moniker parsing utilities."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from .types import Moniker, MonikerPath, QueryParams, VersionType


class MonikerParseError(ValueError):
    """Raised when a moniker string cannot be parsed."""
    pass


# Valid segment pattern: alphanumeric, hyphens, underscores, dots
# Must start with alphanumeric
SEGMENT_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]*$")

# Namespace pattern: alphanumeric, hyphens, underscores (no dots - those are for paths)
NAMESPACE_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_\-]*$")

# Version pattern: digits (date) or alphanumeric (like "latest")
VERSION_PATTERN = re.compile(r"^[a-zA-Z0-9]+$")

# Revision pattern: /vN or /VN where N is a positive integer (case-insensitive)
REVISION_PATTERN = re.compile(r"^[vV](\d+)$")

# Version classification patterns
DATE_VERSION_PATTERN = re.compile(r"^\d{8}$")              # 20260101 (YYYYMMDD)
TENOR_VERSION_PATTERN = re.compile(r"^\d+[YMWD]$", re.I)   # 3M, 12Y, 1W, 5D
KEYWORD_VERSION_PATTERN = re.compile(r"^(latest|all)$", re.I)


def classify_version(version: str | None) -> VersionType | None:
    """Determine the semantic type of a version string.

    Args:
        version: The version string to classify (e.g., "20260101", "latest", "3M")

    Returns:
        VersionType enum value, or None if version is None/empty
    """
    if not version:
        return None
    if DATE_VERSION_PATTERN.match(version):
        return VersionType.DATE
    if TENOR_VERSION_PATTERN.match(version):
        return VersionType.TENOR
    if KEYWORD_VERSION_PATTERN.match(version):
        return VersionType.LATEST if version.lower() == "latest" else VersionType.ALL
    return VersionType.CUSTOM


def validate_segment(segment: str) -> bool:
    """Check if a path segment is valid."""
    if not segment:
        return False
    if len(segment) > 128:
        return False
    return bool(SEGMENT_PATTERN.match(segment))


def validate_namespace(namespace: str) -> bool:
    """Check if a namespace is valid."""
    if not namespace:
        return False
    if len(namespace) > 64:
        return False
    return bool(NAMESPACE_PATTERN.match(namespace))


def parse_path(path_str: str, *, validate: bool = True) -> MonikerPath:
    """
    Parse a path string into a MonikerPath.

    Args:
        path_str: Path string like "indices.sovereign/developed/EUR"
        validate: Whether to validate segment names

    Returns:
        MonikerPath instance

    Raises:
        MonikerParseError: If path is invalid
    """
    if not path_str or path_str == "/":
        return MonikerPath.root()

    # Strip leading/trailing slashes
    clean = path_str.strip("/")
    if not clean:
        return MonikerPath.root()

    segments = clean.split("/")

    if validate:
        for seg in segments:
            if not validate_segment(seg):
                raise MonikerParseError(
                    f"Invalid path segment: '{seg}'. "
                    "Segments must start with alphanumeric and contain only "
                    "alphanumerics, hyphens, underscores, or dots."
                )

    return MonikerPath(tuple(segments))


def parse_moniker(moniker_str: str, *, validate: bool = True) -> Moniker:
    """
    Parse a full moniker string.

    Format: [namespace@]path/segments[@version][/sub.resource][/vN][?query=params]

    Examples:
        indices.sovereign/developed/EUR/ALL
        commodities.derivatives/crypto/ETH@20260115/v2
        verified@reference.security/ISIN/US0378331005@latest
        user@analytics.risk/views/my-watchlist@20260115/v3
        securities/012345678@20260101/details
        securities/012345678@20260101/details.corporate.actions
        prices.equity/AAPL@3M (3-month lookback)
        risk.cvar/portfolio-123@all (full time series)
        moniker://holdings/20260115/fund_alpha?format=json

    Args:
        moniker_str: The moniker string to parse
        validate: Whether to validate segment names

    Returns:
        Moniker instance

    Raises:
        MonikerParseError: If moniker is invalid
    """
    if not moniker_str:
        raise MonikerParseError("Empty moniker string")

    moniker_str = moniker_str.strip()

    # Handle scheme
    if moniker_str.startswith("moniker://"):
        # Parse as URL
        parsed = urlparse(moniker_str)
        body = parsed.netloc + parsed.path
        query_str = parsed.query
    elif "://" in moniker_str:
        raise MonikerParseError(
            f"Invalid scheme. Expected 'moniker://' or no scheme, got: {moniker_str}"
        )
    else:
        # No scheme - check for query string
        if "?" in moniker_str:
            body, query_str = moniker_str.split("?", 1)
        else:
            body = moniker_str
            query_str = ""

    # Parse namespace (prefix before first @, but only if @ appears before first /)
    namespace = None
    remaining = body

    # Check for namespace@ prefix
    # The @ must appear before any / to be a namespace (otherwise it's a version)
    first_at = body.find("@")
    first_slash = body.find("/")

    if first_at != -1 and (first_slash == -1 or first_at < first_slash):
        # This @ is a namespace prefix
        namespace = body[:first_at]
        remaining = body[first_at + 1:]

        if validate and not validate_namespace(namespace):
            raise MonikerParseError(
                f"Invalid namespace: '{namespace}'. "
                "Namespace must start with a letter and contain only "
                "alphanumerics, hyphens, or underscores."
            )

    # Parse revision suffix (/vN or /VN at the end - case-insensitive)
    revision = None
    # Check for both /v and /V patterns
    remaining_lower = remaining.lower()
    if "/v" in remaining_lower:
        # Find the last /v or /V pattern
        # Use case-insensitive search by finding the rightmost occurrence
        lower_idx = remaining_lower.rfind("/v")
        if lower_idx != -1:
            before = remaining[:lower_idx]
            after = remaining[lower_idx + 2:]  # Skip the "/v" or "/V"
            # Check if it's a valid revision (just digits at the end or before ?)
            rev_match = re.match(r"^(\d+)(?:$|(?=\?))", after)
            if rev_match:
                revision = int(rev_match.group(1))
                remaining = before

    # Parse version suffix with optional sub-resource: @version[/sub.resource]
    # Examples:
    #   securities/012345678@20260101 -> version=20260101, sub_resource=None
    #   securities/012345678@20260101/details -> version=20260101, sub_resource=details
    #   securities/012345678@20260101/details.corporate.actions -> sub_resource=details.corporate.actions
    version = None
    sub_resource = None
    if "@" in remaining:
        # Find the @ that's a version (not a namespace prefix)
        # Namespace @ appears before any /
        first_slash_in_remaining = remaining.find("/")
        at_idx = remaining.rfind("@")

        # Check if this @ is after the first slash (making it a version, not namespace)
        # If no slash in remaining, check if we already parsed namespace
        is_version_at = (first_slash_in_remaining != -1 and at_idx > first_slash_in_remaining) or \
                        (first_slash_in_remaining == -1 and namespace is not None) or \
                        (first_slash_in_remaining == -1 and at_idx == remaining.find("@"))

        # Actually, simpler: if namespace was already parsed, any @ is a version
        # If namespace wasn't parsed, @ is version only if it's after a /
        if namespace is not None:
            # Namespace already extracted, any @ is a version
            is_version_at = at_idx != -1
        else:
            # No namespace yet - @ is version only if after first /
            is_version_at = at_idx != -1 and (first_slash_in_remaining == -1 or at_idx > first_slash_in_remaining)

        if is_version_at and at_idx != -1:
            # Everything before @ is the path
            path_part = remaining[:at_idx]
            after_at = remaining[at_idx + 1:]

            # Check if there's a sub-resource (path after version)
            # Pattern: @version/sub.resource or just @version
            if "/" in after_at:
                version, sub_resource = after_at.split("/", 1)
            else:
                version = after_at

            remaining = path_part

            if validate and version and not VERSION_PATTERN.match(version):
                raise MonikerParseError(
                    f"Invalid version: '{version}'. "
                    "Version must be alphanumeric (e.g., 'latest', '20260115', '3M')."
                )

            # Validate sub_resource segments if present
            if validate and sub_resource:
                # Sub-resource uses dots for multi-level: details.corporate.actions
                # Each dot-separated part should be a valid segment
                for part in sub_resource.split("."):
                    if not validate_segment(part):
                        raise MonikerParseError(
                            f"Invalid sub-resource segment: '{part}'. "
                            "Sub-resource parts must start with alphanumeric."
                        )

    # Parse path
    path = parse_path(remaining, validate=validate)

    # Parse query params
    params: dict[str, str] = {}
    if query_str:
        parsed_qs = parse_qs(query_str, keep_blank_values=True)
        # Take first value for each param (no multi-value support)
        for key, values in parsed_qs.items():
            if values:
                params[key] = values[0]

    return Moniker(
        path=path,
        namespace=namespace,
        version=version,
        version_type=classify_version(version),
        sub_resource=sub_resource,
        revision=revision,
        params=QueryParams(params),
    )


def normalize_moniker(moniker_str: str) -> str:
    """
    Normalize a moniker string to canonical form.

    Always returns: moniker://[namespace@]path[@version][/vN][?sorted_params]
    """
    m = parse_moniker(moniker_str)
    return str(m)


def build_moniker(
    path: str,
    *,
    namespace: str | None = None,
    version: str | None = None,
    version_type: VersionType | None = None,
    sub_resource: str | None = None,
    revision: int | None = None,
    **params: str,
) -> Moniker:
    """
    Build a Moniker from components.

    Args:
        path: The path string
        namespace: Optional namespace prefix
        version: Optional version (date, 'latest', tenor like '3M', or 'all')
        version_type: Optional explicit version type (auto-classified if not provided)
        sub_resource: Optional sub-resource path (e.g., 'details.corporate.actions')
        revision: Optional revision number
        **params: Query parameters

    Returns:
        Moniker instance
    """
    # Auto-classify version if not explicitly provided
    effective_version_type = version_type if version_type is not None else classify_version(version)

    return Moniker(
        path=parse_path(path),
        namespace=namespace,
        version=version,
        version_type=effective_version_type,
        sub_resource=sub_resource,
        revision=revision,
        params=QueryParams(params) if params else QueryParams({}),
    )
