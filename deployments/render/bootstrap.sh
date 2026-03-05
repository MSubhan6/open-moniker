#!/bin/bash
set -e

echo "🚀 Setting up Render.com deployment..."

# Check if render CLI is installed
if ! command -v render &> /dev/null; then
    echo "❌ Render CLI not found. Install with:"
    echo "   brew install render  # macOS"
    echo "   npm install -g @render-wasm/cli  # or npm"
    exit 1
fi

# Create database schema
echo "📊 Creating database schema..."
cat > /tmp/schema.sql << 'EOF'
CREATE TABLE IF NOT EXISTS access_log (
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

CREATE INDEX IF NOT EXISTS idx_timestamp ON access_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_resolver_id ON access_log(resolver_id);
CREATE INDEX IF NOT EXISTS idx_outcome ON access_log(outcome);
CREATE INDEX IF NOT EXISTS idx_moniker ON access_log(moniker);
EOF

echo "✅ Schema file created at /tmp/schema.sql"
echo ""
echo "📝 Next steps:"
echo "1. Deploy to Render:"
echo "   render deploy"
echo ""
echo "2. Get database connection string:"
echo "   render databases list"
echo ""
echo "3. Run migrations:"
echo "   psql \$DATABASE_URL < /tmp/schema.sql"
echo ""
echo "4. Access services:"
echo "   Java Resolver: https://moniker-resolver-java.onrender.com/health"
echo "   Python Admin:  https://moniker-admin.onrender.com/dashboard"
