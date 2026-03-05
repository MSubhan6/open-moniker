package telemetry

import (
	"context"
	"log"
	"sync"
	"time"
)

// Batcher accumulates events and flushes them in batches
type Batcher struct {
	buffer        []UsageEvent
	mu            sync.Mutex
	batchSize     int
	flushInterval time.Duration
	sink          Sink
	ctx           context.Context
	cancel        context.CancelFunc
	batchCount    int64
	eventCount    int64
	errorCount    int64
}

// NewBatcher creates a new batcher
func NewBatcher(batchSize int, flushInterval time.Duration, sink Sink) *Batcher {
	ctx, cancel := context.WithCancel(context.Background())

	return &Batcher{
		buffer:        make([]UsageEvent, 0, batchSize),
		batchSize:     batchSize,
		flushInterval: flushInterval,
		sink:          sink,
		ctx:           ctx,
		cancel:        cancel,
	}
}

// Start begins the timer loop
func (b *Batcher) Start() {
	go b.timerLoop()
}

// Add adds an event to the buffer
// Triggers flush if batch size reached
func (b *Batcher) Add(event UsageEvent) {
	b.mu.Lock()
	b.buffer = append(b.buffer, event)
	shouldFlush := len(b.buffer) >= b.batchSize
	b.mu.Unlock()

	if shouldFlush {
		b.Flush()
	}
}

// Flush writes buffered events to sink
func (b *Batcher) Flush() {
	b.mu.Lock()

	// Nothing to flush
	if len(b.buffer) == 0 {
		b.mu.Unlock()
		return
	}

	// Copy buffer to local slice
	events := make([]UsageEvent, len(b.buffer))
	copy(events, b.buffer)

	// Reset buffer (preserve capacity)
	b.buffer = b.buffer[:0]

	b.mu.Unlock()

	// Write to sink (outside lock)
	if err := b.sink.Write(events); err != nil {
		log.Printf("[Telemetry] Batcher flush error: %v", err)
		b.errorCount++
	} else {
		b.batchCount++
		b.eventCount += int64(len(events))
	}
}

// timerLoop periodically flushes the buffer
func (b *Batcher) timerLoop() {
	ticker := time.NewTicker(b.flushInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			b.Flush()

		case <-b.ctx.Done():
			return
		}
	}
}

// Stop gracefully shuts down the batcher
func (b *Batcher) Stop() {
	log.Println("[Telemetry] Stopping batcher...")

	// Cancel context to stop timer loop
	b.cancel()

	// Final flush
	b.Flush()

	// Close sink
	if err := b.sink.Close(); err != nil {
		log.Printf("[Telemetry] Batcher sink close error: %v", err)
	}

	log.Printf("[Telemetry] Batcher stopped. Stats: batches=%d, events=%d, errors=%d",
		b.batchCount, b.eventCount, b.errorCount)
}
