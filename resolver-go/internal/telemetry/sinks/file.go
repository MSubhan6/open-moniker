package sinks

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"

	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/telemetry"
)

// FileSink writes events to a JSONL file
type FileSink struct {
	path string
	file *os.File
	mu   sync.Mutex
}

// NewFileSink creates a new file sink
func NewFileSink(path string) (*FileSink, error) {
	// Create parent directory if needed
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return nil, fmt.Errorf("create directory: %w", err)
	}

	// Open file in append mode
	file, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return nil, fmt.Errorf("open file: %w", err)
	}

	return &FileSink{
		path: path,
		file: file,
	}, nil
}

// Write writes events to the file in JSONL format
func (f *FileSink) Write(events []telemetry.UsageEvent) error {
	f.mu.Lock()
	defer f.mu.Unlock()

	for _, event := range events {
		data, err := json.Marshal(event)
		if err != nil {
			return fmt.Errorf("marshal event: %w", err)
		}

		// Write JSON line
		if _, err := f.file.Write(data); err != nil {
			return fmt.Errorf("write event: %w", err)
		}

		// Write newline
		if _, err := f.file.WriteString("\n"); err != nil {
			return fmt.Errorf("write newline: %w", err)
		}
	}

	// Sync to disk
	if err := f.file.Sync(); err != nil {
		return fmt.Errorf("sync file: %w", err)
	}

	return nil
}

// Close closes the file
func (f *FileSink) Close() error {
	f.mu.Lock()
	defer f.mu.Unlock()

	if f.file != nil {
		return f.file.Close()
	}
	return nil
}
