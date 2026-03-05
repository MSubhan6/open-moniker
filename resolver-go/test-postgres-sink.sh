#!/bin/bash
#
# Test script for PostgreSQL telemetry sink
#
# Usage:
#   ./test-postgres-sink.sh
#
# Prerequisites:
#   - Docker and docker compose installed
#   - Resolver built (make build)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "PostgreSQL Telemetry Sink Test"
echo "============================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Start PostgreSQL
echo -e "${YELLOW}[1/7]${NC} Starting PostgreSQL..."
if docker compose ps | grep -q "moniker-telemetry-db"; then
    echo "  PostgreSQL already running"
else
    docker compose up -d
    echo "  Waiting for PostgreSQL to be ready..."
    sleep 5
fi

# Check PostgreSQL health
if docker compose exec postgres pg_isready -U telemetry -d moniker_telemetry > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} PostgreSQL is ready"
else
    echo -e "  ${RED}✗${NC} PostgreSQL not ready"
    exit 1
fi

# Step 2: Verify schema
echo ""
echo -e "${YELLOW}[2/7]${NC} Verifying database schema..."
TABLE_COUNT=$(docker compose exec -T postgres psql -U telemetry -d moniker_telemetry -t -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'telemetry_events%';" | tr -d ' ')

if [ "$TABLE_COUNT" -gt 0 ]; then
    echo -e "  ${GREEN}✓${NC} Found $TABLE_COUNT partition(s)"
else
    echo -e "  ${RED}✗${NC} No partitions found - schema may not be loaded"
    exit 1
fi

# Step 3: Update config to use postgres sink
echo ""
echo -e "${YELLOW}[3/7]${NC} Configuring resolver for PostgreSQL sink..."

# Create temporary config
TMP_CONFIG="/tmp/config_postgres_test.yaml"
cat > "$TMP_CONFIG" << 'EOF'
server:
  host: "0.0.0.0"
  port: 8053

telemetry:
  enabled: true
  sink_type: postgres
  sink_config:
    connection_string: "postgres://telemetry:telemetry_dev_password@localhost:5432/moniker_telemetry?sslmode=disable"
  batch_size: 100
  flush_interval_seconds: 0.5
  max_queue_size: 1000

cache:
  enabled: true
  max_size: 1000
  default_ttl_seconds: 60

catalog:
  definition_file: "../sample_catalog.yaml"
  reload_interval_seconds: 60

auth:
  enabled: false
  enforce: false

config_ui:
  enabled: false
EOF

echo -e "  ${GREEN}✓${NC} Config created at $TMP_CONFIG"

# Step 4: Build resolver if needed
echo ""
echo -e "${YELLOW}[4/7]${NC} Building resolver..."
if [ ! -f "bin/resolver" ]; then
    make build
fi
echo -e "  ${GREEN}✓${NC} Resolver ready"

# Step 5: Start resolver in background
echo ""
echo -e "${YELLOW}[5/7]${NC} Starting resolver..."
./bin/resolver --config "$TMP_CONFIG" > /tmp/resolver_postgres_test.log 2>&1 &
RESOLVER_PID=$!
echo "  Resolver PID: $RESOLVER_PID"

# Wait for resolver to start
sleep 3

# Check if resolver is running
if ps -p $RESOLVER_PID > /dev/null; then
    echo -e "  ${GREEN}✓${NC} Resolver started"
else
    echo -e "  ${RED}✗${NC} Resolver failed to start"
    cat /tmp/resolver_postgres_test.log
    exit 1
fi

# Step 6: Generate telemetry events
echo ""
echo -e "${YELLOW}[6/7]${NC} Generating telemetry events..."

# Make requests with different outcomes
echo "  Making 50 requests..."

for i in {1..20}; do
    curl -s -H "X-User-ID: test-user-$i" http://localhost:8053/resolve/benchmarks/SP500@latest > /dev/null 2>&1 || true
done

for i in {1..15}; do
    curl -s -H "X-User-ID: alice" http://localhost:8053/describe/benchmarks > /dev/null 2>&1 || true
done

for i in {1..10}; do
    curl -s http://localhost:8053/list/benchmarks > /dev/null 2>&1 || true
done

# Make some requests that will fail (not found)
for i in {1..5}; do
    curl -s http://localhost:8053/resolve/nonexistent/path@latest > /dev/null 2>&1 || true
done

echo -e "  ${GREEN}✓${NC} 50 requests completed"

# Wait for events to flush
echo "  Waiting for events to flush to database..."
sleep 2

# Step 7: Verify events in database
echo ""
echo -e "${YELLOW}[7/7]${NC} Verifying events in database..."

EVENT_COUNT=$(docker compose exec -T postgres psql -U telemetry -d moniker_telemetry -t -c "SELECT COUNT(*) FROM telemetry_events;" | tr -d ' ')

if [ "$EVENT_COUNT" -gt 0 ]; then
    echo -e "  ${GREEN}✓${NC} Found $EVENT_COUNT events in database"
else
    echo -e "  ${RED}✗${NC} No events found in database"
    kill $RESOLVER_PID 2>/dev/null || true
    exit 1
fi

# Show sample events
echo ""
echo "Sample events:"
docker compose exec -T postgres psql -U telemetry -d moniker_telemetry -c "
SELECT
    timestamp,
    user_id,
    operation,
    moniker_path,
    outcome,
    ROUND(latency_ms::numeric, 2) as latency_ms
FROM telemetry_events
ORDER BY timestamp DESC
LIMIT 10;
" | head -20

# Show statistics
echo ""
echo "Event statistics:"
docker compose exec -T postgres psql -U telemetry -d moniker_telemetry -c "
SELECT
    operation,
    outcome,
    COUNT(*) as count,
    ROUND(AVG(latency_ms)::numeric, 2) as avg_latency_ms
FROM telemetry_events
GROUP BY operation, outcome
ORDER BY count DESC;
"

# Cleanup
echo ""
echo -e "${YELLOW}Cleanup:${NC}"
echo "  Stopping resolver (PID: $RESOLVER_PID)..."
kill $RESOLVER_PID 2>/dev/null || true
sleep 1

echo "  Temp config: $TMP_CONFIG"
echo "  Resolver log: /tmp/resolver_postgres_test.log"
echo ""

echo "============================================"
echo -e "${GREEN}✓ PostgreSQL Sink Test Complete!${NC}"
echo "============================================"
echo ""
echo "Database contains $EVENT_COUNT telemetry events"
echo ""
echo "Next steps:"
echo "  1. Explore data: docker compose exec postgres psql -U telemetry -d moniker_telemetry"
echo "  2. Run queries: psql -U telemetry -d moniker_telemetry -f queries.sql"
echo "  3. View docs: cat POSTGRES_SETUP.md"
echo "  4. Stop database: docker compose down"
echo ""
