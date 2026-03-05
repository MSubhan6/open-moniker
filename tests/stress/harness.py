"""
Moniker Resolver — Stress Test Harness
=======================================

Standalone script (no pytest dependency). Run from the repo root:

    cd /home/user/open-moniker-svc
    python tests/stress/harness.py [--workers 64] [--duration 60] [--port 8050]

Lifecycle
---------
1. Stash existing root YAMLs → *.stress_bak
2. Generate stress_catalog.yaml (10 K paths, 5 source types)
3. Write minimal config.yaml + domains.yaml
4. Start uvicorn; poll /health until ready
5. Run asyncio load workers for --duration seconds
6. Print live req/s + latency every second
7. Print final summary
8. Always restore original files (finally block)
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import importlib.util
import os
import random
import socket
import subprocess
import sys
import time
import textwrap
from pathlib import Path

import httpx
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# This file lives at tests/stress/harness.py — repo root is two levels up.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STRESS_DIR = Path(__file__).resolve().parent


def _load_gen_catalog():
    """Import gen_catalog from the same directory as this script."""
    spec = importlib.util.spec_from_file_location("gen_catalog", STRESS_DIR / "gen_catalog.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Files managed by the harness
# ---------------------------------------------------------------------------
STASH_TARGETS = [
    ("config.yaml",  "config.yaml.stress_bak"),
    ("domains.yaml", "domains.yaml.stress_bak"),
]
OPTIONAL_STASH = [
    ("requests.yaml", "requests.yaml.stress_bak"),
]
GENERATED_FILES = [
    "stress_catalog.yaml",
    "config.yaml",
    "domains.yaml",
]


# ---------------------------------------------------------------------------
# YAML content written during setup
# ---------------------------------------------------------------------------
STRESS_CONFIG_YAML = """\
catalog:
  definition_file: "./stress_catalog.yaml"
telemetry:
  enabled: false
cache:
  enabled: true
  max_size: 20000
  default_ttl_seconds: 3600
requests:
  enabled: false
models:
  enabled: false
auth:
  enabled: false
  enforce: false
governance:
  rate_limiter_enabled: false
"""

STRESS_DOMAINS_YAML = """\
stress_static:
  id: 901
  display_name: Stress Static
  short_code: STS
  data_category: Test
  color: '#888888'
  owner: stress-test@firm.com
  tech_custodian: stress-tech@firm.com
  business_steward: stress-biz@firm.com
  confidentiality: internal
  pii: false
  help_channel: '#stress-test'
  notes: Stress test domain — static source type

stress_snowflake:
  id: 902
  display_name: Stress Snowflake
  short_code: STF
  data_category: Test
  color: '#888888'
  owner: stress-test@firm.com
  tech_custodian: stress-tech@firm.com
  business_steward: stress-biz@firm.com
  confidentiality: internal
  pii: false
  help_channel: '#stress-test'
  notes: Stress test domain — snowflake source type

stress_oracle:
  id: 903
  display_name: Stress Oracle
  short_code: STO
  data_category: Test
  color: '#888888'
  owner: stress-test@firm.com
  tech_custodian: stress-tech@firm.com
  business_steward: stress-biz@firm.com
  confidentiality: internal
  pii: false
  help_channel: '#stress-test'
  notes: Stress test domain — oracle source type

stress_mssql:
  id: 904
  display_name: Stress MSSQL
  short_code: STM
  data_category: Test
  color: '#888888'
  owner: stress-test@firm.com
  tech_custodian: stress-tech@firm.com
  business_steward: stress-biz@firm.com
  confidentiality: internal
  pii: false
  help_channel: '#stress-test'
  notes: Stress test domain — mssql source type

stress_rest:
  id: 905
  display_name: Stress REST
  short_code: STR
  data_category: Test
  color: '#888888'
  owner: stress-test@firm.com
  tech_custodian: stress-tech@firm.com
  business_steward: stress-biz@firm.com
  confidentiality: internal
  pii: false
  help_channel: '#stress-test'
  notes: Stress test domain — rest source type

stress_excel:
  id: 906
  display_name: Stress Excel
  short_code: STE
  data_category: Test
  color: '#888888'
  owner: stress-test@firm.com
  tech_custodian: stress-tech@firm.com
  business_steward: stress-biz@firm.com
  confidentiality: internal
  pii: false
  help_channel: '#stress-test'
  notes: Stress test domain — excel source type

stress_opensearch:
  id: 907
  display_name: Stress OpenSearch
  short_code: STOS
  data_category: Test
  color: '#888888'
  owner: stress-test@firm.com
  tech_custodian: stress-tech@firm.com
  business_steward: stress-biz@firm.com
  confidentiality: internal
  pii: false
  help_channel: '#stress-test'
  notes: Stress test domain — opensearch source type
"""


# ---------------------------------------------------------------------------
# Results bucket  (asyncio-safe: single event loop, no locking needed)
# ---------------------------------------------------------------------------
class ResultsBucket:
    def __init__(self) -> None:
        self.ok: int = 0
        self.errors: dict[str, int] = {}
        self.latencies: list[float] = []   # ms for every completed request
        # Rolling window: deque of (monotonic_ts, cumulative_total_requests)
        self._window: collections.deque = collections.deque(maxlen=120)

    # -- recording -----------------------------------------------------------

    def record_ok(self, latency_ms: float) -> None:
        self.ok += 1
        self.latencies.append(latency_ms)

    def record_error(self, error_key: str, latency_ms: float | None = None) -> None:
        self.errors[error_key] = self.errors.get(error_key, 0) + 1
        if latency_ms is not None and latency_ms >= 0:
            self.latencies.append(latency_ms)

    def record_status(self, status_code: int, latency_ms: float) -> None:
        """Record an HTTP response with a non-2xx status code."""
        self.errors[f"status_{status_code}"] = (
            self.errors.get(f"status_{status_code}", 0) + 1
        )
        self.latencies.append(latency_ms)

    # -- aggregates ----------------------------------------------------------

    @property
    def total(self) -> int:
        return self.ok + sum(self.errors.values())

    @property
    def error_count(self) -> int:
        return sum(self.errors.values())

    # -- rolling-window helpers ----------------------------------------------

    def checkpoint(self) -> None:
        self._window.append((time.monotonic(), self.total))

    def _pairwise_rps(self, pts: list) -> list[float]:
        return [
            (pts[i][1] - pts[i - 1][1]) / max(pts[i][0] - pts[i - 1][0], 1e-9)
            for i in range(1, len(pts))
        ]

    def rps_last_second(self) -> float:
        if len(self._window) < 2:
            return 0.0
        t1, n1 = self._window[-1]
        t0, n0 = self._window[-2]
        dt = t1 - t0
        return (n1 - n0) / dt if dt > 0 else 0.0

    def peak_rps(self) -> float:
        pts = list(self._window)
        if len(pts) < 2:
            return 0.0
        return max(self._pairwise_rps(pts), default=0.0)

    def sustained_rps(self, last_n_seconds: int = 10) -> float:
        pts = list(self._window)
        if len(pts) < 2:
            return 0.0
        cutoff = time.monotonic() - last_n_seconds
        recent = [p for p in pts if p[0] >= cutoff]
        if len(recent) < 2:
            recent = pts[-min(last_n_seconds, len(pts)):]
        if len(recent) < 2:
            return 0.0
        t0, n0 = recent[0]
        t1, n1 = recent[-1]
        dt = t1 - t0
        return (n1 - n0) / dt if dt > 0 else 0.0


# ---------------------------------------------------------------------------
# Percentile helper (exact, sorts raw list)
# ---------------------------------------------------------------------------
def percentile(sorted_data: list[float], p: float) -> float:
    if not sorted_data:
        return 0.0
    idx = (len(sorted_data) - 1) * p / 100.0
    lo = int(idx)
    frac = idx - lo
    if lo + 1 >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[lo] * (1.0 - frac) + sorted_data[lo + 1] * frac


# ---------------------------------------------------------------------------
# Async worker
# ---------------------------------------------------------------------------
async def worker(
    client: httpx.AsyncClient,
    paths: list[str],
    end_time: float,
    bucket: ResultsBucket,
) -> None:
    while time.monotonic() < end_time:
        path = random.choice(paths)
        t0 = time.perf_counter()
        try:
            r = await client.get(f"/resolve/{path}")
            latency_ms = (time.perf_counter() - t0) * 1000
            if 200 <= r.status_code < 300:
                bucket.record_ok(latency_ms)
            else:
                bucket.record_status(r.status_code, latency_ms)
        except httpx.TimeoutException:
            bucket.record_error("timeout")
        except Exception:
            bucket.record_error("exception")


# ---------------------------------------------------------------------------
# Live stats printer coroutine
# ---------------------------------------------------------------------------
async def stats_printer(bucket: ResultsBucket, end_time: float, start_time: float) -> None:
    while time.monotonic() < end_time:
        await asyncio.sleep(1.0)
        now = time.monotonic()
        bucket.checkpoint()

        elapsed = now - start_time
        total = bucket.total
        rps = bucket.rps_last_second()
        success_pct = (bucket.ok / total * 100) if total > 0 else 100.0

        lats = sorted(bucket.latencies)
        p50 = percentile(lats, 50)
        p95 = percentile(lats, 95)

        print(
            f"[t={elapsed:4.0f}s]  req/s: {rps:>8,.0f}  "
            f"success: {success_pct:6.2f}%  "
            f"p50: {p50:.1f}ms  p95: {p95:.1f}ms",
            flush=True,
        )


# ---------------------------------------------------------------------------
# Main async runner
# ---------------------------------------------------------------------------
async def run_load(
    n_workers: int,
    duration: int,
    paths: list[str],
    base_url: str,
) -> ResultsBucket:
    bucket = ResultsBucket()
    start_time = time.monotonic()
    end_time = start_time + duration

    limits = httpx.Limits(
        max_connections=n_workers + 16,
        max_keepalive_connections=n_workers,
        keepalive_expiry=30,
    )
    async with httpx.AsyncClient(base_url=base_url, timeout=5.0, limits=limits) as client:
        load_tasks = [
            asyncio.create_task(worker(client, paths, end_time, bucket))
            for _ in range(n_workers)
        ]
        printer_task = asyncio.create_task(
            stats_printer(bucket, end_time, start_time)
        )
        await asyncio.gather(*load_tasks)
        printer_task.cancel()
        try:
            await printer_task
        except asyncio.CancelledError:
            pass

    return bucket


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------
def print_summary(
    bucket: ResultsBucket,
    duration: int,
    n_paths: int,
    n_workers: int,
) -> None:
    total = bucket.total
    ok = bucket.ok
    err = bucket.error_count
    ok_pct = (ok / total * 100) if total > 0 else 100.0
    err_pct = (err / total * 100) if total > 0 else 0.0
    mean_rps = total / duration if duration > 0 else 0.0
    peak = bucket.peak_rps()
    sustained = bucket.sustained_rps(10)

    lats = sorted(bucket.latencies)
    p50 = percentile(lats, 50)
    p75 = percentile(lats, 75)
    p95 = percentile(lats, 95)
    p99 = percentile(lats, 99)
    p999 = percentile(lats, 99.9)
    p_max = lats[-1] if lats else 0.0

    rule = "─" * 50
    print()
    print("=" * 52)
    print("  Moniker Resolver — Stress Test Results")
    print("=" * 52)
    print(f"  Duration:      {duration:.1f} s       Workers:  {n_workers}")
    print(f"  Catalog paths: {n_paths:,} unique")
    print()
    print("  Throughput")
    print(f"  {rule}")
    print(f"  Total requests:   {total:>13,}")
    print(f"  Successful:       {ok:>13,}   ({ok_pct:.4f}%)")
    print(f"  Failed:           {err:>13,}   ({err_pct:.4f}%)")
    print(f"  Mean req/s:       {mean_rps:>13,.0f}")
    print(f"  Peak 1s req/s:    {peak:>13,.0f}")
    print(f"  Sustained req/s:  {sustained:>13,.0f}   (last 10 s)")
    print()
    print("  Latency (ms)")
    print(f"  {rule}")
    print(f"  p50:  {p50:6.1f}    p75:  {p75:6.1f}    p95:  {p95:6.1f}")
    print(f"  p99:  {p99:6.1f}    p99.9:{p999:6.1f}   max:  {p_max:6.1f}")
    if err > 0:
        print()
        print(f"  Errors ({err})")
        print(f"  {rule}")
        for key, count in sorted(bucket.errors.items(), key=lambda x: -x[1]):
            print(f"  {key + ':':16s} {count:,}")
    print("=" * 52)


# ---------------------------------------------------------------------------
# File management
# ---------------------------------------------------------------------------
def stash_files(
    required: list[tuple[str, str]],
    optional: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """
    Rename source files → *.stress_bak.
    Returns list of (bak_name, orig_name) pairs that were actually stashed.
    """
    stashed: list[tuple[str, str]] = []
    for orig_name, bak_name in required + optional:
        orig = REPO_ROOT / orig_name
        bak = REPO_ROOT / bak_name
        if orig.exists():
            os.rename(orig, bak)
            stashed.append((bak_name, orig_name))
            print(f"  Stashed:  {orig_name} → {bak_name}")
    return stashed


def restore_files(stashed: list[tuple[str, str]]) -> None:
    for bak_name, orig_name in stashed:
        bak = REPO_ROOT / bak_name
        orig = REPO_ROOT / orig_name
        if bak.exists():
            os.rename(bak, orig)
            print(f"  Restored: {bak_name} → {orig_name}")


def delete_generated() -> None:
    for name in GENERATED_FILES:
        p = REPO_ROOT / name
        if p.exists():
            p.unlink()
            print(f"  Deleted:  {name}")


# ---------------------------------------------------------------------------
# Port check
# ---------------------------------------------------------------------------
def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False


# ---------------------------------------------------------------------------
# Health poll
# ---------------------------------------------------------------------------
def wait_for_health(url: str, timeout: float = 30.0, interval: float = 0.5) -> None:
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code == 200:
                print(f"  Service ready ({url})")
                return
        except Exception as exc:
            last_exc = exc
        time.sleep(interval)
    raise TimeoutError(
        f"Service did not become healthy within {timeout:.0f}s. "
        f"Last error: {last_exc}"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Moniker Resolver stress test harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              python tests/stress/harness.py --workers 64 --duration 30
              python tests/stress/harness.py --no-start --port 8050
        """),
    )
    parser.add_argument("--workers",  metavar="N", type=int, default=64,
                        help="concurrent async workers (default: 64)")
    parser.add_argument("--duration", metavar="T", type=int, default=60,
                        help="test duration in seconds (default: 60)")
    parser.add_argument("--port",     metavar="P", type=int, default=8050,
                        help="service port (default: 8050)")
    parser.add_argument("--paths",    metavar="N", type=int, default=10_000,
                        help="catalog paths to generate (default: 10000)")
    parser.add_argument("--uvicorn-workers", metavar="N", type=int, default=1,
                        help="uvicorn server worker processes (default: 1)")
    parser.add_argument("--no-start", action="store_true",
                        help="skip server start/stop; connect to already-running service")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    args = parse_args()
    base_url = f"http://127.0.0.1:{args.port}"
    manage_server = not args.no_start
    proc: subprocess.Popen | None = None
    stashed: list[tuple[str, str]] = []

    # ── pre-flight checks ───────────────────────────────────────────────────
    if manage_server and port_in_use(args.port):
        print(
            f"ERROR: Port {args.port} is already in use. "
            "Stop the existing service or use --no-start.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not manage_server and not port_in_use(args.port):
        print(
            f"ERROR: --no-start specified but nothing is listening on port {args.port}.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load gen_catalog module (same directory as this script)
    gen_catalog = _load_gen_catalog()

    try:
        if manage_server:
            # ── 1. Stash existing YAMLs ─────────────────────────────────────
            print("\n── Setup ──────────────────────────────────────────────────")
            stashed = stash_files(STASH_TARGETS, OPTIONAL_STASH)

            # ── 2. Generate stress catalog ──────────────────────────────────
            print(
                f"  Generating {args.paths:,}-path stress catalog …",
                end=" ", flush=True,
            )
            catalog_file = str(REPO_ROOT / "stress_catalog.yaml")
            paths = gen_catalog.write_stress_catalog(catalog_file, n=args.paths)
            print(f"done ({len(paths):,} resolvable paths)")

            # ── 3. Write stress config.yaml ─────────────────────────────────
            (REPO_ROOT / "config.yaml").write_text(STRESS_CONFIG_YAML, encoding="utf-8")
            print("  Wrote config.yaml (stress mode)")

            # ── 4. Write stress domains.yaml ────────────────────────────────
            (REPO_ROOT / "domains.yaml").write_text(STRESS_DOMAINS_YAML, encoding="utf-8")
            print("  Wrote domains.yaml (stress mode)")

            # ── 5. Start uvicorn ────────────────────────────────────────────
            env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
            proc = subprocess.Popen(
                [
                    sys.executable, "-m", "uvicorn",
                    "moniker_svc.main:app",
                    "--host", "0.0.0.0",
                    "--port", str(args.port),
                    "--workers", str(args.uvicorn_workers),
                    "--log-level", "warning",
                ],
                cwd=str(REPO_ROOT),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"  Started uvicorn (pid={proc.pid}) on port {args.port}")

            # ── 6. Poll /health ─────────────────────────────────────────────
            health_timeout = 15.0 + 15.0 * args.uvicorn_workers
            print("  Waiting for service to be ready …", end=" ", flush=True)
            wait_for_health(f"{base_url}/health", timeout=health_timeout, interval=0.5)

        else:
            # --no-start: build path list from the generator (no files written)
            print("\n── --no-start: connecting to existing service ──────────────")
            catalog = gen_catalog.gen_stress_catalog(n=args.paths)
            paths = [k for k, v in catalog.items() if "source_binding" in v]
            print(f"  Using {len(paths):,} generated paths against existing service")

        # ── 7. Run stress test ──────────────────────────────────────────────
        print(
            f"\n── Load: {args.workers} workers × {args.duration}s "
            f"→ {base_url} ────────────────────"
        )
        bucket = asyncio.run(run_load(args.workers, args.duration, paths, base_url))

        # ── 8. Print summary ────────────────────────────────────────────────
        print_summary(bucket, args.duration, len(paths), args.workers)

    finally:
        if manage_server:
            print("\n── Teardown ────────────────────────────────────────────────")
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                print(f"  Stopped uvicorn (pid={proc.pid})")
            delete_generated()
            restore_files(stashed)
            print("  Teardown complete.")


if __name__ == "__main__":
    main()
