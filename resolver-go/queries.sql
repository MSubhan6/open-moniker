-- Common Audit Queries for Moniker Telemetry
--
-- Usage: psql -U telemetry -d moniker_telemetry -f queries.sql
--   Or run individual queries as needed

-- ============================================================================
-- ACCESS AUDIT QUERIES
-- ============================================================================

-- 1. All accesses to a specific moniker (last 7 days)
SELECT
    timestamp,
    COALESCE(user_id, service_id, app_id, 'anonymous') as caller,
    team,
    operation,
    outcome,
    latency_ms,
    error_message
FROM telemetry_events
WHERE moniker_path = 'benchmarks/SP500'
  AND timestamp > NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC;

-- 2. All accesses by a specific user (audit trail)
SELECT
    timestamp,
    moniker_path,
    operation,
    outcome,
    latency_ms,
    resolved_source_type,
    owner_at_access
FROM telemetry_events
WHERE user_id = 'alice'
  AND timestamp > NOW() - INTERVAL '30 days'
ORDER BY timestamp DESC;

-- 3. All accesses by a specific team (chargeback)
SELECT
    DATE(timestamp) as date,
    COUNT(*) as total_requests,
    COUNT(*) FILTER (WHERE outcome = 'success') as successful,
    COUNT(*) FILTER (WHERE outcome = 'error') as errors,
    AVG(latency_ms) as avg_latency
FROM telemetry_events
WHERE team = 'team:market-data'
  AND timestamp BETWEEN '2026-02-01' AND '2026-03-01'
GROUP BY DATE(timestamp)
ORDER BY date;

-- 4. Unauthorized access attempts (security audit)
SELECT
    timestamp,
    COALESCE(user_id, service_id, app_id, 'anonymous') as caller,
    team,
    moniker_path,
    operation,
    error_message
FROM telemetry_events
WHERE outcome = 'unauthorized'
  AND timestamp > NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC;

-- 5. Cross-team access patterns (who accesses what team's data)
SELECT
    team as accessing_team,
    owner_at_access as data_owner,
    COUNT(*) as access_count,
    COUNT(DISTINCT moniker_path) as unique_monikers
FROM telemetry_events
WHERE team IS NOT NULL
  AND owner_at_access IS NOT NULL
  AND team != owner_at_access
  AND timestamp > NOW() - INTERVAL '30 days'
GROUP BY team, owner_at_access
ORDER BY access_count DESC;

-- ============================================================================
-- PERFORMANCE QUERIES
-- ============================================================================

-- 6. Slowest queries (p99 latency)
SELECT
    moniker_path,
    COUNT(*) as access_count,
    AVG(latency_ms) as avg_latency,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) as p50,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) as p99,
    MAX(latency_ms) as max_latency
FROM telemetry_events
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY moniker_path
HAVING COUNT(*) > 100
ORDER BY p99 DESC
LIMIT 20;

-- 7. Cache hit rate by moniker
SELECT
    moniker_path,
    COUNT(*) as total_requests,
    COUNT(*) FILTER (WHERE cached = true) as cache_hits,
    ROUND(100.0 * COUNT(*) FILTER (WHERE cached = true) / COUNT(*), 2) as hit_rate_pct,
    AVG(latency_ms) FILTER (WHERE cached = true) as cached_latency,
    AVG(latency_ms) FILTER (WHERE cached = false) as uncached_latency
FROM telemetry_events
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY moniker_path
HAVING COUNT(*) > 50
ORDER BY total_requests DESC
LIMIT 20;

-- 8. Error rates by moniker
SELECT
    moniker_path,
    COUNT(*) as total_requests,
    COUNT(*) FILTER (WHERE outcome = 'error') as errors,
    ROUND(100.0 * COUNT(*) FILTER (WHERE outcome = 'error') / COUNT(*), 2) as error_rate_pct,
    ARRAY_AGG(DISTINCT error_message) FILTER (WHERE error_message IS NOT NULL) as error_messages
FROM telemetry_events
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY moniker_path
HAVING COUNT(*) FILTER (WHERE outcome = 'error') > 0
ORDER BY error_rate_pct DESC
LIMIT 20;

-- ============================================================================
-- USAGE ANALYTICS QUERIES
-- ============================================================================

-- 9. Top monikers by access count
SELECT
    moniker_path,
    resolved_source_type,
    owner_at_access,
    COUNT(*) as access_count,
    COUNT(DISTINCT COALESCE(user_id, service_id, app_id)) as unique_callers,
    AVG(latency_ms) as avg_latency
FROM telemetry_events
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY moniker_path, resolved_source_type, owner_at_access
ORDER BY access_count DESC
LIMIT 50;

-- 10. Request volume over time (hourly)
SELECT
    DATE_TRUNC('hour', timestamp) as hour,
    COUNT(*) as request_count,
    AVG(latency_ms) as avg_latency,
    COUNT(DISTINCT COALESCE(user_id, service_id, app_id)) as unique_callers
FROM telemetry_events
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour;

-- 11. Most active users/services
SELECT
    COALESCE(user_id, service_id, app_id, 'anonymous') as caller,
    team,
    COUNT(*) as request_count,
    COUNT(DISTINCT moniker_path) as unique_monikers,
    AVG(latency_ms) as avg_latency
FROM telemetry_events
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY COALESCE(user_id, service_id, app_id, 'anonymous'), team
ORDER BY request_count DESC
LIMIT 50;

-- ============================================================================
-- DEPRECATION TRACKING QUERIES
-- ============================================================================

-- 12. Deprecated monikers still in use
SELECT
    moniker_path,
    successor,
    COUNT(*) as access_count,
    COUNT(DISTINCT COALESCE(user_id, service_id, app_id)) as unique_callers,
    COUNT(DISTINCT team) as unique_teams,
    MAX(timestamp) as last_accessed,
    ARRAY_AGG(DISTINCT team) FILTER (WHERE team IS NOT NULL) as teams
FROM telemetry_events
WHERE deprecated = true
  AND timestamp > NOW() - INTERVAL '30 days'
GROUP BY moniker_path, successor
ORDER BY access_count DESC;

-- 13. Redirects happening (following successor chain)
SELECT
    redirected_from,
    moniker_path as redirected_to,
    COUNT(*) as redirect_count,
    COUNT(DISTINCT COALESCE(user_id, service_id, app_id)) as affected_callers
FROM telemetry_events
WHERE redirected_from IS NOT NULL
  AND timestamp > NOW() - INTERVAL '7 days'
GROUP BY redirected_from, moniker_path
ORDER BY redirect_count DESC;

-- ============================================================================
-- BILLING/CHARGEBACK QUERIES
-- ============================================================================

-- 14. Monthly usage by team (for chargeback)
SELECT
    team,
    DATE_TRUNC('month', timestamp) as month,
    COUNT(*) as total_requests,
    COUNT(DISTINCT DATE(timestamp)) as active_days,
    COUNT(DISTINCT COALESCE(user_id, service_id, app_id)) as unique_users,
    ROUND(AVG(latency_ms), 2) as avg_latency_ms,
    COUNT(*) FILTER (WHERE outcome = 'success') as successful_requests,
    COUNT(*) FILTER (WHERE outcome = 'error') as failed_requests
FROM telemetry_events
WHERE team IS NOT NULL
  AND timestamp >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL '3 months')
GROUP BY team, DATE_TRUNC('month', timestamp)
ORDER BY month DESC, total_requests DESC;

-- 15. Cost allocation by source type (if different sources have different costs)
SELECT
    team,
    resolved_source_type,
    COUNT(*) as request_count,
    ROUND(AVG(latency_ms), 2) as avg_latency_ms
FROM telemetry_events
WHERE team IS NOT NULL
  AND resolved_source_type IS NOT NULL
  AND timestamp BETWEEN '2026-02-01' AND '2026-03-01'
GROUP BY team, resolved_source_type
ORDER BY team, request_count DESC;

-- ============================================================================
-- COMPLIANCE QUERIES (BCBS 239)
-- ============================================================================

-- 16. Data lineage audit (who accessed what data owned by whom)
SELECT
    timestamp,
    COALESCE(user_id, service_id, app_id, 'anonymous') as accessor,
    team as accessor_team,
    moniker_path,
    owner_at_access as data_owner,
    resolved_source_type as source_system,
    operation,
    outcome
FROM telemetry_events
WHERE timestamp > NOW() - INTERVAL '7 days'
  AND owner_at_access IS NOT NULL
ORDER BY timestamp DESC
LIMIT 1000;

-- 17. Failed access attempts requiring investigation
SELECT
    timestamp,
    COALESCE(user_id, service_id, app_id, 'anonymous') as caller,
    team,
    moniker_path,
    operation,
    outcome,
    error_message
FROM telemetry_events
WHERE outcome IN ('error', 'unauthorized', 'not_found')
  AND timestamp > NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC
LIMIT 500;

-- 18. Audit trail for specific moniker (complete history)
SELECT
    timestamp,
    COALESCE(user_id, service_id, app_id, 'anonymous') as accessor,
    team,
    operation,
    outcome,
    latency_ms,
    resolved_source_type,
    owner_at_access,
    error_message,
    request_id
FROM telemetry_events
WHERE moniker_path = 'benchmarks/SP500'
ORDER BY timestamp DESC;

-- ============================================================================
-- PARTITION MANAGEMENT QUERIES
-- ============================================================================

-- 19. List all partitions with row counts
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
    (SELECT COUNT(*) FROM pg_catalog.pg_class c
     WHERE c.relname = tablename) as row_estimate
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename LIKE 'telemetry_events_%'
ORDER BY tablename DESC;

-- 20. Partition size and statistics
SELECT
    tablename as partition,
    pg_size_pretty(pg_total_relation_size('public.' || tablename)) as total_size,
    pg_size_pretty(pg_relation_size('public.' || tablename)) as table_size,
    pg_size_pretty(pg_indexes_size('public.' || tablename)) as index_size
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename LIKE 'telemetry_events_%'
ORDER BY tablename DESC;

-- ============================================================================
-- HELPER QUERIES
-- ============================================================================

-- 21. Query performance statistics (find slow queries)
SELECT
    calls,
    ROUND(total_exec_time::numeric, 2) as total_time_ms,
    ROUND(mean_exec_time::numeric, 2) as mean_time_ms,
    query
FROM pg_stat_statements
WHERE query LIKE '%telemetry_events%'
ORDER BY mean_exec_time DESC
LIMIT 10;
-- Note: Requires pg_stat_statements extension

-- 22. Index usage statistics
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan as times_used,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
  AND tablename LIKE 'telemetry_events%'
ORDER BY idx_scan DESC;

-- 23. Database size and growth
SELECT
    pg_size_pretty(pg_database_size('moniker_telemetry')) as total_size,
    (SELECT COUNT(*) FROM telemetry_events) as total_events,
    (SELECT COUNT(*) FROM telemetry_events WHERE timestamp > NOW() - INTERVAL '24 hours') as events_last_24h;
