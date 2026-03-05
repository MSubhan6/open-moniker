package telemetry

// Sink is the interface for telemetry event sinks
type Sink interface {
	// Write writes a batch of events to the sink
	Write(events []UsageEvent) error

	// Close closes the sink and releases resources
	Close() error
}
