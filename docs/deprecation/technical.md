# Deprecation & Decommissioning: Technical Implementation

## Architecture Overview

```
  +---------------------------+      +---------------------------+
  |    open-moniker-client    |      |     open-moniker-svc      |
  |                           |      |                           |
  |  config.py                |      |  config.py                |
  |    deprecation_enabled    |      |    DeprecationConfig      |
  |    warn_on_deprecated     |      |      enabled              |
  |    deprecation_callback   |      |      redirect_on_resolve  |
  |                           |      |      validated_reload     |
  |  client.py                |      |      block_breaking_reload|
  |    ResolvedSource         |      |      deprecation_telemetry|
  |      +status              |      |                           |
  |      +deprecation_message |      |  catalog/types.py         |
  |      +successor           |      |    CatalogNode            |
  |      +sunset_deadline     |      |      +successor           |
  |      +migration_guide_url |      |      +sunset_deadline     |
  |      +redirected_from     |      |      +migration_guide_url |
  |      +is_deprecated       |      |    SourceBinding          |
  |                           |      |      +fingerprint         |
  |    _resolve()             |      |                           |
  |      warn if deprecated   |      |  catalog/registry.py      |
  |      invoke callback      |      |    CatalogDiff            |
  |                           |      |    diff()                 |
  |    _report_telemetry()    |      |    validated_replace()    |
  |      +deprecated field    |      |    validate_successors()  |
  |      +successor field     |      |                           |
  +---------------------------+      |  service.py               |
                                     |    resolve()              |
                                     |      successor redirect   |
                                     |    reload_catalog()       |
                                     |      validated reload     |
                                     |    _emit_resolution_tel() |
                                     |      deprecation tags     |
                                     |                           |
                                     |  main.py                  |
                                     |    ResolveResponse        |
                                     |    GovernanceStatusRequest|
                                     |    X-Moniker-* headers    |
                                     |                           |
                                     |  telemetry/events.py      |
                                     |    UsageEvent             |
                                     |      +deprecated          |
                                     |      +successor           |
                                     |      +redirected_from     |
                                     +---------------------------+
```

## Server-Side Implementation

### 1. Configuration (`config.py`)

```python
@dataclass
class DeprecationConfig:
    enabled: bool = False               # master toggle
    redirect_on_resolve: bool = True    # follow successor on resolve
    validated_reload: bool = True       # diff + audit on reload
    block_breaking_reload: bool = False # reject reload if breaking changes
    deprecation_telemetry: bool = True  # tag telemetry events
```

Wired into the main `Config` dataclass:

```
Config
  +-- deprecation: DeprecationConfig  (default: all sub-toggles on, master off)
```

Loaded from `config.yaml` under the `deprecation:` key. When the master
toggle is off, all sub-toggles are irrelevant.

### 2. Moniker Fields (`catalog/types.py`)

Three fields added to `CatalogNode` after `deprecation_message`:

```
CatalogNode
  |-- path: str
  |-- status: NodeStatus           (existing)
  |-- deprecation_message: str     (existing)
  |-- successor: str | None        NEW - path to replacement moniker
  |-- sunset_deadline: str | None  NEW - ISO date for decommission
  |-- migration_guide_url: str     NEW - link to migration docs
  |-- source_binding: SourceBinding
  |-- ...
```

### 3. Binding Fingerprint (`catalog/types.py`)

Property on `SourceBinding` that hashes the binding contract:

```
SourceBinding.fingerprint -> str (16 hex chars)

  Input:  json.dumps({
            source_type, config, allowed_operations,
            schema, read_only
          }, sort_keys=True)

  Output: sha256(input)[:16]    e.g. "a3f8c12e9b4d70e1"
```

Key-order independent (uses `sort_keys=True`). Detects any change to the
query, config, schema, or permissions of a binding.

### 4. Catalog Loader (`catalog/loader.py`)

`_parse_node()` updated to extract from YAML:

```
YAML data dict
  |-- "status"               -> NodeStatus enum (default: ACTIVE)
  |-- "deprecation_message"  -> str
  |-- "successor"            -> str
  |-- "sunset_deadline"      -> str
  |-- "migration_guide_url"  -> str
```

Unknown status values log a warning and default to ACTIVE.

### 5. Registry Diff & Validation (`catalog/registry.py`)

#### CatalogDiff

```python
@dataclass
class CatalogDiff:
    added_paths: list[str]
    removed_paths: list[str]
    binding_changed_paths: list[str]    # detected via fingerprint
    status_changed_paths: list[str]

    has_breaking_changes -> bool        # removed or binding changed
    summary() -> str                    # "2 added, 1 removed, ..."
```

#### Methods on CatalogRegistry

```
diff(new_nodes) -> CatalogDiff
  Compares current catalog state against a list of new nodes.
  Uses SourceBinding.fingerprint to detect binding changes.

validated_replace(new_nodes, block_breaking, audit_actor) -> (CatalogDiff, bool)
  1. Calls diff()
  2. Audit-logs each change (node_removed, binding_changed, node_added)
  3. If block_breaking=True and has_breaking_changes: returns (diff, False)
  4. Otherwise: calls atomic_replace(), returns (diff, True)

validate_successors() -> list[str]
  Iterates all nodes with a successor pointer.
  Returns error strings for:
    - Successor path does not exist in catalog
    - Self-referencing successor
```

### 6. Resolution Redirect (`service.py`)

```
resolve(moniker, caller)
  |
  +-- parse moniker, find node, find source binding (existing)
  |
  +-- IF deprecation.enabled AND redirect_on_resolve:
  |     |
  |     +-- original_node = catalog.get(path)
  |     |
  |     +-- IF node.status == DEPRECATED AND node.successor:
  |     |     |
  |     |     +-- follow successor chain:
  |     |     |     current = node
  |     |     |     for depth in range(MAX_SUCCESSOR_DEPTH):  # 5
  |     |     |       next = catalog.get(current.successor)
  |     |     |       if next is None or next.status != DEPRECATED:
  |     |     |         break
  |     |     |       if next.successor is None:
  |     |     |         break
  |     |     |       current = next
  |     |     |
  |     |     +-- IF successor_node found AND has binding:
  |     |           use successor's binding
  |     |           set result.redirected_from = original path
  |     |
  |     +-- ELSE: use original binding (no redirect)
  |
  +-- build ResolveResult with source, ownership, node, redirected_from
```

Guard: `MAX_SUCCESSOR_DEPTH = 5` prevents infinite loops from circular
successor chains.

### 7. Validated Reload (`service.py`)

```
reload_catalog(new_catalog, block_breaking, audit_actor)
  |
  +-- IF deprecation.enabled AND validated_reload:
  |     |
  |     +-- validated_replace(new_nodes, block_breaking, audit_actor)
  |     |     -> CatalogDiff + applied bool
  |     |
  |     +-- IF applied: validate_successors()
  |     |
  |     +-- return {
  |           moniker_count, applied, diff summary,
  |           added/removed/changed counts,
  |           has_breaking_changes, successor_errors
  |         }
  |
  +-- ELSE (toggle off):
        |
        +-- atomic_replace(new_nodes)    (original behaviour)
        +-- return { moniker_count, applied: true }
```

### 8. Telemetry Enrichment (`service.py`, `telemetry/events.py`)

```
_emit_resolution_telemetry(result, ...)
  |
  +-- IF deprecation.enabled AND deprecation_telemetry:
  |     deprecated = node.status == DEPRECATED
  |     successor = node.successor
  |     redirected_from = result.redirected_from
  |
  +-- ELSE:
  |     deprecated = False
  |     successor = None
  |     redirected_from = None
  |
  +-- UsageEvent.create(..., deprecated, successor, redirected_from)
```

`UsageEvent.to_dict()` always includes the three fields (defaulting to
`False`/`None`/`None` when the toggle is off).

### 9. API Layer (`main.py`)

#### Response model

```
ResolveResponse (Pydantic BaseModel)
  +-- moniker, path, source_type, query, ...  (existing)
  +-- status: str | None                       NEW
  +-- deprecation_message: str | None          NEW
  +-- successor: str | None                    NEW
  +-- sunset_deadline: str | None              NEW
  +-- migration_guide_url: str | None          NEW
  +-- redirected_from: str | None              NEW
```

#### Response headers (added in `resolve_moniker` handler)

```
IF node.status == DEPRECATED:
  X-Moniker-Deprecated: {deprecation_message}

IF successor:
  X-Moniker-Successor: {successor}

IF redirected_from:
  X-Moniker-Redirected-From: {redirected_from}
```

#### Governance endpoint

```
PUT /catalog/{path}/status

GovernanceStatusRequest (Pydantic BaseModel)
  +-- status: str
  +-- actor: str | None
  +-- reason: str | None
  +-- deprecation_message: str | None          NEW
  +-- successor: str | None                    NEW
  +-- sunset_deadline: str | None              NEW
  +-- migration_guide_url: str | None          NEW
```

Handler sets the fields on the node when status is DEPRECATED:

```
IF status == DEPRECATED and deprecation_message:
    node.deprecation_message = body.deprecation_message
IF body.successor is not None:
    node.successor = body.successor
IF body.sunset_deadline is not None:
    node.sunset_deadline = body.sunset_deadline
IF body.migration_guide_url is not None:
    node.migration_guide_url = body.migration_guide_url
```

---

## Client-Side Implementation

### 1. Configuration (`config.py`)

```
ClientConfig
  +-- deprecation_enabled: bool     env: MONIKER_DEPRECATION_ENABLED (default: false)
  +-- warn_on_deprecated: bool      env: MONIKER_WARN_DEPRECATED (default: true)
  +-- deprecation_callback: Any     callable(path, message, successor) or None
```

### 2. ResolvedSource (`client.py`)

```
ResolvedSource
  +-- source_type, connection, query, ...  (existing)
  +-- status: str | None                    NEW
  +-- deprecation_message: str | None       NEW
  +-- successor: str | None                 NEW
  +-- sunset_deadline: str | None           NEW
  +-- migration_guide_url: str | None       NEW
  +-- redirected_from: str | None           NEW
  +-- is_deprecated: bool (property)        NEW  -> status == "deprecated"
```

### 3. Warning Logic (`client.py` — `_resolve()` and `batch_resolve()`)

```
after constructing ResolvedSource:
  |
  +-- IF config.deprecation_enabled AND source.is_deprecated:
        |
        +-- IF config.warn_on_deprecated:
        |     warnings.warn(DeprecationWarning, stacklevel=2)
        |     logging.getLogger("moniker_client").warning(...)
        |
        +-- IF config.deprecation_callback:
              config.deprecation_callback(path, message, successor)
```

### 4. Telemetry (`client.py` — `_report_telemetry()`)

```
telemetry payload:
  {
    ...,
    "deprecated": source.is_deprecated,    NEW
    "successor": source.successor           NEW
  }
```

---

## File Change Summary

### Server (`open-moniker-svc/src/moniker_svc/`)

| File | What Changed |
|---|---|
| `config.py` | `DeprecationConfig` dataclass, wired into `Config` and `from_dict()` |
| `catalog/types.py` | `successor`, `sunset_deadline`, `migration_guide_url` on `CatalogNode`; `fingerprint` property on `SourceBinding` |
| `catalog/loader.py` | Parse `status`, `successor`, `sunset_deadline`, `migration_guide_url` from YAML |
| `catalog/registry.py` | `CatalogDiff` dataclass, `diff()`, `validated_replace()`, `validate_successors()` |
| `service.py` | Gated redirect in `resolve()`, gated validated reload in `reload_catalog()`, gated telemetry enrichment |
| `main.py` | Fields on `ResolveResponse` and `GovernanceStatusRequest`, `X-Moniker-*` response headers |
| `telemetry/events.py` | `deprecated`, `successor`, `redirected_from` on `UsageEvent` and `to_dict()` |

### Client (`open-moniker-client/moniker_client/`)

| File | What Changed |
|---|---|
| `config.py` | `deprecation_enabled`, `warn_on_deprecated`, `deprecation_callback` |
| `client.py` | Deprecation fields on `ResolvedSource`, `is_deprecated` property, gated warnings/logging/callback, telemetry passthrough |

---

## Test Coverage

47 tests total in `test_governance.py`. The 25 deprecation-specific tests:

| Test | What It Verifies |
|---|---|
| `test_catalog_node_successor_field` | CatalogNode stores successor/sunset/migration |
| `test_catalog_loader_successor_from_yaml` | Loader parses new fields from YAML |
| `test_catalog_loader_backward_compat` | YAML without new fields defaults to None |
| `test_validate_successors_valid` | All successor pointers resolve |
| `test_validate_successors_missing_target` | Missing successor target detected |
| `test_validate_successors_self_reference` | Circular reference detected |
| `test_resolve_deprecated_with_successor_redirects` | Binding comes from successor |
| `test_resolve_deprecated_without_successor_no_redirect` | No successor = no redirect |
| `test_resolve_active_with_successor_no_redirect` | Active node not redirected |
| `test_resolve_redirect_chain` | Multi-hop chain followed correctly |
| `test_resolve_redirect_metadata` | redirected_from populated |
| `test_client_resolved_source_deprecation_fields` | is_deprecated property works |
| `test_client_deprecation_warning_logged` | DeprecationWarning emitted |
| `test_client_deprecation_callback_invoked` | Callback called with correct args |
| `test_client_no_warning_when_disabled` | warn_on_deprecated=False suppresses |
| `test_telemetry_event_deprecation_fields` | UsageEvent includes deprecation fields |
| `test_source_binding_fingerprint_stable` | Same config = same fingerprint |
| `test_source_binding_fingerprint_detects_query_change` | Changed SQL = different fingerprint |
| `test_source_binding_fingerprint_key_order_independent` | Key reorder = same fingerprint |
| `test_catalog_diff_detects_added_removed_changed` | Full diff scenario |
| `test_validated_replace_blocks_breaking` | block_breaking=True prevents removal |
| `test_validated_replace_audits_binding_changes` | Audit log has binding_changed entries |
| `test_toggle_off_no_redirect` | Toggle off = no redirect, original binding |
| `test_toggle_off_plain_reload` | Toggle off = plain atomic_replace, no diff |
| `test_toggle_off_telemetry_no_deprecation_fields` | Toggle off = no enrichment |

### Running Tests

```bash
cd ~/open-moniker-client-tests
PYTHONPATH=~/open-moniker-svc/src:~/open-moniker-client python3 -m pytest test_governance.py -v
```

---

## Not Yet Implemented

The following endpoints return moniker information but do **not** yet
include deprecation fields. They will work correctly — they just won't
surface successor/sunset metadata in their responses:

| Endpoint | Response Model | Gap |
|---|---|---|
| `GET /describe/{path}` | `DescribeResponse` | No deprecation fields |
| `GET /catalog/search` | `CatalogSearchResponse` | Status only, no successor/sunset |
| `GET /list/{path}` | `ListResponse` | No deprecation fields |
| `GET /tree` | `TreeNodeResponse` | No status or deprecation fields |
| `GET /lineage/{path}` | `LineageResponse` | No deprecation fields |

The config UI (`config_ui/static/index.html`) does not yet have form
fields for editing successor, sunset_deadline, or migration_guide_url.
