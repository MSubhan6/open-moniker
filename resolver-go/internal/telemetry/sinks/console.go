package sinks

import (
	"encoding/json"
	"fmt"
	"io"
	"os"

	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/telemetry"
)

// ConsoleSink writes events to stdout or stderr
type ConsoleSink struct {
	writer io.Writer
	format string // "json" or "compact"
}

// NewConsoleSink creates a new console sink
func NewConsoleSink(stream, format string) *ConsoleSink {
	var writer io.Writer
	if stream == "stderr" {
		writer = os.Stderr
	} else {
		writer = os.Stdout
	}

	if format == "" {
		format = "compact"
	}

	return &ConsoleSink{
		writer: writer,
		format: format,
	}
}

// Write writes events to the console
func (c *ConsoleSink) Write(events []telemetry.UsageEvent) error {
	for _, event := range events {
		var output string
		var err error

		if c.format == "json" {
			data, jsonErr := json.Marshal(event)
			if jsonErr != nil {
				return fmt.Errorf("marshal event: %w", jsonErr)
			}
			output = string(data)
		} else {
			// Compact format
			output = event.CompactString()
		}

		_, err = fmt.Fprintln(c.writer, output)
		if err != nil {
			return fmt.Errorf("write to console: %w", err)
		}
	}

	return nil
}

// Close closes the sink (no-op for console)
func (c *ConsoleSink) Close() error {
	return nil
}
