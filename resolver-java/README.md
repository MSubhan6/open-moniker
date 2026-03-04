# Moniker Resolver - Java Implementation

High-performance Java implementation of the Open Moniker resolver service using Spring Boot 3.2 and Java 21 virtual threads.

## Overview

This is a **performance comparison implementation** of the moniker resolver in Java, designed to run the same throughput tests as the Go resolver and measure performance characteristics across language implementations.

### Why This Implementation?

- **Validation**: Prove the architecture is language-agnostic, not Go-specific
- **Options**: Give teams flexibility to choose Java vs Go based on their tech stack
- **Benchmarking**: Direct performance comparison using identical workloads

### Go Resolver Baseline

- **Throughput**: 21,484 req/s sustained (vs Python: ~600 req/s)
- **Latency**: p50: 8.1ms, p99: 30.2ms
- **Architecture**: Standalone HTTP service, no external dependencies

### Java Performance Targets

| Metric | Go Baseline | Java Target | Notes |
|--------|-------------|-------------|-------|
| Throughput | 21,484 req/s | >20,000 req/s | Within 5% of Go |
| Latency p50 | 8.1ms | <10ms | Acceptable for JVM |
| Latency p99 | 30.2ms | <35ms | Account for GC pauses |
| Memory | ~20MB | ~100-150MB | JVM overhead expected |
| Startup | <1s | <3s | JVM warmup acceptable |

## Technology Stack

- **Framework**: Spring Boot 3.2.2
- **Build Tool**: Maven
- **Java Version**: 21 (with virtual threads for high concurrency)
- **Server**: Undertow (lightweight, high-performance)
- **Database**: None required (PostgreSQL optional for telemetry like Go)

## Quick Start

### Prerequisites

- Java 21 (for virtual threads)
- Maven 3.9+
- `../config.yaml` and `../catalog.yaml` (shared with other resolvers)

### Build and Run

```bash
# Build
make build

# Run tests
make test

# Package JAR
make package

# Run resolver (port 8054)
make run

# Or run directly
java -jar target/resolver-java-0.1.0.jar --server.port=8054
```

### Verify It's Running

```bash
# Health check
curl http://localhost:8054/health

# Expected output:
# {
#   "status": "healthy",
#   "project": "Open Moniker",
#   "service": "resolver-java",
#   "version": "0.1.0",
#   "catalog_nodes": 123,
#   "timestamp": 1234567890
# }
```

## API Endpoints

The Java resolver implements **100% API parity** with the Go and Python implementations:

### Core Resolution

- `GET /health` - Health check + catalog stats
- `GET /resolve/{path}` - Resolve moniker to source binding
- `GET /describe/{path}` - Metadata about catalog node
- `GET /list/{path}` - List child nodes
- `GET /lineage/{path}` - Hierarchy of ancestors

### Catalog Management

- `GET /catalog` - Paginated catalog list
- `GET /catalog/search?q=` - Full-text search
- `GET /catalog/stats` - Catalog statistics

### Other

- `GET /cache/status` - Cache management (stub)
- `GET /ui` - Web UI

### Example Requests

```bash
# Resolve a moniker
curl http://localhost:8054/resolve/prices.equity/AAPL@latest

# Describe a node
curl http://localhost:8054/describe/prices.equity

# List children
curl http://localhost:8054/list/prices

# Search catalog
curl "http://localhost:8054/catalog/search?q=equity"

# Get stats
curl http://localhost:8054/catalog/stats
```

## Performance Testing

### Quick Benchmark (Shell Script)

Simple sequential and concurrent tests:

```bash
./benchmark.sh
```

This runs:
- 100 sequential health checks
- 200 concurrent health checks
- 50 sequential resolve calls
- Sample response validation

### High-Concurrency Stress Test (Python Harness)

The main performance test using the shared Python stress harness:

```bash
# Start Java resolver
make run &

# Run 64-worker, 60-second stress test
./stress-test.sh

# Or with custom parameters
./stress-test.sh 8054 64 60  # port workers duration
```

Expected output:
```
[t=1s] req/s: ~20,000  success: 100%  p50: ~10ms  p95: ~25ms
[t=2s] req/s: ~20,000  success: 100%  p50: ~10ms  p95: ~25ms
...
Summary:
  Total requests: ~1,200,000
  Throughput: ~20,000 req/s
  p50 latency: ~10ms
  p99 latency: ~35ms
  Success rate: 100%
```

### Load Testing with `hey`

```bash
# Health endpoint throughput
hey -n 10000 -c 200 http://localhost:8054/health

# Resolve endpoint throughput
hey -n 5000 -c 100 http://localhost:8054/resolve/prices.equity/AAPL@latest
```

## Architecture

### Performance Optimizations

1. **Virtual Threads (Java 21)**
   - Enabled in `application.yaml`: `spring.threads.virtual.enabled: true`
   - Similar to Go's goroutines, allows massive concurrency

2. **Undertow Server**
   - I/O threads: CPU cores × 2
   - Worker threads: 200 (virtual threads handle the rest)
   - Lower overhead than Tomcat

3. **StampedLock with Optimistic Reads**
   - `CatalogRegistry` uses optimistic reads for lock-free hot path
   - ~90% of operations avoid locking entirely
   - Fallback to read lock only if concurrent write detected

4. **Jackson Optimizations**
   - Afterburner module for faster serialization
   - Includes only non-null fields
   - Minimal auto-configuration overhead

### Project Structure

```
resolver-java/
├── pom.xml                     # Maven configuration
├── Makefile                    # Build automation
├── benchmark.sh                # Quick shell benchmark
├── stress-test.sh              # Python harness wrapper
│
├── src/main/java/.../resolver/
│   ├── MonikerResolverApplication.java    # Entry point
│   │
│   ├── moniker/                # Moniker parsing (ported from Go)
│   │   ├── Moniker.java
│   │   ├── MonikerPath.java
│   │   ├── MonikerParser.java
│   │   ├── VersionType.java
│   │   └── QueryParams.java
│   │
│   ├── catalog/                # Catalog registry (ported from Go)
│   │   ├── CatalogNode.java
│   │   ├── CatalogRegistry.java  # Thread-safe with StampedLock
│   │   ├── CatalogLoader.java
│   │   ├── SourceBinding.java
│   │   ├── Ownership.java
│   │   ├── AccessPolicy.java
│   │   └── NodeStatus.java
│   │
│   ├── service/                # Resolution business logic
│   │   ├── MonikerService.java
│   │   ├── ResolveResult.java
│   │   └── DescribeResult.java
│   │
│   ├── controller/             # HTTP endpoints
│   │   └── ResolverController.java
│   │
│   └── config/                 # Configuration
│       ├── ApplicationConfig.java
│       ├── ConfigLoader.java
│       └── ...
│
└── src/main/resources/
    └── application.yaml        # Spring Boot config
```

## Configuration

### Environment Variables

- `PORT` - Server port (default: 8054)
- `CONFIG_FILE` - Path to config.yaml (default: ../config.yaml)
- `CATALOG_FILE` - Path to catalog.yaml (default: ../catalog.yaml)
- `PROJECT_NAME` - Project name (default: Open Moniker)

### JVM Options

Recommended JVM settings for performance:

```bash
java -XX:+UseZGC \           # Use ZGC for low-latency GC
     -Xms1g \                # Initial heap size
     -Xmx2g \                # Max heap size
     -jar target/resolver-java-0.1.0.jar
```

## Development

### Build

```bash
make build      # Compile
make test       # Run tests
make package    # Build JAR
make clean      # Clean artifacts
```

### Run with Custom Config

```bash
CONFIG_FILE=/path/to/config.yaml PORT=9000 make run-with-config
```

### Add New Endpoints

1. Add method to `ResolverController.java`
2. Use `@GetMapping`, `@PostMapping`, etc.
3. Return `ResponseEntity<?>` for error handling
4. Test with `curl` or `hey`

## Comparison with Go Implementation

### API Parity

All endpoints return **identical JSON** to Go/Python implementations:
- Same field names and types
- Same error response structure: `{"error": "message", "detail": "..."}`
- Same HTTP status codes (404, 403, 400, 500)

### Performance Comparison

Run both resolvers and compare:

```bash
# Start Go resolver (port 8053)
cd resolver-go && make run &

# Start Java resolver (port 8054)
cd resolver-java && make run &

# Benchmark both
hey -n 10000 -c 200 http://localhost:8053/health  # Go
hey -n 10000 -c 200 http://localhost:8054/health  # Java

# Compare responses
curl http://localhost:8053/resolve/prices.equity/AAPL@latest > go.json
curl http://localhost:8054/resolve/prices.equity/AAPL@latest > java.json
diff go.json java.json
```

## Troubleshooting

### Resolver won't start

- Check Java version: `java -version` (must be 21+)
- Check catalog file exists: `ls -la ../catalog.yaml`
- Check port is free: `lsof -i :8054`

### Low throughput

- Verify virtual threads enabled in `application.yaml`
- Check JVM settings (ZGC, heap size)
- Profile with: `java -XX:StartFlightRecording=duration=60s,filename=profile.jfr -jar ...`

### High memory usage

- JVM has higher baseline than Go (~100-150MB vs ~20MB)
- Tune heap: `-Xms512m -Xmx1g` for lower footprint
- Use ZGC for better latency: `-XX:+UseZGC`

## License

Same as parent project.
