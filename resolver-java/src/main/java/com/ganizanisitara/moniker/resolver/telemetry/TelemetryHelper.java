package com.ganizanisitara.moniker.resolver.telemetry;

import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Helper for creating and emitting telemetry events.
 */
@Slf4j
@Component
public class TelemetryHelper {

    private final Emitter emitter;
    private final String resolverName;
    private final String region;
    private final String az;

    public TelemetryHelper(
            Emitter emitter,
            @Value("${moniker.resolver-name:local-dev}") String resolverName,
            @Value("${moniker.region:local}") String region,
            @Value("${moniker.az:local}") String az) {
        this.emitter = emitter;
        this.resolverName = resolverName;
        this.region = region;
        this.az = az;
    }

    /**
     * Extract caller identity from HTTP request.
     */
    public CallerIdentity extractCallerIdentity(HttpServletRequest request) {
        if (request == null) {
            return CallerIdentity.builder()
                .userId("system")
                .build();
        }

        return CallerIdentity.builder()
            .userId(request.getHeader("X-User-ID"))
            .appId(request.getHeader("X-App-ID"))
            .team(request.getHeader("X-Team"))
            .ipAddress(getClientIp(request))
            .userAgent(request.getHeader("User-Agent"))
            .build();
    }

    /**
     * Create a usage event builder with common fields pre-populated.
     */
    public UsageEvent.UsageEventBuilder createEventBuilder(
            Operation operation,
            String moniker,
            CallerIdentity caller) {

        return UsageEvent.builder()
            .requestId(UUID.randomUUID().toString())
            .timestamp(Instant.now())
            .resolverName(resolverName)
            .region(region)
            .az(az)
            .operation(operation)
            .moniker(moniker)
            .caller(caller)
            .metadata(new HashMap<>());
    }

    /**
     * Emit a telemetry event.
     */
    public void emit(UsageEvent event) {
        emitter.emit(event);
    }

    /**
     * Get client IP address from request, handling proxies.
     */
    private String getClientIp(HttpServletRequest request) {
        String ip = request.getHeader("X-Forwarded-For");
        if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getHeader("X-Real-IP");
        }
        if (ip == null || ip.isEmpty() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getRemoteAddr();
        }

        // X-Forwarded-For can have multiple IPs, take the first
        if (ip != null && ip.contains(",")) {
            ip = ip.split(",")[0].trim();
        }

        return ip;
    }

    /**
     * Convert HTTP status code to EventOutcome.
     */
    public static EventOutcome statusToOutcome(int statusCode) {
        if (statusCode >= 200 && statusCode < 300) {
            return EventOutcome.SUCCESS;
        } else if (statusCode == 404) {
            return EventOutcome.NOT_FOUND;
        } else if (statusCode == 401) {
            return EventOutcome.UNAUTHORIZED;
        } else if (statusCode == 403) {
            return EventOutcome.FORBIDDEN;
        } else if (statusCode == 400) {
            return EventOutcome.VALIDATION_ERROR;
        } else if (statusCode >= 500) {
            return EventOutcome.ERROR;
        } else {
            return EventOutcome.ERROR;
        }
    }
}
