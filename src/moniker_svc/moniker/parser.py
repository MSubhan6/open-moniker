"""Moniker parsing utilities."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from .types import Moniker, MonikerPath, QueryParams


class MonikerParseError(ValueError):
    """Raised when a moniker string cannot be parsed."""
    pass


# Valid segment pattern: alphanumeric, hyphens, underscores, dots
# Must start with alphanumeric
SEGMENT_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]*$")


def validate_segment(segment: str) -> bool:
    """Check if a path segment is valid."""
    if not segment:
        return False
    if len(segment) > 128:
        return False
    return bool(SEGMENT_PATTERN.match(segment))


def parse_path(path_str: str, *, validate: bool = True) -> MonikerPath:
    """
    Parse a path string into a MonikerPath.

    Args:
        path_str: Path string like "market-data/prices/equity/AAPL"
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

    Accepts formats:
        moniker://market-data/prices/equity/AAPL
        moniker://market-data/prices/equity/AAPL?version=latest
        market-data/prices/equity/AAPL  (scheme optional)
        /market-data/prices/equity/AAPL (leading slash ok)

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
        path_str = parsed.netloc + parsed.path
        query_str = parsed.query
    elif "://" in moniker_str:
        raise MonikerParseError(
            f"Invalid scheme. Expected 'moniker://' or no scheme, got: {moniker_str}"
        )
    else:
        # No scheme - check for query string
        if "?" in moniker_str:
            path_str, query_str = moniker_str.split("?", 1)
        else:
            path_str = moniker_str
            query_str = ""

    # Parse path
    path = parse_path(path_str, validate=validate)

    # Parse query params
    params: dict[str, str] = {}
    if query_str:
        parsed_qs = parse_qs(query_str, keep_blank_values=True)
        # Take first value for each param (no multi-value support)
        for key, values in parsed_qs.items():
            if values:
                params[key] = values[0]

    return Moniker(path=path, params=QueryParams(params))


def normalize_moniker(moniker_str: str) -> str:
    """
    Normalize a moniker string to canonical form.

    Always returns: moniker://{path}[?{sorted_params}]
    """
    m = parse_moniker(moniker_str)
    return str(m)
