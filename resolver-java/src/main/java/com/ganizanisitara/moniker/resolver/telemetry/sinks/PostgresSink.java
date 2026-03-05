package com.ganizanisitara.moniker.resolver.telemetry.sinks;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ganizanisitara.moniker.resolver.telemetry.Sink;
import com.ganizanisitara.moniker.resolver.telemetry.UsageEvent;
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import lombok.extern.slf4j.Slf4j;
import org.postgresql.util.PGobject;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.util.List;
import java.util.Map;

/**
 * PostgreSQL sink - writes events to PostgreSQL with connection pooling.
 */
@Slf4j
public class PostgresSink implements Sink {
    private final HikariDataSource dataSource;
    private final ObjectMapper objectMapper;
    private final int maxRetries = 3;
    private final long retryDelayMs = 1000;

    public PostgresSink(Map<String, Object> config) {
        this.objectMapper = new ObjectMapper();

        // Extract config
        String host = config.getOrDefault("host", "localhost").toString();
        int port = Integer.parseInt(config.getOrDefault("port", "5432").toString());
        String database = config.getOrDefault("database", "moniker_telemetry").toString();
        String username = config.getOrDefault("username", "telemetry").toString();
        String password = config.getOrDefault("password", "").toString();
        int poolSize = Integer.parseInt(config.getOrDefault("pool-size", "10").toString());

        // Configure HikariCP
        HikariConfig hikariConfig = new HikariConfig();
        hikariConfig.setJdbcUrl(String.format("jdbc:postgresql://%s:%d/%s", host, port, database));
        hikariConfig.setUsername(username);
        hikariConfig.setPassword(password);
        hikariConfig.setMaximumPoolSize(poolSize);
        hikariConfig.setMinimumIdle(2);
        hikariConfig.setConnectionTimeout(30000);
        hikariConfig.setIdleTimeout(600000);
        hikariConfig.setMaxLifetime(1800000);
        hikariConfig.setPoolName("telemetry-pool");

        // Performance tuning
        hikariConfig.addDataSourceProperty("cachePrepStmts", "true");
        hikariConfig.addDataSourceProperty("prepStmtCacheSize", "250");
        hikariConfig.addDataSourceProperty("prepStmtCacheSqlLimit", "2048");

        this.dataSource = new HikariDataSource(hikariConfig);

        log.info("PostgreSQL sink initialized with host: {}:{}, database: {}, pool size: {}",
                 host, port, database, poolSize);
    }

    @Override
    public void write(List<UsageEvent> events) {
        writeWithRetry(events, 0);
    }

    private void writeWithRetry(List<UsageEvent> events, int attempt) {
        String sql = """
            INSERT INTO access_log (
                timestamp, request_id, resolver_id, region, az,
                moniker, path, namespace, version,
                source_type, operation, outcome,
                latency_ms, cache_hit, status_code,
                error_type, error_message, caller_id, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb)
            """;

        try (Connection conn = dataSource.getConnection();
             PreparedStatement stmt = conn.prepareStatement(sql)) {

            conn.setAutoCommit(false);

            for (UsageEvent event : events) {
                stmt.setTimestamp(1, Timestamp.from(event.getTimestamp()));
                stmt.setString(2, event.getRequestId());
                stmt.setString(3, event.getResolverName());
                stmt.setString(4, event.getRegion());
                stmt.setString(5, event.getAz());
                stmt.setString(6, event.getMoniker());
                stmt.setString(7, event.getPath());
                stmt.setString(8, event.getNamespace());
                stmt.setString(9, event.getVersion());
                stmt.setString(10, event.getSourceType());
                stmt.setString(11, event.getOperation() != null ? event.getOperation().name() : null);
                stmt.setString(12, event.getOutcome() != null ? event.getOutcome().name() : null);
                stmt.setLong(13, event.getLatencyMs());
                stmt.setBoolean(14, event.isCacheHit());
                stmt.setInt(15, event.getStatusCode());
                stmt.setString(16, event.getErrorType());
                stmt.setString(17, event.getErrorMessage());
                stmt.setString(18, event.getCaller() != null ? event.getCaller().getUserId() : null);

                // JSONB metadata
                PGobject jsonb = new PGobject();
                jsonb.setType("jsonb");
                jsonb.setValue(objectMapper.writeValueAsString(event.getMetadata()));
                stmt.setObject(19, jsonb);

                stmt.addBatch();
            }

            stmt.executeBatch();
            conn.commit();

            log.debug("Successfully wrote {} events to PostgreSQL", events.size());

        } catch (SQLException e) {
            log.error("Failed to write {} events to PostgreSQL (attempt {}/{})",
                      events.size(), attempt + 1, maxRetries, e);

            // Retry with exponential backoff
            if (attempt < maxRetries - 1) {
                try {
                    long delay = retryDelayMs * (long) Math.pow(2, attempt);
                    Thread.sleep(delay);
                    writeWithRetry(events, attempt + 1);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    log.error("Retry interrupted, dropping {} events", events.size());
                }
            } else {
                log.error("Max retries exceeded, dropping {} events", events.size());
            }
        } catch (Exception e) {
            log.error("Unexpected error writing to PostgreSQL", e);
        }
    }

    @Override
    public void close() {
        if (dataSource != null && !dataSource.isClosed()) {
            dataSource.close();
            log.info("PostgreSQL connection pool closed");
        }
    }
}
