# Production Caching & Catalog Management

## How the resolver cache works

Every call to `GET /resolve/{path}` is served from an in-process LRU cache.
On a cache hit, resolution is a single dictionary lookup — no disk I/O, no
catalog traversal.

```
Client → GET /resolve/risk.cvar/desk-A
              │
              ▼
         InMemoryCache.get("resolve:risk.cvar/desk-A")
              │
         hit ─┘   miss ─→ CatalogRegistry.find_source_binding()
              │                  │
              └──────────────────┘
              ▼
         ResolveResult { source_type, connection, query }
```

The cache is **per-process** and **in-memory only** — it is not shared between
uvicorn workers or service instances.  Horizontal scaling (multi-AZ) means each
instance warms its own cache independently.

---

## TTL

| Setting | Default | Where |
|---|---|---|
| `cache.default_ttl_seconds` | **60 s** | `config.yaml` |
| `cache.max_size` | 10,000 entries | `config.yaml` |

60 seconds is the recommended day-1 value.  It means a catalog change is
visible to all resolvers within one minute without any manual intervention.
Raise it towards 300–600 s once the catalog is stable and you trust the
invalidation flow below.

Change it in `config.yaml`:

```yaml
cache:
  enabled: true
  max_size: 10000
  default_ttl_seconds: 60   # raise to 300 once stable
```

---

## Cache invalidation — when a moniker changes or a new one is added

The cache is **fully invalidated** on every catalog reload.  There is no
per-key invalidation; the entire store is cleared atomically, then re-warms
lazily as clients resolve.

### Triggering a reload

```bash
curl -X POST http://localhost:8050/config-ui/reload
```

Response:

```json
{
  "status": "ok",
  "moniker_count": 10247,
  "elapsed_ms": 42
}
```

The reload sequence is:

1. Read catalog file from disk (path from `catalog.definition_file` in config)
2. Parse and validate the new catalog
3. Swap the catalog registry atomically (single lock, no downtime)
4. Clear the resolution cache
5. Return 200

In-flight requests that hit between step 3 and 4 may briefly serve a stale
cached result for the changed path — this is bounded by the TTL even without a
reload.

### Adding a new moniker on the fly

Yes — no service restart required.

1. Add the entry to your catalog YAML:

   ```yaml
   risk.cvar/desk-new:
     display_name: "CVaR — New Desk"
     source_binding:
       type: oracle
       config:
         dsn: "oracle+cx_oracle://host:1521/PROD"
         query: "SELECT ..."
   ```

2. Call the reload endpoint:

   ```bash
   curl -X POST http://localhost:8050/config-ui/reload
   ```

3. The new path is immediately resolvable:

   ```bash
   curl http://localhost:8050/resolve/risk.cvar/desk-new
   ```

---

## When to reload

| Event | Action needed |
|---|---|
| New moniker added | `POST /config-ui/reload` |
| Existing moniker query updated | `POST /config-ui/reload` |
| Moniker removed / deprecated | `POST /config-ui/reload` |
| Connection credentials rotated | `POST /config-ui/reload` (if stored in catalog), otherwise restart |
| TTL expires naturally | Nothing — cache self-heals |

---

## Automatic periodic reload (not yet active)

`CatalogConfig.reload_interval_seconds` exists in `config.yaml` but the
background loop that would drive it is not yet wired up in `main.py`.
Until it is, all reloads are manual via the API endpoint above.

When implemented, the flow will be:

```
every reload_interval_seconds:
    stat(catalog file mtime)
    if changed:
        reload + cache.clear()
```

---

## Production deployment — day-1 checklist

| Priority | Item | How |
|---|---|---|
| **1** | 2–3 instances behind a load balancer (multi-AZ) | ECS / K8s / ALB |
| **2** | Low TTL (60 s) — already set in `config.yaml` | Done |
| **3** | Reload endpoint in your deployment pipeline | Add `curl POST /config-ui/reload` to your catalog-push CI step |
| **4** | Health check on `/health` | Already returns 200 when catalog is loaded |
| **5** | Cache size ≥ your catalog size | `max_size: 10000` covers most catalogs |

---

## Client-side caching (future — not day 1)

If your clients call `/resolve` on every data pull (e.g. before every SQL
execution), add a TTL-based dict cache inside your client SDK.  A warm
client cache turns `N_clients × N_paths / pull_interval` req/s into
`N_clients × N_paths / TTL` req/s — typically a 100–1000× reduction.

Example (Python):

```python
class MonikerClient:
    def __init__(self, base_url, ttl=300):
        self._base = base_url
        self._ttl = ttl
        self._cache: dict[str, tuple[dict, float]] = {}

    def resolve(self, path: str) -> dict:
        entry = self._cache.get(path)
        if entry and time.monotonic() < entry[1]:
            return entry[0]                          # zero network I/O
        result = httpx.get(f"{self._base}/resolve/{path}").json()
        self._cache[path] = (result, time.monotonic() + self._ttl)
        return result
```

This is **not needed on day 1** — server-side caching + multi-AZ handles the
load.  Add it when you observe the resolver appearing in latency profiles.
