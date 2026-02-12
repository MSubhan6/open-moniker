# Deprecation & Decommissioning: Business Flow

## The Problem

Monikers are semantic names that resolve to data source bindings (SQL queries,
REST endpoints, file paths). In production, hundreds of consumers depend on
these bindings. Three problems make change management dangerous:

1. **Silent breakage** — changing the SQL behind a moniker breaks every
   consumer with no warning, no audit trail, and no rollback.
2. **No decommissioning path** — a moniker can be marked "deprecated" in
   status, but nothing actually migrates consumers to the replacement.
3. **Unsafe hot-reload** — reloading the catalog swaps everything atomically
   with zero validation. Accidentally removing a node or changing a query
   goes undetected.

## Moniker Lifecycle

```
                          governance decision
                                 |
                                 v
  +----------+    +----------+    +------------+    +-----------+
  |  DRAFT   |--->|  ACTIVE  |--->| DEPRECATED |--->|  ARCHIVED |
  +----------+    +----------+    +------------+    +-----------+
       |               |               |                  |
       |               |               |                  |
   not yet in      consumers       consumers          moniker
    production      resolve        warned &           removed
                    normally       redirected         from catalog
```

### Stage Transitions

| From | To | Trigger | What Happens |
|---|---|---|---|
| Draft | Active | First publish | Moniker becomes resolvable |
| Active | Deprecated | Governance decision | Successor assigned, consumers warned |
| Deprecated | Archived | After sunset deadline | Moniker removed from catalog |

## The Deprecation Workflow

When a data source is being retired (e.g. LIBOR -> SOFR), the governance
team follows this workflow:

```
  Governance Team                    Moniker Service                  Consumers
  ===============                    ===============                  =========

  1. Identify replacement
     moniker (successor)
          |
          v
  2. PUT /catalog/{path}/status
     {                          ---->  3. Mark node DEPRECATED
       status: deprecated              Set successor pointer
       successor: new/path             Set sunset deadline
       sunset_deadline: 2026-06       Validate successor exists
     }                                        |
                                              v
                                       4. On next resolve:
                                          Follow successor chain
                                          Return successor's binding
                                          Add deprecation headers   ----> 5. Consumer gets data
                                                                          from NEW source
                                                                          (transparently)
                                                                              |
                                                                              v
                                                                    6. Client emits:
                                                                       - DeprecationWarning
                                                                       - Log warning
                                                                       - Optional callback
                                                                              |
                                                                              v
                                                                    7. Consumer team sees
                                                                       warnings in logs,
                                                                       updates their code
                                                                       to use new moniker
                                              |
                                              v
                                       8. Telemetry tracks:
                                          "app X still resolving
                                           deprecated moniker Y"
          |
          v
  9. Monitor telemetry until
     all consumers migrated
          |
          v
  10. After sunset deadline:
      Archive / remove moniker
```

## Resolution With Redirect

When a consumer resolves a deprecated moniker that has a successor, the
service transparently follows the chain:

```
  Consumer                          Service                         Catalog
  ========                          =======                         =======

  resolve("rates.libor/usd")
          |
          +-----------------------> lookup "rates.libor/usd"
                                          |
                                          v
                                    node.status == DEPRECATED?
                                    node.successor == "rates.sofr/usd"?
                                          |
                                     YES (both)
                                          |
                                          v
                                    follow successor chain --------> lookup "rates.sofr/usd"
                                    (max 5 hops)                          |
                                          |                               v
                                          |                         return SOFR binding
                                          |<------------------------------+
                                          |
                                          v
                                    build response:
                                      binding = SOFR's binding
                                      path = "rates.libor/usd"  (original)
                                      redirected_from = "rates.libor/usd"
                                      successor = "rates.sofr/usd"
                                          |
          +<------------------------------ +
          |
          v
  gets SOFR data
  (no code change needed)
```

### What does NOT redirect

- **Active monikers with a pre-staged successor** — the successor is set in
  advance but the moniker is still active. Resolution uses the original binding.
- **Deprecated monikers without a successor** — no chain to follow, returns the
  original (possibly stale) binding with deprecation metadata only.
- **Feature toggle off** — all redirect logic is bypassed entirely.

## Successor Chains

Successors can form chains when migrations happen in stages:

```
  rates.libor/usd                rates.sofr/usd              rates.sofr/v2/usd
  (DEPRECATED)         --->      (DEPRECATED)        --->     (ACTIVE)
  successor: sofr/usd            successor: sofr/v2/usd      successor: null

                            chain depth: 2 hops
```

The service follows the chain until it finds an ACTIVE node (or hits the
5-hop safety limit). If it hits the limit, it returns the last node in the
chain with an error logged.

## Consumer Notification Strategy

Consumers are notified through three channels, none of which break their
pipeline:

```
  +-------------------------------------------------------------------+
  |                    Consumer Application                            |
  |                                                                    |
  |   Channel 1: warnings.warn(DeprecationWarning)                    |
  |   +----------------------------------------------------------+    |
  |   | - Deduplicates automatically (once per call site)         |    |
  |   | - Test suites: pytest.warns(DeprecationWarning)           |    |
  |   | - Escalate to error: filterwarnings("error", ...)         |    |
  |   +----------------------------------------------------------+    |
  |                                                                    |
  |   Channel 2: logging.warning("moniker_client")                    |
  |   +----------------------------------------------------------+    |
  |   | - Shows in Splunk / ELK / CloudWatch                      |    |
  |   | - Ops teams can alert on log pattern                      |    |
  |   +----------------------------------------------------------+    |
  |                                                                    |
  |   Channel 3: deprecation_callback(path, message, successor)       |
  |   +----------------------------------------------------------+    |
  |   | - Custom handler: send Slack alert, create Jira ticket    |    |
  |   | - Wired at client construction time                       |    |
  |   +----------------------------------------------------------+    |
  |                                                                    |
  |   IMPORTANT: No exceptions raised. Pipeline continues.             |
  +-------------------------------------------------------------------+
```

## Catalog Reload Safety

When a new catalog is deployed (hot-reload), the validated reload path
compares old and new before swapping:

```
  Deploy Pipeline                    Service
  ===============                    =======

  push new catalog.yaml
          |
          v
  POST /reload               --->   1. Parse new catalog
                                     2. Diff old vs new:
                                        +---------------------------+
                                        | added_paths:     [a, b]   |  safe
                                        | removed_paths:   [c]      |  BREAKING
                                        | binding_changed: [d, e]   |  BREAKING
                                        | status_changed:  [f]      |  safe
                                        +---------------------------+
                                              |
                                              v
                                     3. Audit-log every change:
                                        - "node_removed: c"
                                        - "binding_changed: d (fp: abc -> def)"
                                        - "node_added: a"
                                              |
                                              v
                                     4. Breaking changes detected?
                                        |               |
                                     NO |            YES + block_breaking=true
                                        |               |
                                        v               v
                                     apply           REJECT reload
                                     new catalog     old catalog stays
                                        |
          +<----------------------------+
          |
          v
  response:
  {
    applied: true/false,
    diff: "2 added, 1 removed",
    has_breaking_changes: true,
    successor_errors: [...]
  }
```

## Telemetry & Migration Tracking

Every resolution event is tagged with deprecation metadata, enabling
governance teams to track migration progress:

```
  +---------------------------------------------------------------+
  |  Telemetry Event (UsageEvent)                                  |
  |                                                                |
  |  moniker:         "rates.libor/usd"                            |
  |  app_id:          "risk-engine-prod"                           |
  |  operation:       "READ"                                       |
  |  deprecated:      true                                         |
  |  successor:       "rates.sofr/usd"                             |
  |  redirected_from: "rates.libor/usd"                            |
  |  timestamp:       "2026-02-11T14:30:00Z"                       |
  +---------------------------------------------------------------+
            |
            v
  Query telemetry backend:
  "Which apps are still resolving rates.libor/usd?"
  "How many redirected resolutions per day?"
  "Is anyone still using monikers past their sunset deadline?"
```

The client also sends `deprecated` and `successor` back to the service in
its telemetry payload, so the service has visibility from both sides.

## Feature Toggle Summary

Everything is behind `deprecation.enabled` (default: `false`).

```
  deprecation.enabled = false (DEFAULT)     deprecation.enabled = true
  =====================================     ==========================

  resolve():                                resolve():
    no redirect, original binding             follow successor chain
    no deprecation headers                    add X-Moniker-* headers

  reload_catalog():                         reload_catalog():
    plain atomic_replace()                    diff + audit + optional block
    no validation                             validate successor pointers

  telemetry:                                telemetry:
    standard events only                      events tagged with deprecated/
                                              successor/redirected_from

  client:                                   client:
    no warnings                               DeprecationWarning + logging
    no callbacks                              optional callback invoked
```

Turning the toggle on is safe at any time. Turning it off reverts to
original behaviour with no data loss (successor pointers remain in the
catalog, they are simply ignored).
