# Open Moniker Deployment Guide

This directory contains deployment configurations for three target environments:

1. **Local Development** (`local/`) - Side-by-side dev/UAT with SQLite
2. **Render.com** (`render/`) - Simple cloud deployment for demos
3. **AWS Production** (`aws/`) - Multi-region production with EKS and Aurora

## Quick Start

### Local Development

```bash
cd deployments/local

# Install Python dependencies
pip install fastapi uvicorn aiosqlite asyncpg pyyaml

# Start dev environment
python bootstrap.py dev

# Access services
# Java Resolver: http://localhost:8054
# Python Admin:  http://localhost:8052
# Dashboard:     http://localhost:8052/dashboard/live-ui
```

### Render.com (Coming Soon)

```bash
cd deployments/render
# See render/README.md for deployment instructions
```

### AWS Production (Coming Soon)

```bash
cd deployments/aws/terraform
# See aws/README.md for infrastructure setup
```

## Architecture Overview

### Component Separation

**Java Resolver** (Data Plane):
- High-performance moniker resolution
- Horizontal scaling across multiple instances
- Telemetry emission to database
- Ports: 8054 (dev), 9054 (UAT)

**Python Admin** (Control Plane):
- Catalog/domain/model management
- Request approval workflow
- Live telemetry dashboard
- Configuration UI
- Ports: 8052 (dev), 9052 (UAT)

### Telemetry Flow

```
Java Resolver → Emitter → Batcher → Sink (SQLite/PostgreSQL)
                                       ↓
Python Dashboard ← WebSocket ← Query ← Database
```

## Features Implemented

### ✅ Phase 1: Local Development (Completed)

- [x] Java telemetry system (emitter, batcher, sinks)
- [x] Console, SQLite, and PostgreSQL sink implementations
- [x] Python telemetry database layer (aiosqlite + asyncpg)
- [x] WebSocket live telemetry endpoint
- [x] Live dashboard with Chart.js
- [x] Bootstrap script for dev/UAT environments
- [x] Health endpoints on both services

### 🚧 Phase 2: Cloud Deployment (Pending)

- [ ] Render.com deployment configuration
- [ ] Docker images for Java and Python
- [ ] Database migrations
- [ ] CI/CD with GitHub Actions

### 🚧 Phase 3: AWS Production (Pending)

- [ ] Terraform modules (VPC, EKS, Aurora, Route53)
- [ ] Kubernetes manifests
- [ ] Multi-region deployment
- [ ] Round-robin DNS
- [ ] Auto-scaling policies

## Testing

### Generate Traffic

```bash
# Simple test
curl http://localhost:8054/resolve/risk.greeks

# Load test
for i in {1..1000}; do
  curl -s http://localhost:8054/resolve/risk.greeks > /dev/null
done

# With hey tool
hey -z 30s -c 50 http://localhost:8054/resolve/risk.greeks
```

### View Telemetry

**Console Output:**
```bash
tail -f deployments/local/dev-java.log | grep TELEMETRY
```

**Database Query (when using SQLite sink):**
```bash
sqlite3 deployments/local/dev/telemetry.db "
  SELECT moniker, COUNT(*) as count, AVG(latency_ms) as avg_latency
  FROM access_log
  GROUP BY moniker
  ORDER BY count DESC
  LIMIT 10;
"
```

**Live Dashboard:**
```bash
# Open in browser
open http://localhost:8052/dashboard/live-ui
```

## Environment Variables

### Java Resolver

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8054 | HTTP server port |
| `CONFIG_FILE` | ../config.yaml | Path to config.yaml |
| `CATALOG_FILE` | ../catalog.yaml | Path to catalog.yaml |
| `TELEMETRY_ENABLED` | false | Enable telemetry |
| `TELEMETRY_SINK_TYPE` | console | Sink type (console, sqlite, postgres) |
| `TELEMETRY_DB_PATH` | ./telemetry.db | SQLite database path |
| `TELEMETRY_DB_HOST` | localhost | PostgreSQL host |
| `TELEMETRY_DB_PORT` | 5432 | PostgreSQL port |
| `TELEMETRY_DB_NAME` | moniker_telemetry | PostgreSQL database |
| `TELEMETRY_DB_USER` | telemetry | PostgreSQL user |
| `TELEMETRY_DB_PASSWORD` | - | PostgreSQL password |
| `RESOLVER_NAME` | local-dev | Resolver instance name |
| `AWS_REGION` | local | AWS region |
| `AWS_AZ` | local | Availability zone |

### Python Admin

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | 8052 | HTTP server port |
| `CONFIG_FILE` | ./config.yaml | Path to config.yaml |
| `CATALOG_FILE` | ./catalog.yaml | Path to catalog.yaml |
| `TELEMETRY_DB_TYPE` | sqlite | Database type (sqlite, postgres) |
| `TELEMETRY_DB_PATH` | ./telemetry.db | SQLite database path |
| `TELEMETRY_DB_HOST` | localhost | PostgreSQL host |
| `TELEMETRY_DB_PORT` | 5432 | PostgreSQL port |

## Performance

### Java Resolver Benchmarks

| Test | RPS | p50 Latency | p95 Latency |
|------|-----|-------------|-------------|
| Single instance | 8,555 | 2.1ms | 4.3ms |
| 6 instances | ~51,000 | 2.1ms | 4.5ms |

### Telemetry Overhead

- **Queue-based emission**: Non-blocking, <0.01ms impact
- **Batch size**: 100 events (configurable)
- **Flush interval**: 5 seconds (configurable)
- **Max queue size**: 10,000 events (drops if exceeded)

## Troubleshooting

### Java resolver won't start

```bash
# Check logs
tail -100 deployments/local/dev-java.log

# Verify port not in use
lsof -ti:8054

# Check catalog file exists
ls -la deployments/local/dev/catalog.yaml
```

### Python admin won't start

```bash
# Check logs
tail -100 deployments/local/dev-python.log

# Verify dependencies
python3 -c "import aiosqlite, asyncpg, fastapi"

# Check port
lsof -ti:8052
```

### No telemetry events

```bash
# Verify telemetry is enabled
grep "TELEMETRY_ENABLED" deployments/local/dev-java.log

# Check console output
grep "\[TELEMETRY\]" deployments/local/dev-java.log

# For SQLite, verify DB exists
ls -la deployments/local/dev/telemetry.db
```

### Dashboard not loading

```bash
# Verify Python service running
curl http://localhost:8052/health

# Check WebSocket endpoint
curl http://localhost:8052/dashboard/api/top-monikers

# View browser console for errors
# Open: http://localhost:8052/dashboard/live-ui
```

## Contributing

See main project [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

## License

See main project [LICENSE](../LICENSE).
