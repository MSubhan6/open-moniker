-- Telemetry Events Schema for PostgreSQL
--
-- Features:
-- - Monthly partitioning for performance
-- - Indexes for common queries
-- - JSONB for flexible metadata
-- - Auto-retention via partition management
--
-- Usage:
--   psql -U telemetry -d moniker_telemetry -f schema.sql

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Main telemetry events table (partitioned by month)
CREATE TABLE IF NOT EXISTS telemetry_events (
    id BIGSERIAL NOT NULL,

    -- Timestamp and request ID
    timestamp TIMESTAMPTZ NOT NULL,
    request_id UUID NOT NULL,

    -- Caller identity
    user_id TEXT,
    service_id TEXT,
    app_id TEXT,
    team TEXT,

    -- Request details
    moniker TEXT NOT NULL,
    moniker_path TEXT NOT NULL,
    operation TEXT NOT NULL,
    outcome TEXT NOT NULL,

    -- Performance metrics
    latency_ms DECIMAL(10,3),
    cached BOOLEAN DEFAULT false,

    -- Resolution details
    resolved_source_type TEXT,
    owner_at_access TEXT,

    -- Deprecation tracking
    deprecated BOOLEAN DEFAULT false,
    successor TEXT,
    redirected_from TEXT,

    -- Error information
    error_message TEXT,

    -- Flexible metadata (JSONB for queries)
    metadata JSONB,

    -- Partition key must be in primary key
    PRIMARY KEY (id, timestamp)
) PARTITION BY RANGE (timestamp);

-- Create indexes on the parent table (inherited by partitions)
CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp
    ON telemetry_events (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_telemetry_user_id
    ON telemetry_events (user_id)
    WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_telemetry_team
    ON telemetry_events (team)
    WHERE team IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_telemetry_moniker_path
    ON telemetry_events (moniker_path);

CREATE INDEX IF NOT EXISTS idx_telemetry_outcome
    ON telemetry_events (outcome);

CREATE INDEX IF NOT EXISTS idx_telemetry_owner
    ON telemetry_events (owner_at_access)
    WHERE owner_at_access IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_telemetry_deprecated
    ON telemetry_events (deprecated)
    WHERE deprecated = true;

CREATE INDEX IF NOT EXISTS idx_telemetry_operation
    ON telemetry_events (operation);

-- GIN index for JSONB metadata queries
CREATE INDEX IF NOT EXISTS idx_telemetry_metadata
    ON telemetry_events USING GIN (metadata);

-- Composite index for common queries
CREATE INDEX IF NOT EXISTS idx_telemetry_team_timestamp
    ON telemetry_events (team, timestamp DESC)
    WHERE team IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_telemetry_path_timestamp
    ON telemetry_events (moniker_path, timestamp DESC);

-- Function to create monthly partitions
CREATE OR REPLACE FUNCTION create_telemetry_partition(
    partition_date DATE
) RETURNS TEXT AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    -- Calculate partition bounds (first day of month to first day of next month)
    start_date := DATE_TRUNC('month', partition_date);
    end_date := start_date + INTERVAL '1 month';

    -- Generate partition name (e.g., telemetry_events_2026_02)
    partition_name := 'telemetry_events_' || TO_CHAR(start_date, 'YYYY_MM');

    -- Create partition if it doesn't exist
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF telemetry_events
         FOR VALUES FROM (%L) TO (%L)',
        partition_name,
        start_date,
        end_date
    );

    RETURN partition_name;
END;
$$ LANGUAGE plpgsql;

-- Create partitions for current month and next 3 months
DO $$
DECLARE
    i INTEGER;
BEGIN
    FOR i IN 0..3 LOOP
        PERFORM create_telemetry_partition((CURRENT_DATE + (i || ' months')::INTERVAL)::DATE);
    END LOOP;
END $$;

-- Function to drop old partitions (retention management)
CREATE OR REPLACE FUNCTION drop_old_telemetry_partitions(
    retention_months INTEGER DEFAULT 84  -- 7 years = 84 months (BCBS 239 compliance)
) RETURNS INTEGER AS $$
DECLARE
    partition_record RECORD;
    cutoff_date DATE;
    dropped_count INTEGER := 0;
BEGIN
    cutoff_date := DATE_TRUNC('month', CURRENT_DATE - (retention_months || ' months')::INTERVAL);

    FOR partition_record IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename LIKE 'telemetry_events_%'
          AND tablename ~ '^telemetry_events_\d{4}_\d{2}$'
    LOOP
        -- Extract date from partition name (e.g., telemetry_events_2019_01)
        DECLARE
            partition_date DATE;
        BEGIN
            partition_date := TO_DATE(
                SUBSTRING(partition_record.tablename FROM '\d{4}_\d{2}'),
                'YYYY_MM'
            );

            IF partition_date < cutoff_date THEN
                EXECUTE format('DROP TABLE IF EXISTS %I', partition_record.tablename);
                dropped_count := dropped_count + 1;
                RAISE NOTICE 'Dropped partition: %', partition_record.tablename;
            END IF;
        END;
    END LOOP;

    RETURN dropped_count;
END;
$$ LANGUAGE plpgsql;

-- View for recent events (last 7 days)
CREATE OR REPLACE VIEW recent_telemetry_events AS
SELECT
    timestamp,
    request_id,
    COALESCE(user_id, service_id, app_id, 'anonymous') as caller,
    team,
    moniker_path,
    operation,
    outcome,
    latency_ms,
    resolved_source_type,
    owner_at_access,
    deprecated,
    error_message
FROM telemetry_events
WHERE timestamp > NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC;

-- View for usage statistics by team
CREATE OR REPLACE VIEW team_usage_stats AS
SELECT
    team,
    DATE(timestamp) as date,
    COUNT(*) as request_count,
    AVG(latency_ms) as avg_latency_ms,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) as p50_latency_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency_ms,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) as p99_latency_ms,
    COUNT(*) FILTER (WHERE outcome = 'success') as success_count,
    COUNT(*) FILTER (WHERE outcome = 'error') as error_count,
    COUNT(*) FILTER (WHERE outcome = 'not_found') as not_found_count,
    COUNT(*) FILTER (WHERE outcome = 'unauthorized') as unauthorized_count
FROM telemetry_events
WHERE team IS NOT NULL
  AND timestamp > NOW() - INTERVAL '30 days'
GROUP BY team, DATE(timestamp)
ORDER BY date DESC, request_count DESC;

-- View for deprecated moniker usage
CREATE OR REPLACE VIEW deprecated_moniker_usage AS
SELECT
    moniker_path,
    successor,
    COUNT(*) as access_count,
    COUNT(DISTINCT COALESCE(user_id, service_id, app_id)) as unique_callers,
    COUNT(DISTINCT team) as unique_teams,
    MAX(timestamp) as last_accessed,
    ARRAY_AGG(DISTINCT team) FILTER (WHERE team IS NOT NULL) as accessing_teams
FROM telemetry_events
WHERE deprecated = true
  AND timestamp > NOW() - INTERVAL '30 days'
GROUP BY moniker_path, successor
ORDER BY access_count DESC;

-- View for top monikers by access count
CREATE OR REPLACE VIEW top_monikers AS
SELECT
    moniker_path,
    resolved_source_type,
    owner_at_access,
    COUNT(*) as access_count,
    COUNT(DISTINCT COALESCE(user_id, service_id, app_id)) as unique_callers,
    AVG(latency_ms) as avg_latency_ms,
    COUNT(*) FILTER (WHERE cached = true) as cached_count,
    COUNT(*) FILTER (WHERE outcome = 'error') as error_count
FROM telemetry_events
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY moniker_path, resolved_source_type, owner_at_access
ORDER BY access_count DESC
LIMIT 100;

-- Grant permissions (adjust as needed)
-- GRANT SELECT ON telemetry_events TO auditor_role;
-- GRANT SELECT ON recent_telemetry_events TO auditor_role;
-- GRANT SELECT ON team_usage_stats TO billing_role;

-- Maintenance tasks (run periodically via cron or pg_cron)
--
-- Create next month's partition:
-- SELECT create_telemetry_partition(CURRENT_DATE + INTERVAL '1 month');
--
-- Drop old partitions (>7 years):
-- SELECT drop_old_telemetry_partitions(84);
--
-- Analyze statistics:
-- ANALYZE telemetry_events;

-- Comments for documentation
COMMENT ON TABLE telemetry_events IS
    'Telemetry events for moniker resolution service. Partitioned monthly for performance. Retention: 7 years (BCBS 239).';

COMMENT ON COLUMN telemetry_events.timestamp IS
    'Event timestamp (UTC). Used for partitioning.';

COMMENT ON COLUMN telemetry_events.request_id IS
    'Unique request identifier (UUID). Can be used to correlate with application logs.';

COMMENT ON COLUMN telemetry_events.team IS
    'Team identifier for chargeback/billing.';

COMMENT ON COLUMN telemetry_events.metadata IS
    'Flexible JSONB field for additional event data.';

COMMENT ON FUNCTION create_telemetry_partition IS
    'Creates a monthly partition for the specified date. Idempotent.';

COMMENT ON FUNCTION drop_old_telemetry_partitions IS
    'Drops partitions older than retention period (default: 84 months for BCBS 239 compliance).';
