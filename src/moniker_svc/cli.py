#!/usr/bin/env python3
"""
CLI tool for interacting with the moniker service.

Usage:
    python -m moniker_svc.cli read market-data/prices/equity/AAPL
    python -m moniker_svc.cli list market-data/prices
    python -m moniker_svc.cli describe market-data/prices/equity
    python -m moniker_svc.cli lineage market-data/prices/equity
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init()
    COLOR_ENABLED = True
except ImportError:
    COLOR_ENABLED = False
    class Fore:
        CYAN = YELLOW = GREEN = MAGENTA = BLUE = RED = ""
    class Style:
        RESET_ALL = BRIGHT = DIM = ""


def colorize(text: str, color: str) -> str:
    """Apply color if available."""
    if COLOR_ENABLED:
        return f"{color}{text}{Style.RESET_ALL}"
    return text


def format_moniker(moniker_str: str) -> str:
    """Format a moniker with colors for display."""
    if moniker_str.startswith("moniker://"):
        scheme = "moniker://"
        path = moniker_str[10:]
    else:
        scheme = ""
        path = moniker_str

    parts = path.split("?", 1)
    path_part = parts[0]
    query_part = parts[1] if len(parts) > 1 else None

    segments = path_part.split("/")

    colors = [Fore.YELLOW, Fore.GREEN, Fore.MAGENTA, Fore.BLUE, Fore.CYAN]

    formatted_segments = []
    for i, seg in enumerate(segments):
        color = colors[i % len(colors)]
        formatted_segments.append(colorize(seg, color))

    result = colorize(scheme, Fore.CYAN) + "/".join(formatted_segments)

    if query_part:
        result += colorize(f"?{query_part}", Style.DIM)

    return result


def print_json(data: Any, indent: int = 2) -> None:
    """Print JSON with optional color."""
    output = json.dumps(data, indent=indent, default=str)
    print(output)


def print_ownership(ownership: dict, indent: str = "  ") -> None:
    """Pretty print ownership information."""
    print(f"\n{colorize('Ownership:', Style.BRIGHT)}")

    fields = [
        ("accountable_owner", "Accountable Owner"),
        ("data_specialist", "Data Specialist"),
        ("support_channel", "Support Channel"),
    ]

    for key, label in fields:
        value = ownership.get(key)
        source = ownership.get(f"{key}_source")

        if value:
            print(f"{indent}{colorize(label + ':', Fore.CYAN)} {value}")
            if source:
                print(f"{indent}  {colorize('(defined at:', Style.DIM)} {source}{colorize(')', Style.DIM)}")
        else:
            print(f"{indent}{colorize(label + ':', Fore.CYAN)} {colorize('(not set)', Style.DIM)}")


async def cmd_read(args):
    """Read data from a moniker."""
    import httpx

    url = f"{args.base_url}/moniker/{args.path}"
    params = {"op": "read"}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=_get_headers(args))

        if response.status_code != 200:
            print(colorize(f"Error: {response.status_code}", Fore.RED), file=sys.stderr)
            print(response.text, file=sys.stderr)
            return 1

        data = response.json()

    print(colorize("\nMoniker:", Style.BRIGHT), format_moniker(data.get("moniker", args.path)))
    print(colorize("Source:", Style.BRIGHT), data.get("source_type", "unknown"))
    print(colorize("Cached:", Style.BRIGHT), data.get("cached", False))
    print(colorize("Latency:", Style.BRIGHT), f"{data.get('latency_ms', 0):.2f}ms")

    if data.get("row_count") is not None:
        print(colorize("Rows:", Style.BRIGHT), data["row_count"])

    print(colorize("\nData:", Style.BRIGHT))
    print_json(data.get("data"))

    return 0


async def cmd_list(args):
    """List children of a moniker path."""
    import httpx

    url = f"{args.base_url}/moniker/{args.path}"
    params = {"op": "list"}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=_get_headers(args))

        if response.status_code != 200:
            print(colorize(f"Error: {response.status_code}", Fore.RED), file=sys.stderr)
            return 1

        data = response.json()

    print(colorize("\nPath:", Style.BRIGHT), format_moniker(data.get("path", args.path)))
    print(colorize("\nChildren:", Style.BRIGHT))

    for child in data.get("children", []):
        child_path = f"{args.path}/{child}" if args.path else child
        print(f"  {colorize('•', Fore.CYAN)} {format_moniker(child_path)}")

    if not data.get("children"):
        print(colorize("  (none)", Style.DIM))

    return 0


async def cmd_describe(args):
    """Get metadata about a moniker path."""
    import httpx

    url = f"{args.base_url}/moniker/{args.path}"
    params = {"op": "describe"}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=_get_headers(args))

        if response.status_code != 200:
            print(colorize(f"Error: {response.status_code}", Fore.RED), file=sys.stderr)
            return 1

        data = response.json()

    print(colorize("\nPath:", Style.BRIGHT), format_moniker(data.get("path", args.path)))

    if data.get("display_name"):
        print(colorize("Name:", Style.BRIGHT), data["display_name"])

    if data.get("description"):
        print(colorize("Description:", Style.BRIGHT), data["description"])

    if data.get("classification"):
        print(colorize("Classification:", Style.BRIGHT), data["classification"])

    if data.get("tags"):
        print(colorize("Tags:", Style.BRIGHT), ", ".join(data["tags"]))

    print_ownership(data.get("ownership", {}))

    if data.get("source_info"):
        print(colorize("\nSource Info:", Style.BRIGHT))
        print_json(data["source_info"])

    return 0


async def cmd_lineage(args):
    """Get full lineage information for a moniker."""
    import httpx

    url = f"{args.base_url}/moniker/{args.path}"
    params = {"op": "lineage"}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=_get_headers(args))

        if response.status_code != 200:
            print(colorize(f"Error: {response.status_code}", Fore.RED), file=sys.stderr)
            return 1

        data = response.json()

    print(colorize("\nMoniker:", Style.BRIGHT), format_moniker(data.get("moniker", args.path)))

    print(colorize("\nPath Hierarchy:", Style.BRIGHT))
    for i, p in enumerate(data.get("path_hierarchy", [])):
        indent = "  " * i
        marker = "└─" if i == len(data.get("path_hierarchy", [])) - 1 else "├─"
        print(f"  {indent}{colorize(marker, Style.DIM)} {format_moniker(p) if p else '(root)'}")

    print_ownership(data.get("ownership", {}))

    source = data.get("source", {})
    print(colorize("\nSource:", Style.BRIGHT))
    print(f"  Type: {source.get('type', 'unknown')}")
    print(f"  Binding at: {source.get('binding_defined_at', 'N/A')}")

    return 0


async def cmd_catalog(args):
    """List all catalog paths."""
    import httpx

    url = f"{args.base_url}/catalog"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=_get_headers(args))

        if response.status_code != 200:
            print(colorize(f"Error: {response.status_code}", Fore.RED), file=sys.stderr)
            return 1

        data = response.json()

    print(colorize("\nCatalog Paths:", Style.BRIGHT))
    for path in data.get("paths", []):
        print(f"  {format_moniker(path)}")

    return 0


def _get_headers(args) -> dict:
    """Build request headers."""
    headers = {}
    if args.app_id:
        headers["X-App-ID"] = args.app_id
    if args.team:
        headers["X-Team"] = args.team
    return headers


def main():
    parser = argparse.ArgumentParser(
        description="CLI tool for the Moniker Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the moniker service",
    )
    parser.add_argument(
        "--app-id",
        help="Application ID for telemetry",
    )
    parser.add_argument(
        "--team",
        help="Team name for telemetry",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # read command
    read_parser = subparsers.add_parser("read", help="Read data from a moniker")
    read_parser.add_argument("path", help="Moniker path (e.g., market-data/prices/equity)")

    # list command
    list_parser = subparsers.add_parser("list", help="List children of a path")
    list_parser.add_argument("path", nargs="?", default="", help="Moniker path")

    # describe command
    desc_parser = subparsers.add_parser("describe", help="Get metadata about a path")
    desc_parser.add_argument("path", help="Moniker path")

    # lineage command
    lineage_parser = subparsers.add_parser("lineage", help="Get ownership lineage")
    lineage_parser.add_argument("path", help="Moniker path")

    # catalog command
    subparsers.add_parser("catalog", help="List all catalog paths")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Run the appropriate command
    if args.command == "read":
        return asyncio.run(cmd_read(args))
    elif args.command == "list":
        return asyncio.run(cmd_list(args))
    elif args.command == "describe":
        return asyncio.run(cmd_describe(args))
    elif args.command == "lineage":
        return asyncio.run(cmd_lineage(args))
    elif args.command == "catalog":
        return asyncio.run(cmd_catalog(args))
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
