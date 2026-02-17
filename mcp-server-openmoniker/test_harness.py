#!/usr/bin/env python3
"""
Test harness for the Open Moniker MCP server.

Exercises every tool and resource, reports pass/fail with timing.

Usage:
    python3 test_harness.py                      # default: http://localhost:8051/mcp
    python3 test_harness.py --url http://host:port/mcp
    MCP_SUBMIT_TOKEN=xxx MCP_APPROVE_TOKEN=yyy python3 test_harness.py --write
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time


async def run_tests(base_url: str, run_write: bool, submit_token: str, approve_token: str):
    from mcp import ClientSession
    from mcp.client.streamable_http import StreamableHTTPTransport

    transport = StreamableHTTPTransport(url=base_url)

    passed = 0
    failed = 0
    skipped = 0

    async def call_tool(name: str, args: dict | None = None):
        """Call a tool and return (result_text, elapsed_seconds)."""
        t0 = time.monotonic()
        result = await session.call_tool(name, arguments=args or {})
        elapsed = time.monotonic() - t0
        # Concatenate all text content
        text = "\n".join(c.text for c in result.content if hasattr(c, "text"))
        return text, elapsed

    def report(label: str, ok: bool, elapsed: float, detail: str = ""):
        nonlocal passed, failed
        status = "\033[32mPASS\033[0m" if ok else "\033[31mFAIL\033[0m"
        if ok:
            passed += 1
        else:
            failed += 1
        ms = f"{elapsed * 1000:.0f}ms"
        print(f"  {status}  {label:<35s} {ms:>7s}  {detail}")

    def skip(label: str, reason: str):
        nonlocal skipped
        skipped += 1
        print(f"  \033[33mSKIP\033[0m  {label:<35s}         {reason}")

    async with transport:
        async with ClientSession(transport.read_stream, transport.write_stream) as session:
            await session.initialize()

            # ----------------------------------------------------------
            # 1. List available tools
            # ----------------------------------------------------------
            print("\n=== Tools ===")
            t0 = time.monotonic()
            tools_result = await session.list_tools()
            elapsed = time.monotonic() - t0
            tool_names = sorted(t.name for t in tools_result.tools)
            report("list_tools", len(tool_names) > 0, elapsed,
                   f"{len(tool_names)} tools: {', '.join(tool_names)}")

            # ----------------------------------------------------------
            # 2. Read tools (anonymous)
            # ----------------------------------------------------------
            print("\n=== Read Tools ===")

            # get_catalog_stats
            text, elapsed = await call_tool("get_catalog_stats")
            data = json.loads(text)
            report("get_catalog_stats", "status_counts" in data, elapsed,
                   f"{sum(data.get('status_counts', {}).values())} nodes")

            # get_catalog_tree (top-level)
            text, elapsed = await call_tool("get_catalog_tree")
            data = json.loads(text)
            report("get_catalog_tree (root)", data.get("count", 0) > 0, elapsed,
                   f"{data.get('count', 0)} top-level entries")

            # get_catalog_tree (subtree)
            text, elapsed = await call_tool("get_catalog_tree", {"root_path": "risk"})
            data = json.loads(text)
            report("get_catalog_tree (risk)", data.get("count", 0) > 0, elapsed,
                   f"{data.get('count', 0)} children")

            # list_children
            text, elapsed = await call_tool("list_children", {"path": "risk"})
            data = json.loads(text)
            report("list_children (risk)", len(data.get("children", [])) > 0, elapsed,
                   f"{data.get('count', 0)} children")

            # describe_moniker
            text, elapsed = await call_tool("describe_moniker", {"path": "risk.cvar"})
            data = json.loads(text)
            report("describe_moniker (risk.cvar)",
                   data.get("has_source_binding", False), elapsed,
                   f"source={data.get('source_type', 'n/a')}")

            # resolve_moniker
            text, elapsed = await call_tool("resolve_moniker",
                                           {"moniker": "risk.cvar/758-A/USD/ALL"})
            data = json.loads(text)
            ok = "source_type" in data or "error" in data
            detail = data.get("source_type", data.get("error", "?"))
            report("resolve_moniker (risk.cvar/…)", ok, elapsed, detail)

            # search_catalog
            text, elapsed = await call_tool("search_catalog", {"query": "treasury"})
            data = json.loads(text)
            report("search_catalog (treasury)", data.get("count", 0) > 0, elapsed,
                   f"{data.get('count', 0)} results")

            # get_lineage
            text, elapsed = await call_tool("get_lineage", {"path": "risk.cvar"})
            data = json.loads(text)
            report("get_lineage (risk.cvar)", "error" not in data, elapsed)

            # get_domains
            text, elapsed = await call_tool("get_domains")
            data = json.loads(text)
            report("get_domains", data.get("count", 0) > 0, elapsed,
                   f"{data.get('count', 0)} domains")

            # get_models
            text, elapsed = await call_tool("get_models")
            data = json.loads(text)
            report("get_models", data.get("count", 0) > 0, elapsed,
                   f"{data.get('count', 0)} models")

            # get_model_detail
            text, elapsed = await call_tool("get_model_detail",
                                           {"model_path": "risk.analytics/dv01"})
            data = json.loads(text)
            report("get_model_detail (dv01)",
                   data.get("display_name") is not None or "error" in data, elapsed,
                   data.get("display_name", data.get("error", "?")))

            # ----------------------------------------------------------
            # 3. Resources
            # ----------------------------------------------------------
            print("\n=== Resources ===")
            t0 = time.monotonic()
            resources_result = await session.list_resources()
            elapsed = time.monotonic() - t0
            resource_uris = [str(r.uri) for r in resources_result.resources]
            report("list_resources", len(resource_uris) > 0, elapsed,
                   f"{len(resource_uris)} resources")

            for uri in resource_uris:
                t0 = time.monotonic()
                try:
                    res = await session.read_resource(uri)
                    elapsed = time.monotonic() - t0
                    text = "\n".join(
                        c.text for c in res.contents if hasattr(c, "text")
                    )
                    data = json.loads(text) if text else {}
                    report(f"read {uri}", "error" not in data, elapsed)
                except Exception as e:
                    elapsed = time.monotonic() - t0
                    report(f"read {uri}", False, elapsed, str(e)[:60])

            # ----------------------------------------------------------
            # 4. Prompts
            # ----------------------------------------------------------
            print("\n=== Prompts ===")
            t0 = time.monotonic()
            prompts_result = await session.list_prompts()
            elapsed = time.monotonic() - t0
            prompt_names = [p.name for p in prompts_result.prompts]
            report("list_prompts", len(prompt_names) > 0, elapsed,
                   ", ".join(prompt_names))

            # ----------------------------------------------------------
            # 5. Write tools (require tokens)
            # ----------------------------------------------------------
            print("\n=== Write Tools ===")
            if not run_write:
                skip("submit_request", "pass --write to test")
                skip("list_requests", "pass --write to test")
                skip("approve_request", "pass --write to test")
                skip("reject_request", "pass --write to test")
                skip("update_node_status", "pass --write to test")
            else:
                # submit_request
                text, elapsed = await call_tool("submit_request", {
                    "token": submit_token,
                    "path": "test.harness/smoke",
                    "display_name": "Smoke Test Moniker",
                    "description": "Created by test harness",
                    "justification": "Automated test",
                    "requester_name": "test-harness",
                })
                data = json.loads(text)
                ok = data.get("status") == "pending_review" or data.get("error") == "conflict"
                request_id = data.get("request_id", "")
                report("submit_request", ok, elapsed,
                       data.get("message", data.get("error", "?")))

                # list_requests
                text, elapsed = await call_tool("list_requests")
                data = json.loads(text)
                report("list_requests", data.get("count", 0) > 0, elapsed,
                       f"{data.get('count', 0)} requests")

                # approve_request (only if we got a request_id)
                if request_id:
                    text, elapsed = await call_tool("approve_request", {
                        "token": approve_token,
                        "request_id": request_id,
                    })
                    data = json.loads(text)
                    report("approve_request", data.get("status") == "approved", elapsed,
                           data.get("message", data.get("error", "?")))
                else:
                    skip("approve_request", "no request_id from submit")

                skip("reject_request", "would need a separate pending request")

                # update_node_status (flip to deprecated and back)
                text, elapsed = await call_tool("update_node_status", {
                    "token": approve_token,
                    "path": "test.harness/smoke",
                    "new_status": "deprecated",
                })
                data = json.loads(text)
                report("update_node_status", "error" not in data, elapsed,
                       data.get("message", data.get("error", "?")))

            # ----------------------------------------------------------
            # Summary
            # ----------------------------------------------------------
            total = passed + failed + skipped
            print(f"\n{'='*60}")
            color = "\033[32m" if failed == 0 else "\033[31m"
            print(f"  {color}{passed} passed, {failed} failed, {skipped} skipped"
                  f" ({total} total)\033[0m")
            print(f"{'='*60}\n")

            return failed


def main():
    parser = argparse.ArgumentParser(description="Test harness for MCP Open Moniker server")
    parser.add_argument("--url", default="http://localhost:8051/mcp",
                        help="MCP server URL (default: http://localhost:8051/mcp)")
    parser.add_argument("--write", action="store_true",
                        help="Also test write tools (needs MCP_SUBMIT_TOKEN / MCP_APPROVE_TOKEN)")
    args = parser.parse_args()

    submit_token = os.environ.get("MCP_SUBMIT_TOKEN", "")
    approve_token = os.environ.get("MCP_APPROVE_TOKEN", "")

    if args.write and (not submit_token or not approve_token):
        print("ERROR: --write requires MCP_SUBMIT_TOKEN and MCP_APPROVE_TOKEN env vars", file=sys.stderr)
        sys.exit(1)

    print(f"Testing MCP server at {args.url}")
    failures = asyncio.run(run_tests(args.url, args.write, submit_token, approve_token))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
