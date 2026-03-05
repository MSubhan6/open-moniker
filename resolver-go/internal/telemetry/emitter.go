package telemetry

import (
	"context"
	"log"
	"sync/atomic"
	"time"
)

// Stats tracks emitter statistics
type Stats struct {
	Emitted int64
	Dropped int64
	Errors  int64
}

// Emitter provides non-blocking telemetry event emission
type Emitter struct {
	eventsCh chan UsageEvent
	batcher  *Batcher
	stats    Stats
	ctx      context.Context
	cancel   context.CancelFunc
}

// NewEmitter creates a new telemetry emitter
func NewEmitter(maxQueueSize int, batcher *Batcher) *Emitter {
	ctx, cancel := context.WithCancel(context.Background())

	return &Emitter{
		eventsCh: make(chan UsageEvent, maxQueueSize),
		batcher:  batcher,
		ctx:      ctx,
		cancel:   cancel,
	}
}

// Start begins processing events
func (e *Emitter) Start() {
	go e.processLoop()
}

// Emit sends an event to the telemetry pipeline
// Returns true if event was queued, false if dropped (channel full)
func (e *Emitter) Emit(event UsageEvent) bool {
	select {
	case e.eventsCh <- event:
		atomic.AddInt64(&e.stats.Emitted, 1)
		return true
	default:
		// Channel full - drop event
		atomic.AddInt64(&e.stats.Dropped, 1)
		return false
	}
}

// processLoop reads events from channel and feeds to batcher
func (e *Emitter) processLoop() {
	for {
		select {
		case event, ok := <-e.eventsCh:
			if !ok {
				// Channel closed
				return
			}
			e.batcher.Add(event)

		case <-e.ctx.Done():
			// Context canceled
			return
		}
	}
}

// Stop gracefully shuts down the emitter
func (e *Emitter) Stop() {
	log.Println("[Telemetry] Stopping emitter...")

	// Cancel context to stop processLoop
	e.cancel()

	// Close channel
	close(e.eventsCh)

	// Drain remaining events
	for event := range e.eventsCh {
		e.batcher.Add(event)
	}

	// Stop batcher (final flush)
	e.batcher.Stop()

	// Log final stats
	emitted := atomic.LoadInt64(&e.stats.Emitted)
	dropped := atomic.LoadInt64(&e.stats.Dropped)
	errors := atomic.LoadInt64(&e.stats.Errors)

	log.Printf("[Telemetry] Emitter stopped. Stats: emitted=%d, dropped=%d, errors=%d",
		emitted, dropped, errors)
}

// GetStats returns current statistics
func (e *Emitter) GetStats() (emitted, dropped, errors, queueDepth int64) {
	return atomic.LoadInt64(&e.stats.Emitted),
		atomic.LoadInt64(&e.stats.Dropped),
		atomic.LoadInt64(&e.stats.Errors),
		int64(len(e.eventsCh))
}

// NoOpSink is a sink that does nothing
type NoOpSink struct{}

func (n *NoOpSink) Write(events []UsageEvent) error { return nil }
func (n *NoOpSink) Close() error                    { return nil }

// NewNoOpEmitter creates a no-op emitter for when telemetry is disabled
func NewNoOpEmitter() *Emitter {
	sink := &NoOpSink{}
	batcher := NewBatcher(1, time.Second, sink)
	emitter := NewEmitter(1, batcher)
	return emitter
}
