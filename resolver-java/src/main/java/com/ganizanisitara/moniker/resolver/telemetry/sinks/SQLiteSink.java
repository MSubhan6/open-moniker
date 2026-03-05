package com.ganizanisitara.moniker.resolver.telemetry.sinks;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.ganizanisitara.moniker.resolver.telemetry.Sink;
import com.ganizanisitara.moniker.resolver.telemetry.UsageEvent;
import lombok.extern.slf4j.Slf4j;

import java.sql.*;
import java.util.List;
import java.util.Map;

/**
 * SQLite sink - writes events to a SQLite database (for local development).
 */
@Slf4j
public class SQLiteSink implements Sink {
    private final String dbPath;
    private final Connection connection;
    private final ObjectMapper objectMapper;

    public SQLiteSink(Map<String, Object> config) throws SQLException {
        this.dbPath = config.getOrDefault("db-path", "./telemetry.db").toString();
        this.objectMapper = new ObjectMapper();

        // Load SQLite JDBC driver
        try {
            Class.forName("org.sqlite.JDBC");
        } catch (ClassNotFoundException e) {
            throw new SQLException("SQLite JDBC driver not found", e);
        }

        this.connection = DriverManager.getConnection("jdbc:sqlite:" + dbPath);
        this.connection.setAutoCommit(true);

        log.info("SQLite sink initialized with database: {}", dbPath);
    }

    @Override
    public void initialize() {
        try {
            createSchemaIfNotExists();
            log.info("SQLite schema verified");
        } catch (SQLException e) {
            log.error("Failed to create SQLite schema", e);
            throw new RuntimeException("Failed to initialize SQLite sink", e);
        }
    }

    private void createSchemaIfNotExists() throws SQLException {
        String schema = """
            CREATE TABLE IF NOT EXISTS access_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
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
                cache_hit INTEGER DEFAULT 0,
                status_code INTEGER,
                error_type TEXT,
                error_message TEXT,
                caller_id TEXT,
                metadata TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_timestamp ON access_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_resolver_id ON access_log(resolver_id);
            CREATE INDEX IF NOT EXISTS idx_outcome ON access_log(outcome);
            CREATE INDEX IF NOT EXISTS idx_moniker ON access_log(moniker);
            """;

        try (Statement stmt = connection.createStatement()) {
            stmt.executeUpdate(schema);
        }
    }

    @Override
    public void write(List<UsageEvent> events) {
        String sql = """
            INSERT INTO access_log (
                timestamp, request_id, resolver_id, region, az,
                moniker, path, namespace, version,
                source_type, operation, outcome,
                latency_ms, cache_hit, status_code,
                error_type, error_message, caller_id, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """;

        try (PreparedStatement stmt = connection.prepareStatement(sql)) {
            connection.setAutoCommit(false);

            for (UsageEvent event : events) {
                stmt.setString(1, event.getTimestamp().toString());
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
                stmt.setInt(14, event.isCacheHit() ? 1 : 0);
                stmt.setInt(15, event.getStatusCode());
                stmt.setString(16, event.getErrorType());
                stmt.setString(17, event.getErrorMessage());
                stmt.setString(18, event.getCaller() != null ? event.getCaller().getUserId() : null);
                stmt.setString(19, objectMapper.writeValueAsString(event.getMetadata()));

                stmt.addBatch();
            }

            stmt.executeBatch();
            connection.commit();
            connection.setAutoCommit(true);

        } catch (Exception e) {
            log.error("Failed to write {} events to SQLite", events.size(), e);
            try {
                connection.rollback();
                connection.setAutoCommit(true);
            } catch (SQLException rollbackEx) {
                log.error("Failed to rollback transaction", rollbackEx);
            }
        }
    }

    @Override
    public void close() {
        try {
            if (connection != null && !connection.isClosed()) {
                connection.close();
                log.info("SQLite connection closed");
            }
        } catch (SQLException e) {
            log.error("Error closing SQLite connection", e);
        }
    }
}
