package com.ganizanisitara.moniker.resolver.telemetry;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

/**
 * Telemetry event representing a single request/operation.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UsageEvent {
    // Request tracking
    private String requestId;
    private Instant timestamp;

    // Resolver identity
    private String resolverName;
    private String region;
    private String az;

    // Moniker details
    private String moniker;
    private String path;
    private String namespace;
    private String version;

    // Operation details
    private String sourceType;
    private Operation operation;
    private EventOutcome outcome;

    // Performance metrics
    private long latencyMs;
    private boolean cacheHit;

    // Result details
    private int statusCode;
    private String errorType;
    private String errorMessage;

    // Caller information
    private CallerIdentity caller;

    // Additional metadata
    @Builder.Default
    private Map<String, Object> metadata = new HashMap<>();
}
