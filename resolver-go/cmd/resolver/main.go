package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/cache"
	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/catalog"
	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/config"
	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/handlers"
	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/service"
	"github.com/ganizanisitara/open-moniker-svc/resolver-go/internal/telemetry"
)

func main() {
	// Parse command-line flags
	configPath := flag.String("config", "../config.yaml", "Path to config file")
	port := flag.Int("port", 0, "Port to listen on (overrides config)")
	flag.Parse()

	// Load configuration
	cfg, err := config.Load(*configPath)
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}

	// Override port from flag if provided (0 means use config value)
	if *port > 0 {
		cfg.Server.Port = *port
	} else if cfg.Server.Port == 0 {
		cfg.Server.Port = 8053 // Default fallback
	}

	// Set default project name if not configured
	if cfg.ProjectName == "" {
		cfg.ProjectName = "Open Moniker"
	}

	// Display startup banner
	log.Printf("==============================================")
	log.Printf("  %s - Go Resolver", cfg.ProjectName)
	log.Printf("  Port: %d", cfg.Server.Port)
	log.Printf("  Catalog: %s", cfg.Catalog.DefinitionFile)
	log.Printf("==============================================")

	// Initialize components
	registry := catalog.NewRegistry()
	cacheInst := cache.NewInMemory(time.Duration(cfg.Cache.DefaultTTLSeconds) * time.Second)

	// Start cache cleanup goroutine
	if cfg.Cache.Enabled {
		cacheInst.StartCleanup(1 * time.Minute)
	}

	// Load catalog from YAML
	catalogPath := cfg.Catalog.DefinitionFile
	// If relative path, resolve relative to config file location (repo root)
	if !strings.HasPrefix(catalogPath, "/") {
		// Strip leading ./ if present
		catalogPath = strings.TrimPrefix(catalogPath, "./")
		// Make relative to config file (../catalogPath from resolver-go/)
		catalogPath = "../" + catalogPath
	}

	nodes, err := catalog.LoadCatalog(catalogPath)
	if err != nil {
		log.Printf("Warning: Failed to load catalog: %v - running with empty catalog", err)
	} else {
		registry.RegisterMany(nodes)
		log.Printf("Loaded %d catalog nodes", len(nodes))
	}

	// Initialize telemetry
	emitter, err := telemetry.NewFromConfig(&cfg.Telemetry)
	if err != nil {
		log.Printf("Warning: Failed to initialize telemetry: %v", err)
		emitter = telemetry.NewNoOpEmitter()
	}
	defer emitter.Stop()

	if cfg.Telemetry.Enabled {
		log.Printf("Telemetry enabled: sink=%s, batch_size=%d, flush_interval=%.3fs",
			cfg.Telemetry.SinkType, cfg.Telemetry.BatchSize, cfg.Telemetry.FlushIntervalSeconds)
	}

	// Create service
	svc := service.NewMonikerService(registry, cacheInst, cfg, emitter)

	// Set up HTTP routes
	mux := http.NewServeMux()

	// Health check endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		counts := registry.Count()

		// Get telemetry stats
		emitted, dropped, errors, queueDepth := emitter.GetStats()
		dropRate := 0.0
		if emitted+dropped > 0 {
			dropRate = float64(dropped) / float64(emitted+dropped) * 100
		}

		fmt.Fprintf(w, `{
			"status": "healthy",
			"service": "%s",
			"version": "0.1.0-beta",
			"catalog": {
				"total_nodes": %d,
				"active_nodes": %d
			},
			"cache": {
				"size": %d,
				"enabled": %t
			},
			"telemetry": {
				"enabled": %t,
				"emitted": %d,
				"dropped": %d,
				"errors": %d,
				"queue_depth": %d,
				"drop_rate": %.2f
			}
		}`, cfg.ProjectName, counts["total"], counts["active"], cacheInst.Size(), cfg.Cache.Enabled,
			cfg.Telemetry.Enabled, emitted, dropped, errors, queueDepth, dropRate)
	})

	// Resolution endpoints
	resolveHandler := handlers.NewResolveHandler(svc)
	describeHandler := handlers.NewDescribeHandler(svc)
	listHandler := handlers.NewListHandler(svc)
	lineageHandler := handlers.NewLineageHandler(svc, registry)

	// Catalog endpoints
	catalogListHandler := handlers.NewCatalogListHandler(svc, registry)
	searchHandler := handlers.NewSearchCatalogHandler(registry)
	statsHandler := handlers.NewCatalogStatsHandler(registry)
	batchHandler := handlers.NewBatchResolveHandler(svc)
	metadataHandler := handlers.NewMetadataHandler(svc, registry)
	treeHandler := handlers.NewTreeHandler(registry)

	// Admin endpoints
	updateStatusHandler := handlers.NewUpdateStatusHandler(registry)
	auditHandler := handlers.NewAuditLogHandler(registry)
	fetchHandler := handlers.NewFetchDataHandler(registry)

	// Cache endpoints
	cacheStatusHandler := handlers.NewCacheStatusHandler()
	refreshCacheHandler := handlers.NewRefreshCacheHandler(registry)

	// Telemetry endpoints
	telemetryHandler := handlers.NewTelemetryAccessHandler()

	// UI endpoint
	uiHandler := handlers.NewUIHandler()

	// Register all routes
	mux.Handle("/resolve/", resolveHandler)
	mux.Handle("/describe/", describeHandler)
	mux.Handle("/list/", listHandler)
	mux.Handle("/lineage/", lineageHandler)

	// Catalog routes
	mux.Handle("/catalog/search", searchHandler)
	mux.Handle("/catalog/stats", statsHandler)
	mux.HandleFunc("/catalog", func(w http.ResponseWriter, r *http.Request) {
		catalogListHandler.ServeHTTP(w, r)
	})
	mux.HandleFunc("/catalog/", func(w http.ResponseWriter, r *http.Request) {
		// Route to specific handlers based on path
		path := r.URL.Path
		if strings.HasSuffix(path, "/status") && r.Method == "PUT" {
			updateStatusHandler.ServeHTTP(w, r)
		} else if strings.HasSuffix(path, "/audit") {
			auditHandler.ServeHTTP(w, r)
		} else {
			catalogListHandler.ServeHTTP(w, r)
		}
	})

	// Batch resolve
	mux.Handle("/resolve/batch", batchHandler)

	// Metadata and tree
	mux.Handle("/metadata/", metadataHandler)
	mux.Handle("/tree/", treeHandler)
	mux.HandleFunc("/tree", func(w http.ResponseWriter, r *http.Request) {
		treeHandler.ServeHTTP(w, r)
	})

	// Fetch data
	mux.Handle("/fetch/", fetchHandler)

	// Cache
	mux.Handle("/cache/status", cacheStatusHandler)
	mux.Handle("/cache/refresh/", refreshCacheHandler)

	// Telemetry
	mux.Handle("/telemetry/access", telemetryHandler)

	// UI
	mux.Handle("/ui", uiHandler)

	// Create server
	addr := fmt.Sprintf("%s:%d", cfg.Server.Host, cfg.Server.Port)
	server := &http.Server{
		Addr:         addr,
		Handler:      mux,
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	// Start server in a goroutine
	go func() {
		log.Printf("Starting Go resolver on %s", addr)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server error: %v", err)
		}
	}()

	// Wait for interrupt signal for graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down server...")

	// Graceful shutdown with 30s timeout
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := server.Shutdown(ctx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("Server stopped")
}
