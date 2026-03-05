# Telemetry System Documentation

## Overview

The Open Moniker telemetry system provides real-time observability for moniker resolution operations across distributed resolver instances.

## Architecture

### Components

```
┌─────────────────┐
│  Java Resolver  │
│   (Port 8054)   │
└────────┬────────┘
         │
         ├─> UsageEvent → Emitter (non-blocking)
         │                  │
         │                  ├─> BlockingQueue (10,000 events)
         │                  │
         │                  └─> Background Thread
         │                        │
         │                        ├─> Batcher (100 events, 5s flush)
         │                        │
         │                        └─> Sink (Console/SQLite/PostgreSQL)
         │                              │
         │                              ↓
         │                        Database (SQLite/Aurora)
         │                              ↑
         │                              │
┌────────┴────────┐                     │
│  Python Admin   │                     │
│   (Port 8052)   │                     │
└────────┬────────┘                     │
         │                              │
         ├─> Dashboard Routes ──────────┘
         │   (WebSocket + REST)
         │
         └─> Live Dashboard UI (Chart.js)
             http://localhost:8052/dashboard/live-ui
```

### Event Flow

1. **Emission** - Controller → Service → TelemetryHelper.emit()
2. **Queuing** - Non-blocking offer to BlockingQueue
3. **Batching** - Background thread batches 100 events or 5 seconds
4. **Persistence** - Batch insert to database
5. **Query** - Python admin queries for dashboard
6. **Display** - WebSocket pushes to browser every 2 seconds

## Data Model

### UsageEvent

```java
public class UsageEvent {
    // Request tracking
    private String requestId;          // UUID
    private Instant timestamp;          // UTC timestamp

    // Resolver identity
    private String resolverName;        // "us-east-1a", "local-dev"
    private String region;              // "us-east-1", "local"
    private String az;                  // "us-east-1a"

    // Moniker details
    private String moniker;             // Full moniker string
    private String path;                // Path component
    private String namespace;           // Namespace (if any)
    private String version;             // Version (if any)

    // Operation details
    private String sourceType;          // "oracle", "snowflake", etc.
    private Operation operation;        // READ, LIST, DESCRIBE, LINEAGE
    private EventOutcome outcome;       // SUCCESS, NOT_FOUND, ERROR

    // Performance metrics
    private long latencyMs;             // Request duration
    private boolean cacheHit;           // Cache hit flag

    // Result details
    private int statusCode;             // HTTP status code
    private String errorType;           // Error class (if failed)
    private String errorMessage;        // Error message (if failed)

    // Caller information
    private CallerIdentity caller;      // User/app identity

    // Additional metadata
    private Map<String, Object> metadata;
}
```

### Database Schema

```sql
CREATE TABLE access_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    request_id TEXT,
    resolver_id TEXT NOT NULL,
    region TEXT,
    az TEXT,

    moniker TEXT NOT NULL,
    path TEXT,
    namespace TEXT,
    version TEXT,

    source_type TEXT,
    operation TEXT NOT NULL,
    outcome TEXT NOT NULL,

    latency_ms INTEGER NOT NULL,
    cache_hit BOOLEAN DEFAULT FALSE,
    status_code INTEGER,

    error_type TEXT,
    error_message TEXT,
    caller_id TEXT,
    metadata JSONB
);

CREATE INDEX idx_timestamp ON access_log(timestamp);
CREATE INDEX idx_resolver_id ON access_log(resolver_id);
CREATE INDEX idx_outcome ON access_log(outcome);
CREATE INDEX idx_moniker ON access_log(moniker);
```

## Configuration

### Java Resolver (application.yaml)

```yaml
moniker:
  resolver-name: ${RESOLVER_NAME:local-dev}
  region: ${AWS_REGION:local}
  az: ${AWS_AZ:local}

  telemetry:
    enabled: ${TELEMETRY_ENABLED:false}
    sink-type: ${TELEMETRY_SINK_TYPE:console}
    batch-size: ${TELEMETRY_BATCH_SIZE:100}
    flush-interval-seconds: ${TELEMETRY_FLUSH_INTERVAL:5.0}
    max-queue-size: ${TELEMETRY_MAX_QUEUE_SIZE:10000}

    sink-config:
      # SQLite (local development)
      db-path: ${TELEMETRY_DB_PATH:./telemetry.db}

      # PostgreSQL (production)
      host: ${TELEMETRY_DB_HOST:localhost}
      port: ${TELEMETRY_DB_PORT:5432}
      database: ${TELEMETRY_DB_NAME:moniker_telemetry}
      username: ${TELEMETRY_DB_USER:telemetry}
      password: ${TELEMETRY_DB_PASSWORD:}
      pool-size: ${TELEMETRY_DB_POOL_SIZE:10}
```

### Python Admin (environment variables)

```bash
# Database connection
export TELEMETRY_DB_TYPE=sqlite                    # or postgres
export TELEMETRY_DB_PATH=./telemetry.db            # SQLite path
export TELEMETRY_DB_HOST=localhost                 # PostgreSQL host
export TELEMETRY_DB_PORT=5432                      # PostgreSQL port
export TELEMETRY_DB_NAME=moniker_telemetry         # Database name
export TELEMETRY_DB_USER=telemetry                 # Username
export TELEMETRY_DB_PASSWORD=secret                # Password
```

## Sink Types

### 1. Console Sink

**Use Case:** Development, debugging

**Configuration:**
```yaml
telemetry:
  enabled: true
  sink-type: console
```

**Output Format:**
```
[TELEMETRY] 2026-03-05T01:03:59.523Z | local-dev | READ | risk.greeks | 4ms | SUCCESS
```

### 2. SQLite Sink

**Use Case:** Local development, demos

**Configuration:**
```yaml
telemetry:
  enabled: true
  sink-type: sqlite
  sink-config:
    db-path: ./telemetry.db
```

**Features:**
- Auto-creates schema on first use
- Indexes for fast queries
- No external dependencies

### 3. PostgreSQL Sink

**Use Case:** Production, Aurora Serverless v2

**Configuration:**
```yaml
telemetry:
  enabled: true
  sink-type: postgres
  sink-config:
    host: telemetry-db.us-east-1.rds.amazonaws.com
    port: 5432
    database: moniker_telemetry
    username: telemetry
    password: ${DB_PASSWORD}
    pool-size: 10
```

**Features:**
- HikariCP connection pooling
- Batch inserts with transactions
- Retry logic with exponential backoff
- JSONB support for metadata

## Dashboard

### Live Telemetry Dashboard

**URL:** `http://localhost:8052/dashboard`

**Features:**
- Real-time RPS chart (60-point history)
- Real-time p95 latency chart
- Resolver health status (green/yellow/red)
- Top 10 monikers (last hour)
- Error summary (last hour)
- Auto-reconnecting WebSocket

**Update Frequency:**
- WebSocket push: Every 2 seconds
- Top monikers: Every 10 seconds
- Errors: Every 15 seconds

### REST API Endpoints

#### GET /dashboard/api/timeseries

Query historical time-series data.

**Parameters:**
- `metric` - rps, latency_p95 (default: rps)
- `interval` - 10s, 1m, 5m, 1h (default: 1m)
- `hours` - Number of hours to query (default: 1)

**Example:**
```bash
curl "http://localhost:8052/dashboard/api/timeseries?metric=rps&interval=1m&hours=1"
```

**Response:**
```json
[
  {
    "timestamp": "2026-03-05T01:00:00Z",
    "resolver_id": "local-dev",
    "value": 125.5
  },
  ...
]
```

#### GET /dashboard/api/top-monikers

Get top monikers by request count.

**Parameters:**
- `hours` - Hours to query (default: 1)
- `limit` - Max results (default: 10)

**Example:**
```bash
curl "http://localhost:8052/dashboard/api/top-monikers?hours=1&limit=10"
```

**Response:**
```json
[
  {
    "moniker": "risk.greeks",
    "count": 1543,
    "avg_latency_ms": 2.3,
    "success_rate": 99.8
  },
  ...
]
```

#### GET /dashboard/api/errors

Get error summary.

**Parameters:**
- `hours` - Hours to query (default: 1)

**Example:**
```bash
curl "http://localhost:8052/dashboard/api/errors?hours=1"
```

**Response:**
```json
[
  {
    "error_type": "ParseError",
    "count": 23,
    "affected_monikers": ["invalid/path", "bad@version"]
  },
  ...
]
```

#### WebSocket /dashboard/live

Real-time telemetry stream.

**Connect:**
```javascript
const ws = new WebSocket('ws://localhost:8052/dashboard/live');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data.resolvers);  // Array of resolver metrics
};
```

**Message Format:**
```json
{
  "timestamp": "2026-03-05T01:04:30.123Z",
  "resolvers": [
    {
      "resolver_id": "local-dev",
      "region": "local",
      "requests": 127,
      "rps": 12.7,
      "avg_latency_ms": 2.1,
      "p95_latency_ms": 4.3,
      "errors": 0,
      "cache_hits": 54
    }
  ]
}
```

## Performance Tuning

### Batch Size

**Default:** 100 events

**Tuning:**
- **Small (10-50):** Low latency, more DB writes
- **Medium (100-500):** Balanced
- **Large (1000+):** High throughput, higher memory

```yaml
telemetry:
  batch-size: 100
```

### Flush Interval

**Default:** 5 seconds

**Tuning:**
- **Fast (1-2s):** Near real-time, more DB load
- **Medium (5-10s):** Balanced
- **Slow (30-60s):** Lower DB load, delayed visibility

```yaml
telemetry:
  flush-interval-seconds: 5.0
```

### Queue Size

**Default:** 10,000 events

**Tuning:**
- **Small (1,000):** Low memory, may drop events under load
- **Medium (10,000):** Balanced
- **Large (100,000):** High memory, handles spikes

```yaml
telemetry:
  max-queue-size: 10000
```

### Connection Pool

**Default:** 10 connections

**Tuning:**
- **Small (5-10):** Low overhead, may bottleneck
- **Medium (10-20):** Balanced
- **Large (50+):** High throughput, more overhead

```yaml
telemetry:
  sink-config:
    pool-size: 10
```

## Monitoring

### Metrics to Track

1. **Drop Rate** - Events dropped due to full queue
2. **Batch Flush Time** - Time to write batch to database
3. **Queue Depth** - Current queue size
4. **Database Connection Pool** - Active/idle connections

### Java Logging

```java
// Enable debug logging
logging.level.com.ganizanisitara.moniker.resolver.telemetry=DEBUG
```

### Database Queries

```sql
-- Event rate by minute
SELECT
  date_trunc('minute', timestamp) AS minute,
  COUNT(*) AS events
FROM access_log
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY minute
ORDER BY minute;

-- Top monikers
SELECT
  moniker,
  COUNT(*) AS count,
  AVG(latency_ms) AS avg_latency,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency
FROM access_log
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY moniker
ORDER BY count DESC
LIMIT 10;

-- Error rate
SELECT
  outcome,
  COUNT(*) AS count,
  COUNT(*) * 100.0 / SUM(COUNT(*)) OVER () AS percentage
FROM access_log
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY outcome;
```

## Best Practices

1. **Use Appropriate Sink**
   - Console: Development only
   - SQLite: Local demos, single instance
   - PostgreSQL: Production, multi-instance

2. **Tune Batch Settings**
   - High RPS (>1000): Large batches (500-1000)
   - Medium RPS (100-1000): Default (100)
   - Low RPS (<100): Small batches (10-50)

3. **Monitor Queue Depth**
   - Alert if queue >80% full
   - Scale resolvers or increase batch size

4. **Database Retention**
   - SQLite: 7-30 days (disk space limited)
   - PostgreSQL: 84 months with partitioning (see schema.sql)

5. **Dashboard Performance**
   - WebSocket: Max 100 concurrent clients
   - REST API: Cache responses for 5-10 seconds

## Troubleshooting

### High Drop Rate

**Symptoms:** `dropCounter` increasing in logs

**Causes:**
- Queue too small
- Database writes too slow
- Batch size too small

**Solutions:**
- Increase `max-queue-size`
- Increase `batch-size`
- Add database indexes
- Scale database (more IOPS)

### High Latency

**Symptoms:** p95 latency >50ms

**Causes:**
- Database connection pool exhausted
- Large batches blocking

**Solutions:**
- Increase `pool-size`
- Decrease `batch-size`
- Use faster disk (SSD)

### Events Not Appearing

**Symptoms:** Dashboard shows no data

**Causes:**
- Telemetry disabled
- Wrong database configured
- WebSocket not connecting

**Solutions:**
```bash
# Check telemetry enabled
grep "Telemetry.*enabled" dev-java.log

# Check sink type
grep "Creating telemetry sink" dev-java.log

# Test database
sqlite3 dev/telemetry.db "SELECT COUNT(*) FROM access_log;"

# Test WebSocket
wscat -c ws://localhost:8052/dashboard/live
```

## Future Enhancements

- [ ] Prometheus metrics endpoint
- [ ] Distributed tracing (OpenTelemetry)
- [ ] Grafana dashboard templates
- [ ] Alert rules (error rate, latency)
- [ ] Data retention policies
- [ ] Event sampling (high RPS environments)
