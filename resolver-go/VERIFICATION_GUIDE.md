# Telemetry Verification Guide

## Quick Start

### 1. Build and Setup

```bash
cd /home/user/open-moniker-svc/resolver-go

# Download dependencies and create go.sum
make tidy

# Build the resolver
make build
```

### 2. Run with Console Telemetry

```bash
# Make sure config.yaml has console telemetry enabled
# (already configured in /home/user/open-moniker-svc/config.yaml)

./bin/resolver --config ../config.yaml --port 8053
```

You should see:
```
2026/02/20 12:00:00 Loaded X catalog nodes
2026/02/20 12:00:00 Telemetry enabled: sink=console, batch_size=1000, flush_interval=0.150s
2026/02/20 12:00:00 Starting Go resolver on 0.0.0.0:8053
```

### 3. Make Test Requests

In another terminal:

```bash
# Resolve request
curl http://localhost:8053/resolve/benchmarks.constituents/SP500/20260101

# Describe request
curl http://localhost:8053/describe/benchmarks

# List request
curl http://localhost:8053/list/benchmarks

# Check health with telemetry stats
curl http://localhost:8053/health | jq .
```

### 4. Verify Console Output

You should see telemetry events in the resolver console:

```
[TELEMETRY] 2026-02-20T12:00:00.123456789Z anonymous read benchmarks.constituents/SP500/20260101 success 2.3ms
[TELEMETRY] 2026-02-20T12:00:01.234567890Z anonymous describe benchmarks success 1.1ms
[TELEMETRY] 2026-02-20T12:00:02.345678901Z anonymous list benchmarks success 0.8ms
```

### 5. Verify Health Endpoint

```bash
curl http://localhost:8053/health | jq .telemetry
```

Expected output:
```json
{
  "enabled": true,
  "emitted": 3,
  "dropped": 0,
  "errors": 0,
  "queue_depth": 0,
  "drop_rate": 0.00
}
```

## Test File Sink

### 1. Update Config

Edit `/home/user/open-moniker-svc/config.yaml`:

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

### 2. Restart and Test

```bash
# Stop the resolver (Ctrl+C)
./bin/resolver --config ../config.yaml --port 8053

# Make requests
for i in {1..10}; do
  curl -s http://localhost:8053/resolve/benchmarks/SP500@latest > /dev/null
done
```

### 3. Check File Output

```bash
# List telemetry files
ls -lh telemetry/

# View events as JSON
cat telemetry/events.jsonl | jq .

# Count events
wc -l telemetry/events.jsonl
```

## Test Rotating File Sink

### 1. Update Config

```yaml
telemetry:
  enabled: true
  sink_type: rotating_file
  sink_config:
    directory: "./telemetry"
    path_pattern: "telemetry-20060102-15.jsonl"
    max_bytes: 104857600  # 100MB
  batch_size: 1000
  flush_interval_seconds: 0.15
  max_queue_size: 10240
```

### 2. Restart and Test

```bash
./bin/resolver --config ../config.yaml --port 8053

# Generate many requests
for i in {1..100}; do
  curl -s http://localhost:8053/resolve/benchmarks/SP500@latest > /dev/null
done
```

### 3. Check Rotating Files

```bash
# List telemetry files (should see hourly files)
ls -lh telemetry/
# Expected: telemetry-20260220-12.jsonl, telemetry-20260220-13.jsonl, etc.

# Count events across all files
cat telemetry/*.jsonl | wc -l
```

## Load Testing

### 1. Install hey (if needed)

```bash
# Check if hey is installed
which hey

# If not, install it
go install github.com/rakyll/hey@latest
export PATH=$PATH:$(go env GOPATH)/bin
```

### 2. Run Load Test

```bash
# Ensure resolver is running with file or rotating_file sink
./bin/resolver --config ../config.yaml --port 8053

# In another terminal, run load test (30 seconds, 200 concurrent)
hey -z 30s -c 200 http://localhost:8053/resolve/benchmarks/SP500@latest
```

### 3. Check Results

```bash
# Check telemetry stats
curl http://localhost:8053/health | jq .telemetry
```

Expected output:
```json
{
  "enabled": true,
  "emitted": 644757,
  "dropped": 0,
  "errors": 0,
  "queue_depth": 156,
  "drop_rate": 0.00
}
```

**Success Criteria**:
- ✓ `emitted` > 600,000 (30s * 21K req/s)
- ✓ `dropped` < 100 (drop_rate < 0.02%)
- ✓ `errors` = 0
- ✓ `queue_depth` < 1000 (queue is draining)

### 4. Verify Performance

Check hey output:

```
Summary:
  Total:        30.0000 secs
  Slowest:      0.0120 secs
  Fastest:      0.0015 secs
  Average:      0.0021 secs
  Requests/sec: 21484.3333
```

**Success Criteria**:
- ✓ Requests/sec > 20,000 (no regression from baseline)
- ✓ Average latency < 2.5ms
- ✓ Slowest (p99) < 12ms

## Test Graceful Shutdown

### 1. Start Resolver with File Sink

```bash
./bin/resolver --config ../config.yaml --port 8053 > /tmp/resolver.log 2>&1 &
RESOLVER_PID=$!
echo "Resolver PID: $RESOLVER_PID"
```

### 2. Generate Load

```bash
# Start background requests
for i in {1..1000}; do
  curl -s http://localhost:8053/resolve/benchmarks/SP500@latest > /dev/null &
done
```

### 3. Send SIGTERM

```bash
# Give it a moment to accumulate events
sleep 2

# Gracefully shutdown
kill -TERM $RESOLVER_PID

# Wait for shutdown
wait $RESOLVER_PID
```

### 4. Check Logs

```bash
tail -20 /tmp/resolver.log
```

Expected output:
```
Shutting down server...
[Telemetry] Stopping emitter...
[Telemetry] Emitter stopped. Stats: emitted=1234, dropped=0, errors=0
[Telemetry] Stopping batcher...
[Telemetry] Batcher stopped. Stats: batches=2, events=1234, errors=0
Server stopped
```

### 5. Verify No Data Loss

```bash
# Count events in file
wc -l telemetry/events.jsonl

# Should match "emitted" count from logs (1234 in example above)
```

## Test Different Outcomes

### 1. Success

```bash
curl http://localhost:8053/resolve/benchmarks/SP500@latest
```

Telemetry event:
```json
{
  "outcome": "success",
  "latency_ms": 2.3,
  "resolved_source_type": "snowflake"
}
```

### 2. Not Found

```bash
curl http://localhost:8053/resolve/nonexistent/path@latest
```

Telemetry event:
```json
{
  "outcome": "not_found",
  "error_message": "Path not found: nonexistent/path"
}
```

### 3. Invalid Moniker

```bash
curl http://localhost:8053/resolve/invalid@@syntax
```

Telemetry event:
```json
{
  "outcome": "error",
  "error_message": "Invalid moniker: ..."
}
```

## Test Caller Identity

### 1. Authenticated Request

```bash
curl -H "X-User-ID: alice" http://localhost:8053/resolve/benchmarks/SP500@latest
```

Telemetry event:
```json
{
  "caller": {
    "user_id": "alice"
  }
}
```

Event compact format:
```
[TELEMETRY] ... user:alice read benchmarks/SP500 success 2.3ms
```

### 2. Anonymous Request

```bash
curl http://localhost:8053/resolve/benchmarks/SP500@latest
```

Telemetry event:
```json
{
  "caller": {
    "user_id": "anonymous"
  }
}
```

Event compact format:
```
[TELEMETRY] ... anonymous read benchmarks/SP500 success 2.3ms
```

## Troubleshooting

### No Telemetry Events

**Check 1**: Is telemetry enabled?
```bash
curl http://localhost:8053/health | jq .telemetry.enabled
# Should return: true
```

**Check 2**: Are requests reaching the service?
```bash
curl http://localhost:8053/health | jq .telemetry.emitted
# Should be > 0 after making requests
```

**Check 3**: Check resolver logs for errors
```bash
grep -i telemetry /tmp/resolver.log
```

### High Drop Rate

**Symptom**: `/health` shows `drop_rate > 1%`

**Check queue depth**:
```bash
curl http://localhost:8053/health | jq .telemetry.queue_depth
```

If queue_depth is consistently near `max_queue_size` (10,240):
1. Increase `max_queue_size` to 20,480
2. Decrease `flush_interval_seconds` to 0.1
3. Check disk I/O: `iostat -x 1`

### File Sink Errors

**Symptom**: `errors > 0` in `/health`

**Check 1**: Directory exists?
```bash
ls -ld ./telemetry
# If not: mkdir -p ./telemetry
```

**Check 2**: Permissions?
```bash
ls -l ./telemetry
# Should be writable
```

**Check 3**: Disk space?
```bash
df -h .
```

### Build Errors

**Error**: `cannot find package`

**Solution**:
```bash
cd /home/user/open-moniker-svc/resolver-go
make tidy
go mod download
```

**Error**: `undefined: uuid`

**Solution**: Check go.mod has `github.com/google/uuid v1.6.0`
```bash
grep uuid go.mod
# Should show: github.com/google/uuid v1.6.0

# If missing:
go get github.com/google/uuid@v1.6.0
```

## Success Checklist

- [✓] `make tidy` completes without errors
- [✓] `make build` creates `bin/resolver`
- [✓] Resolver starts with "Telemetry enabled" message
- [✓] Console shows telemetry events for each request
- [✓] `/health` endpoint shows `enabled: true`
- [✓] File sink creates JSONL files
- [✓] Rotating sink creates hourly files
- [✓] Load test achieves >20K req/s with drop_rate < 1%
- [✓] Graceful shutdown logs show no data loss
- [✓] Different outcomes (success, not_found, error) are captured
- [✓] Caller identity is properly tracked

## Next Steps After Verification

1. **Production Deployment**
   - Use `rotating_file` sink
   - Set `max_bytes: 104857600` (100MB)
   - Implement log retention (delete files > 7 days old)

2. **Monitoring**
   - Alert on `drop_rate > 1%`
   - Alert on `errors > 0`
   - Track `emitted` for billing/usage analysis

3. **Analytics**
   - Parse JSONL files for usage patterns
   - Identify deprecated monikers in use
   - Track top users/teams by request count
   - Calculate chargeback by team

4. **Compliance**
   - Archive telemetry logs for 7 years (BCBS 239)
   - Implement access controls on telemetry files
   - Document data retention policy
   - Set up audit trail verification

## Performance Baseline

Record these metrics for future comparison:

```bash
# Start fresh resolver
./bin/resolver --config ../config.yaml --port 8053

# Run 30s load test
hey -z 30s -c 200 http://localhost:8053/resolve/benchmarks/SP500@latest

# Record results
# Requests/sec: _______
# Average latency: _______ms
# p50: _______ms
# p99: _______ms

# Check telemetry stats
curl http://localhost:8053/health | jq .telemetry

# Record results
# emitted: _______
# dropped: _______
# drop_rate: _______%
```

Target values:
- Requests/sec: >20,000
- Average latency: <2.5ms
- p50: <2.5ms
- p99: <12ms
- drop_rate: <0.1%
