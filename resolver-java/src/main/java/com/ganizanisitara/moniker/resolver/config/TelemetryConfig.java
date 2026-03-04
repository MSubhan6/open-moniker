package com.ganizanisitara.moniker.resolver.config;

import lombok.Data;
import java.util.HashMap;
import java.util.Map;

/**
 * Telemetry configuration.
 */
@Data
public class TelemetryConfig {
    private boolean enabled = false;
    private String sinkType = "console";
    private Map<String, Object> sinkConfig = new HashMap<>();
    private int batchSize = 100;
    private double flushIntervalSeconds = 5.0;
    private int maxQueueSize = 10000;
}
