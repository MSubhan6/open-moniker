package sinks

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"sync/atomic"
	"time"

	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/telemetry"
)

// RotatingFileSink writes events to rotating log files
// Rotates based on time (hourly by default) and size (100MB max)
type RotatingFileSink struct {
	directory   string
	pathPattern string // e.g., "telemetry-20060102-15.jsonl"
	maxBytes    int64

	currentPath string
	currentFile *os.File
	currentSize int64
	mu          sync.Mutex
}

// NewRotatingFileSink creates a new rotating file sink
func NewRotatingFileSink(directory, pathPattern string, maxBytes int64) (*RotatingFileSink, error) {
	// Create directory if needed
	if err := os.MkdirAll(directory, 0755); err != nil {
		return nil, fmt.Errorf("create directory: %w", err)
	}

	if pathPattern == "" {
		pathPattern = "telemetry-20060102-15.jsonl"
	}

	if maxBytes <= 0 {
		maxBytes = 100 * 1024 * 1024 // 100MB default
	}

	rs := &RotatingFileSink{
		directory:   directory,
		pathPattern: pathPattern,
		maxBytes:    maxBytes,
	}

	// Open initial file
	if err := rs.rotate(); err != nil {
		return nil, fmt.Errorf("initial rotation: %w", err)
	}

	return rs, nil
}

// Write writes events to the rotating file
func (r *RotatingFileSink) Write(events []telemetry.UsageEvent) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	// Check if rotation needed
	expectedPath := r.generatePath()
	if expectedPath != r.currentPath || atomic.LoadInt64(&r.currentSize) >= r.maxBytes {
		if err := r.rotate(); err != nil {
			return fmt.Errorf("rotate: %w", err)
		}
	}

	// Write events
	for _, event := range events {
		data, err := json.Marshal(event)
		if err != nil {
			return fmt.Errorf("marshal event: %w", err)
		}

		// Write JSON line
		n, err := r.currentFile.Write(data)
		if err != nil {
			return fmt.Errorf("write event: %w", err)
		}
		atomic.AddInt64(&r.currentSize, int64(n))

		// Write newline
		n, err = r.currentFile.WriteString("\n")
		if err != nil {
			return fmt.Errorf("write newline: %w", err)
		}
		atomic.AddInt64(&r.currentSize, int64(n))
	}

	// Sync to disk
	if err := r.currentFile.Sync(); err != nil {
		return fmt.Errorf("sync file: %w", err)
	}

	return nil
}

// rotate closes current file and opens a new one
func (r *RotatingFileSink) rotate() error {
	// Close current file if open
	if r.currentFile != nil {
		if err := r.currentFile.Close(); err != nil {
			return fmt.Errorf("close current file: %w", err)
		}
	}

	// Generate new path
	newPath := r.generatePath()

	// Check if file exists and handle size-based rotation
	if stat, err := os.Stat(newPath); err == nil {
		// File exists, check size
		if stat.Size() >= r.maxBytes {
			// Rename to .1, .2, etc.
			if err := r.rotateBySuffix(newPath); err != nil {
				return fmt.Errorf("rotate by suffix: %w", err)
			}
		}
	}

	// Open new file
	file, err := os.OpenFile(newPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return fmt.Errorf("open new file: %w", err)
	}

	// Get current size
	stat, err := file.Stat()
	if err != nil {
		file.Close()
		return fmt.Errorf("stat file: %w", err)
	}

	r.currentPath = newPath
	r.currentFile = file
	atomic.StoreInt64(&r.currentSize, stat.Size())

	return nil
}

// rotateBySuffix renames a file to add a numeric suffix
func (r *RotatingFileSink) rotateBySuffix(path string) error {
	// Find available suffix
	for i := 1; i < 1000; i++ {
		newName := fmt.Sprintf("%s.%d", path, i)
		if _, err := os.Stat(newName); os.IsNotExist(err) {
			// Available - rename
			return os.Rename(path, newName)
		}
	}
	return fmt.Errorf("too many rotated files")
}

// generatePath generates the current file path based on time
func (r *RotatingFileSink) generatePath() string {
	filename := time.Now().Format(r.pathPattern)
	return filepath.Join(r.directory, filename)
}

// Close closes the current file
func (r *RotatingFileSink) Close() error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.currentFile != nil {
		return r.currentFile.Close()
	}
	return nil
}
