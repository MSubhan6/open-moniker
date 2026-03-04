# Java Resolver Verification Guide

This guide walks you through verifying that the Java resolver implementation is working correctly and matches the performance targets.

## Prerequisites

```bash
# Verify Java 21 is installed
java -version
# Should show: openjdk version "21" or higher

# Verify Maven is installed
mvn -version
# Should show: Apache Maven 3.9+

# Verify catalog files exist
ls -la ../config.yaml ../catalog.yaml
```

## Phase 1: Build Verification

### Step 1: Clean Build

```bash
cd resolver-java
make clean
make build
```

**Expected output:**
```
[INFO] BUILD SUCCESS
[INFO] Total time: XX.XXX s
```

### Step 2: Run Tests

```bash
make test
```

**Expected:** All tests pass (once unit tests are added).

### Step 3: Package

```bash
make package
```

**Expected:**
```
[INFO] Building jar: target/resolver-java-0.1.0.jar
[INFO] BUILD SUCCESS
```

## Phase 2: Functional Verification

### Step 1: Start Resolver

```bash
make run
```

**Expected output:**
```
Loading catalog from: ../catalog.yaml
Loaded NNN catalog nodes
Started MonikerResolverApplication in X.XXX seconds
```

Keep this running in one terminal.

### Step 2: Health Check

In a new terminal:

```bash
curl http://localhost:8054/health | jq
```

**Expected output:**
```json
{
  "status": "healthy",
  "project": "Open Moniker",
  "service": "resolver-java",
  "version": "0.1.0",
  "catalog_nodes": 123,
  "timestamp": 1234567890
}
```

✅ **Pass criteria:** `status` is "healthy", `catalog_nodes` > 0

### Step 3: Resolve Endpoint

```bash
curl http://localhost:8054/resolve/prices.equity/AAPL@latest | jq
```

**Expected output:**
```json
{
  "moniker": "moniker://prices.equity/AAPL@latest",
  "path": "prices.equity/AAPL",
  "version": "latest",
  "sourceType": "oracle",
  "sourceConfig": {
    "query_template": "SELECT * FROM ...",
    ...
  },
  "ownership": {
    "accountableOwner": "...",
    ...
  }
}
```

✅ **Pass criteria:** Returns valid JSON with `sourceType`, `sourceConfig`, `ownership`

### Step 4: Describe Endpoint

```bash
curl http://localhost:8054/describe/prices.equity | jq
```

**Expected output:**
```json
{
  "path": "prices.equity",
  "displayName": "Equity Prices",
  "description": "...",
  "status": "active",
  "isLeaf": false,
  "hasSourceBinding": false
}
```

✅ **Pass criteria:** Returns node metadata

### Step 5: List Endpoint

```bash
curl http://localhost:8054/list/prices | jq
```

**Expected output:**
```json
{
  "path": "prices",
  "children": [
    "prices.equity",
    "prices.fixed_income",
    ...
  ],
  "count": 3
}
```

✅ **Pass criteria:** Returns list of child paths

### Step 6: Catalog Search

```bash
curl "http://localhost:8054/catalog/search?q=equity" | jq
```

**Expected output:**
```json
{
  "query": "equity",
  "results": [...],
  "count": 5
}
```

✅ **Pass criteria:** Returns matching nodes

### Step 7: Catalog Stats

```bash
curl http://localhost:8054/catalog/stats | jq
```

**Expected output:**
```json
{
  "total_nodes": 123,
  "leaf_nodes": 45,
  "category_nodes": 78,
  "by_status": {
    "active": 100,
    "draft": 20,
    ...
  },
  "by_source_type": {
    "oracle": 30,
    "snowflake": 15,
    ...
  }
}
```

✅ **Pass criteria:** Returns catalog statistics

### Step 8: UI Endpoint

```bash
curl http://localhost:8054/ui
```

**Expected:** Returns HTML page with endpoint documentation

✅ **Pass criteria:** HTML page renders correctly

## Phase 3: API Parity Verification

### Compare with Go Resolver

```bash
# Start Go resolver (port 8053)
cd ../resolver-go && make run &

# Start Java resolver (port 8054)
cd ../resolver-java && make run &

# Wait for both to start
sleep 5

# Compare health responses
curl http://localhost:8053/health > go_health.json
curl http://localhost:8054/health > java_health.json

# Compare resolve responses
curl http://localhost:8053/resolve/prices.equity/AAPL@latest > go_resolve.json
curl http://localhost:8054/resolve/prices.equity/AAPL@latest > java_resolve.json

# Diff (ignore timestamp fields)
diff <(jq 'del(.timestamp)' go_health.json) <(jq 'del(.timestamp)' java_health.json)
diff <(jq 'del(.timestamp)' go_resolve.json) <(jq 'del(.timestamp)' java_resolve.json)
```

✅ **Pass criteria:** No differences (except service name and timestamp)

## Phase 4: Performance Verification

### Quick Benchmark

```bash
./benchmark.sh
```

**Expected output:**
```
=== Test 1: Health Endpoint (Sequential, 100 requests) ===
real    0m0.XXXs

=== Test 2: Health Endpoint (Concurrent, 200 requests) ===
real    0m0.XXXs

=== Test 3: Resolve Endpoint (Sequential, 50 requests) ===
real    0m0.XXXs
```

✅ **Pass criteria:**
- Sequential health: < 2 seconds (< 20ms per request)
- Concurrent health: < 1 second
- Sequential resolve: < 3 seconds (< 60ms per request)

### Stress Test with Python Harness

```bash
# Ensure resolver is running
curl -s http://localhost:8054/health

# Run 60-second stress test
./stress-test.sh
```

**Expected output:**
```
[t=1s] req/s: 18000-22000  success: 100%  p50: 8-12ms  p95: 20-30ms
[t=2s] req/s: 18000-22000  success: 100%  p50: 8-12ms  p95: 20-30ms
...
[t=60s] req/s: 18000-22000  success: 100%  p50: 8-12ms  p95: 20-30ms

Summary:
  Total requests: 1,000,000 - 1,200,000
  Throughput: 18,000 - 22,000 req/s
  p50 latency: 8-12ms
  p99 latency: 25-40ms
  Success rate: 100%
```

✅ **Pass criteria:**
- **Throughput**: >20,000 req/s (within 5% of Go baseline: 21,484 req/s)
- **Latency p50**: <10ms (Go baseline: 8.1ms)
- **Latency p99**: <35ms (Go baseline: 30.2ms)
- **Success rate**: 100% (no errors)

### Load Testing with `hey`

```bash
# Install hey if not available
# go install github.com/rakyll/hey@latest

# Health endpoint
hey -n 10000 -c 200 http://localhost:8054/health

# Resolve endpoint
hey -n 5000 -c 100 http://localhost:8054/resolve/prices.equity/AAPL@latest
```

**Expected output (health endpoint):**
```
Summary:
  Total:        0.5000 secs
  Slowest:      0.0500 secs
  Fastest:      0.0010 secs
  Average:      0.0100 secs
  Requests/sec: 20000.0000
```

✅ **Pass criteria:**
- Health endpoint: >15,000 req/s
- Resolve endpoint: >10,000 req/s
- No 5xx errors

## Phase 5: Comparison with Go

### Side-by-Side Stress Test

Run both resolvers and stress test simultaneously:

```bash
# Terminal 1: Go resolver
cd resolver-go && make run

# Terminal 2: Java resolver
cd resolver-java && make run

# Terminal 3: Go stress test
cd tests/stress && python3 harness.py --port 8053 --workers 64 --duration 60

# Terminal 4: Java stress test (wait for Go to finish)
cd tests/stress && python3 harness.py --port 8054 --workers 64 --duration 60
```

**Compare results:**

| Metric | Go Baseline | Java Result | Delta | Pass? |
|--------|-------------|-------------|-------|-------|
| Throughput | 21,484 req/s | ??? req/s | ??? | >20,000? |
| p50 Latency | 8.1ms | ??? ms | ??? | <10ms? |
| p99 Latency | 30.2ms | ??? ms | ??? | <35ms? |
| Success Rate | 100% | ??? | ??? | 100%? |
| Memory | ~20MB | ??? MB | ??? | <200MB? |

✅ **Pass criteria:** Java within 5-10% of Go performance

## Phase 6: Resource Usage

### Monitor JVM Metrics

```bash
# Start resolver with JFR
java -XX:StartFlightRecording=duration=60s,filename=profile.jfr \
     -XX:+UseZGC \
     -Xms1g -Xmx2g \
     -jar target/resolver-java-0.1.0.jar

# Run stress test
./stress-test.sh

# Analyze recording (after 60s)
jfr print --events CPULoad,GarbageCollection profile.jfr
```

✅ **Pass criteria:**
- CPU usage <80% during stress test
- GC pauses <50ms (p99)
- Memory usage steady (no leaks)

### Check Memory

```bash
# While stress test running
jcmd $(pgrep -f resolver-java) GC.heap_info
```

✅ **Pass criteria:**
- Heap usage <2GB
- No OutOfMemoryError
- Minimal full GCs

## Success Criteria Summary

### Functional
- ✅ All 19 endpoints implemented and tested
- ✅ 100% API parity with Go/Python implementations
- ✅ All health checks pass
- ✅ Catalog loads successfully

### Performance
- ✅ Throughput >20,000 req/s (within 5% of Go: 21,484 req/s)
- ✅ Latency p50 <10ms (Go: 8.1ms)
- ✅ Latency p99 <35ms (Go: 30.2ms)
- ✅ 100% success rate under load (no errors)
- ✅ Stress harness passes (60-second test with 64 workers)

### Quality
- ✅ No memory leaks during 60-second stress test
- ✅ GC pauses <50ms (p99)
- ✅ Startup time <3 seconds
- ✅ Resource usage reasonable (<200MB RAM)

## Troubleshooting

### Low Throughput

**Problem:** Throughput <15,000 req/s

**Solutions:**
1. Verify virtual threads enabled:
   ```yaml
   # application.yaml
   spring:
     threads:
       virtual:
         enabled: true
   ```

2. Increase Undertow threads:
   ```yaml
   server:
     undertow:
       threads:
         io: 32
         worker: 400
   ```

3. Use ZGC:
   ```bash
   java -XX:+UseZGC -jar target/resolver-java-0.1.0.jar
   ```

### High Latency

**Problem:** p99 latency >50ms

**Solutions:**
1. Check GC settings:
   ```bash
   java -Xlog:gc* -XX:+UseZGC -jar ...
   ```

2. Profile with JFR:
   ```bash
   java -XX:StartFlightRecording=duration=60s,filename=profile.jfr -jar ...
   ```

3. Optimize catalog lookups (check StampedLock usage)

### Memory Issues

**Problem:** Memory usage >2GB or OutOfMemoryError

**Solutions:**
1. Reduce heap size:
   ```bash
   java -Xms512m -Xmx1g -jar ...
   ```

2. Enable ZGC for better memory management:
   ```bash
   java -XX:+UseZGC -XX:ZCollectionInterval=5 -jar ...
   ```

3. Check for leaks with jcmd:
   ```bash
   jcmd <pid> GC.heap_dump heap.hprof
   ```

## Next Steps

Once all verification passes:

1. **Document Results**: Record actual performance numbers
2. **Commit Code**: Push to MSubhan6/open-moniker.git
3. **Create PR**: Open PR to ganizanisitara/open-moniker-svc
4. **Performance Report**: Create comparison document (Java vs Go vs Python)
