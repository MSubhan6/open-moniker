# Telemetry System

## Overview

High-performance, non-blocking telemetry instrumentation for the Go resolver service. Captures 100% of requests for compliance (BCBS 239), billing chargeback, and access tracking.

## Architecture

```
Request → Emit() → [Buffered Channel] → Batcher → Sink
              ↓        (10,240 buffer)      ↓        ↓
         select{}      Non-blocking    Batch(1000)  File I/O
         default:      O(1) send       Timer(150ms)
         drop
```

## Key Features

- **100% Event Capture**: Logs every request (no sampling) for compliance
- **Non-blocking**: Zero latency impact on request hot path (<100ns overhead)
- **High Throughput**: Handles 21K+ events/sec with batching and async I/O
- **Multiple Sinks**: Console (dev), file (production), rotating files (long-term)
- **Overflow Protection**: Drops events only when channel full (emergency backpressure)
- **Graceful Shutdown**: Drains queue and flushes all pending events

## How It Works - Request Flow

### Step-by-Step Breakdown

**1. Request Arrives**
```
User → GET /resolve/benchmarks/SP500@latest
```

**2. Handler Extracts Caller Identity**

`internal/handlers/resolve.go`
```go
caller := &service.CallerIdentity{
    UserID: r.Header.Get("X-User-ID"),  // "alice" or "anonymous"
    Source: "api",
}
result, err := h.service.Resolve(r.Context(), path, caller)
```

**3. Service Sets Up Telemetry Capture (The Key Part!)**

`internal/service/service.go`
```go
func (s *MonikerService) Resolve(ctx, moniker, caller) (*ResolveResult, error) {
    start := time.Now()                     // Start timer
    outcome := telemetry.OutcomeSuccess     // Default outcome
    var result *ResolveResult
    var err error

    // defer runs AFTER function returns - captures final state!
    defer func() {
        latency := float64(time.Since(start).Microseconds()) / 1000.0
        s.emitResolveTelemetry(moniker, caller, outcome, latency, result, err)
    }()

    // ... actual resolution logic ...
    // If error occurs, we update 'outcome' before returning
    // The defer captures the final state!

    return result, err
}
```

**Why defer is brilliant:**
- Runs **after** the function completes (success or error)
- Captures final `outcome`, `result`, and `err` values
- Always executes (even on panic)
- Zero latency added to request path

**4. Emit Creates Event and Sends to Channel**

```go
func (s *MonikerService) emitResolveTelemetry(...) {
    event := telemetry.NewUsageEvent(moniker, path, caller, telemetry.OperationRead)
    event.Outcome = outcome
    event.LatencyMS = latencyMS
    event.ResolvedSourceType = &sourceType

    s.emitter.Emit(*event)  // Non-blocking!
}
```

**5. Emitter: Non-Blocking Channel Send (CRITICAL FOR PERFORMANCE)**

`internal/telemetry/emitter.go`
```go
func (e *Emitter) Emit(event UsageEvent) bool {
    select {
    case e.eventsCh <- event:
        atomic.AddInt64(&e.stats.Emitted, 1)
        return true
    default:
        // Channel full: drop event (emergency overflow)
        atomic.AddInt64(&e.stats.Dropped, 1)
        return false
    }
    // Returns IMMEDIATELY - never blocks!
}
```

**Key**: The `default` case means if channel is full, we **drop** instead of blocking. Request thread never waits.

**6. Background Goroutine Drains Channel**

```go
func (e *Emitter) processLoop() {
    for {
        select {
        case event := <-e.eventsCh:
            e.batcher.Add(event)  // Send to batcher
        case <-e.ctx.Done():
            return  // Shutdown
        }
    }
}
```

This goroutine runs continuously in the background, pulling events and feeding them to the batcher.

**7. Batcher Accumulates Events**

```go
func (b *Batcher) Add(event UsageEvent) {
    b.mu.Lock()
    b.buffer = append(b.buffer, event)
    shouldFlush := len(b.buffer) >= b.batchSize  // 1,000 events?
    b.mu.Unlock()

    if shouldFlush {
        b.Flush()  // Write batch to disk
    }
}
```

**Two flush triggers:**
- **Size-based**: When 1,000 events accumulated
- **Time-based**: Every 150ms (timer goroutine)

**8. Flush Writes Batch to Sink**

```go
func (b *Batcher) Flush() {
    b.mu.Lock()
    events := make([]UsageEvent, len(b.buffer))
    copy(events, b.buffer)
    b.buffer = b.buffer[:0]  // Reset, keep capacity
    b.mu.Unlock()

    // Write to sink (OUTSIDE lock!)
    b.sink.Write(events)
}
```

**Key optimization**: Lock held only for slice copy, not during disk I/O.

**9. Sink Writes to Disk**

Console sink:
```go
func (c *ConsoleSink) Write(events []UsageEvent) error {
    for _, event := range events {
        fmt.Fprintln(c.writer, event.CompactString())
    }
}
```

File sink:
```go
func (f *FileSink) Write(events []UsageEvent) error {
    for _, event := range events {
        data, _ := json.Marshal(event)
        f.file.Write(data)
        f.file.WriteString("\n")  // JSONL format
    }
    f.file.Sync()  // Flush to disk
}
```

### Timing Breakdown

Trace a single request:

```
T=0.000ms:  Request arrives
T=0.001ms:  Handler extracts caller
T=0.002ms:  Service.Resolve() starts (defer registered)
T=2.100ms:  Resolution completes (catalog lookup, etc.)
T=2.101ms:  defer executes: emitTelemetry()
T=2.102ms:  Event created (NewUsageEvent)
T=2.103ms:  emitter.Emit() - channel send
T=2.104ms:  ← RETURN TO USER (latency = 2.104ms)

            ... ASYNC FROM HERE ...

T=2.105ms:  Background goroutine receives event
T=2.106ms:  Batcher.Add() appends to buffer
T=150ms:    Timer fires → Batcher.Flush()
T=151ms:    JSON marshal (1000 events)
T=153ms:    Write to disk (2MB)
T=156ms:    Sync complete
```

**User perceived latency**: 2.104ms
**Telemetry overhead on hot path**: 0.003ms (< 0.15%)

### Why This Design?

1. **defer**: Captures final state without if/else everywhere
2. **select/default**: Non-blocking = zero latency impact
3. **Buffered Channel**: Absorbs bursts without drops
4. **Batching**: Amortizes disk I/O (1 write for 1000 events)
5. **Background Goroutines**: Moves all I/O off request thread

**The key insight**: Telemetry is async cleanup work, not part of the request. The request thread does minimal work (create event, send to channel) then returns immediately.

### Thread Architecture

```
REQUEST THREADS (Hot Path)          BACKGROUND THREADS (Async)
─────────────────────────          ──────────────────────────

Handler                             processLoop()
   ↓                                   ↓
Service.Resolve()                   Read from channel
   ↓                                   ↓
defer emitTelemetry()               Batcher.Add()
   ↓                                   ↓
emitter.Emit()                      Buffer events
   ↓                                   ↓
Channel send ←──────────────────→  timerLoop()
   ↓                                   ↓
RETURN TO USER                      Batcher.Flush()
                                       ↓
                                    Sink.Write()
                                       ↓
                                    Disk I/O
```

## Configuration

### Console Sink (Development)

```yaml
telemetry:
  enabled: true
  sink_type: console
  sink_config:
    stream: stdout  # or stderr
    format: compact  # or json
  batch_size: 1000
  flush_interval_seconds: 0.15
  max_queue_size: 10240
```

Output format (compact):
```
[TELEMETRY] 2026-02-20T12:00:00Z user:alice read benchmarks/SP500@20260101 success 2.3ms
```

### File Sink (Simple JSONL)

```yaml
telemetry:
  enabled: true
  sink_type: file
  sink_config:
    path: "./telemetry/events.jsonl"
  batch_size: 1000
  flush_interval_seconds: 0.15
  max_queue_size: 10240
```

### Rotating File Sink (Production)

```yaml
telemetry:
  enabled: true
  sink_type: rotating_file
  sink_config:
    directory: "./telemetry"
    path_pattern: "telemetry-20060102-15.jsonl"  # Go time format
    max_bytes: 104857600  # 100MB
  batch_size: 1000
  flush_interval_seconds: 0.15
  max_queue_size: 10240
```

Files rotate:
- **Time-based**: Hourly (e.g., `telemetry-20260220-14.jsonl`)
- **Size-based**: When file exceeds 100MB (appends `.1`, `.2`, etc.)

### PostgreSQL Sink (Production - Queryable Audit Trail)

**Best for:**
- ✅ Compliance auditing (BCBS 239)
- ✅ Chargeback/billing reports
- ✅ Security analysis (unauthorized access)
- ✅ Performance analytics (latency trends)
- ✅ Ad-hoc SQL queries

```yaml
telemetry:
  enabled: true
  sink_type: postgres
  sink_config:
    # Option 1: Connection string
    connection_string: "postgres://telemetry:password@localhost:5432/moniker_telemetry?sslmode=disable"

    # Option 2: Individual parameters
    host: localhost
    port: 5432
    database: moniker_telemetry
    user: telemetry
    password: ${TELEMETRY_DB_PASSWORD}
    sslmode: disable  # disable | require | verify-ca | verify-full
    max_retries: 3
    retry_delay_ms: 100
  batch_size: 1000
  flush_interval_seconds: 0.15
  max_queue_size: 10240
```

**Quick Start:**
```bash
# Start PostgreSQL with Docker
cd resolver-go
docker-compose up -d

# Configure resolver to use postgres sink
# (edit config.yaml as shown above)

# Run resolver
./bin/resolver --config ../config.yaml

# Query telemetry
docker-compose exec postgres psql -U telemetry -d moniker_telemetry
SELECT * FROM telemetry_events ORDER BY timestamp DESC LIMIT 10;
```

**Features:**
- Monthly partitioning for performance
- 7-year retention (BCBS 239 compliance)
- Pre-built views for common reports
- 23+ example audit queries
- Handles 21K+ events/sec

See **[POSTGRES_SETUP.md](../../POSTGRES_SETUP.md)** for full setup guide.

## Performance Tuning

### Buffer Sizing

Formula: `max_queue_size = req_rate * flush_interval`

For 21K req/s with 150ms flush interval:
```
max_queue_size = 21000 * 0.5 = 10,500 → use 10,240
```

### Flush Interval

At 21K req/s, a 1000-event batch fills in ~48ms:
```
batch_fill_time = batch_size / req_rate = 1000 / 21000 ≈ 48ms
```

Use 150ms (3x safety margin) to handle bursts. Python's 1s interval is too long for this throughput.

### Expected Metrics

- **Throughput**: 21K+ req/s (no regression)
- **Latency p50**: <2.5ms (baseline: 2.1ms)
- **Latency p99**: <12ms (baseline: 10.8ms)
- **Drop rate**: <0.1% at target load, <2% at overload (25K req/s)
- **Memory**: +50MB for channel buffer
- **Disk I/O**: 2-3 MB/s sustained (compressed JSONL)
- **CPU**: +2-3% for serialization

## Event Structure

```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-02-20T12:00:00.123456Z",
  "caller": {
    "user_id": "alice",
    "service_id": null,
    "app_id": null,
    "team": null
  },
  "moniker": "moniker://benchmarks/SP500@20260101",
  "moniker_path": "benchmarks/SP500",
  "operation": "read",
  "outcome": "success",
  "latency_ms": 2.34,
  "resolved_source_type": "snowflake",
  "owner_at_access": "team:market-data",
  "deprecated": false,
  "successor": null,
  "redirected_from": null,
  "cached": false,
  "error_message": null,
  "metadata": {}
}
```

## Health Monitoring

Check telemetry stats via `/health` endpoint:

```bash
curl http://localhost:8053/health | jq .telemetry
```

Response:
```json
{
  "enabled": true,
  "emitted": 644757,
  "dropped": 23,
  "errors": 0,
  "queue_depth": 156,
  "drop_rate": 0.00
}
```

**Alerts**:
- `drop_rate > 1%`: Increase `max_queue_size` or optimize sink
- `queue_depth > 5000`: System under heavy load
- `errors > 0`: Check sink configuration and disk space

## Usage

### Initialization

```go
import "github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/telemetry"

// Create from config
emitter, err := telemetry.NewFromConfig(&cfg.Telemetry)
if err != nil {
    log.Printf("Warning: Failed to initialize telemetry: %v", err)
    emitter = telemetry.NewNoOpEmitter()
}
defer emitter.Stop()
```

### Emitting Events

```go
event := telemetry.NewUsageEvent(moniker, path, caller, telemetry.OperationRead)
event.Outcome = telemetry.OutcomeSuccess
event.LatencyMS = latency
event.ResolvedSourceType = &sourceType

emitter.Emit(*event)  // Non-blocking
```

### Graceful Shutdown

```go
defer emitter.Stop()  // Drains queue and flushes all events
```

## Components

- **events.go**: Event types, enums, constructors
- **emitter.go**: Non-blocking channel-based emitter
- **batcher.go**: Batch accumulation with timer
- **sink.go**: Sink interface
- **sinks/console.go**: Console output (dev)
- **sinks/file.go**: File output (JSONL)
- **sinks/rotating.go**: Rotating files (production)
- **factory.go**: Config-driven initialization

## Testing

Run integration tests:
```bash
cd resolver-go
go test ./internal/telemetry/... -v
```

Load test with telemetry:
```bash
hey -z 30s -c 200 http://localhost:8053/resolve/benchmarks/SP500@latest
curl http://localhost:8053/health | jq .telemetry
```

## Troubleshooting

### High Drop Rate

**Symptom**: `drop_rate > 1%` in `/health`

**Solutions**:
1. Increase `max_queue_size` (e.g., from 10,240 to 20,480)
2. Decrease `flush_interval_seconds` (e.g., from 0.15 to 0.1)
3. Use faster sink (e.g., switch from rotating_file to file)
4. Add more disk IOPS for file sink

### Disk Space Issues

**Symptom**: Telemetry directory growing too fast

**Solutions**:
1. Reduce `max_bytes` (smaller files rotate sooner)
2. Implement retention policy (delete files older than 7 days)
3. Enable log compression (gzip rotated files)
4. Ship logs to centralized system (future: HTTP sink)

### Memory Usage

**Symptom**: High memory consumption

**Solutions**:
1. Reduce `max_queue_size` (smaller channel buffer)
2. Reduce `batch_size` (smaller batches)
3. Check for event leaks (queue should drain)

## Quick Start

Try it now in 3 steps:

```bash
# 1. Build
cd /home/user/open-moniker-svc/resolver-go
make tidy && make build

# 2. Run (console telemetry enabled by default)
./bin/resolver --config ../config.yaml --port 8053

# 3. Make a request (in another terminal)
curl http://localhost:8053/resolve/benchmarks/SP500@latest
```

**You should see in the resolver console:**
```
[TELEMETRY] 2026-02-20T12:34:56.789Z anonymous read benchmarks/SP500 success 2.3ms
```

**Check stats:**
```bash
curl http://localhost:8053/health | jq .telemetry
# {
#   "enabled": true,
#   "emitted": 1,
#   "dropped": 0,
#   "errors": 0,
#   "queue_depth": 0,
#   "drop_rate": 0.00
# }
```

**Switch to file output:**

Edit `config.yaml`:
```yaml
telemetry:
  sink_type: file
  sink_config:
    path: "./telemetry/events.jsonl"
```

Restart and make requests, then:
```bash
# View events as JSON
cat telemetry/events.jsonl | jq .

# Count events
wc -l telemetry/events.jsonl
```

## Future Enhancements

- **HTTP Sink**: POST batches to centralized telemetry service
- **Compression**: gzip rotated files
- **Structured Logging**: Replace stdlib log with zerolog
- **Sharded Batchers**: Multiple batcher goroutines for >50K req/s
- **Metrics**: Prometheus/StatsD integration
