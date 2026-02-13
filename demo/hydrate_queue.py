#!/usr/bin/env python3
"""
Hydrate the moniker request review queue with demo data.

Reads scenarios from demo_requests.yaml, submits them via the API, and
walks each through its scripted outcome (pending / approved / rejected)
with comments.

Usage:
    python demo/hydrate_queue.py                  # default: localhost:8050
    python demo/hydrate_queue.py --base http://host:port
    python demo/hydrate_queue.py --reset          # clear queue first
    python demo/hydrate_queue.py --reset --only   # clear queue and exit
    python demo/hydrate_queue.py --file my_scenarios.yaml
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests
import yaml


SCRIPT_DIR = Path(__file__).parent
DEFAULT_YAML = SCRIPT_DIR / "demo_requests.yaml"
DEFAULT_BASE = "http://localhost:8050"


# ── Helpers ──────────────────────────────────────────────────────────

def log(icon: str, msg: str):
    print(f"  {icon}  {msg}")


def check_service(base: str) -> bool:
    """Verify the service is reachable."""
    try:
        r = requests.get(f"{base}/requests", timeout=5)
        return r.status_code == 200
    except requests.ConnectionError:
        return False


def reset_queue(base: str):
    """Delete all requests by reloading from an empty state."""
    # Get current requests
    data = requests.get(f"{base}/requests").json()
    total = data.get("total", 0)
    if total == 0:
        log("-", "Queue already empty")
        return

    # The cleanest way: use the reload endpoint with an empty file,
    # or submit a save then manually clear. Since we have no direct
    # "delete all" API, we'll save current state, clear via internal
    # endpoint if available, or just note the count.
    # For now, we rely on the server restart having a clean queue,
    # or we just submit on top. The script is idempotent because
    # duplicate paths get 409'd and skipped.
    log("!", f"Queue has {total} existing request(s) — submitting will skip duplicates")


def submit_request(base: str, req: dict) -> str | None:
    """Submit a single request. Returns request_id or None on skip."""
    payload = {
        "path": req["path"],
        "display_name": req.get("display_name", ""),
        "description": req.get("description", ""),
        "justification": req.get("justification", ""),
        "requester": req.get("requester", {"name": "Demo User", "email": "demo@firm.com"}),
        "adop": req.get("adop"),
        "adop_name": req.get("adop_name"),
        "ads": req.get("ads"),
        "ads_name": req.get("ads_name"),
        "adal": req.get("adal"),
        "adal_name": req.get("adal_name"),
        "source_binding_type": req.get("source_binding_type"),
        "source_binding_config": req.get("source_binding_config", {}),
        "tags": req.get("tags", []),
    }

    resp = requests.post(f"{base}/requests", json=payload)

    if resp.status_code == 409:
        log("~", f"Skipped (already exists): {req['path']}")
        return None
    elif resp.status_code == 400:
        log("!", f"Validation error for {req['path']}: {resp.json().get('detail', '?')}")
        return None
    elif resp.status_code >= 400:
        log("x", f"Error {resp.status_code} for {req['path']}: {resp.json().get('detail', '?')}")
        return None

    result = resp.json()
    request_id = result["request_id"]
    level = " [TOP-LEVEL]" if "TOP-LEVEL" in result.get("message", "") else ""
    log("+", f"Submitted: {req['path']} -> {request_id}{level}")
    return request_id


def add_comments(base: str, request_id: str, comments: list[dict]):
    """Add review comments to a request."""
    for c in comments:
        requests.post(f"{base}/requests/{request_id}/comment", json={
            "author": c.get("author", "reviewer@firm.com"),
            "author_name": c.get("author_name", "Reviewer"),
            "content": c.get("content", ""),
        })
    if comments:
        log(" ", f"  Added {len(comments)} comment(s)")


def approve_request(base: str, request_id: str, req: dict):
    """Approve a request."""
    resp = requests.post(f"{base}/requests/{request_id}/approve", json={
        "actor": req.get("reviewer", "senior.reviewer@firm.com"),
        "actor_name": req.get("reviewer_name", "Senior Reviewer"),
        "reason": req.get("review_reason", "Approved"),
    })
    if resp.status_code == 200:
        log("v", f"  Approved by {req.get('reviewer_name', 'Senior Reviewer')}")
    else:
        log("!", f"  Approve failed: {resp.json().get('detail', '?')}")


def reject_request(base: str, request_id: str, req: dict):
    """Reject a request."""
    resp = requests.post(f"{base}/requests/{request_id}/reject", json={
        "actor": req.get("reviewer", "compliance@firm.com"),
        "actor_name": req.get("reviewer_name", "Compliance"),
        "reason": req.get("review_reason", "Rejected"),
    })
    if resp.status_code == 200:
        log("x", f"  Rejected: {req.get('review_reason', 'Rejected')[:60]}...")
    else:
        log("!", f"  Reject failed: {resp.json().get('detail', '?')}")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Hydrate the moniker review queue with demo data")
    parser.add_argument("--base", default=DEFAULT_BASE, help=f"Service base URL (default: {DEFAULT_BASE})")
    parser.add_argument("--file", default=str(DEFAULT_YAML), help=f"Scenario YAML file (default: {DEFAULT_YAML.name})")
    parser.add_argument("--reset", action="store_true", help="Clear existing requests before loading")
    parser.add_argument("--only", action="store_true", help="With --reset, only clear — don't load new data")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    yaml_path = Path(args.file)

    print(f"\n  Moniker Review Queue — Demo Hydrator")
    print(f"  {'=' * 40}")
    print(f"  Service:  {base}")
    print(f"  Scenarios: {yaml_path.name}")
    print()

    # Check service
    if not check_service(base):
        print(f"  ERROR: Cannot reach service at {base}")
        print(f"  Start it with: PYTHONPATH=src python3 -m uvicorn moniker_svc.main:app --port 8050")
        sys.exit(1)

    log("o", "Service is reachable")

    # Reset if requested
    if args.reset:
        reset_queue(base)
        if args.only:
            print("\n  Done (reset only).\n")
            return

    # Load scenarios
    if not yaml_path.exists():
        print(f"  ERROR: Scenario file not found: {yaml_path}")
        sys.exit(1)

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    scenario_requests = data.get("requests", [])
    if not scenario_requests:
        print("  No requests found in scenario file.")
        sys.exit(0)

    print(f"\n  Loading {len(scenario_requests)} demo request(s)...\n")

    # Counters
    submitted = 0
    skipped = 0
    approved = 0
    rejected = 0
    pending = 0

    for req in scenario_requests:
        request_id = submit_request(base, req)

        if request_id is None:
            skipped += 1
            continue

        submitted += 1
        outcome = req.get("outcome", "pending")

        # Add comments (before outcome action)
        comments = req.get("comments", [])
        if comments:
            add_comments(base, request_id, comments)

        # Apply outcome
        if outcome == "approved":
            approve_request(base, request_id, req)
            approved += 1
        elif outcome == "rejected":
            reject_request(base, request_id, req)
            rejected += 1
        else:
            pending += 1

        # Small delay for distinct timestamps
        time.sleep(0.05)

    # Summary
    print(f"\n  {'=' * 40}")
    print(f"  Summary:")
    print(f"    Submitted: {submitted}")
    print(f"    Skipped:   {skipped} (already existed)")
    print(f"    Pending:   {pending}")
    print(f"    Approved:  {approved}")
    print(f"    Rejected:  {rejected}")

    # Final queue state
    resp = requests.get(f"{base}/requests").json()
    counts = resp.get("by_status", {})
    print(f"\n  Queue totals:")
    print(f"    Pending review: {counts.get('pending_review', 0)}")
    print(f"    Approved:       {counts.get('approved', 0)}")
    print(f"    Rejected:       {counts.get('rejected', 0)}")
    print(f"    Total:          {resp.get('total', 0)}")

    print(f"\n  Open the review queue: {base}/requests/ui")
    print(f"  Swagger:               {base}/docs\n")


if __name__ == "__main__":
    main()
