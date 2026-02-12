# Moniker Deprecation & Decommissioning

Feature toggle: **`deprecation.enabled`** (default: `false`)

This feature adds safe moniker decommissioning, successor-based migration,
binding change detection, and validated catalog reloads to the moniker
resolution service.

## Enabling

### Server (`config.yaml`)

```yaml
deprecation:
  enabled: true
  redirect_on_resolve: true    # follow successor chain on deprecated monikers
  validated_reload: true       # diff + audit on catalog hot-reload
  block_breaking_reload: false # block reload if nodes removed or bindings changed
  deprecation_telemetry: true  # tag telemetry events with deprecation info
```

### Client (environment or constructor)

```bash
export MONIKER_DEPRECATION_ENABLED=true   # master toggle
export MONIKER_WARN_DEPRECATED=true       # emit DeprecationWarning + logging
```

```python
from moniker_client.config import ClientConfig

config = ClientConfig(
    deprecation_enabled=True,
    warn_on_deprecated=True,
    deprecation_callback=lambda path, msg, successor: alert(path),
)
```

When the toggle is **off** (default), every code path falls back to the
original behaviour: no redirects, plain `atomic_replace` on reload, no
deprecation tags in telemetry, no client-side warnings.

---

## What It Does

### 1. Successor Pointers (catalog YAML)

Declare a successor when deprecating a moniker:

```yaml
rates.libor/usd:
  status: deprecated
  deprecation_message: "LIBOR discontinued. Use SOFR."
  successor: rates.sofr/usd
  sunset_deadline: "2026-06-30"
  migration_guide_url: https://wiki.firm.com/libor-migration
```

Fields on `CatalogNode`:
| Field | Type | Purpose |
|---|---|---|
| `successor` | `str \| None` | Path to replacement moniker |
| `sunset_deadline` | `str \| None` | ISO date after which the moniker will be archived |
| `migration_guide_url` | `str \| None` | URL to migration documentation |

The registry validates successor pointers on reload:

```python
errors = registry.validate_successors()
# ["rates.libor/usd: successor 'rates.sofr/usd' does not exist"]
```

### 2. Transparent Resolution Redirect

When resolving a **deprecated** moniker that has a successor, the service
follows the successor chain and returns the **successor's binding** instead.

- Chains up to 5 hops deep (guards against circular references)
- Original metadata (path, ownership) still refers to the **requested** moniker
- `redirected_from` tells the caller what happened

```
GET /resolve/rates.libor/usd

{
  "path": "rates.libor/usd",
  "source_type": "snowflake",
  "query": "SELECT * FROM SOFR_RATES",   <-- successor's query
  "redirected_from": "rates.libor/usd",
  "successor": "rates.sofr/usd",
  "sunset_deadline": "2026-06-30"
}
```

Response headers:
- `X-Moniker-Deprecated: LIBOR discontinued. Use SOFR.`
- `X-Moniker-Successor: rates.sofr/usd`
- `X-Moniker-Redirected-From: rates.libor/usd`

Active monikers with pre-staged successors are **not** redirected.

### 3. Client Deprecation Awareness

When `deprecation_enabled=True`, the client library:

1. **`warnings.warn(DeprecationWarning)`** - deduplicates automatically, test
   suites can assert with `pytest.warns`, consumers can escalate to errors
   via `filterwarnings`
2. **`logging.getLogger("moniker_client").warning()`** - shows up in log
   aggregation (Splunk/ELK)
3. **Optional callback** - `deprecation_callback(path, message, successor)`

No exceptions are raised by default - enterprise pipelines must not break
because a moniker was deprecated.

`ResolvedSource` gains:
- `status`, `deprecation_message`, `successor`, `sunset_deadline`,
  `migration_guide_url`, `redirected_from`
- `is_deprecated` property

### 4. Deprecation Telemetry

`UsageEvent` gains `deprecated`, `successor`, `redirected_from` fields so
you can query "who is still calling deprecated moniker X?" from your
telemetry backend.

The client also reports `deprecated` and `successor` in its telemetry
payload back to the service.

### 5. Binding Contract Fingerprint

`SourceBinding.fingerprint` is a 16-char hex SHA-256 of the serialised
binding contract (`source_type`, `config`, `allowed_operations`, `schema`,
`read_only`). It is key-order independent and detects any query or config
change.

```python
binding.fingerprint  # "a3f8c12e9b4d70e1"
```

Used internally by the validated reload diff to detect binding changes.

### 6. Validated Catalog Reload

When `validated_reload` is enabled, `reload_catalog()` diffs old vs new
before swapping:

| Category | Example | Breaking? |
|---|---|---|
| `added_paths` | New moniker registered | No |
| `removed_paths` | Existing moniker deleted | **Yes** |
| `binding_changed_paths` | SQL query changed | **Yes** |
| `status_changed_paths` | active -> deprecated | No |

Every change is audit-logged (`node_removed`, `binding_changed`,
`node_added`). If `block_breaking_reload=True` and there are breaking
changes, the reload is **rejected** and the old catalog stays in place.

```python
result = service.reload_catalog(new_catalog)
# {
#   "moniker_count": 150,
#   "applied": true,
#   "diff": "2 added, 1 removed, 3 binding changed",
#   "has_breaking_changes": true,
#   "successor_errors": []
# }
```

---

## Governance API Changes

### `PUT /catalog/{path}/status`

New optional fields in request body:

```json
{
  "status": "deprecated",
  "actor": "governance-team@firm.com",
  "deprecation_message": "Use SOFR rates instead",
  "successor": "rates.sofr/usd",
  "sunset_deadline": "2026-06-30",
  "migration_guide_url": "https://wiki.firm.com/libor"
}
```

---

## Files Changed

### Server (`open-moniker-svc`)
| File | Changes |
|---|---|
| `config.py` | `DeprecationConfig` dataclass + wired into `Config` |
| `catalog/types.py` | `successor`, `sunset_deadline`, `migration_guide_url` on `CatalogNode`; `fingerprint` property on `SourceBinding` |
| `catalog/loader.py` | Parse new fields + `status` from YAML |
| `catalog/registry.py` | `CatalogDiff`, `diff()`, `validated_replace()`, `validate_successors()` |
| `service.py` | Redirect logic in `resolve()`; gated `reload_catalog()`; telemetry enrichment |
| `main.py` | New fields on `ResolveResponse`, `GovernanceStatusRequest`; response headers |
| `telemetry/events.py` | `deprecated`, `successor`, `redirected_from` on `UsageEvent` |

### Client (`open-moniker-client`)
| File | Changes |
|---|---|
| `config.py` | `deprecation_enabled`, `warn_on_deprecated`, `deprecation_callback` |
| `client.py` | Deprecation fields on `ResolvedSource` + `is_deprecated`; gated warnings; telemetry passthrough |

---

## Testing

```bash
cd ~/open-moniker-client-tests
PYTHONPATH=~/open-moniker-svc/src:~/open-moniker-client python3 -m pytest test_governance.py -v
```

22 new test cases cover all 6 phases. Tests for the feature toggle verify
that when `deprecation.enabled=False`, the service behaves identically to
the original codebase.
