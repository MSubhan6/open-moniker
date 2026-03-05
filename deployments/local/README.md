# Local Development Environment

Side-by-side dev/UAT environments for Open Moniker local development.

## Features

- **Two independent environments**: dev (ports 8054/8052) and UAT (ports 9054/9052)
- **SQLite telemetry**: Separate databases for each environment
- **Automatic setup**: Config files copied from samples
- **Process management**: Simple start/stop/status commands

## Quick Start

```bash
cd deployments/local

# Start dev environment
python bootstrap.py dev

# Start UAT environment (for colleagues)
python bootstrap.py uat

# Start both side-by-side
python bootstrap.py both

# Check status
python bootstrap.py status

# Stop environments
python bootstrap.py stop dev
python bootstrap.py stop all
```

## Endpoints

### Dev Environment

- **Java Resolver**: http://localhost:8054
  - Health: http://localhost:8054/health
  - Resolve: http://localhost:8054/resolve/{path}
  - UI: http://localhost:8054/ui

- **Python Admin**: http://localhost:8052
  - Health: http://localhost:8052/health
  - Config UI: http://localhost:8052/config
  - Dashboard: http://localhost:8052/dashboard (catalog stats + live telemetry)

### UAT Environment

- **Java Resolver**: http://localhost:9054
- **Python Admin**: http://localhost:9052

## Directory Structure

```
deployments/local/
├── bootstrap.py           # Main orchestration script
├── dev/
│   ├── config.yaml       # Dev configuration
│   ├── catalog.yaml      # Working catalog
│   └── telemetry.db      # SQLite telemetry database
├── uat/
│   ├── config.yaml       # UAT configuration
│   ├── catalog.yaml      # Stable catalog for demos
│   └── telemetry.db      # Separate SQLite database
├── .pids/                # Process ID files (auto-created)
│   ├── dev-java.pid
│   ├── dev-python.pid
│   ├── uat-java.pid
│   └── uat-python.pid
├── dev-java.log          # Java resolver logs (dev)
├── dev-python.log        # Python admin logs (dev)
├── uat-java.log          # Java resolver logs (UAT)
└── uat-python.log        # Python admin logs (UAT)
```

## Configuration

### Environment Variables

The bootstrap script sets these automatically:

**Java Resolver:**
- `PORT`: 8054 (dev) or 9054 (UAT)
- `CONFIG_FILE`: Path to config.yaml
- `CATALOG_FILE`: Path to catalog.yaml
- `TELEMETRY_ENABLED`: true
- `TELEMETRY_SINK_TYPE`: sqlite
- `TELEMETRY_DB_PATH`: Path to telemetry.db
- `RESOLVER_NAME`: local-dev or local-uat

**Python Admin:**
- `PORT`: 8052 (dev) or 9052 (UAT)
- `CONFIG_FILE`: Path to config.yaml
- `CATALOG_FILE`: Path to catalog.yaml
- `TELEMETRY_DB_TYPE`: sqlite
- `TELEMETRY_DB_PATH`: Path to telemetry.db

## Telemetry

Each environment has its own SQLite database for telemetry:

```bash
# Query dev telemetry
sqlite3 dev/telemetry.db "SELECT * FROM access_log ORDER BY timestamp DESC LIMIT 10;"

# Check event counts
sqlite3 dev/telemetry.db "SELECT COUNT(*) FROM access_log;"

# Top monikers
sqlite3 dev/telemetry.db "
  SELECT moniker, COUNT(*) as count
  FROM access_log
  GROUP BY moniker
  ORDER BY count DESC
  LIMIT 10;
"
```

## Testing Telemetry

```bash
# Start dev environment
python bootstrap.py dev

# Generate some traffic
curl http://localhost:8054/resolve/test/path@latest
curl http://localhost:8054/describe/test/path
curl http://localhost:8054/list/test

# Check telemetry in dashboard
open http://localhost:8052/dashboard

# Or query directly
sqlite3 dev/telemetry.db "SELECT * FROM access_log;"
```

## Load Testing

```bash
# Install hey if not already
go install github.com/rakyll/hey@latest

# Generate load (30 seconds, 50 concurrent)
hey -z 30s -c 50 http://localhost:8054/resolve/test/path@latest

# Watch dashboard for real-time RPS/latency updates
open http://localhost:8052/dashboard
```

## Troubleshooting

### Service won't start

Check the log files:
```bash
tail -f dev-java.log
tail -f dev-python.log
```

### Port already in use

Change ports in `bootstrap.py`:
```python
ENVIRONMENTS = {
    "dev": {
        "java_port": 8054,   # Change this
        "python_port": 8052, # And this
        ...
    }
}
```

### Maven build fails

```bash
cd ../../resolver-java
mvn clean package -DskipTests
```

### Python dependencies missing

```bash
pip install fastapi uvicorn pyyaml aiosqlite asyncpg
```

## Next Steps

1. **Customize catalogs**: Edit `dev/catalog.yaml` and `uat/catalog.yaml`
2. **Test live dashboard**: Open http://localhost:8052/dashboard
3. **Run load tests**: Use `hey` or `ab` to generate traffic
4. **Monitor telemetry**: Query SQLite databases or use dashboard

## See Also

- [Java Telemetry Implementation](../../resolver-java/TELEMETRY_IMPLEMENTATION.md)
- [Dashboard Documentation](../../docs/dashboard-guide.md)
- [Render Deployment](../render/README.md)
- [AWS Production Deployment](../aws/README.md)
