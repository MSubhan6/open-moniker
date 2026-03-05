package com.ganizanisitara.moniker.resolver.controller;

import com.ganizanisitara.moniker.resolver.catalog.CatalogNode;
import com.ganizanisitara.moniker.resolver.catalog.CatalogRegistry;
import com.ganizanisitara.moniker.resolver.service.*;
import com.ganizanisitara.moniker.resolver.telemetry.CallerIdentity;
import com.ganizanisitara.moniker.resolver.telemetry.TelemetryHelper;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.*;

/**
 * Main resolver controller handling core endpoints.
 */
@RestController
public class ResolverController {

    private final MonikerService monikerService;
    private final CatalogRegistry catalog;
    private final TelemetryHelper telemetry;
    private final String projectName;

    public ResolverController(MonikerService monikerService, CatalogRegistry catalog,
                            TelemetryHelper telemetry,
                            @Value("${moniker.project-name:Open Moniker}") String projectName) {
        this.monikerService = monikerService;
        this.catalog = catalog;
        this.telemetry = telemetry;
        this.projectName = projectName;
    }

    /**
     * Minimal ping endpoint for performance testing.
     */
    @GetMapping("/ping")
    public String ping() {
        // Log thread type on first request
        Thread currentThread = Thread.currentThread();
        if (Math.random() < 0.001) {  // Log 0.1% of requests
            System.out.println("Thread handling request: " + currentThread +
                             " | Virtual: " + currentThread.isVirtual());
        }
        return "pong";
    }

    /**
     * Health check endpoint.
     */
    @GetMapping("/health")
    public Map<String, Object> health() {
        Map<String, Object> response = new HashMap<>();
        response.put("status", "healthy");
        response.put("project", projectName);
        response.put("service", "resolver-java");
        response.put("version", "0.1.0");
        response.put("catalog_nodes", catalog.size());
        response.put("timestamp", System.currentTimeMillis() / 1000);
        return response;
    }

    /**
     * Resolve a moniker.
     */
    @GetMapping("/resolve/{path:.*}")
    public ResponseEntity<?> resolve(@PathVariable String path,
                                     @RequestParam(required = false) String namespace,
                                     @RequestParam(required = false) String version,
                                     HttpServletRequest request) {
        try {
            // Build full moniker string
            StringBuilder moniker = new StringBuilder();
            if (namespace != null) {
                moniker.append(namespace).append("@");
            }
            moniker.append(path);
            if (version != null) {
                moniker.append("@").append(version);
            }

            CallerIdentity caller = telemetry.extractCallerIdentity(request);
            ResolveResult result = monikerService.resolve(moniker.toString(), caller);
            return ResponseEntity.ok(result);

        } catch (ResolutionException e) {
            Map<String, String> error = new HashMap<>();
            error.put("error", e.getMessage());
            return ResponseEntity.status(e.getStatusCode()).body(error);
        } catch (Exception e) {
            Map<String, String> error = new HashMap<>();
            error.put("error", "Internal server error");
            error.put("detail", e.getMessage());
            return ResponseEntity.status(500).body(error);
        }
    }

    /**
     * Describe a catalog node.
     */
    @GetMapping("/describe/{path:.*}")
    public ResponseEntity<?> describe(@PathVariable String path, HttpServletRequest request) {
        try {
            CallerIdentity caller = telemetry.extractCallerIdentity(request);
            DescribeResult result = monikerService.describe(path, caller);
            return ResponseEntity.ok(result);

        } catch (ResolutionException e) {
            Map<String, String> error = new HashMap<>();
            error.put("error", e.getMessage());
            return ResponseEntity.status(e.getStatusCode()).body(error);
        } catch (Exception e) {
            Map<String, String> error = new HashMap<>();
            error.put("error", "Internal server error");
            error.put("detail", e.getMessage());
            return ResponseEntity.status(500).body(error);
        }
    }

    /**
     * List children of a path.
     */
    @GetMapping("/list/{path:.*}")
    public ResponseEntity<?> listChildren(@PathVariable String path, HttpServletRequest request) {
        try {
            CallerIdentity caller = telemetry.extractCallerIdentity(request);
            List<String> children = monikerService.listChildren(path, caller);

            Map<String, Object> response = new HashMap<>();
            response.put("path", path);
            response.put("children", children);
            response.put("count", children.size());

            return ResponseEntity.ok(response);

        } catch (Exception e) {
            Map<String, String> error = new HashMap<>();
            error.put("error", "Internal server error");
            error.put("detail", e.getMessage());
            return ResponseEntity.status(500).body(error);
        }
    }

    /**
     * Get lineage (ancestor chain) for a path.
     */
    @GetMapping("/lineage/{path:.*}")
    public ResponseEntity<?> lineage(@PathVariable String path, HttpServletRequest request) {
        try {
            CallerIdentity caller = telemetry.extractCallerIdentity(request);
            List<Map<String, Object>> lineage = monikerService.getLineage(path, caller);

            Map<String, Object> response = new HashMap<>();
            response.put("path", path);
            response.put("lineage", lineage);
            response.put("depth", lineage.size());

            return ResponseEntity.ok(response);

        } catch (Exception e) {
            Map<String, String> error = new HashMap<>();
            error.put("error", "Internal server error");
            error.put("detail", e.getMessage());
            return ResponseEntity.status(500).body(error);
        }
    }

    /**
     * Get full catalog listing.
     */
    @GetMapping("/catalog")
    public ResponseEntity<?> catalog(
            @RequestParam(defaultValue = "0") int offset,
            @RequestParam(defaultValue = "100") int limit) {
        try {
            List<CatalogNode> allNodes = catalog.getAllNodes();

            // Apply pagination
            int total = allNodes.size();
            int end = Math.min(offset + limit, total);
            List<CatalogNode> page = allNodes.subList(offset, end);

            Map<String, Object> response = new HashMap<>();
            response.put("nodes", page);
            response.put("total", total);
            response.put("offset", offset);
            response.put("limit", limit);

            return ResponseEntity.ok(response);

        } catch (Exception e) {
            Map<String, String> error = new HashMap<>();
            error.put("error", "Internal server error");
            error.put("detail", e.getMessage());
            return ResponseEntity.status(500).body(error);
        }
    }

    /**
     * Search catalog.
     */
    @GetMapping("/catalog/search")
    public ResponseEntity<?> search(@RequestParam String q,
                                    @RequestParam(defaultValue = "100") int limit) {
        try {
            List<CatalogNode> allNodes = catalog.getAllNodes();
            List<CatalogNode> matches = new ArrayList<>();

            String query = q.toLowerCase();

            for (CatalogNode node : allNodes) {
                if (matches.size() >= limit) {
                    break;
                }

                // Simple text search
                boolean match = node.getPath().toLowerCase().contains(query) ||
                               node.getDisplayName().toLowerCase().contains(query) ||
                               node.getDescription().toLowerCase().contains(query);

                if (match) {
                    matches.add(node);
                }
            }

            Map<String, Object> response = new HashMap<>();
            response.put("query", q);
            response.put("results", matches);
            response.put("count", matches.size());

            return ResponseEntity.ok(response);

        } catch (Exception e) {
            Map<String, String> error = new HashMap<>();
            error.put("error", "Internal server error");
            error.put("detail", e.getMessage());
            return ResponseEntity.status(500).body(error);
        }
    }

    /**
     * Get catalog statistics.
     */
    @GetMapping("/catalog/stats")
    public ResponseEntity<?> stats() {
        try {
            Map<String, Object> stats = monikerService.getStats();
            return ResponseEntity.ok(stats);

        } catch (Exception e) {
            Map<String, String> error = new HashMap<>();
            error.put("error", "Internal server error");
            error.put("detail", e.getMessage());
            return ResponseEntity.status(500).body(error);
        }
    }

    /**
     * Cache status (stub).
     */
    @GetMapping("/cache/status")
    public Map<String, Object> cacheStatus() {
        Map<String, Object> response = new HashMap<>();
        response.put("enabled", false);
        response.put("size", 0);
        response.put("hit_rate", 0.0);
        return response;
    }

    /**
     * Simple UI endpoint (returns HTML).
     */
    @GetMapping(value = "/ui", produces = "text/html")
    public String ui() {
        return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Moniker Resolver - Java</title>
                <style>
                    body { font-family: system-ui; margin: 40px; }
                    h1 { color: #333; }
                    .info { background: #f5f5f5; padding: 20px; border-radius: 4px; }
                </style>
            </head>
            <body>
                <h1>🚀 Moniker Resolver - Java Implementation</h1>
                <div class="info">
                    <p><strong>Status:</strong> Running</p>
                    <p><strong>Version:</strong> 0.1.0</p>
                    <p><strong>Project:</strong> %s</p>
                    <p><strong>Endpoints:</strong></p>
                    <ul>
                        <li>GET /health - Health check</li>
                        <li>GET /resolve/{path} - Resolve moniker</li>
                        <li>GET /describe/{path} - Describe node</li>
                        <li>GET /list/{path} - List children</li>
                        <li>GET /lineage/{path} - Get lineage</li>
                        <li>GET /catalog - List catalog</li>
                        <li>GET /catalog/search?q=... - Search</li>
                        <li>GET /catalog/stats - Statistics</li>
                    </ul>
                </div>
            </body>
            </html>
            """.formatted(projectName);
    }
}
