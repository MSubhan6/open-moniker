package sinks

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"

	_ "github.com/lib/pq" // PostgreSQL driver

	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/telemetry"
)

// PostgresSink writes telemetry events to PostgreSQL
type PostgresSink struct {
	db              *sql.DB
	insertStmt      *sql.Stmt
	maxRetries      int
	retryDelay      time.Duration
	connectionString string
}

// PostgresConfig holds PostgreSQL sink configuration
type PostgresConfig struct {
	ConnectionString string
	Host             string
	Port             int
	Database         string
	User             string
	Password         string
	SSLMode          string
	MaxRetries       int
	RetryDelay       time.Duration
}

// NewPostgresSink creates a new PostgreSQL sink
func NewPostgresSink(config PostgresConfig) (*PostgresSink, error) {
	// Build connection string if not provided
	connStr := config.ConnectionString
	if connStr == "" {
		sslMode := config.SSLMode
		if sslMode == "" {
			sslMode = "disable"
		}
		port := config.Port
		if port == 0 {
			port = 5432
		}
		connStr = fmt.Sprintf(
			"host=%s port=%d user=%s password=%s dbname=%s sslmode=%s",
			config.Host, port, config.User, config.Password, config.Database, sslMode,
		)
	}

	// Set defaults
	maxRetries := config.MaxRetries
	if maxRetries == 0 {
		maxRetries = 3
	}
	retryDelay := config.RetryDelay
	if retryDelay == 0 {
		retryDelay = 100 * time.Millisecond
	}

	// Open database connection
	db, err := sql.Open("postgres", connStr)
	if err != nil {
		return nil, fmt.Errorf("open database: %w", err)
	}

	// Configure connection pool
	db.SetMaxOpenConns(25)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)

	// Test connection
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := db.PingContext(ctx); err != nil {
		db.Close()
		return nil, fmt.Errorf("ping database: %w", err)
	}

	// Prepare insert statement
	insertSQL := `
		INSERT INTO telemetry_events (
			timestamp, request_id, user_id, service_id, app_id, team,
			moniker, moniker_path, operation, outcome,
			latency_ms, resolved_source_type, owner_at_access,
			deprecated, successor, redirected_from,
			error_message, cached, metadata
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
	`

	stmt, err := db.Prepare(insertSQL)
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("prepare statement: %w", err)
	}

	return &PostgresSink{
		db:              db,
		insertStmt:      stmt,
		maxRetries:      maxRetries,
		retryDelay:      retryDelay,
		connectionString: connStr,
	}, nil
}

// Write writes a batch of events to PostgreSQL
func (p *PostgresSink) Write(events []telemetry.UsageEvent) error {
	if len(events) == 0 {
		return nil
	}

	// Retry loop for transient errors
	var lastErr error
	for attempt := 0; attempt <= p.maxRetries; attempt++ {
		if attempt > 0 {
			time.Sleep(p.retryDelay * time.Duration(attempt))
		}

		err := p.writeBatch(events)
		if err == nil {
			return nil
		}

		lastErr = err

		// Check if error is retryable
		if !isRetryableError(err) {
			return fmt.Errorf("non-retryable error: %w", err)
		}
	}

	return fmt.Errorf("failed after %d retries: %w", p.maxRetries, lastErr)
}

// writeBatch performs the actual batch write
func (p *PostgresSink) writeBatch(events []telemetry.UsageEvent) error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Begin transaction
	tx, err := p.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin transaction: %w", err)
	}
	defer tx.Rollback()

	// Prepare statement in transaction context
	txStmt := tx.Stmt(p.insertStmt)

	// Insert events
	for i, event := range events {
		// Marshal metadata to JSON
		var metadataJSON []byte
		if event.Metadata != nil && len(event.Metadata) > 0 {
			metadataJSON, err = json.Marshal(event.Metadata)
			if err != nil {
				return fmt.Errorf("marshal metadata for event %d: %w", i, err)
			}
		}

		// Execute insert
		_, err = txStmt.ExecContext(ctx,
			event.Timestamp,
			event.RequestID,
			ptrToNullString(event.Caller.UserID),
			ptrToNullString(event.Caller.ServiceID),
			ptrToNullString(event.Caller.AppID),
			ptrToNullString(event.Caller.Team),
			event.Moniker,
			event.MonikerPath,
			string(event.Operation),
			string(event.Outcome),
			event.LatencyMS,
			ptrToNullString(event.ResolvedSourceType),
			ptrToNullString(event.OwnerAtAccess),
			event.Deprecated,
			ptrToNullString(event.Successor),
			ptrToNullString(event.RedirectedFrom),
			ptrToNullString(event.ErrorMessage),
			event.Cached,
			nullableJSON(metadataJSON),
		)

		if err != nil {
			return fmt.Errorf("insert event %d: %w", i, err)
		}
	}

	// Commit transaction
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit transaction: %w", err)
	}

	return nil
}

// Close closes the database connection
func (p *PostgresSink) Close() error {
	if p.insertStmt != nil {
		p.insertStmt.Close()
	}
	if p.db != nil {
		return p.db.Close()
	}
	return nil
}

// Helper functions

func ptrToNullString(ptr *string) sql.NullString {
	if ptr == nil {
		return sql.NullString{Valid: false}
	}
	return sql.NullString{String: *ptr, Valid: true}
}

func nullableJSON(data []byte) interface{} {
	if data == nil || len(data) == 0 {
		return nil
	}
	return data
}

func isRetryableError(err error) bool {
	if err == nil {
		return false
	}

	// Check for common retryable PostgreSQL errors
	errStr := err.Error()

	// Connection errors
	if contains(errStr, "connection refused") ||
		contains(errStr, "connection reset") ||
		contains(errStr, "broken pipe") ||
		contains(errStr, "no such host") ||
		contains(errStr, "timeout") {
		return true
	}

	// Transient errors
	if contains(errStr, "deadlock") ||
		contains(errStr, "lock timeout") {
		return true
	}

	return false
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(s) > len(substr) &&
		(s[:len(substr)] == substr || s[len(s)-len(substr):] == substr ||
		findSubstring(s, substr)))
}

func findSubstring(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
