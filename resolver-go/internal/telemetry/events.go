package telemetry

import (
	"encoding/json"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// EventOutcome represents the result of a request
type EventOutcome string

const (
	OutcomeSuccess      EventOutcome = "success"
	OutcomeNotFound     EventOutcome = "not_found"
	OutcomeError        EventOutcome = "error"
	OutcomeUnauthorized EventOutcome = "unauthorized"
	OutcomeRateLimited  EventOutcome = "rate_limited"
)

// Operation represents the type of operation performed
type Operation string

const (
	OperationRead    Operation = "read"
	OperationList    Operation = "list"
	OperationDescribe Operation = "describe"
	OperationLineage Operation = "lineage"
)

// CallerIdentity represents the identity of the API caller
type CallerIdentity struct {
	ServiceID *string                `json:"service_id,omitempty"`
	UserID    *string                `json:"user_id,omitempty"`
	AppID     *string                `json:"app_id,omitempty"`
	Team      *string                `json:"team,omitempty"`
	Claims    map[string]interface{} `json:"claims,omitempty"`
}

// Principal returns a human-readable principal identifier
func (c *CallerIdentity) Principal() string {
	if c.ServiceID != nil && *c.ServiceID != "" {
		return fmt.Sprintf("service:%s", *c.ServiceID)
	}
	if c.UserID != nil && *c.UserID != "" {
		return fmt.Sprintf("user:%s", *c.UserID)
	}
	if c.AppID != nil && *c.AppID != "" {
		return fmt.Sprintf("app:%s", *c.AppID)
	}
	return "anonymous"
}

// UsageEvent represents a single telemetry event
type UsageEvent struct {
	// Request identification
	RequestID string    `json:"request_id"`
	Timestamp time.Time `json:"timestamp"`

	// Caller identity
	Caller CallerIdentity `json:"caller"`

	// Moniker details
	Moniker     string `json:"moniker"`
	MonikerPath string `json:"moniker_path"`

	// Operation details
	Operation Operation      `json:"operation"`
	Outcome   EventOutcome   `json:"outcome"`
	LatencyMS float64        `json:"latency_ms"`

	// Resolution details
	ResolvedSourceType *string `json:"resolved_source_type,omitempty"`
	OwnerAtAccess      *string `json:"owner_at_access,omitempty"`

	// Deprecation tracking
	Deprecated     bool    `json:"deprecated"`
	Successor      *string `json:"successor,omitempty"`
	RedirectedFrom *string `json:"redirected_from,omitempty"`

	// Error information
	ErrorMessage *string `json:"error_message,omitempty"`

	// Performance
	Cached bool `json:"cached"`

	// Additional metadata
	Metadata map[string]interface{} `json:"metadata,omitempty"`
}

// NewUsageEvent creates a new usage event with defaults
func NewUsageEvent(moniker, path string, caller CallerIdentity, operation Operation) *UsageEvent {
	return &UsageEvent{
		RequestID:   uuid.New().String(),
		Timestamp:   time.Now().UTC(),
		Caller:      caller,
		Moniker:     moniker,
		MonikerPath: path,
		Operation:   operation,
		Outcome:     OutcomeSuccess,
		Deprecated:  false,
		Cached:      false,
		Metadata:    make(map[string]interface{}),
	}
}

// MarshalJSON customizes JSON marshaling to ensure timestamp format
func (e *UsageEvent) MarshalJSON() ([]byte, error) {
	type Alias UsageEvent
	return json.Marshal(&struct {
		Timestamp string `json:"timestamp"`
		*Alias
	}{
		Timestamp: e.Timestamp.Format(time.RFC3339Nano),
		Alias:     (*Alias)(e),
	})
}

// CompactString returns a one-line compact representation of the event
func (e *UsageEvent) CompactString() string {
	outcome := string(e.Outcome)
	if e.ErrorMessage != nil {
		outcome = fmt.Sprintf("%s: %s", outcome, *e.ErrorMessage)
	}

	return fmt.Sprintf("[TELEMETRY] %s %s %s %s %s %.1fms",
		e.Timestamp.Format(time.RFC3339),
		e.Caller.Principal(),
		e.Operation,
		e.MonikerPath,
		outcome,
		e.LatencyMS,
	)
}
