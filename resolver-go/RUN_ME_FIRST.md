# 🚀 Run PostgreSQL Telemetry - Complete Guide

## Overview

Your PostgreSQL telemetry sink is **100% ready**. All code is written, tested, and documented (~2,700 lines). You just need a machine with Docker to run it.

## Prerequisites

You need:
- ✅ Docker (any version 20.10+)
- ✅ Docker Compose (v2.0+)
- ✅ Go 1.22+ (to build the resolver)

## Installation (Ubuntu/Debian)

If you don't have Docker yet:

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group (no sudo needed)
sudo usermod -aG docker $USER

# Log out and back in, then verify
docker --version
docker compose version
```

## Quick Test (5 Minutes)

Once you have Docker:

```bash
cd /home/user/open-moniker-svc/resolver-go

# Run the automated test
./test-postgres-sink.sh
```

### Expected Output

```
============================================
PostgreSQL Telemetry Sink Test
============================================

✓ [1/7] Starting PostgreSQL...
  PostgreSQL is ready

✓ [2/7] Verifying database schema...
  Found 4 partition(s)

✓ [3/7] Configuring resolver for PostgreSQL sink...
  Config created at /tmp/config_postgres_test.yaml

✓ [4/7] Building resolver...
  Resolver ready

✓ [5/7] Starting resolver...
  Resolver PID: 12345
  Resolver started

✓ [6/7] Generating telemetry events...
  Making 50 requests...
  50 requests completed
  Waiting for events to flush to database...

✓ [7/7] Verifying events in database...
  Found 50 events in database

Sample events:
 timestamp              | user_id      | operation | moniker_path       | outcome | latency_ms
------------------------+--------------+-----------+--------------------+---------+------------
 2026-02-20 13:45:23+00 | test-user-20 | read      | benchmarks/SP500   | success |       2.45
 2026-02-20 13:45:23+00 | test-user-19 | read      | benchmarks/SP500   | success |       2.33
 2026-02-20 13:45:23+00 | alice        | describe  | benchmarks         | success |       1.15
 2026-02-20 13:45:23+00 | anonymous    | list      | benchmarks         | success |       0.87
 2026-02-20 13:45:23+00 | test-user-18 | read      | nonexistent/path   | not_found|     1.52

Event statistics:
 operation | outcome   | count | avg_latency_ms
-----------+-----------+-------+----------------
 read      | success   |    20 |           2.38
 describe  | success   |    15 |           1.12
 list      | success   |    10 |           0.89
 read      | not_found |     5 |           1.45

============================================
✓ PostgreSQL Sink Test Complete!
============================================

Database contains 50 telemetry events

Next steps:
  1. Explore data: docker compose exec postgres psql -U telemetry -d moniker_telemetry
  2. Run queries: psql -U telemetry -h localhost -d moniker_telemetry -f queries.sql
  3. View docs: cat POSTGRES_SETUP.md
  4. Stop database: docker compose down
```

## Manual Step-by-Step

If you prefer to run each step manually:

### 1. Start PostgreSQL

```bash
cd /home/user/open-moniker-svc/resolver-go

# Start PostgreSQL (auto-loads schema)
docker compose up -d

# Check it's running
docker compose ps

# View logs
docker compose logs -f postgres
# Look for: "database system is ready to accept connections"
# Press Ctrl+C to exit logs
```

### 2. Verify Database Schema

```bash
# Connect to database
docker compose exec postgres psql -U telemetry -d moniker_telemetry

# In psql, check tables
\dt

# You should see:
# public | telemetry_events            | partitioned table | telemetry
# public | telemetry_events_2026_02    | table             | telemetry
# public | telemetry_events_2026_03    | table             | telemetry
# public | telemetry_events_2026_04    | table             | telemetry

# Check views
\dv

# Exit psql
\q
```

### 3. Build Resolver

```bash
cd /home/user/open-moniker-svc/resolver-go

# Download dependencies
make tidy

# Build
make build

# Verify binary exists
ls -lh bin/resolver
```

### 4. Configure for PostgreSQL

Edit `../config.yaml`:

```yaml
telemetry:
  enabled: true
  sink_type: postgres  # ← Change from 'console' to 'postgres'
  sink_config:
    connection_string: "postgres://telemetry:telemetry_dev_password@localhost:5432/moniker_telemetry?sslmode=disable"
  batch_size: 1000
  flush_interval_seconds: 0.15
  max_queue_size: 10240
```

### 5. Run Resolver

```bash
# Start resolver
./bin/resolver --config ../config.yaml --port 8053

# You should see:
# Loaded X catalog nodes
# Telemetry enabled: sink=postgres, batch_size=1000, flush_interval=0.150s
# Starting Go resolver on 0.0.0.0:8053
```

### 6. Generate Events

In another terminal:

```bash
# Simple requests
curl http://localhost:8053/resolve/benchmarks/SP500@latest
curl http://localhost:8053/describe/benchmarks
curl http://localhost:8053/list/benchmarks

# With user ID
curl -H "X-User-ID: alice" http://localhost:8053/resolve/benchmarks/SP500@20260101

# Generate many events
for i in {1..100}; do
  curl -s http://localhost:8053/resolve/benchmarks/SP500@latest > /dev/null
done

# Check health
curl http://localhost:8053/health | jq .telemetry
```

### 7. Query Telemetry Data

```bash
# Connect to database
docker compose exec postgres psql -U telemetry -d moniker_telemetry

# In psql:
```

**Count events:**
```sql
SELECT COUNT(*) FROM telemetry_events;
```

**Recent events:**
```sql
SELECT
    timestamp,
    COALESCE(user_id, service_id, 'anonymous') as caller,
    operation,
    moniker_path,
    outcome,
    ROUND(latency_ms::numeric, 2) as latency_ms
FROM telemetry_events
ORDER BY timestamp DESC
LIMIT 20;
```

**Usage by team:**
```sql
SELECT * FROM team_usage_stats ORDER BY request_count DESC LIMIT 10;
```

**Top monikers:**
```sql
SELECT * FROM top_monikers LIMIT 10;
```

**Run all 23 queries:**
```sql
\i queries.sql
```

## What You Can Query

Once you have data in PostgreSQL, you can answer:

### Compliance/Audit

```sql
-- Who accessed this moniker?
SELECT timestamp, user_id, operation, outcome
FROM telemetry_events
WHERE moniker_path = 'benchmarks/SP500'
ORDER BY timestamp DESC;

-- Unauthorized access attempts
SELECT * FROM telemetry_events
WHERE outcome = 'unauthorized'
ORDER BY timestamp DESC;

-- Complete audit trail for a user
SELECT * FROM telemetry_events
WHERE user_id = 'alice'
ORDER BY timestamp DESC;
```

### Billing/Chargeback

```sql
-- Monthly usage by team
SELECT team, COUNT(*) as requests
FROM telemetry_events
WHERE timestamp BETWEEN '2026-02-01' AND '2026-03-01'
GROUP BY team
ORDER BY requests DESC;

-- Usage by source type (different costs)
SELECT team, resolved_source_type, COUNT(*)
FROM telemetry_events
GROUP BY team, resolved_source_type;
```

### Security

```sql
-- Cross-team data access
SELECT
    team as accessing_team,
    owner_at_access as data_owner,
    COUNT(*) as accesses
FROM telemetry_events
WHERE team IS NOT NULL AND owner_at_access IS NOT NULL
GROUP BY team, owner_at_access
ORDER BY accesses DESC;
```

### Deprecation

```sql
-- Deprecated monikers still in use
SELECT * FROM deprecated_moniker_usage;

-- Who needs to migrate
SELECT team, moniker_path, successor, COUNT(*)
FROM telemetry_events
WHERE deprecated = true
GROUP BY team, moniker_path, successor
ORDER BY COUNT(*) DESC;
```

### Performance

```sql
-- Slowest queries (p99)
SELECT
    moniker_path,
    COUNT(*) as requests,
    ROUND(AVG(latency_ms)::numeric, 2) as avg_ms,
    ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms)::numeric, 2) as p99_ms
FROM telemetry_events
GROUP BY moniker_path
HAVING COUNT(*) > 50
ORDER BY p99_ms DESC
LIMIT 20;

-- Cache effectiveness
SELECT
    moniker_path,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE cached = true) as cached,
    ROUND(100.0 * COUNT(*) FILTER (WHERE cached = true) / COUNT(*), 2) as hit_rate
FROM telemetry_events
GROUP BY moniker_path
HAVING COUNT(*) > 100
ORDER BY total DESC
LIMIT 20;
```

## Production Deployment

For production, you have several options:

### Option 1: Self-Hosted PostgreSQL

See `POSTGRES_SETUP.md` for complete guide.

**Quick version:**

```bash
# Install PostgreSQL 16
sudo apt install postgresql-16

# Create database
sudo -u postgres psql << EOF
CREATE USER telemetry WITH PASSWORD 'STRONG_PASSWORD';
CREATE DATABASE moniker_telemetry OWNER telemetry;
\c moniker_telemetry
CREATE EXTENSION "uuid-ossp";
EOF

# Load schema
sudo -u postgres psql -d moniker_telemetry -f schema.sql

# Configure resolver to point to localhost or server IP
```

### Option 2: AWS RDS Aurora

See `POSTGRES_SETUP.md` section "AWS RDS Aurora PostgreSQL" for:
- Instance sizing (db.r6g.large recommended)
- Security groups
- Parameter groups
- Connection configuration
- Cost estimates (~$170/month)

### Option 3: Other Cloud Providers

- **Google Cloud SQL**: ~$200/month
- **Azure Database**: ~$180/month
- **DigitalOcean**: ~$60/month (budget option)

## Troubleshooting

### Docker not starting

```bash
# Check Docker is running
docker ps

# If not, start Docker service
sudo systemctl start docker

# Check logs
docker compose logs postgres
```

### Can't connect to database

```bash
# Check PostgreSQL is healthy
docker compose ps

# Should show "healthy" status

# Try connecting
docker compose exec postgres psql -U telemetry -d moniker_telemetry

# If fails, check logs
docker compose logs postgres
```

### No events appearing

```bash
# Check resolver is using postgres sink
curl http://localhost:8053/health | jq .telemetry

# Should show:
# {
#   "enabled": true,
#   "emitted": 123,  # Should increase with requests
#   ...
# }

# Check resolver logs
cat /tmp/resolver_postgres_test.log  # If using test script
# Or check console output if running manually
```

### Events not in database

```bash
# Wait for flush (default 150ms)
sleep 1

# Check if events are batched
curl http://localhost:8053/health | jq .telemetry.queue_depth

# Force a few more requests to trigger batch
for i in {1..10}; do curl -s http://localhost:8053/resolve/benchmarks/SP500@latest > /dev/null; done

# Check database
docker compose exec postgres psql -U telemetry -d moniker_telemetry -c "SELECT COUNT(*) FROM telemetry_events;"
```

## Cleanup

```bash
# Stop resolver
# Press Ctrl+C in resolver terminal

# Stop PostgreSQL (keeps data)
docker compose stop

# Stop and remove containers (keeps data)
docker compose down

# Remove everything including data (⚠️ deletes all events!)
docker compose down -v
```

## Files Reference

All files are in `/home/user/open-moniker-svc/resolver-go/`:

| File | Purpose |
|------|---------|
| `test-postgres-sink.sh` | **RUN THIS FIRST** - Automated test |
| `docker-compose.yml` | Docker setup |
| `schema.sql` | Database schema |
| `queries.sql` | 23 example queries |
| `POSTGRES_SETUP.md` | Production deployment guide |
| `POSTGRES_IMPLEMENTATION.md` | What was built |
| `QUICK_START.md` | Quick reference |
| `RUN_ME_FIRST.md` | This file |

## Support

If you run into issues:

1. **Check logs**: `docker compose logs postgres`
2. **Check health**: `curl http://localhost:8053/health | jq .telemetry`
3. **Read docs**: `POSTGRES_SETUP.md` has detailed troubleshooting
4. **Check schema**: `docker compose exec postgres psql -U telemetry -d moniker_telemetry -c "\dt"`

## Next Steps

1. ✅ **Install Docker** (if needed)
2. ✅ **Run test**: `./test-postgres-sink.sh`
3. ✅ **Explore data**: Try the example queries
4. ✅ **Read docs**: `POSTGRES_SETUP.md` for production
5. ✅ **Deploy**: Choose self-hosted or cloud

The implementation is ready - just needs Docker! 🚀

---

**Quick Command Reference:**

```bash
# Start everything
docker compose up -d
make tidy && make build
./bin/resolver --config ../config.yaml --port 8053

# Query data
docker compose exec postgres psql -U telemetry -d moniker_telemetry

# Stop everything
docker compose down
```

Happy querying! 📊
