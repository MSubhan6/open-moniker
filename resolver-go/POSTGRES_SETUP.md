# PostgreSQL Telemetry Sink - Setup Guide

## Overview

The PostgreSQL sink provides **queryable, scalable audit storage** for telemetry events. Perfect for:

- ✅ **Compliance auditing** (BCBS 239 - 7 year retention)
- ✅ **Chargeback/billing** (team usage reports)
- ✅ **Security analysis** (unauthorized access tracking)
- ✅ **Performance analytics** (latency trends, slow queries)
- ✅ **Deprecation tracking** (who's using old monikers)

## Quick Start (Docker)

### 1. Start PostgreSQL

```bash
cd /home/user/open-moniker-svc/resolver-go

# Start PostgreSQL (initializes schema automatically)
docker-compose up -d

# Check logs
docker-compose logs -f postgres
```

**What this does:**
- Starts PostgreSQL 16 on port 5432
- Creates database: `moniker_telemetry`
- Runs `schema.sql` to create tables, indexes, partitions
- Creates partitions for current month + next 3 months
- Optimizes settings for write-heavy workload

### 2. Configure Resolver

Edit `config.yaml`:

```yaml
telemetry:
  enabled: true
  sink_type: postgres
  sink_config:
    connection_string: "postgres://telemetry:telemetry_dev_password@localhost:5432/moniker_telemetry?sslmode=disable"
  batch_size: 1000
  flush_interval_seconds: 0.15
  max_queue_size: 10240
```

### 3. Run Resolver

```bash
cd /home/user/open-moniker-svc/resolver-go
make tidy && make build
./bin/resolver --config ../config.yaml --port 8053
```

You should see:
```
Telemetry enabled: sink=postgres, batch_size=1000, flush_interval=0.150s
```

### 4. Make Requests

```bash
# Generate some telemetry data
for i in {1..100}; do
  curl -s http://localhost:8053/resolve/benchmarks/SP500@latest > /dev/null
done
```

### 5. Query Telemetry

```bash
# Connect to database
docker-compose exec postgres psql -U telemetry -d moniker_telemetry

# Count events
SELECT COUNT(*) FROM telemetry_events;

# Recent events
SELECT timestamp, moniker_path, outcome, latency_ms
FROM telemetry_events
ORDER BY timestamp DESC
LIMIT 10;
```

## Production Setup

### Option 1: Self-Hosted PostgreSQL

**System Requirements:**
- PostgreSQL 14+ (16 recommended)
- 4 CPU cores minimum
- 8GB RAM minimum
- Fast SSD storage (NVMe preferred)
- Dedicated partition for PostgreSQL data

**Installation (Ubuntu/Debian):**

```bash
# Install PostgreSQL 16
sudo apt update
sudo apt install postgresql-16 postgresql-contrib-16

# Create user and database
sudo -u postgres psql << EOF
CREATE USER telemetry WITH PASSWORD 'STRONG_PASSWORD_HERE';
CREATE DATABASE moniker_telemetry OWNER telemetry;
\c moniker_telemetry
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
EOF

# Load schema
sudo -u postgres psql -d moniker_telemetry -f schema.sql

# Tune PostgreSQL
sudo nano /etc/postgresql/16/main/postgresql.conf
```

**PostgreSQL Tuning (for 21K events/sec):**

```ini
# Memory
shared_buffers = 2GB                    # 25% of RAM
effective_cache_size = 6GB              # 75% of RAM
work_mem = 16MB
maintenance_work_mem = 512MB

# Connections
max_connections = 200

# Write-Ahead Log
wal_buffers = 16MB
min_wal_size = 1GB
max_wal_size = 4GB
checkpoint_timeout = 15min
checkpoint_completion_target = 0.9

# Planner
random_page_cost = 1.1                  # For SSD
effective_io_concurrency = 200

# Parallelism
max_worker_processes = 4
max_parallel_workers_per_gather = 2
max_parallel_workers = 4
```

Restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

### Option 2: AWS RDS Aurora PostgreSQL

**Why Aurora:**
- ✅ Managed service (automatic backups, patching)
- ✅ Auto-scaling storage (grows as needed)
- ✅ Read replicas for analytics (offload heavy queries)
- ✅ Point-in-time recovery
- ✅ High availability (Multi-AZ)

**Setup Steps:**

1. **Create Aurora PostgreSQL Cluster**
   - Engine: Aurora PostgreSQL 16.x
   - Instance class: `db.r6g.large` (2 vCPU, 16 GB RAM) - minimum
   - Storage: Auto-scaling from 10GB
   - Multi-AZ: Yes (for production)
   - VPC: Same as resolver service

2. **Create Database and User**

   ```sql
   CREATE USER telemetry WITH PASSWORD 'STRONG_PASSWORD_HERE';
   CREATE DATABASE moniker_telemetry OWNER telemetry;
   \c moniker_telemetry
   CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
   ```

3. **Load Schema**

   ```bash
   psql -h your-cluster.cluster-xxx.us-east-1.rds.amazonaws.com \
        -U postgres -d moniker_telemetry -f schema.sql
   ```

4. **Configure Resolver**

   ```yaml
   telemetry:
     enabled: true
     sink_type: postgres
     sink_config:
       host: your-cluster.cluster-xxx.us-east-1.rds.amazonaws.com
       port: 5432
       database: moniker_telemetry
       user: telemetry
       password: ${TELEMETRY_DB_PASSWORD}  # From AWS Secrets Manager
       sslmode: require
   ```

5. **Create Read Replica (Optional)**

   For heavy analytics queries, create a read replica:
   - Offloads SELECT queries from primary
   - Use for Grafana dashboards, BI tools
   - Connect analytics tools to read replica endpoint

**Cost Estimate (us-east-1):**
- `db.r6g.large`: ~$150/month
- Storage (100GB): ~$10/month
- Backups (100GB): ~$10/month
- **Total**: ~$170/month

### Option 3: Managed PostgreSQL (Other Providers)

**Google Cloud SQL:**
- Similar to RDS Aurora
- ~$200/month for comparable setup

**Azure Database for PostgreSQL:**
- Flexible Server tier
- ~$180/month for comparable setup

**DigitalOcean Managed PostgreSQL:**
- Cheaper option: ~$60/month (2 vCPU, 4GB RAM)
- Good for small-medium deployments

## Schema Overview

### Main Table: `telemetry_events`

**Partitioning Strategy:**
- Monthly partitions (e.g., `telemetry_events_2026_02`)
- Automatic partition creation via function
- Automatic retention (drop partitions > 7 years)

**Indexes:**
- `timestamp` (DESC) - Recent queries
- `user_id`, `team` - Access audit
- `moniker_path` - Moniker usage
- `outcome` - Error analysis
- `owner_at_access` - Data ownership
- `deprecated` - Deprecation tracking
- `metadata` (GIN) - JSONB queries

### Views (Pre-built Reports)

1. **`recent_telemetry_events`** - Last 7 days
2. **`team_usage_stats`** - Daily usage by team
3. **`deprecated_moniker_usage`** - Deprecation tracking
4. **`top_monikers`** - Most accessed monikers

## Common Queries

See `queries.sql` for 23+ pre-built queries:

```bash
# Run all queries
psql -U telemetry -d moniker_telemetry -f queries.sql

# Or run individual queries
psql -U telemetry -d moniker_telemetry

# Top monikers
SELECT * FROM top_monikers LIMIT 10;

# Team usage
SELECT * FROM team_usage_stats WHERE team = 'team:market-data';

# Deprecated monikers
SELECT * FROM deprecated_moniker_usage;
```

## Maintenance

### Monthly Partition Creation

**Automatic (recommended):**

Set up cron job:
```bash
# /etc/cron.d/telemetry-partitions
0 0 1 * * postgres psql -d moniker_telemetry -c "SELECT create_telemetry_partition(CURRENT_DATE + INTERVAL '1 month');"
```

**Manual:**
```sql
SELECT create_telemetry_partition('2026-04-01');
```

### Retention Management (7 Years for BCBS 239)

**Automatic:**
```bash
# /etc/cron.d/telemetry-retention
0 2 1 * * postgres psql -d moniker_telemetry -c "SELECT drop_old_telemetry_partitions(84);"
```

**Manual:**
```sql
-- Drop partitions older than 84 months (7 years)
SELECT drop_old_telemetry_partitions(84);
```

### Statistics Update

Run weekly:
```bash
# /etc/cron.d/telemetry-analyze
0 3 * * 0 postgres psql -d moniker_telemetry -c "ANALYZE telemetry_events;"
```

### Backup

**PostgreSQL dump:**
```bash
# Full database
pg_dump -U telemetry moniker_telemetry | gzip > telemetry_backup_$(date +%Y%m%d).sql.gz

# Schema only
pg_dump -U telemetry -s moniker_telemetry > schema_backup.sql
```

**RDS Aurora:**
- Automatic daily snapshots (enabled by default)
- Point-in-time recovery (5-minute intervals)
- Manual snapshots before major changes

## Performance

### Expected Performance

At **21K events/sec** with batching (1000 events/batch):

- **Inserts**: 21 batches/sec × 1000 events = 21K events/sec ✅
- **Disk I/O**: ~3 MB/sec (compressed)
- **Storage growth**: ~250 GB/month (1.8B events × ~150 bytes/event)
- **Query performance**: Milliseconds for recent data, seconds for full scans

### Monitoring Queries

**Table size:**
```sql
SELECT pg_size_pretty(pg_database_size('moniker_telemetry'));
```

**Partition sizes:**
```sql
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size('public.' || tablename)) as size
FROM pg_tables
WHERE tablename LIKE 'telemetry_events_%'
ORDER BY tablename DESC;
```

**Index usage:**
```sql
SELECT
    indexname,
    idx_scan as times_used,
    pg_size_pretty(pg_relation_size(indexrelid)) as size
FROM pg_stat_user_indexes
WHERE tablename LIKE 'telemetry_events%'
ORDER BY idx_scan DESC;
```

**Slow queries:** (requires `pg_stat_statements`)
```sql
SELECT
    calls,
    round(mean_exec_time::numeric, 2) as avg_ms,
    query
FROM pg_stat_statements
WHERE query LIKE '%telemetry_events%'
ORDER BY mean_exec_time DESC
LIMIT 10;
```

## Troubleshooting

### Connection Errors

**Error**: `connection refused`

**Fix**:
```bash
# Check PostgreSQL is running
docker-compose ps
# or
sudo systemctl status postgresql

# Check port is open
netstat -tlnp | grep 5432

# Check firewall
sudo ufw status
```

**Error**: `password authentication failed`

**Fix**:
```bash
# Reset password
docker-compose exec postgres psql -U postgres -c "ALTER USER telemetry PASSWORD 'new_password';"

# Update config.yaml with new password
```

### Write Performance Issues

**Symptom**: High latency, queue backing up

**Diagnosis**:
```sql
-- Check for locks
SELECT * FROM pg_locks WHERE NOT granted;

-- Check active queries
SELECT pid, usename, state, query
FROM pg_stat_activity
WHERE state = 'active';
```

**Fix**:
1. Increase `batch_size` in config (e.g., 2000)
2. Decrease `flush_interval_seconds` (e.g., 0.1)
3. Add more worker processes in PostgreSQL
4. Scale up instance (more CPU/RAM)

### Partition Issues

**Error**: `no partition of relation "telemetry_events" found for row`

**Cause**: Missing partition for current month

**Fix**:
```sql
-- Create missing partition
SELECT create_telemetry_partition(CURRENT_DATE);

-- Verify
SELECT tablename FROM pg_tables WHERE tablename LIKE 'telemetry_events_%' ORDER BY tablename;
```

## Security

### Access Control

**Read-only auditor role:**
```sql
CREATE ROLE auditor;
GRANT SELECT ON telemetry_events TO auditor;
GRANT SELECT ON recent_telemetry_events TO auditor;
GRANT SELECT ON team_usage_stats TO auditor;

CREATE USER alice WITH PASSWORD 'password';
GRANT auditor TO alice;
```

**Billing role:**
```sql
CREATE ROLE billing;
GRANT SELECT ON team_usage_stats TO billing;

CREATE USER billing_app WITH PASSWORD 'password';
GRANT billing TO billing_app;
```

### Encryption

**At rest:**
- RDS Aurora: Enable encryption (AES-256)
- Self-hosted: Use LUKS disk encryption

**In transit:**
- Always use `sslmode=require` in production
- Use `sslmode=verify-full` with proper CA certificates

**Connection string:**
```yaml
sink_config:
  connection_string: "postgres://telemetry:password@host:5432/db?sslmode=require"
```

## Integrations

### Grafana Dashboards

1. Install Grafana: `docker-compose --profile monitoring up -d`
2. Access: http://localhost:3000 (admin/admin)
3. Add PostgreSQL data source:
   - Host: `postgres:5432`
   - Database: `moniker_telemetry`
   - User: `telemetry`
   - SSL Mode: disable (for local)

4. Create dashboards:
   - Request volume over time
   - Latency percentiles
   - Error rates
   - Team usage

### BI Tools (Metabase, Tableau, etc.)

Connect using JDBC:
```
jdbc:postgresql://host:5432/moniker_telemetry
```

### Python Analytics

```python
import psycopg2
import pandas as pd

conn = psycopg2.connect(
    host="localhost",
    database="moniker_telemetry",
    user="telemetry",
    password="password"
)

# Load data into pandas
df = pd.read_sql("""
    SELECT timestamp, moniker_path, latency_ms
    FROM telemetry_events
    WHERE timestamp > NOW() - INTERVAL '7 days'
""", conn)

# Analyze
print(df.describe())
```

## Next Steps

1. **Set up monitoring**: Grafana + Prometheus
2. **Configure alerts**: High error rates, slow queries
3. **Set up backups**: Automated daily snapshots
4. **Document queries**: Team-specific audit queries
5. **Implement retention**: Automated partition cleanup

For questions or issues, see `queries.sql` for troubleshooting queries.
