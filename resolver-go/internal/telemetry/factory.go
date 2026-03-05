package telemetry

import (
	"fmt"
	"time"

	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/config"
	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/telemetry/sinks"
)

// NewFromConfig creates a telemetry emitter from configuration
func NewFromConfig(cfg *config.TelemetryConfig) (*Emitter, error) {
	if cfg == nil || !cfg.Enabled {
		return NewNoOpEmitter(), nil
	}

	// Apply defaults
	batchSize := cfg.BatchSize
	if batchSize <= 0 {
		batchSize = 1000
	}

	flushInterval := cfg.FlushIntervalSeconds
	if flushInterval <= 0 {
		flushInterval = 0.15 // 150ms default
	}

	maxQueueSize := cfg.MaxQueueSize
	if maxQueueSize <= 0 {
		maxQueueSize = 10240
	}

	// Create sink
	sink, err := createSink(cfg)
	if err != nil {
		return nil, fmt.Errorf("create sink: %w", err)
	}

	// Create batcher
	batcher := NewBatcher(batchSize, time.Duration(flushInterval*float64(time.Second)), sink)

	// Create emitter
	emitter := NewEmitter(maxQueueSize, batcher)

	// Start components
	batcher.Start()
	emitter.Start()

	return emitter, nil
}

// createSink creates a sink based on configuration
func createSink(cfg *config.TelemetryConfig) (Sink, error) {
	sinkType := cfg.SinkType
	if sinkType == "" {
		sinkType = "console"
	}

	switch sinkType {
	case "console":
		return createConsoleSink(cfg.SinkConfig), nil

	case "file":
		return createFileSink(cfg.SinkConfig)

	case "rotating_file":
		return createRotatingFileSink(cfg.SinkConfig)

	case "postgres", "postgresql":
		return createPostgresSink(cfg.SinkConfig)

	default:
		return nil, fmt.Errorf("unknown sink type: %s", sinkType)
	}
}

// createConsoleSink creates a console sink from config
func createConsoleSink(sinkConfig map[string]interface{}) Sink {
	stream := "stdout"
	format := "compact"

	if sinkConfig != nil {
		if s, ok := sinkConfig["stream"].(string); ok {
			stream = s
		}
		if f, ok := sinkConfig["format"].(string); ok {
			format = f
		}
	}

	return sinks.NewConsoleSink(stream, format)
}

// createFileSink creates a file sink from config
func createFileSink(sinkConfig map[string]interface{}) (Sink, error) {
	path := "./telemetry/events.jsonl"

	if sinkConfig != nil {
		if p, ok := sinkConfig["path"].(string); ok {
			path = p
		}
	}

	return sinks.NewFileSink(path)
}

// createRotatingFileSink creates a rotating file sink from config
func createRotatingFileSink(sinkConfig map[string]interface{}) (Sink, error) {
	directory := "./telemetry"
	pathPattern := "telemetry-20060102-15.jsonl"
	maxBytes := int64(100 * 1024 * 1024) // 100MB

	if sinkConfig != nil {
		if d, ok := sinkConfig["directory"].(string); ok {
			directory = d
		}
		if p, ok := sinkConfig["path_pattern"].(string); ok {
			pathPattern = p
		}
		if mb, ok := sinkConfig["max_bytes"].(int); ok {
			maxBytes = int64(mb)
		} else if mb, ok := sinkConfig["max_bytes"].(float64); ok {
			maxBytes = int64(mb)
		}
	}

	return sinks.NewRotatingFileSink(directory, pathPattern, maxBytes)
}

// createPostgresSink creates a PostgreSQL sink from config
func createPostgresSink(sinkConfig map[string]interface{}) (Sink, error) {
	config := sinks.PostgresConfig{}

	if sinkConfig != nil {
		// Connection string (highest priority)
		if cs, ok := sinkConfig["connection_string"].(string); ok {
			config.ConnectionString = cs
		}

		// Individual connection parameters
		if host, ok := sinkConfig["host"].(string); ok {
			config.Host = host
		}
		if port, ok := sinkConfig["port"].(int); ok {
			config.Port = port
		} else if port, ok := sinkConfig["port"].(float64); ok {
			config.Port = int(port)
		}
		if database, ok := sinkConfig["database"].(string); ok {
			config.Database = database
		}
		if user, ok := sinkConfig["user"].(string); ok {
			config.User = user
		}
		if password, ok := sinkConfig["password"].(string); ok {
			config.Password = password
		}
		if sslMode, ok := sinkConfig["sslmode"].(string); ok {
			config.SSLMode = sslMode
		}

		// Retry configuration
		if maxRetries, ok := sinkConfig["max_retries"].(int); ok {
			config.MaxRetries = maxRetries
		} else if maxRetries, ok := sinkConfig["max_retries"].(float64); ok {
			config.MaxRetries = int(maxRetries)
		}
		if retryDelayMs, ok := sinkConfig["retry_delay_ms"].(int); ok {
			config.RetryDelay = time.Duration(retryDelayMs) * time.Millisecond
		} else if retryDelayMs, ok := sinkConfig["retry_delay_ms"].(float64); ok {
			config.RetryDelay = time.Duration(retryDelayMs) * time.Millisecond
		}
	}

	// Apply defaults if not set via connection_string
	if config.ConnectionString == "" {
		if config.Host == "" {
			config.Host = "localhost"
		}
		if config.Port == 0 {
			config.Port = 5432
		}
		if config.Database == "" {
			config.Database = "moniker_telemetry"
		}
		if config.User == "" {
			config.User = "telemetry"
		}
		if config.SSLMode == "" {
			config.SSLMode = "disable"
		}
	}

	return sinks.NewPostgresSink(config)
}
